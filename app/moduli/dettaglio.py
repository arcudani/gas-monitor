"""
Modulo Dettaglio — una pagina per variabile (RF-02) con filtri periodo (RF-03),
multi-commodity dal 21/08/2026 (g008).

Per ogni variabile: grafico storico completo, overlay di confronto (media
5 anni sullo stesso giorno dell'anno, o norma pluriennale per il meteo,
o anno precedente), metriche di supporto e il punteggio percentile che
entra nello SCENARIO (orientato a favore dell'acquirente, requisiti v1.6).
Per il prezzo: scostamento dai tre trend. Solo dati pre-calcolati (cache 10').
L'elenco delle variabili viene dall'anagrafica gas_variabili (commodity.py).
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import branding
import commodity
import db

BLU = "#0F6FA8"          # dato (come i numeri grandi in Dashboard)
TEAL = "#14B8A6"         # riferimento / confronto (come il trend medio in Dashboard)
GRIGIO = "#64748b"
ROSSO = "#C00000"        # serie principale (come il prezzo in Dashboard)

COM = commodity.corrente()
INFO = commodity.info(COM)
VARS = commodity.variabili(COM)

st.title(f"🔎 Dettaglio variabili — {INFO['nome']}")
st.caption("Storico completo, confronto con la media pluriennale e punteggio "
           "di ciascuna variabile dello scenario (alto = favorevole all'acquirente); "
           "per il prezzo, lo scostamento dai tre trend.")

# Definizione delle variabili dall'anagrafica: il prezzo per primo, poi le
# variabili dello scenario nell'ordine della tabella.
VARIABILI = {
    f"{INFO['icona']} Prezzo {INFO['prezzo_label']}": dict(
        chiave="prezzo", sql=commodity.sql_prezzo(INFO), udm=INFO["prezzo_udm"],
        direzione="prezzo sotto i trend → condizione favorevole al fixing",
        confronto="anno_prec", fonte=INFO["prezzo_fonte"],
        spiega=f"Prezzo di riferimento {INFO['prezzo_label']} ({INFO['prezzo_fonte']}). Non entra nello "
               "scenario: è la **condizione prezzo** del segnale, misurata come "
               "scostamento dalle rette di tendenza di breve, medio e lungo periodo "
               "(vedi Dashboard e Admin)."),
}
for v in VARS:
    VARIABILI[f"{v['icona']} {v['etichetta']}"] = dict(
        chiave=v["variabile"], sql=commodity.sql_valori(v), udm=v["udm"],
        direzione=v["direzione"], confronto=commodity.tipo_confronto(v),
        abs_delta=(v["trasformazione"] == "abs_delta"),
        fonte=v["fonte"], spiega=v["spiegazione"])

scelta = st.selectbox("Variabile", list(VARIABILI), label_visibility="collapsed")
cfg = VARIABILI[scelta]
C_SERIE = ROSSO if cfg["chiave"] == "prezzo" else BLU   # come in Dashboard

periodo = st.radio(
    "Periodo", ["Settimana", "Mese", "3 mesi", "Da inizio anno", "12 mesi", "5 anni", "Tutto"],
    index=2, horizontal=True, label_visibility="collapsed",
)


# =============================================================================
# Dati (cache 10 min)
# =============================================================================

@st.cache_data(ttl=600, show_spinner="📡 Leggo la serie…")
def _serie(sql: str, params: tuple) -> pd.DataFrame:
    rows = db.query(sql, params)
    df = pd.DataFrame(rows, columns=["Data", "Valore"])
    if not df.empty:
        df["Data"] = pd.to_datetime(df["Data"])
        df["Valore"] = pd.to_numeric(df["Valore"], errors="coerce")
    return df


@st.cache_data(ttl=600, show_spinner=False)
def _punteggi(com: str) -> pd.DataFrame:
    # punteggi dello SCENARIO (gas_segnale): orientati a favore dell'acquirente;
    # per il prezzo porta anche gli scostamenti dai trend
    rows = db.query(
        "SELECT data, punteggi, scost_breve_pct, scost_medio_pct, pendenza_lungo_pct "
        "FROM public.gas_segnale WHERE commodity = %s ORDER BY data", (com,))
    df = pd.DataFrame(rows, columns=["Data", "Punteggi", "ScB", "ScM", "PendL"])
    if not df.empty:
        df["Data"] = pd.to_datetime(df["Data"])
    return df


try:
    df = _serie(*cfg["sql"])
    df_p = _punteggi(COM)
except db.DBConfigError as e:
    st.warning(f"⚙️ {e}")
    st.stop()
except Exception as e:
    st.error(f"📡 Impossibile leggere la serie: {e}")
    st.stop()

if df.empty:
    st.info("Nessun dato ancora disponibile per questa variabile: la serie si popola con il "
            "primo caricamento della pipeline (nel frattempo conta come neutra nello scenario).")
    st.stop()

# =============================================================================
# Confronto: colonna "Riferimento" allineata per giorno
# =============================================================================
df = df.copy()
df["doy"] = df["Data"].dt.dayofyear
if cfg["confronto"] == "norma":
    # norma pluriennale = media di TUTTO lo storico per giorno dell'anno
    norma = df.groupby("doy")["Valore"].mean()
    df["Riferimento"] = df["doy"].map(norma)
    label_rif = "Norma pluriennale (stesso giorno)"
elif cfg["confronto"] == "media5":
    # media dei 5 anni precedenti, stesso giorno ±3 (come nel ricalcolo)
    s = df.set_index("Data")["Valore"]
    def _m5(row):
        d = row["Data"]
        fin = s[(s.index < d) & (s.index >= d - pd.DateOffset(years=5))]
        if fin.empty:
            return None
        doy = fin.index.dayofyear
        m = fin[(abs(doy - row["doy"]) <= 3)]
        return m.mean() if not m.empty else None
    df["Riferimento"] = df.apply(_m5, axis=1)
    label_rif = "Media 5 anni (stesso giorno ±3)"
else:
    # stesso giorno dell'anno precedente
    prec = df.set_index("Data")["Valore"]
    df["Riferimento"] = [
        prec.get(d - pd.DateOffset(years=1), None) for d in df["Data"]]
    label_rif = "Anno precedente"

# =============================================================================
# Filtro periodo
# =============================================================================
fine = df["Data"].max()
inizio = {
    "Settimana": fine - pd.Timedelta(days=7),
    "Mese": fine - pd.Timedelta(days=31),
    "3 mesi": fine - pd.Timedelta(days=92),
    "Da inizio anno": pd.Timestamp(year=fine.year, month=1, day=1),
    "12 mesi": fine - pd.Timedelta(days=366),
    "5 anni": fine - pd.DateOffset(years=5),
    "Tutto": df["Data"].min(),
}[periodo]
dfp = df[df["Data"] >= inizio]

# =============================================================================
# KPI di supporto
# =============================================================================
ult = dfp.iloc[-1]
val = float(ult["Valore"])
rif = ult["Riferimento"]
delta_rif = (val - float(rif)) if pd.notna(rif) else None
prec_g = float(dfp.iloc[-2]["Valore"]) if len(dfp) > 1 else val
d1 = val - prec_g

p_ult = None
r_ult = None
if not df_p.empty:
    r_ult = df_p.iloc[-1]
    pj = r_ult["Punteggi"] or {}
    p_ult = pj.get(cfg["chiave"])


def _fmt(v: float, dec: int = 1) -> str:
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


dec = commodity.decimali(cfg["udm"]) if cfg["chiave"] != "prezzo" else 2
udm_vis = "" if cfg["udm"] == "indice" else cfg["udm"]
val_txt = _fmt(val, dec)
rif_txt = "n.d." if pd.isna(rif) else _fmt(float(rif), dec)
delta_txt = ("n.d." if delta_rif is None else
             f"{'+' if delta_rif >= 0 else '−'}{_fmt(abs(delta_rif), dec)} {udm_vis} rispetto al riferimento")
if cfg.get("abs_delta"):
    delta_txt += " · conta la distanza, in entrambe le direzioni"


def _sc(v):
    return "n.d." if v is None or pd.isna(v) else f"{'+' if float(v) >= 0 else '−'}{_fmt(abs(float(v)), 1)} %"


cards = (
    branding.gm_tile("Valore attuale", val_txt, udm_vis,
                     f"{branding.gm_delta(d1, dec, udm_vis)} vs giorno precedente · {ult['Data'].strftime('%d/%m/%Y')}",
                     accent=BLU)
    + branding.gm_tile(label_rif, rif_txt, udm_vis if not pd.isna(rif) else "",
                       delta_txt, accent=TEAL)
    + (branding.gm_tile_mini("Scostamento dai trend",
                             [("vs breve 20 gg", _sc(r_ult["ScB"]) if r_ult is not None else "n.d."),
                              ("vs medio 60 gg", _sc(r_ult["ScM"]) if r_ult is not None else "n.d.")],
                             f"trend lungo 180 gg: {('in salita' if float(r_ult['PendL']) > 0.05 else 'in discesa' if float(r_ult['PendL']) < -0.05 else 'piatto') if r_ult is not None and pd.notna(r_ult['PendL']) else 'n.d.'}",
                             accent=BLU)
       if cfg["chiave"] == "prezzo" else
       branding.gm_tile("Punteggio nello scenario",
                        "n.d." if p_ult is None else f"{float(p_ult):.0f}", "/100" if p_ult is not None else "",
                        cfg["direzione"], accent=BLU, score=p_ult, score_label="alto = favorevole"))
    + branding.gm_tile_mini("Nel periodo selezionato",
                            [("minimo", f"{_fmt(dfp['Valore'].min(), dec)}<small>{udm_vis}</small>"),
                             ("massimo", f"{_fmt(dfp['Valore'].max(), dec)}<small>{udm_vis}</small>")],
                            f"media {_fmt(dfp['Valore'].mean(), dec)} {udm_vis}", accent=BLU)
)
st.markdown(f"<div class='gm-grid'>{cards}</div>", unsafe_allow_html=True)

# =============================================================================
# Grafico: serie + riferimento in overlay
# =============================================================================
base = alt.Chart(dfp).encode(x=alt.X("Data:T", title=""))
linea = base.mark_line(color=C_SERIE, strokeWidth=2).encode(
    y=alt.Y("Valore:Q", title=udm_vis, scale=alt.Scale(zero=False)),
    tooltip=[alt.Tooltip("Data:T", format="%d/%m/%Y"),
             alt.Tooltip("Valore:Q", format=".2f", title=udm_vis or "valore")],
)
rif_line = base.mark_line(color=TEAL, strokeWidth=1.8,
                          strokeDash=[7, 4]).encode(
    y=alt.Y("Riferimento:Q"),
    tooltip=[alt.Tooltip("Data:T", format="%d/%m/%Y"),
             alt.Tooltip("Riferimento:Q", format=".2f", title=label_rif)],
)
st.markdown(branding.gm_legend([("solid", C_SERIE, scelta.split(" ", 1)[-1]), ("dash", TEAL, label_rif.lower())]),
            unsafe_allow_html=True)
branding.altair_it(linea + rif_line, width="stretch")

# =============================================================================
# Punteggio nel tempo (percentile che entra nello scenario)
# =============================================================================
if not df_p.empty and cfg["chiave"] != "prezzo":
    dpp = df_p[df_p["Data"] >= inizio].copy()
    dpp["Punteggio"] = [
        (p or {}).get(cfg["chiave"]) for p in dpp["Punteggi"]]
    dpp = dpp.dropna(subset=["Punteggio"])
    if not dpp.empty:
        st.markdown("<div class='gm-section'><div style='font-size:1.7rem;font-weight:800;color:#C00000;letter-spacing:-.02em;line-height:1.1'>Punteggio nello scenario</div><span>nel periodo · alto = favorevole</span></div>", unsafe_allow_html=True)
        ch = alt.Chart(dpp).mark_area(
            color=BLU, opacity=0.25, line={"color": BLU, "strokeWidth": 1.5}
        ).encode(
            x=alt.X("Data:T", title=""),
            y=alt.Y("Punteggio:Q", scale=alt.Scale(domain=[0, 100]), title="0–100"),
            tooltip=[alt.Tooltip("Data:T", format="%d/%m/%Y"),
                     alt.Tooltip("Punteggio:Q", format=".0f")],
        )
        branding.altair_it(ch, width="stretch")

st.markdown(cfg["spiega"])
st.caption(f"🗂 Fonte: {cfg['fonte']}")
