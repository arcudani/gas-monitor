// Edge Function `gas-monitor-gpr` — SOLO il download+parse del GPR daily.
//
// Vive in una funzione separata da `gas-monitor` perche' il parsing
// dell'.xls (~3MB, 15k righe, SheetJS) e' l'operazione piu' avida di
// memoria della pipeline: nello stesso worker delle altre fonti causava
// WORKER_RESOURCE_LIMIT (18/08/2026), e una sub-invocazione dello stesso
// slug riusa lo stesso isolate. Slug diverso = memoria propria.
//
// Chiamata da gas-monitor (run giornaliero e ?backfill=geopolitica):
//   GET /functions/v1/gas-monitor-gpr?dal=YYYY-MM-DD&al=YYYY-MM-DD
// Risposta: { righe: n } upsertate in gas_serie (geopolitica/gpr).

import * as XLSX from "npm:xlsx@0.18.5";

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const GPR_URL =
  "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls";

type Riga = {
  data: string; variabile: string; metrica: string;
  valore: number; fonte: string;
};

async function upsertSerie(righe: Riga[]): Promise<number> {
  let n = 0;
  for (let i = 0; i < righe.length; i += 1000) {
    const blocco = righe.slice(i, i + 1000);
    const r = await fetch(
      `${SB_URL}/rest/v1/gas_serie?on_conflict=data,commodity,variabile,metrica`,
      {
        method: "POST",
        headers: {
          apikey: SB_KEY,
          Authorization: `Bearer ${SB_KEY}`,
          "Content-Type": "application/json",
          Prefer: "resolution=merge-duplicates,return=minimal",
        },
        body: JSON.stringify(blocco),
      },
    );
    if (!r.ok) throw new Error(`REST gas_serie: ${r.status} ${await r.text()}`);
    n += blocco.length;
  }
  return n;
}

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  const dal = url.searchParams.get("dal") ?? "2015-01-01";
  const al = url.searchParams.get("al") ?? new Date().toISOString().slice(0, 10);
  try {
    const r = await fetch(GPR_URL);
    if (!r.ok) throw new Error(`GPR: ${r.status}`);
    // dense:true = foglio come array di array (niente 15k oggetti a chiavi)
    const wb = XLSX.read(new Uint8Array(await r.arrayBuffer()),
                         { type: "array", dense: true });
    const foglio = wb.Sheets[wb.SheetNames[0]] as unknown as
      Array<Array<{ v?: unknown } | undefined>>;
    if (!Array.isArray(foglio) || !foglio.length) {
      throw new Error("GPR: foglio vuoto o formato inatteso");
    }
    const intestazioni = (foglio[0] ?? []).map((c) => String(c?.v ?? ""));
    const iDay = intestazioni.indexOf("DAY");
    const iGprd = intestazioni.indexOf("GPRD");
    if (iDay < 0 || iGprd < 0) {
      throw new Error("GPR: colonne DAY/GPRD non trovate (formato cambiato?)");
    }
    const righe: Riga[] = [];
    for (let i = 1; i < foglio.length; i++) {
      const riga = foglio[i];
      if (!riga) continue;
      const day = String(riga[iDay]?.v ?? "");
      const gprd = Number(riga[iGprd]?.v);
      if (day.length !== 8 || !Number.isFinite(gprd)) continue;
      const data = `${day.slice(0, 4)}-${day.slice(4, 6)}-${day.slice(6, 8)}`;
      if (data < dal || data > al) continue;
      righe.push({
        data, variabile: "geopolitica", metrica: "gpr",
        valore: Math.round(gprd * 1000) / 1000,
        fonte: "GPR Caldara-Iacoviello",
      });
    }
    if (!righe.length) {
      throw new Error("GPR: nessuna riga nel range (formato cambiato?)");
    }
    const n = await upsertSerie(righe);
    return Response.json({ righe: n, dal, al });
  } catch (e) {
    return new Response(`errore GPR: ${e}`, { status: 500 });
  }
});
