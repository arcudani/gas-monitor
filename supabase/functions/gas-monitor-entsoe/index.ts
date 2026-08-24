// Edge Function `gas-monitor-entsoe` — produzione elettrica italiana da
// ENTSO-E Transparency (dati trasmessi da Terna, Reg. UE 543/2013).
//
// Vive in una funzione separata da `gas-monitor` (come gas-monitor-gpr):
// l'XML "Actual Generation per Type" e' grande (un mese ~ 7-10k punti per
// una decina di fonti) e il parsing non deve contendere memoria alla pipeline.
//
// Scarica documentType=A75 (Actual generation per type), processType=A16
// (Realised) per il dominio ITALIA (10YIT-GRTN-----B: aggregato nazionale,
// pari alla somma delle 7 zone di mercato) e scrive in gas_serie:
//   - commodity 'ee', variabile 'produzione',  metrica 'produzione_tot' (GWh/g)
//   - commodity 'ee', variabile 'rinnovabili', metrica 'quota_pct'
//     (solare B16 + eolico B18/B19 sul totale, %)
// I giorni sono giorni SOLARI Europe/Rome (i punti ENTSO-E sono in UTC).
//
// Parametri (Authorization: Bearer anon/service key):
//   ?dal=YYYY-MM-DD&al=YYYY-MM-DD   intervallo (default: ultimi 10 giorni)
//   ?dry=1                          parse senza scrivere (test)
// L'API accetta max 1 anno per richiesta: si chiede un mese alla volta con
// un giorno di margine per lato e si scartano i giorni di bordo (parziali).
//
// Secret: ENTSOE_API_KEY (token Restful API del portale transparency.entsoe.eu).

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ENTSOE_KEY = Deno.env.get("ENTSOE_API_KEY") ?? "";

const DOMINIO_IT = "10YIT-GRTN-----B";           // Italia (aggregato nazionale)
const RINNOVABILI = new Set(["B16", "B18", "B19"]); // solare, eolico offshore, eolico onshore
const FONTE = "ENTSO-E Transparency (Terna)";

type Riga = { data: string; commodity: string; variabile: string; metrica: string; valore: number; fonte: string };

async function upsertSerie(righe: Riga[]): Promise<number> {
  let n = 0;
  for (let i = 0; i < righe.length; i += 1000) {
    const blocco = righe.slice(i, i + 1000);
    const r = await fetch(`${SB_URL}/rest/v1/gas_serie?on_conflict=data,commodity,variabile,metrica`, {
      method: "POST",
      headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, "Content-Type": "application/json",
                 Prefer: "resolution=merge-duplicates,return=minimal" },
      body: JSON.stringify(blocco),
    });
    if (!r.ok) throw new Error(`REST gas_serie: ${r.status} ${await r.text()}`);
    n += blocco.length;
  }
  return n;
}

function dataRoma(d: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" }).format(d);
}

function isoAddDays(iso: string, giorni: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + giorni);
  return d.toISOString().slice(0, 10);
}

