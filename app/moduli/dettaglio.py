"""
Modulo Dettaglio — una pagina per variabile (RF-02) con filtri periodo (RF-03).

Per ogni variabile: grafico storico completo, overlay di confronto (media
5 anni sullo stesso giorno dell'anno, o norma pluriennale per il meteo,
o anno precedente), metriche di supporto e il punteggio percentile che
entra nello SCENARIO (orientato a favore dell'acquirente, requisiti v1.6).
Per il prezzo: scostamento dai tre trend. Solo dati pre-calcolati (cache 10').
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import branding
import db

BLU = "#0F6FA8"          # dato (come i numeri grandi in Dashboard)
TEAL = "#14B8A6"         # riferimento / confronto (come il trend medio in Dashboard)
GRIGIO = "#64748b"
ROSSO = "#C00000"        # serie principale (come il prezzo in Dashboard)

st.title("🔎 Dettaglio variabili")
st.caption("Storico completo, confronto con la media pluriennale e punteggio "
           "di ciascuna variabile dello scenario (alto = favorevole all'acquirente); "
           "per il prezzo, lo scostamento dai tre trend.")

# Definizione delle variabili: (etichetta, chiave punteggio, sorgente,
# metrica, unità, direzione rialzista, spiegazione, tipo confronto)
VARIABILI = {
    "🔥 Prezzo MGP-GAS": dict(
        chiave="prezzo", tabella="mgp", metrica=None, udm="€/MWh",
        direzione="prezzo sotto i trend → condizione favorevole al fixing",
        confronto="anno_prec",
        spiega="Prezzo day-ahead del gas sul mercato italiano (GME). Non entra nello "
               "scenario: è la **condizione prezzo** del segnale, misurata come "
               "scostamento dalle rette di tendenza di breve, medio e lungo periodo "
               "(vedi Dashboard e Admin)."),
    "🛢 Stoccaggi IT": dict(
        chiave="stoccaggi", tabella="serie", metrica="riempimento_pct", udm="%",
        direzione="riempimento SOPRA la media 5 anni → punteggio alto (favorevole)",
        confronto="media5",
        spiega="Percentuale di riempimento degli stoccaggi italiani (GIE AGSI+). "
               "Il punteggio confronta il valore con la **media dei 5 anni "
               "precedenti nello stesso giorno (±3 gg)**: sopra media = offerta "
               "abbondante = scenario più favorevole all'acquirente."),
    "🌡 Meteo (T paniere)": dict(
        chiave="meteo", tabella="serie", metrica="t_media_paniere", udm="°C",
        direzione="più MITE della norma → punteggio alto (favorevole)",
        confronto="norma",
        spiega="Temperatura media giornaliera del paniere città pesato per "
               "consumo gas (MI 30 · RM 20 · TO 15 · BO 15 · FI 10 · VE 10; "
               "Open-Meteo/ERA5). Il punteggio è lo **scostamento dalla norma "
               "1991–oggi dello stesso giorno dell'anno**: più mite = meno "
               "domanda per riscaldamento = scenario più favorevole."),
    "🚢 LNG send-out": dict(
        chiave="lng", tabella="serie", metrica="lng_sendout", udm="GWh/g",
        direzione="send-out SOPRA la media 5 anni → punteggio alto (favorevole)",
        confronto="media5",
        spiega="Gas immesso in rete dai rigassificatori italiani (GIE ALSI). "
               "Il punteggio confronta con la **media 5 anni** dello stesso "
               "periodo: rigassificatori molto utilizzati = molta offerta via nave "
               "= scenario più favorevole."),
    "🌍 Geopolitica (GPR)": dict(
        chiave="geopolitica", tabella="serie", metrica="gpr", udm="indice",
        direzione="GPR BASSO → punteggio alto (favorevole)",
        confronto="anno_prec",
        spiega="**Geopolitical Risk Index** giornaliero di Caldara–Iacoviello: "
               "conta gli articoli su tensioni, minacce e conflitti in 10 grandi "
               "quotidiani internazionali (base 1985–2019 = 100). Il punteggio è "
               "il rango percentile sullo storico 2020–oggi, invertito: contesto "
               "calmo = scenario più favorevole."),
}

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
def _serie(tabella: str, metrica: str | None) -> pd.DataFrame:
    if tabella == "mgp":
        rows = db.query(
            "SELECT data, valore FROM public.indici_mercato "
            "WHERE codice = 'MGP_GAS' AND stato = 'consuntivo' ORDER BY data")
    else:
        rows = db.query(
            "SELECT data, valore FROM public.gas_serie "
            "WHERE commodity = 'gas' AND metrica = %s ORDER BY data", (metrica,))
    df = pd.DataFrame(rows, columns=["Data", "Valore"])
    if not df.empty:
        df["Data"] = pd.to_datetime(df["Data"])
        df["Valore"] = pd.to_numeric(df["Valore"], errors="coerce")
    return df


@st.cache_data(ttl=600, show_spinner=False)
def _punteggi() -> pd.DataFrame:
    # punteggi dello SCENARIO (gas_segnale): orientati a favore dell'acquirente;
    # per il prezzo porta anche gli scostamenti dai trend
    rows = db.query(
        "SELECT data, punteggi, scost_breve_pct, scost_medio_pct, pendenza_lungo_pct "
        "FROM public.gas_segnale WHERE commodity = 'gas' ORDER BY data")
    df = pd.DataFrame(rows, columns=["Data", "Punteggi", "ScB", "ScM", "PendL"])
    if not df.empty:
        df["Data"] = pd.to_datetime(df["Data"])
    return df


try:
    df = _serie(cfg["tabella"], cfg["metrica"])
    df_p = _punteggi()
except db.DBConfigError as e:
    st.warning(f"⚙️ {e}")
    st.stop()
except Exception as e:
    st.error(f"📡 Impossibile leggere la serie: {e}")
    st.stop()

if df.empty:
    st.info("Nessun dato disponibile per questa variabile.")
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
sc_txt = None
if not df_p.empty:
    r_ult = df_p.iloc[-1]
    pj = r_ult["Punteggi"] or {}
    p_ult = pj.get(cfg["chiave"])
    if cfg["chiave"] == "prezzo":
        def _pc(v):
            return "n.d." if v is None or pd.isna(v) else f"{'+' if float(v) >= 0 else '−'}{abs(float(v)):.1f}%"
        sc_txt = f"breve {_pc(r_ult['ScB'])} · medio {_pc(r_ult['ScM'])}"

def _fmt(v: float, dec: int = 1) -> str:
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")

col_d1 = "#C00000" if d1 > 0 else "#008000" if d1 < 0 else "#64748b"
fr1 = "▲" if d1 > 0 else "▼" if d1 < 0 else "="
sub_rif = ("n.d." if delta_rif is None else
           f"{'+' if delta_rif >= 0 else ''}{_fmt(delta_rif)} {cfg['udm']} vs riferimento")

dec = 2 if cfg["udm"] == "€/MWh" else 1
val_txt = _fmt(val, dec)
rif_txt = "n.d." if pd.isna(rif) else _fmt(float(rif), dec)
delta_txt = ("n.d." if delta_rif is None else
             f"{'+' if delta_rif >= 0 else '−'}{_fmt(abs(delta_rif), dec)} {cfg['udm']} rispetto al riferimento")
def _sc(v):
    return "n.d." if v is None or pd.isna(v) else f"{'+' if float(v) >= 0 else '−'}{_fmt(abs(float(v)), 1)} %"
cards = (
    branding.gm_tile("Valore attuale", val_txt, cfg["udm"],
                     f"{branding.gm_delta(d1, dec, cfg['udm'])} vs giorno precedente · {ult['Data'].strftime('%d/%m/%Y')}",
                     accent=BLU)
    + branding.gm_tile(label_rif, rif_txt, cfg["udm"] if not pd.isna(rif) else "",
                       delta_txt, accent=TEAL)
    + (branding.gm_tile_mini("Scostamento dai trend",
                             [("vs breve 20 gg", _sc(r_ult["ScB"]) if not df_p.empty else "n.d."),
                              ("vs medio 60 gg", _sc(r_ult["ScM"]) if not df_p.empty else "n.d.")],
                             f"trend lungo 180 gg: {('in salita' if float(r_ult['PendL']) > 0.05 else 'in discesa' if float(r_ult['PendL']) < -0.05 else 'piatto') if not df_p.empty and pd.notna(r_ult['PendL']) else 'n.d.'}",
                             accent=BLU)
       if cfg["chiave"] == "prezzo" else
       branding.gm_tile("Punteggio nello scenario",
                        "n.d." if p_ult is None else f"{float(p_ult):.0f}", "/100" if p_ult is not None else "",
                        cfg["direzione"], accent=BLU, score=p_ult, score_label="alto = favorevole"))
    + branding.gm_tile_mini("Nel periodo selezionato",
                            [("minimo", f"{_fmt(dfp['Valore'].min(), dec)}<small>{cfg['udm']}</small>"),
                             ("massimo", f"{_fmt(dfp['Valore'].max(), dec)}<small>{cfg['udm']}</small>")],
                            f"media {_fmt(dfp['Valore'].mean(), dec)} {cfg['udm']}", accent=BLU)
)
st.markdown(f"<div class='gm-grid'>{cards}</div>", unsafe_allow_html=True)

# =============================================================================
# Grafico: serie + riferimento in overlay
# =============================================================================
base = alt.Chart(dfp).encode(x=alt.X("Data:T", title=""))
linea = base.mark_line(color=C_SERIE, strokeWidth=2).encode(
    y=alt.Y("Valore:Q", title=cfg["udm"], scale=alt.Scale(zero=False)),
    tooltip=[alt.Tooltip("Data:T", format="%d/%m/%Y"),
             alt.Tooltip("Valore:Q", format=".2f", title=cfg["udm"])],
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
# Punteggio nel tempo (percentile che entra nell'indice)
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
FONTI = {"prezzo": "GME — MGP-GAS", "stoccaggi": "GIE AGSI+", "meteo": "Open-Meteo (ERA5)",
         "lng": "GIE ALSI", "geopolitica": "GPR — Caldara & Iacoviello"}
st.caption(f"🗂 Fonte: {FONTI[cfg['chiave']]}")

st.divider()
st.caption("ℹ️ Informazioni a scopo informativo e di supporto all'approvvigionamento; "
           "non costituiscono consulenza finanziaria. La decisione resta dell'utente.")
