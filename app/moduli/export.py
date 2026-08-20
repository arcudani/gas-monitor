"""
Modulo Export (RF-05): PDF snapshot della situazione in veste Bros ed Excel
delle serie storiche del periodo filtrato. La generazione e' in export.py
(funzioni pure); qui solo filtri e download_button.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

import db
import export

st.title("📤 Export")
st.caption("Scarica lo snapshot PDF della situazione odierna o le serie "
           "storiche in Excel per il periodo che scegli.")

LOGO = Path(__file__).resolve().parent.parent / "assets" / "Logo_Bros_Consulenza_460.png"


@st.cache_data(ttl=600, show_spinner="📡 Preparo i dati…")
def _segnale() -> tuple[pd.DataFrame, dict]:
    rows = db.query(
        "SELECT data, scenario, scenario_medio, punteggi, prezzo, trend_breve, "
        "       trend_medio, trend_lungo, scost_breve_pct, scost_medio_pct, "
        "       pendenza_lungo_pct, prezzo_favorevole, giorni_consecutivi, codice, testo "
        "FROM public.gas_segnale WHERE commodity='gas' ORDER BY data")
    cfg = db.query("SELECT pesi FROM public.gas_pesi ORDER BY versione DESC LIMIT 1")
    df = pd.DataFrame(rows, columns=[
        "Data", "Scenario", "ScenarioM", "Punteggi", "Prezzo", "TBreve", "TMedio",
        "TLungo", "ScB", "ScM", "PendL", "PzOk", "N", "Codice", "Testo"])
    if not df.empty:
        df["Data"] = pd.to_datetime(df["Data"])
        for c in ("Scenario", "ScenarioM", "Prezzo", "TBreve", "TMedio", "TLungo",
                  "ScB", "ScM", "PendL"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, ((cfg[0][0] if cfg else {}) or {})


@st.cache_data(ttl=600, show_spinner=False)
def _variabili(dal: dt.date, al: dt.date) -> pd.DataFrame:
    rows = db.query(
        "SELECT data, metrica, valore FROM public.gas_serie "
        "WHERE commodity='gas' AND data BETWEEN %s AND %s ORDER BY data", (dal, al))
    df = pd.DataFrame(rows, columns=["Data", "Metrica", "Valore"])
    if not df.empty:
        df["Data"] = pd.to_datetime(df["Data"])
        df["Valore"] = pd.to_numeric(df["Valore"], errors="coerce")
    return df


try:
    df, cfg = _segnale()
except Exception as e:
    st.error(f"📡 Impossibile leggere i dati: {e}")
    st.stop()
if df.empty:
    st.info("Nessun dato disponibile.")
    st.stop()

ult = df.iloc[-1]
prec = df.iloc[-2] if len(df) > 1 else ult

# =============================================================================
# PDF snapshot
# =============================================================================
st.subheader("📄 Snapshot PDF")
st.caption("Una pagina A4 in veste Bros: scenario, prezzo con i trend, segnale del "
           "giorno, ultimi 14 giorni, fonti e disclaimer. Pronta da inoltrare.")
sit = dict(
    data=ult["Data"], scenario=float(ult["Scenario"]),
    scenario_m=float(ult["ScenarioM"]) if pd.notna(ult["ScenarioM"]) else float(ult["Scenario"]),
    punteggi=ult["Punteggi"] or {}, prezzo=float(ult["Prezzo"]),
    d_prezzo=float(ult["Prezzo"]) - float(prec["Prezzo"]),
    sc_b=ult["ScB"], sc_m=ult["ScM"], pend_l=ult["PendL"], pz_ok=bool(ult["PzOk"]),
    codice=ult["Codice"], n=int(ult["N"]), testo=ult["Testo"],
)
pdf_bytes = export.pdf_snapshot(sit, df, cfg, LOGO)
st.download_button(
    "⬇️ Scarica snapshot PDF", data=pdf_bytes,
    file_name=f"gas_monitor_{ult['Data'].strftime('%Y%m%d')}.pdf",
    mime="application/pdf", type="primary",
)

# =============================================================================
# Excel serie
# =============================================================================
st.subheader("📊 Serie storiche Excel")
preset = st.radio(
    "Periodo", ["Mese", "3 mesi", "12 mesi", "Anno corrente", "Tutto", "Personalizzato"],
    index=2, horizontal=True, label_visibility="collapsed",
)
fine = ult["Data"].date()
if preset == "Personalizzato":
    c1, c2 = st.columns(2)
    dal = c1.date_input("Dal", value=fine - dt.timedelta(days=365),
                        min_value=df["Data"].min().date(), max_value=fine)
    al = c2.date_input("Al", value=fine, min_value=dal, max_value=fine)
else:
    dal = {
        "Mese": fine - dt.timedelta(days=31),
        "3 mesi": fine - dt.timedelta(days=92),
        "12 mesi": fine - dt.timedelta(days=366),
        "Anno corrente": dt.date(fine.year, 1, 1),
        "Tutto": df["Data"].min().date(),
    }[preset]
    al = fine

seg_p = df[(df["Data"].dt.date >= dal) & (df["Data"].dt.date <= al)]
var_p = _variabili(dal, al)
st.caption(f"Periodo {dal.strftime('%d/%m/%Y')} – {al.strftime('%d/%m/%Y')}: "
           f"{len(seg_p)} giorni di segnale, {len(var_p)} righe di variabili. "
           "Fogli: Segnale · Variabili · Note.")
xlsx_bytes = export.excel_serie(seg_p, var_p, dal, al)
st.download_button(
    "⬇️ Scarica Excel", data=xlsx_bytes,
    file_name=f"gas_monitor_serie_{dal.strftime('%Y%m%d')}_{al.strftime('%Y%m%d')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()
st.caption("ℹ️ " + export.DISCLAIMER)
