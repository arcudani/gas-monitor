// Edge Function `gas-monitor` — pipeline giornaliera del Gas Market Monitor.
//
// Raccoglie le variabili (RF-06) e ricalcola l'indice sintetico 0-100:
//  - METEO: Open-Meteo, T media giornaliera del paniere citta' IT pesate per
//    consumo gas (MI 30, TO 15, BO 15, RM 20, FI 10, VE 10) -> gas_serie
//  - STOCCAGGI: GIE AGSI+ (IT): % riempimento, iniezione, erogazione
//  - LNG: GIE ALSI (IT): send-out e giacenza
//  - GEOPOLITICA: GPR daily Caldara-Iacoviello (file .xls, storico completo)
//  - PREZZO: gia' in indici_mercato (MGP_GAS, job dati-mercato) — non toccato
//  - INDICE + SEGNALE: RPC gas_ricalcola_indice + gas_ricalcola_segnale (v1.6)
//
// Scheduling: pg_cron ogni 30' 04:00-07:30 UTC; gate interno Europe/Rome
// 06:30-09:30 + skip se gia' 'ok' oggi -> una sola esecuzione buona al
// giorno, con retry automatici fino alle 09:30 (RF-06).
// Log: public.task_runs (task_id 'gas-monitor'), visibile nel Monitor ERP.
//
// Parametri (Authorization: Bearer anon/service key):
//   ?force=1                       bypassa gate orario e skip
//   ?backfill=meteo&dal=&al=       backfill archivio ERA5 (senza ricalcolo)
//   ?backfill=stoccaggi&dal=&al=   backfill AGSI+
//   ?backfill=lng&dal=&al=         backfill ALSI
//   ?backfill=geopolitica&dal=&al= backfill GPR daily
//   ?ricalcola=1&dal=&al=          solo ricalcolo indice
//
// Deploy: MCP deploy_edge_function — SEMPRE get_edge_function e confronto
// prima (regola repo). Sorgente versionato in C:\Code\Gas_Monitor.

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const GIE_KEY = Deno.env.get("GIE_API_KEY") ?? "";

// Paniere citta' (pesi % consumo gas, requisiti v1.4)
const CITTA = [
  { nome: "Milano",  lat: 45.464, lon: 9.190,  peso: 30 },
  { nome: "Torino",  lat: 45.070, lon: 7.686,  peso: 15 },
  { nome: "Bologna", lat: 44.494, lon: 11.343, peso: 15 },
  { nome: "Roma",    lat: 41.893, lon: 12.483, peso: 20 },
  { nome: "Firenze", lat: 43.771, lon: 11.248, peso: 10 },
  { nome: "Venezia", lat: 45.438, lon: 12.318, peso: 10 },
];