// Parser leggero dell'XML GL_MarketDocument (niente DOMParser nell'edge runtime):
// per ogni <TimeSeries> estrae psrType, inBiddingZone (produzione; il consumo dei
// pompaggi arriva come outBiddingZone e si ignora), i <Period> con start/resolution
// e i <Point>. Le posizioni mancanti ripetono l'ultimo valore (standard ENTSO-E).
function accumula(xml: string, mwhGiorno: Map<string, Map<string, number>>) {
  const serieRe = /<TimeSeries>([\s\S]*?)<\/TimeSeries>/g;
  let m: RegExpExecArray | null;
  while ((m = serieRe.exec(xml)) !== null) {
    const ts = m[1];
    if (!/<inBiddingZone_Domain\.mRID/.test(ts)) continue;   // produzione, non consumo
    const psr = (ts.match(/<psrType>([^<]+)<\/psrType>/) ?? [])[1] ?? "??";
    const perRe = /<Period>([\s\S]*?)<\/Period>/g;
    let p: RegExpExecArray | null;
    while ((p = perRe.exec(ts)) !== null) {
      const per = p[1];
      const start = (per.match(/<start>([^<]+)<\/start>/) ?? [])[1];
      const resol = (per.match(/<resolution>PT(\d+)M<\/resolution>/) ?? [])[1];
      if (!start || !resol) continue;
      const minuti = Number(resol);
      const t0 = new Date(start).getTime();
      const punti: { pos: number; q: number }[] = [];
      const ptRe = /<position>(\d+)<\/position>\s*<quantity>([\d.]+)<\/quantity>/g;
      let q: RegExpExecArray | null;
      while ((q = ptRe.exec(per)) !== null) punti.push({ pos: Number(q[1]), q: Number(q[2]) });
      if (!punti.length) continue;
      const maxPos = punti[punti.length - 1].pos;
      let idx = 0, ultimo = punti[0].q;
      for (let pos = 1; pos <= maxPos; pos++) {
        if (idx < punti.length && punti[idx].pos === pos) ultimo = punti[idx++].q;
        const giorno = dataRoma(new Date(t0 + (pos - 1) * minuti * 60000));
        const mwh = ultimo * minuti / 60;         // quantity in MW
        let perPsr = mwhGiorno.get(giorno);
        if (!perPsr) { perPsr = new Map(); mwhGiorno.set(giorno, perPsr); }
        perPsr.set(psr, (perPsr.get(psr) ?? 0) + mwh);
      }
    }
  }
}

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  const oggi = dataRoma(new Date());
  const dal = url.searchParams.get("dal") ?? isoAddDays(oggi, -10);
  const al = url.searchParams.get("al") ?? isoAddDays(oggi, -1);
  const dry = url.searchParams.get("dry") === "1";
  if (!ENTSOE_KEY) return new Response("ENTSOE_API_KEY assente nei secrets", { status: 500 });

  try {
    // finestre mensili con 1 giorno di margine per lato (i giorni di bordo,
    // parziali in UTC, si scartano dopo)
    const mwhGiorno = new Map<string, Map<string, number>>();
    let cur = isoAddDays(dal, -1);
    const fine = isoAddDays(al, 1);
    let richieste = 0;
    while (cur <= fine) {
      const fin = new Date(`${cur}T00:00:00Z`);
      fin.setUTCDate(fin.getUTCDate() + 31);
      let stop = fin.toISOString().slice(0, 10);
      if (stop > fine) stop = fine;
      const ps = cur.replaceAll("-", "") + "0000";
      const pe = isoAddDays(stop, 1).replaceAll("-", "") + "0000";
      const u = `https://web-api.tp.entsoe.eu/api?securityToken=${ENTSOE_KEY}` +
        `&documentType=A75&processType=A16&in_Domain=${DOMINIO_IT}` +
        `&periodStart=${ps}&periodEnd=${pe}`;
      const r = await fetch(u);
      const body = await r.text();
      richieste++;
      if (!r.ok) throw new Error(`ENTSO-E ${r.status}: ${body.slice(0, 300)}`);
      if (body.includes("<Acknowledgement_MarketDocument")) {
        // "No matching data": range senza dati (es. futuro) — non e' un errore
        const motivo = (body.match(/<text>([^<]+)<\/text>/) ?? [])[1] ?? "no data";
        if (!/no matching data/i.test(motivo)) throw new Error(`ENTSO-E: ${motivo}`);
      } else {
        accumula(body, mwhGiorno);
      }
      cur = isoAddDays(stop, 1);
    }

    const righe: Riga[] = [];
    const giorni = [...mwhGiorno.keys()].sort().filter((g) => g >= dal && g <= al);
    for (const g of giorni) {
      const perPsr = mwhGiorno.get(g)!;
      let tot = 0, rinn = 0;
      for (const [psr, mwh] of perPsr) {
        tot += mwh;
        if (RINNOVABILI.has(psr)) rinn += mwh;
      }
      if (tot <= 0) continue;
      righe.push({ data: g, commodity: "ee", variabile: "produzione", metrica: "produzione_tot",
                   valore: Math.round(tot / 1000 * 10) / 10, fonte: FONTE });          // GWh/g
      righe.push({ data: g, commodity: "ee", variabile: "rinnovabili", metrica: "quota_pct",
                   valore: Math.round(rinn / tot * 1000) / 10, fonte: FONTE });        // %
    }
    if (dry) {
      return Response.json({ dal, al, richieste, giorni: righe.length / 2,
                             campione: righe.slice(0, 6), ultimo: righe.slice(-2) });
    }
    const n = await upsertSerie(righe);
    return Response.json({ dal, al, richieste, giorni: righe.length / 2, righe: n });
  } catch (e) {
    return new Response(`errore ENTSO-E: ${e}`, { status: 500 });
  }
});
