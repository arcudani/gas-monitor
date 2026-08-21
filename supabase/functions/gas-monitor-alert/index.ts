// Edge Function `gas-monitor-alert` — valutazione soglie e invio email (RF-04),
// multi-commodity dal 21/08/2026 (g008: gas + energia elettrica).
//
// Invocata da `gas-monitor` al termine del run giornaliero (dopo il
// ricalcolo del segnale), oppure a mano:
//   ?preview=1          valuta e ritorna cosa invierebbe, SENZA inviare ne'
//                       registrare (test sicuro)
//   ?data=YYYY-MM-DD    giorno del dato da valutare (default ieri, Roma)
//
// Logica: per ogni regola attiva (gas_alert, con la sua commodity) con utente
// attivo e email valorizzata, legge il valore del giorno (segnale/scenario da
// gas_segnale; prezzo da indici_mercato secondo gas_commodity; variabili
// secondo gas_variabili), verifica la condizione, controlla anti-duplicato
// (stesso alert+giorno) e cooldown (ultimo invio < N gg), poi manda UNA email
// per utente E commodity che raggruppa tutte le regole scattate (Brevo HTTP
// API, mittente verificato energia@) e registra gli invii.
//
// Regola aziendale email: nessun riferimento all'automazione nel testo.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const BREVO_API_KEY = Deno.env.get("BREVO_API_KEY") ?? "";
const APP_URL = Deno.env.get("GAS_MONITOR_APP_URL") ??
  "https://gas-monitor-gtspes3q3h5ry5wp3dj9rn.streamlit.app";

const SENDER = { name: "Bros Consulenza", email: "energia@brosconsulenza.com" };
const RED = "#C00000";
const BLU = "#0F6FA8";