// ---------------------------------------------------------------- REST helper
async function sb(path: string, init: RequestInit = {}): Promise<Response> {
  const r = await fetch(`${SB_URL}${path}`, {
    ...init,
    headers: {
      apikey: SB_KEY,
      Authorization: `Bearer ${SB_KEY}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!r.ok) {
    throw new Error(`REST ${path}: ${r.status} ${await r.text()}`);
  }
  return r;
}

type Riga = {
  data: string; commodity?: string; variabile: string;
  metrica: string; valore: number; fonte: string;
};

async function upsertSerie(righe: Riga[]): Promise<number> {
  let n = 0;
  for (let i = 0; i < righe.length; i += 1000) {
    const blocco = righe.slice(i, i + 1000);
    await sb(
      "/rest/v1/gas_serie?on_conflict=data,commodity,variabile,metrica",
      {
        method: "POST",
        headers: { Prefer: "resolution=merge-duplicates,return=minimal" },
        body: JSON.stringify(blocco),
      },
    );
    n += blocco.length;
  }
  return n;
}

// ---------------------------------------------------------------- sorgenti
async function fetchMeteo(dal: string, al: string, archivio: boolean): Promise<Riga[]> {
  // archivio=true: archive-api (ERA5, per il backfill; ~5 gg di ritardo)
  // archivio=false: forecast-api con past_days (per il run giornaliero)
  const lats = CITTA.map((c) => c.lat).join(",");
  const lons = CITTA.map((c) => c.lon).join(",");
  const base = archivio
    ? `https://archive-api.open-meteo.com/v1/archive?start_date=${dal}&end_date=${al}`
    : `https://api.open-meteo.com/v1/forecast?past_days=10&forecast_days=1`;
  const url = `${base}&latitude=${lats}&longitude=${lons}` +
    `&daily=temperature_2m_mean&timezone=Europe%2FRome`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Open-Meteo: ${r.status} ${await r.text()}`);
  const js = await r.json();
  const serie = Array.isArray(js) ? js : [js];   // multi-citta' -> array
  if (serie.length !== CITTA.length) {
    throw new Error(`Open-Meteo: attese ${CITTA.length} serie, ricevute ${serie.length}`);
  }
  const giorni: string[] = serie[0].daily.time;
  const righe: Riga[] = [];
  const oggi = new Date().toISOString().slice(0, 10);
  for (let g = 0; g < giorni.length; g++) {
    if (giorni[g] >= oggi) continue;             // solo giorni chiusi
    let somma = 0, pesoTot = 0;
    for (let c = 0; c < CITTA.length; c++) {
      const t = serie[c].daily.temperature_2m_mean[g];
      if (t === null || t === undefined) { pesoTot = 0; break; }
      somma += t * CITTA[c].peso;
      pesoTot += CITTA[c].peso;
    }
    if (pesoTot !== 100) continue;               // paniere incompleto -> salta il giorno
    righe.push({
      data: giorni[g], variabile: "meteo", metrica: "t_media_paniere",
      valore: Math.round(somma) / 100,
      fonte: archivio ? "Open-Meteo ERA5" : "Open-Meteo",
    });
  }
  return righe;
}

async function fetchGie(api: "agsi" | "alsi", dal: string, al: string): Promise<Riga[]> {
  if (!GIE_KEY) throw new Error("GIE_API_KEY assente nei secrets");
  const righe: Riga[] = [];
  let pagina = 1;
  while (pagina < 100) {                          // guardia anti-loop
    const url = `https://${api}.gie.eu/api?country=IT&from=${dal}&to=${al}` +
      `&size=300&page=${pagina}`;
    const r = await fetch(url, { headers: { "x-key": GIE_KEY } });
    if (!r.ok) throw new Error(`GIE ${api}: ${r.status} ${await r.text()}`);
    const js = await r.json();
    const dati = js.data ?? [];
    for (const d of dati) {
      const giorno = d.gasDayStart;
      if (!giorno) continue;
      const num = (v: unknown) => {
        const x = Number(v);
        return Number.isFinite(x) ? x : null;
      };
      if (api === "agsi") {
        const full = num(d.full), inj = num(d.injection), wit = num(d.withdrawal);
        if (full !== null) righe.push({ data: giorno, variabile: "stoccaggi", metrica: "riempimento_pct", valore: full, fonte: "GIE AGSI+" });
        if (inj !== null) righe.push({ data: giorno, variabile: "stoccaggi", metrica: "iniezione", valore: inj, fonte: "GIE AGSI+" });
        if (wit !== null) righe.push({ data: giorno, variabile: "stoccaggi", metrica: "erogazione", valore: wit, fonte: "GIE AGSI+" });
      } else {
        // inventory e' un oggetto {lng, gwh}: si salva la giacenza in GWh
        const so = num(d.sendOut), inv = num(d.inventory?.gwh);
        if (so !== null) righe.push({ data: giorno, variabile: "lng", metrica: "lng_sendout", valore: so, fonte: "GIE ALSI" });
        if (inv !== null) righe.push({ data: giorno, variabile: "lng", metrica: "lng_giacenza", valore: inv, fonte: "GIE ALSI" });
      }
    }
    if (pagina >= Number(js.last_page ?? 1)) break;
    pagina++;
  }
  return righe;
}

async function delegaGpr(dal: string, al: string): Promise<number> {
  // Il parsing dell'.xls GPR e' avido di memoria: vive nella funzione
  // DEDICATA gas-monitor-gpr (slug diverso = worker/memoria propri; una
  // sub-invocazione dello stesso slug riusa l'isolate e va in
  // WORKER_RESOURCE_LIMIT — visto il 18/08/2026).
  const r = await fetch(
    `${SB_URL}/functions/v1/gas-monitor-gpr?dal=${dal}&al=${al}`,
    { headers: { Authorization: `Bearer ${SB_KEY}`, apikey: SB_KEY } },
  );
  if (!r.ok) throw new Error(`GPR: ${r.status} ${await r.text()}`);
  return Number(((await r.json()) as { righe: number }).righe);
}

async function ricalcola(dal: string, al: string): Promise<number> {
  // indice di pressione (storico, g003) + SEGNALE scenario/prezzo/finestra
  // (g005, requisiti v1.6): il segnale e' la fonte della dashboard e degli
  // alert; l'indice resta per confronto. Il segnale parte 180 gg prima per
  // avere i trend completi e il conteggio dei giorni consecutivi corretto.
  const r1 = await sb("/rest/v1/rpc/gas_ricalcola_indice", {
    method: "POST", body: JSON.stringify({ p_dal: dal, p_al: al }),
  });
  const n1 = Number(await r1.text());
  const r2 = await sb("/rest/v1/rpc/gas_ricalcola_segnale", {
    method: "POST", body: JSON.stringify({ p_dal: isoAddDays(dal, -180), p_al: al }),
  });
  return n1 + Number(await r2.text());
}

// ---------------------------------------------------------------- alert interno
const BREVO_API_KEY = Deno.env.get("BREVO_API_KEY") ?? "";
async function alertInterno(problemi: string[], dettagli: Record<string, number>) {
  if (!BREVO_API_KEY) return;
  try {
    const esc = (x: unknown) => String(x ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const html = `<div style="font-family:Inter,Arial,sans-serif;max-width:640px;color:#0f172a">
      <h2 style="color:#C00000;border-bottom:3px solid #C00000;padding-bottom:8px">Gas Market Monitor — aggiornamento dati con problemi</h2>
      <p>Il controllo giornaliero ha rilevato:</p>
      <ul>${problemi.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
      <p style="font-size:13px;color:#475569">Righe aggiornate: ${esc(JSON.stringify(dettagli))}</p>
      <p style="font-size:12px;color:#64748b">Dettagli in Admin → Stato pipeline. Il prossimo tentativo automatico e' entro 30 minuti (fino alle 09:30).</p>
    </div>`;
    await fetch("https://api.brevo.com/v3/smtp/email", {
      method: "POST",
      headers: { "api-key": BREVO_API_KEY, "content-type": "application/json" },
      body: JSON.stringify({
        sender: { name: "Bros Consulenza", email: "energia@brosconsulenza.com" },
        to: [{ email: "energia@brosconsulenza.com" }],
        subject: "[ALERT] Gas Market Monitor — dati non aggiornati o errore pipeline",
        htmlContent: html,
      }),
    });
  } catch (_e) { /* l'alert non deve mai far fallire il run */ }
}

// ---------------------------------------------------------------- run log
async function logRun(inizio: Date, status: string, errore: string | null) {
  const fine = new Date();
  try {
    await sb("/rest/v1/task_runs", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({
        task_id: "gas-monitor",
        started_at: inizio.toISOString(),
        ended_at: fine.toISOString(),
        status,
        error: errore,
        duration_s: Math.round((fine.getTime() - inizio.getTime()) / 1000),
      }),
    });
  } catch (_e) { /* il log non deve mai far fallire il run */ }
}

function oraRoma(): { hhmm: number; data: string } {
  const parti = new Intl.DateTimeFormat("it-IT", {
    timeZone: "Europe/Rome", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date());
  const p = (t: string) => parti.find((x) => x.type === t)?.value ?? "00";
  return {
    hhmm: Number(p("hour")) * 100 + Number(p("minute")),
    data: `${p("year")}-${p("month")}-${p("day")}`,
  };
}

async function giaOkOggi(dataRoma: string): Promise<boolean> {
  const r = await sb(
    `/rest/v1/task_runs?task_id=eq.gas-monitor&status=eq.success` +
    `&started_at=gte.${dataRoma}T00:00:00%2B02:00&select=id&limit=1`,
  );
  return ((await r.json()) as unknown[]).length > 0;
}

// Un run in errore c'e' gia' stato oggi? Serve a NON ripetere l'email di
// alert interna a ogni tentativo del cron (21/08/2026: GPR stantio = 5
// tentativi = 5 email): si avvisa solo al PRIMO errore del giorno, i
// successivi restano comunque in task_runs.
async function giaErroreOggi(dataRoma: string): Promise<boolean> {
  const r = await sb(
    `/rest/v1/task_runs?task_id=eq.gas-monitor&status=eq.error` +
    `&started_at=gte.${dataRoma}T00:00:00%2B02:00&select=id&limit=1`,
  );
  return ((await r.json()) as unknown[]).length > 0;
}

function isoAddDays(iso: string, giorni: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + giorni);
  return d.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------- handler
Deno.serve(async (req: Request) => {
  const inizio = new Date();
  const url = new URL(req.url);
  const force = url.searchParams.get("force") === "1";
  const backfill = url.searchParams.get("backfill");
  const soloRicalcolo = url.searchParams.get("ricalcola") === "1";
  const { hhmm, data: oggiRoma } = oraRoma();
  const ieri = isoAddDays(oggiRoma, -1);

  try {
    // ---- modalita' backfill (manuale, senza gate ne' log task_runs) ----
    if (backfill) {
      const dal = url.searchParams.get("dal") ?? "2015-01-01";
      const al = url.searchParams.get("al") ?? ieri;
      let righe: Riga[] = [];
      if (backfill === "meteo") righe = await fetchMeteo(dal, al, true);
      else if (backfill === "stoccaggi") righe = await fetchGie("agsi", dal, al);
      else if (backfill === "lng") righe = await fetchGie("alsi", dal, al);
      else if (backfill === "geopolitica") {
        return Response.json({ backfill, dal, al, righe: await delegaGpr(dal, al) });
      }
      else return new Response(`backfill sconosciuto: ${backfill}`, { status: 400 });
      const n = await upsertSerie(righe);
      return Response.json({ backfill, dal, al, righe: n });
    }

    if (soloRicalcolo) {
      const dal = url.searchParams.get("dal") ?? isoAddDays(oggiRoma, -10);
      const al = url.searchParams.get("al") ?? ieri;
      const n = await ricalcola(dal, al);
      return Response.json({ ricalcolo: n, dal, al });
    }

    // ---- run giornaliero: gate orario + una sola esecuzione buona ----
    if (!force) {
      if (hhmm < 630 || hhmm > 930) {
        return Response.json({ skip: `fuori finestra (${hhmm})` });
      }
      if (await giaOkOggi(oggiRoma)) {
        return Response.json({ skip: "gia' eseguito con esito ok oggi" });
      }
    }

    const dal = isoAddDays(oggiRoma, -10);
    const dettagli: Record<string, number> = {};
    const problemi: string[] = [];

    const sorgenti: [string, () => Promise<number>][] = [
      ["meteo", async () => upsertSerie(await fetchMeteo(dal, ieri, false))],
      ["stoccaggi", async () => upsertSerie(await fetchGie("agsi", dal, ieri))],
      ["lng", async () => upsertSerie(await fetchGie("alsi", dal, ieri))],
      ["geopolitica", () => delegaGpr(dal, ieri)],
    ];
    for (const [nome, fn] of sorgenti) {
      try {
        dettagli[nome] = await fn();
      } catch (e) {
        problemi.push(`${nome}: ${(e as Error).message}`.slice(0, 200));
      }
    }
    dettagli.indice = await ricalcola(dal, ieri);

    // Energia elettrica (g008, 21/08/2026): stesso motore, commodity 'ee'
    // (prezzo PUN + variabili condivise meteo/GPR/gas; produzione e rinnovabili
    // da ENTSO-E quando la chiave sara' disponibile). Best-effort: un problema
    // sull'EE non blocca il gas, ma viene segnalato.
    try {
      const r = await sb("/rest/v1/rpc/gas_ricalcola_segnale", {
        method: "POST",
        body: JSON.stringify({ p_commodity: "ee", p_dal: isoAddDays(dal, -180), p_al: ieri }),
      });
      dettagli.segnale_ee = Number(await r.text());
    } catch (e) {
      problemi.push(`ee: ${(e as Error).message}`.slice(0, 200));
    }

    // Alert soglie utenti (RF-04): funzione dedicata, DOPO il ricalcolo.
    // Best-effort: un problema negli alert non deve far fallire il run
    // dati (ma viene segnalato).
    try {
      const r = await fetch(`${SB_URL}/functions/v1/gas-monitor-alert?data=${ieri}`,
        { headers: { Authorization: `Bearer ${SB_KEY}`, apikey: SB_KEY } });
      if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
      dettagli.alert_inviati = Number(((await r.json()) as { scattate: number }).scattate);
    } catch (e) {
      problemi.push(`alert: ${(e as Error).message}`.slice(0, 200));
    }

    // ---- Controllo FRESCHEZZA (richiesta utente 19/08): ogni serie deve avere
    // un dato recente; oltre la tolleranza il run e' errore anche se le
    // chiamate sono andate bene, e parte un'email interna di alert.
    // Tolleranze in giorni (le fonti pubblicano con 1-2 gg di ritardo fisiologico).
    // GPR a 7: il file .xls e' aggiornato A MANO dagli autori e puo' saltare
    // anche 4-6 giorni (fermo dal 17 al 21/08/2026); il motore fa fill-forward
    // e la variabile pesa il 20%, quindi qualche giorno di ritardo non e' critico.
    const TOLLERANZA: Record<string, number> = {
      "prezzo MGP_GAS": 2, "segnale": 2, "meteo t_media_paniere": 3,
      "stoccaggi riempimento_pct": 3, "lng lng_sendout": 3, "geopolitica gpr": 7,
    };
    const stantii: string[] = [];
    try {
      const r = await sb("/rest/v1/rpc/gas_freschezza");
      const righe = (await r.json()) as { serie: string; ultimo: string; giorni_fa: number }[];
      for (const x of righe) {
        const tol = TOLLERANZA[x.serie] ?? 3;
        if (Number(x.giorni_fa) > tol) stantii.push(`${x.serie}: ultimo dato ${x.ultimo} (${x.giorni_fa} gg fa, tolleranza ${tol})`);
      }
      // EE: la funzione generica porta la tolleranza dall'anagrafica (gas_variabili);
      // le serie condivise col gas (meteo, GPR) non vengono ripetute.
      const r2 = await sb("/rest/v1/rpc/gas_freschezza", {
        method: "POST", body: JSON.stringify({ p_commodity: "ee" }),
      });
      const righe2 = (await r2.json()) as { serie: string; ultimo: string; giorni_fa: number; tolleranza: number }[];
      for (const x of righe2) {
        if (x.serie.startsWith("meteo") || x.serie.startsWith("geopolitica")) continue;
        const tol = Number(x.tolleranza ?? 3);
        if (Number(x.giorni_fa) > tol) stantii.push(`EE ${x.serie}: ultimo dato ${x.ultimo} (${x.giorni_fa} gg fa, tolleranza ${tol})`);
      }
    } catch (e) {
      problemi.push(`freschezza: ${(e as Error).message}`.slice(0, 200));
    }
    if (stantii.length) problemi.push(`dati non aggiornati: ${stantii.join("; ")}`);

    // task_runs ha un CHECK: gli esiti ammessi sono 'success' | 'error'
    const status = problemi.length ? "error" : "success";
    // Prima di registrare il run: c'era GIA' un errore oggi? (per il dedup email)
    const giaAvvisato = problemi.length ? await giaErroreOggi(oggiRoma) : false;
    await logRun(inizio, status, problemi.length ? problemi.join(" | ") : null);

    // Email interna di alert (energia@) se qualcosa non va: chi deve
    // intervenire lo sa subito, senza aprire l'app. Best-effort.
    // UNA sola email al giorno: solo al primo run in errore.
    if (problemi.length && !giaAvvisato) await alertInterno(problemi, dettagli);
    return Response.json({ status, dettagli, problemi });
  } catch (e) {
    await logRun(inizio, "error", String(e).slice(0, 500));
    return new Response(`errore: ${e}`, { status: 500 });
  }
});