const H = { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}` };

// deno-lint-ignore no-explicit-any
async function q(path: string): Promise<any[]> {
  const r = await fetch(`${SB_URL}/rest/v1/${path}`, { headers: H });
  if (!r.ok) throw new Error(`DB ${r.status}: ${await r.text()}`);
  return r.json();
}

async function ins(table: string, rows: unknown) {
  const r = await fetch(`${SB_URL}/rest/v1/${table}`, {
    method: "POST",
    headers: { ...H, "content-type": "application/json", Prefer: "return=minimal" },
    body: JSON.stringify(rows),
  });
  if (!r.ok) throw new Error(`DB insert ${table} ${r.status}: ${await r.text()}`);
}

async function sendBrevo(to: string, subject: string, html: string) {
  const r = await fetch("https://api.brevo.com/v3/smtp/email", {
    method: "POST",
    headers: { "api-key": BREVO_API_KEY, "content-type": "application/json" },
    body: JSON.stringify({ sender: SENDER, to: [{ email: to }], subject, htmlContent: html }),
  });
  if (!r.ok) throw new Error(`Brevo ${r.status}: ${await r.text()}`);
}

function esc(s: unknown): string {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function ieriRoma(): string {
  const oggi = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" }).format(new Date());
  const d = new Date(`${oggi}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function fmtIt(v: number, dec: number): string {
  return v.toLocaleString("it-IT", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function decimali(udm: string): number {
  return udm === "€/MWh" ? 2 : (udm === "GWh/g" || udm === "indice" || udm === "") ? 0 : 1;
}

// ---------------------------------------------------------------- anagrafica (g008)
type Commodity = {
  commodity: string; nome: string; icona: string; prezzo_codice: string;
  prezzo_label: string; prezzo_udm: string; prezzo_aggregazione: string;
};
type Variabile = {
  commodity: string; variabile: string; etichetta: string; icona: string; udm: string;
  sorgente: string; commodity_dati: string | null; variabile_dati: string | null;
  metrica_dati: string | null; codice_indice: string | null;
};
type Grandezza = { nome: string; udm: string; dec: number };

function grandezze(c: Commodity, vars: Variabile[]): Record<string, Grandezza> {
  const g: Record<string, Grandezza> = {
    indice:   { nome: "Indice di pressione (storico)", udm: "/100", dec: 0 },
    scenario: { nome: "Scenario di approvvigionamento", udm: "/100", dec: 0 },
    segnale:  { nome: "Livello del segnale", udm: "", dec: 0 },
    prezzo:   { nome: `Prezzo ${c.nome.toLowerCase()} ${c.prezzo_label}`, udm: c.prezzo_udm, dec: 2 },
  };
  for (const v of vars) {
    g[v.variabile] = { nome: v.etichetta, udm: v.udm === "indice" ? "" : v.udm, dec: decimali(v.udm) };
  }
  return g;
}

// Segnale del giorno (gas_segnale): scenario, prezzo e testo
type Segnale = {
  data: string; scenario: number; prezzo: number; codice: string; testo: string;
  giorni_consecutivi: number; scost_breve_pct: number | null; scost_medio_pct: number | null;
};
const LIVELLI: Record<string, number> = {
  attesa: 0, chiusa: 0, monitorare: 1, opportunita: 2, prime: 2, minimo: 3, iniziale: 3, fixing: 4, trend: 5,
};
const NOME_SEGNALE: Record<string, string> = {
  attesa: "attesa", chiusa: "finestra chiusa", monitorare: "monitorare",
  opportunita: "opportunità di prezzo", minimo: "minimo di periodo",
  prime: "prime condizioni", iniziale: "segnale iniziale", fixing: "segnale di fixing",
  trend: "trend consolidato",
};
async function segnaleDelGiorno(commodity: string, data: string): Promise<Segnale | null> {
  const r = await q(`gas_segnale?commodity=eq.${commodity}&data=lte.${data}&order=data.desc&limit=1` +
    `&select=data,scenario,prezzo,codice,testo,giorni_consecutivi,scost_breve_pct,scost_medio_pct`);
  if (!r[0]) return null;
  const x = r[0];
  return { data: x.data, scenario: Number(x.scenario), prezzo: Number(x.prezzo), codice: x.codice,
           testo: x.testo, giorni_consecutivi: Number(x.giorni_consecutivi),
           scost_breve_pct: x.scost_breve_pct === null ? null : Number(x.scost_breve_pct),
           scost_medio_pct: x.scost_medio_pct === null ? null : Number(x.scost_medio_pct) };
}

// Ultimo valore (<= data) di un indice di mercato: media delle righe del giorno
// (il PUN e' orario: 24 righe; MGP-GAS una riga)
async function indiceDelGiorno(codice: string, data: string): Promise<{ v: number; d: string } | null> {
  const u = await q(`indici_mercato?codice=eq.${codice}&stato=eq.consuntivo&data=lte.${data}&order=data.desc&limit=1&select=data`);
  if (!u[0]) return null;
  const giorno = u[0].data as string;
  const rows = await q(`indici_mercato?codice=eq.${codice}&stato=eq.consuntivo&data=eq.${giorno}&select=valore`);
  if (!rows.length) return null;
  const media = rows.reduce((s, r) => s + Number(r.valore), 0) / rows.length;
  return { v: media, d: giorno };
}

// Valori del giorno per tutte le grandezze di una commodity (fill-forward: ultimo disponibile <= data)
async function valoriDelGiorno(c: Commodity, vars: Variabile[], data: string)
  : Promise<Record<string, { v: number; d: string }>> {
  const out: Record<string, { v: number; d: string }> = {};
  if (c.commodity === "gas") {
    const idx = await q(`gas_indice?commodity=eq.gas&data=lte.${data}&order=data.desc&limit=1&select=data,valore`);
    if (idx[0]) out.indice = { v: Number(idx[0].valore), d: idx[0].data };
  }
  const sg = await segnaleDelGiorno(c.commodity, data);
  if (sg) {
    out.scenario = { v: sg.scenario, d: sg.data };
    out.segnale = { v: LIVELLI[sg.codice] ?? 0, d: sg.data };
  }
  const pz = await indiceDelGiorno(c.prezzo_codice, data);
  if (pz) out.prezzo = pz;
  for (const v of vars) {
    if (v.sorgente === "indice" && v.codice_indice) {
      const x = await indiceDelGiorno(v.codice_indice, data);
      if (x) out[v.variabile] = x;
    } else {
      const r = await q(`gas_serie?commodity=eq.${v.commodity_dati}&variabile=eq.${v.variabile_dati}` +
        `&metrica=eq.${v.metrica_dati}&data=lte.${data}&order=data.desc&limit=1&select=data,valore`);
      if (r[0]) out[v.variabile] = { v: Number(r[0].valore), d: r[0].data };
    }
  }
  return out;
}

type Scattato = {
  alert_id: number; utente_id: number; username: string; email: string; commodity: string;
  grandezza: string; condizione: string; soglia: number; valore: number; data_dato: string;
};

function titolo(c: Commodity): string {
  return c.commodity === "gas" ? "Gas Market Monitor" : `Market Monitor — ${c.nome}`;
}

function htmlEmail(c: Commodity, G: Record<string, Grandezza>, username: string,
                   righe: Scattato[], data: string, sg: Segnale | null): string {
  const tr = righe.map((s) => {
    const g = G[s.grandezza] ?? { nome: s.grandezza, udm: "", dec: 1 };
    const cond = s.condizione === "sopra" ? "sopra" : "sotto";
    if (s.grandezza === "segnale") {
      const nomeLiv = (n: number) => Object.entries(LIVELLI).find(([, v]) => v === n)?.[0] ?? String(n);
      return `<tr>
      <td style="padding:8px 10px;border-bottom:1px solid #e7eaf0">${esc(g.nome)}</td>
      <td style="padding:8px 10px;border-bottom:1px solid #e7eaf0;text-align:right;font-weight:700;color:${BLU}">${esc(NOME_SEGNALE[nomeLiv(s.valore)] ?? nomeLiv(s.valore))}</td>
      <td style="padding:8px 10px;border-bottom:1px solid #e7eaf0;color:#475569">raggiunto il livello “${esc(NOME_SEGNALE[nomeLiv(s.soglia)] ?? nomeLiv(s.soglia))}”</td>
    </tr>`;
    }
    return `<tr>
      <td style="padding:8px 10px;border-bottom:1px solid #e7eaf0">${esc(g.nome)}</td>
      <td style="padding:8px 10px;border-bottom:1px solid #e7eaf0;text-align:right;font-weight:700;color:${BLU}">${fmtIt(s.valore, g.dec)} ${esc(g.udm)}</td>
      <td style="padding:8px 10px;border-bottom:1px solid #e7eaf0;color:#475569">${cond} la soglia di ${fmtIt(s.soglia, g.dec)} ${esc(g.udm)}</td>
    </tr>`;
  }).join("");
  const dataIt = new Date(`${data}T00:00:00Z`).toLocaleDateString("it-IT", { timeZone: "UTC" });
  const link = APP_URL ? `<p style="margin-top:18px"><a href="${esc(APP_URL)}" style="color:${RED};font-weight:600">Apri il ${esc(titolo(c))} →</a></p>` : "";
  return `<div style="font-family:Inter,Arial,sans-serif;max-width:640px;margin:auto;color:#0f172a">
    <h2 style="color:${RED};border-bottom:3px solid ${RED};padding-bottom:8px">${esc(titolo(c))} — soglie raggiunte</h2>
    <p style="font-size:15px">Buongiorno ${esc(username)},<br>con i dati aggiornati al <b>${esc(dataIt)}</b> sono state raggiunte le soglie che hai impostato per <b>${esc(c.nome.toLowerCase())}</b>:</p>
    ${sg === null ? "" : `<div style="margin:14px 0 18px;padding:14px 16px;background:#f6f7f9;border-left:4px solid ${BLU};border-radius:6px">
      <div style="font-size:13px;color:#475569;text-transform:uppercase;letter-spacing:.04em">Situazione odierna · ${esc(c.nome)}</div>
      <div style="display:flex;gap:28px;flex-wrap:wrap;margin-top:6px">
        <div><div style="font-size:12px;color:#64748b">Scenario di approvvigionamento</div>
             <div style="font-size:26px;font-weight:800;color:${BLU};line-height:1.1">${fmtIt(sg.scenario, 0)}<span style="font-size:13px;font-weight:600;color:#475569"> /100</span></div></div>
        <div><div style="font-size:12px;color:#64748b">Prezzo ${esc(c.nome.toLowerCase())} ${esc(c.prezzo_label)}</div>
             <div style="font-size:26px;font-weight:800;color:#0f172a;line-height:1.1">${fmtIt(sg.prezzo, 2)}<span style="font-size:13px;font-weight:600;color:#475569"> ${esc(c.prezzo_udm)}</span></div>
             <div style="font-size:12px;color:#64748b">${sg.scost_breve_pct === null ? "" : `vs trend breve ${sg.scost_breve_pct >= 0 ? "+" : ""}${fmtIt(sg.scost_breve_pct, 1)}% · `}${sg.scost_medio_pct === null ? "" : `vs trend medio ${sg.scost_medio_pct >= 0 ? "+" : ""}${fmtIt(sg.scost_medio_pct, 1)}%`}</div></div>
      </div>
      <div style="font-size:14px;margin-top:10px"><b>${esc(NOME_SEGNALE[sg.codice] ?? sg.codice)}</b> — ${esc(sg.testo)}</div>
    </div>`}
    <table style="border-collapse:collapse;width:100%;font-size:14px">
      <thead><tr style="background:#f6f7f9">
        <th style="text-align:left;padding:8px 10px">Grandezza</th>
        <th style="text-align:right;padding:8px 10px">Valore</th>
        <th style="text-align:left;padding:8px 10px">Condizione</th>
      </tr></thead>
      <tbody>${tr}</tbody>
    </table>
    ${link}
    <p style="font-size:12px;color:#64748b;margin-top:22px">Le informazioni hanno scopo informativo e di supporto all'approvvigionamento; non costituiscono consulenza finanziaria. La decisione resta dell'utente.<br>Puoi modificare le tue soglie nella sezione Alert dell'applicazione.</p>
    <p style="font-size:12px;color:#64748b">Bros Consulenza s.r.l.</p>
  </div>`;
}

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  const preview = url.searchParams.get("preview") === "1";
  const data = url.searchParams.get("data") ?? ieriRoma();

  try {
    const commodities = (await q("gas_commodity?attivo=eq.true&order=ordine&select=commodity,nome,icona,prezzo_codice,prezzo_label,prezzo_udm,prezzo_aggregazione")) as Commodity[];
    const tutteVar = (await q("gas_variabili?order=commodity,ordine&select=commodity,variabile,etichetta,icona,udm,sorgente,commodity_dati,variabile_dati,metrica_dati,codice_indice")) as Variabile[];
    const regole = await q(
      "gas_alert?attivo=eq.true&select=id,utente_id,commodity,grandezza,condizione,soglia,cooldown_gg," +
      "gas_utenti!inner(username,email,attivo)&gas_utenti.attivo=eq.true");

    // anti-duplicato e cooldown
    const ids = regole.map((r) => r.id);
    const inviati = ids.length
      ? await q(`gas_alert_inviati?alert_id=in.(${ids.join(",")})&select=alert_id,data_dato,inviato_at&order=inviato_at.desc`)
      : [];
    const giaOggi = new Set(inviati.filter((i) => i.data_dato === data).map((i) => i.alert_id));
    const ultimoInvio = new Map<number, string>();
    for (const i of inviati) if (!ultimoInvio.has(i.alert_id)) ultimoInvio.set(i.alert_id, i.inviato_at);

    const scattati: Scattato[] = [];
    const saltati: string[] = [];
    const valoriPer: Record<string, Record<string, { v: number; d: string }>> = {};
    const segnalePer: Record<string, Segnale | null> = {};
    const esiti: Record<string, unknown>[] = [];

    for (const c of commodities) {
      const vars = tutteVar.filter((v) => v.commodity === c.commodity);
      const G = grandezze(c, vars);
      const regoleC = regole.filter((r) => (r.commodity ?? "gas") === c.commodity);
      if (!regoleC.length) continue;
      const valori = await valoriDelGiorno(c, vars, data);
      const sgGiorno = await segnaleDelGiorno(c.commodity, data);
      valoriPer[c.commodity] = valori;
      segnalePer[c.commodity] = sgGiorno;

      const scattatiC: Scattato[] = [];
      for (const r of regoleC) {
        const val = valori[r.grandezza];
        if (!val) { saltati.push(`#${r.id}: nessun dato per ${r.grandezza} (${c.commodity})`); continue; }
        const soglia = Number(r.soglia);
        const ok = r.grandezza === "segnale"
          ? (r.condizione === "sopra" ? val.v >= soglia : val.v < soglia)   // livello: inclusivo
          : (r.condizione === "sopra" ? val.v > soglia : val.v < soglia);
        if (!ok) continue;
        if (giaOggi.has(r.id)) { saltati.push(`#${r.id}: gia' inviato per ${data}`); continue; }
        const ult = ultimoInvio.get(r.id);
        if (ult) {
          const gg = (Date.now() - new Date(ult).getTime()) / 86400000;
          if (gg < Number(r.cooldown_gg)) { saltati.push(`#${r.id}: in cooldown (${gg.toFixed(1)} gg < ${r.cooldown_gg})`); continue; }
        }
        const u = r.gas_utenti;
        if (!u?.email) { saltati.push(`#${r.id}: utente ${u?.username} senza email`); continue; }
        scattatiC.push({
          alert_id: r.id, utente_id: r.utente_id, username: u.username, email: u.email,
          commodity: c.commodity, grandezza: r.grandezza, condizione: r.condizione,
          soglia, valore: val.v, data_dato: data,
        });
      }
      scattati.push(...scattatiC);

      // raggruppa per utente: UNA email per utente e commodity con tutte le regole scattate
      const perUtente = new Map<string, Scattato[]>();
      for (const s of scattatiC) perUtente.set(s.email, [...(perUtente.get(s.email) ?? []), s]);
      for (const [email, righe] of perUtente) {
        const soggetto = `${titolo(c)} — ${righe.length === 1 ? "soglia raggiunta" : `${righe.length} soglie raggiunte`} (${data.split("-").reverse().join("/")})`;
        const html = htmlEmail(c, G, righe[0].username, righe, data, sgGiorno);
        if (preview) {
          esiti.push({ email, commodity: c.commodity, soggetto, regole: righe.map((s) => s.alert_id), html_len: html.length });
          continue;
        }
        if (!BREVO_API_KEY) throw new Error("BREVO_API_KEY mancante");
        await sendBrevo(email, soggetto, html);
        await ins("gas_alert_inviati", righe.map((s) => ({ alert_id: s.alert_id, data_dato: s.data_dato, valore: s.valore })));
        esiti.push({ email, commodity: c.commodity, soggetto, regole: righe.map((s) => s.alert_id), inviata: true });
      }
    }

    return Response.json({ preview, data, regole_attive: regole.length, scattate: scattati.length,
                           email: esiti, saltati, valori: valoriPer });
  } catch (e) {
    return new Response(`errore alert: ${e}`, { status: 500 });
  }
});
