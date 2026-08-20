"""
Modulo Dashboard — Scenario + Prezzo + Segnale di fixing (requisiti v1.6-1.8).

Layout (design 19/08/2026, componenti gm-* in branding.py):
  1. due pannelli affiancati — SCENARIO (0-100, alto = favorevole
     all'acquirente) | PREZZO MGP-GAS (in chiaro, tre trend)
  2. SEGNALE del giorno a tutta larghezza: livello, testo, giorni, tacche
  3. quattro stat tile delle variabili con barra punteggio 0-100
  4. storico: prezzo + tre rette + bande dei giorni favorevoli; scenario + soglia
Etichette fuori dai box, numeri grandi, testo in inchiostro neutro, colore
solo sul dato (scala blu = intensita', nessun semaforo).
Legge SOLO dati pre-calcolati (gas_segnale; cache 10').
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import branding
import db

st.title("📊 Gas Market Monitor")
st.caption("Finestre favorevoli per il fixing del gas: scenario di "
           "approvvigionamento, prezzo rispetto ai trend, segnale giornaliero.")

BLU, BLU_CHIARO, BLU_SCURO, INK = "#0F6FA8", "#7FB3D5", "#0B4F78", "#0f172a"
# Trend: tre FORME e tre colori distinti (CVD validati 19/08): breve grigio ardesia
# punteggiato, medio VERDE ACQUA tratteggiato (scelto dall'utente; e' il riferimento
# per il fixing e deve saltare all'occhio), lungo blu scuro pieno sottile.
C_BREVE, C_MEDIO, C_LUNGO = "#64748b", "#14B8A6", "#0B4F78"
C_PREZZO = "#C00000"   # rosso Bros (scelta utente): la serie principale porta il brand
LIVELLI = {   # codice -> (nome, intensita' 0-5)
    "attesa": ("Attesa", 0), "chiusa": ("Finestra chiusa", 0),
    "monitorare": ("Monitorare", 1),
    "opportunita": ("Opportunità di prezzo", 2), "prime": ("Prime condizioni", 2),
    "minimo": ("Minimo di periodo", 3), "iniziale": ("Segnale iniziale", 3),
    "fixing": ("Segnale di fixing", 4), "trend": ("Trend consolidato", 5),
}
COL_LIV = ["#94a3b8", "#7FB3D5", "#5A9FCB", "#3D8BBF", "#1E6FA3", "#0B4F78"]


# =============================================================================
# Dati (cache 10 min)
# =============================================================================

@st.cache_data(ttl=600, show_spinner="📡 Leggo segnale e serie…")
def _carica() -> dict:
    seg = db.query(
        "SELECT data, scenario, scenario_medio, punteggi, prezzo, trend_breve, trend_medio, "
        "       trend_lungo, scost_breve_pct, scost_medio_pct, pendenza_lungo_pct, "
        "       pct_finestra1, pct_finestra2, prezzo_favorevole, favorevole, "
        "       giorni_consecutivi, codice, testo "
        "FROM public.gas_segnale WHERE commodity = 'gas' ORDER BY data")
    cfg = db.query("SELECT pesi FROM public.gas_pesi ORDER BY versione DESC LIMIT 1")
    var = db.query(
        "SELECT metrica, valore FROM public.gas_serie s "
        "WHERE commodity='gas' AND metrica IN ('riempimento_pct','t_media_paniere','lng_sendout','gpr') "
        "  AND data = (SELECT max(data) FROM public.gas_serie t WHERE t.metrica = s.metrica)")
    df = pd.DataFrame(seg, columns=[
        "Data", "Scenario", "ScenarioM", "Punteggi", "Prezzo", "TBreve", "TMedio", "TLungo",
        "ScB", "ScM", "PendL", "Pct1", "Pct2", "PzOk", "Fav", "N", "Codice", "Testo"])
    if not df.empty:
        df["Data"] = pd.to_datetime(df["Data"])
        for c in ("Scenario", "ScenarioM", "Prezzo", "TBreve", "TMedio", "TLungo",
                  "ScB", "ScM", "PendL", "Pct1", "Pct2"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    fresh = db.query("SELECT serie, ultimo, giorni_fa FROM public.gas_freschezza() ORDER BY serie")
    run = db.query("SELECT started_at, status, left(coalesce(error,''),300) FROM public.task_runs "
                   "WHERE task_id='gas-monitor' ORDER BY started_at DESC LIMIT 1")
    return {"seg": df, "cfg": (cfg[0][0] if cfg else {}) or {},
            "var": {m: float(v) for m, v in var}, "fresh": fresh, "run": run[0] if run else None}


try:
    dati = _carica()
except db.DBConfigError as e:
    st.warning(f"⚙️ {e}")
    st.stop()
except Exception as e:
    st.error(f"📡 Impossibile leggere i dati: {e}")
    if st.button("🔄 Riprova"):
        _carica.clear()
        st.rerun()
    st.stop()

df, cfg, var = dati["seg"], dati["cfg"], dati["var"]

# ---- Stato dei dati: banner se qualche serie e' stantia o l'ultimo run e' fallito ----
TOLL = {"prezzo MGP_GAS": 2, "segnale": 2}          # le altre fonti pubblicano con 1-2 gg di ritardo: 3
stantie = [f"{se} (ultimo {ul.strftime('%d/%m') if hasattr(ul, 'strftime') else ul}, {g} gg fa)"
           for se, ul, g in dati["fresh"] if g is not None and int(g) > TOLL.get(se, 3)]
run = dati["run"]
run_ko = run is not None and run[1] != "success"
if stantie or run_ko:
    msg = []
    if stantie:
        msg.append("**Dati non aggiornati**: " + "; ".join(stantie) + ".")
    if run_ko:
        msg.append(f"**Ultimo aggiornamento fallito** ({pd.Timestamp(run[0]).tz_convert('Europe/Rome').strftime('%d/%m %H:%M')}): {run[2]}")
    st.warning(" ".join(msg) + " La pipeline riprova automaticamente; il dettaglio è in Admin → Stato pipeline.",
               icon="⚠️")

if df.empty:
    st.info("⏳ Segnale non ancora calcolato: verificare la pipeline `gas-monitor`.")
    st.stop()

soglia = float(cfg.get("scenario_soglia", 60))
gg_b, gg_m, gg_l = (int(cfg.get("trend_breve_gg", 20)), int(cfg.get("trend_medio_gg", 60)),
                    int(cfg.get("trend_lungo_gg", 180)))
mf1, mf2 = int(cfg.get("minimo_finestra1_mesi", 6)), int(cfg.get("minimo_finestra2_mesi", 18))


def _it(v, dec=1) -> str:
    return f"{float(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v) -> str:
    if v is None or pd.isna(v):
        return "n.d."
    return f"{'+' if v >= 0 else '−'}{_it(abs(float(v)), 1)} %"


ult = df.iloc[-1]
prec = df.iloc[-2] if len(df) > 1 else ult
p = ult["Punteggi"] or {}

# =============================================================================
# 1. Pannelli SCENARIO | PREZZO
# =============================================================================
sc = float(ult["Scenario"])
scm = float(ult["ScenarioM"]) if pd.notna(ult["ScenarioM"]) else sc
col_sc = BLU_SCURO if scm >= soglia else (BLU if scm >= 40 else BLU_CHIARO)
fascia = "favorevole" if scm >= soglia else "neutro" if scm >= 40 else "sfavorevole"
pz = float(ult["Prezzo"])
d_pz = pz - float(prec["Prezzo"]) if pd.notna(prec["Prezzo"]) else 0.0
pz_ok = bool(ult["PzOk"])
pend = float(ult["PendL"]) if pd.notna(ult["PendL"]) else None
dir_l = "n.d." if pend is None else ("in salita" if pend > 0.05 else "in discesa" if pend < -0.05 else "piatto")
# percentile 6 mesi: "piu' alto del X% dei prezzi"; sotto il 5% = tra i piu' bassi (minimo di periodo)
_p1 = None if pd.isna(ult["Pct1"]) else float(ult["Pct1"])
pct1_txt = "n.d." if _p1 is None else (f"{_p1:.0f} %")
pct1_lbl = (f"più alto del … degli ultimi {mf1} mesi" if _p1 is None else
            f"più alto del {_p1:.0f}% dei prezzi degli ultimi {mf1} mesi")

st.markdown(f"<div class='gm-section'><div style='font-size:1.7rem;font-weight:800;color:#C00000;letter-spacing:-.02em;line-height:1.1'>Oggi</div><span>dati aggiornati al "
            f"{ult['Data'].strftime('%d/%m/%Y')}</span></div>", unsafe_allow_html=True)
st.markdown(
    "<div class='gm-grid gm-2'>"
    # --- scenario ---
    "<div><div class='gm-label'>Scenario di approvvigionamento</div>"
    f"<div class='gm-panel'>"
    "<div class='gm-panel-top'>"
    f"<div class='gm-value' style='color:{BLU}'>{sc:.0f}<small>/100 oggi</small></div>"
    f"<div class='gm-tag'>media {int(cfg.get('scenario_media_gg', 7))} gg <b>{scm:.0f}</b> · <b style='color:{col_sc}'>{fascia}</b></div>"
    "</div>"
    f"<div class='gm-sub'>{branding.gm_delta(sc - float(prec['Scenario']), 1)} vs ieri · "
    f"favorevole da {soglia:.0f} (sulla media)</div>"
    "<div class='gm-mini'>"
    + "".join(
        f"<div>{lbl}<b>{(p.get(k) if p.get(k) is not None else 50):.0f}</b>"
        f"<div class='gm-bar' style='--bar-color:{BLU}'><span style='width:{max(0, min(100, (p.get(k) if p.get(k) is not None else 50))):.0f}%'></span></div></div>"
        for k, lbl in (("stoccaggi", "🛢 Stoccaggi"), ("meteo", "🌡 Meteo"),
                       ("lng", "🚢 LNG"), ("geopolitica", "🌍 Geopolitica")))
    + "</div></div></div>"
    # --- prezzo ---
    "<div><div class='gm-label'>Prezzo gas MGP-GAS</div>"
    f"<div class='gm-panel'>"
    "<div class='gm-panel-top'>"
    f"<div class='gm-value' style='color:{BLU}'>{_it(pz, 2)}<small>€/MWh</small></div>"
    f"<div class='gm-tag'>vs trend · <b style='color:{BLU_SCURO if pz_ok else '#64748b'}'>{'in flessione' if pz_ok else 'non in flessione'}</b></div>"
    "</div>"
    f"<div class='gm-sub'>{branding.gm_delta(d_pz, 2, '€/MWh')} vs ieri · dato del {ult['Data'].strftime('%d/%m/%Y')}</div>"
    "<div class='gm-mini gm-mini-ink'>"
    f"<div>vs breve {gg_b} gg<b>{_pct(ult['ScB'])}</b></div>"
    f"<div>vs medio {gg_m} gg<b>{_pct(ult['ScM'])}</b></div>"
    f"<div>lungo {gg_l} gg<b>{dir_l}</b></div>"
    f"<div title='{pct1_lbl}'>percentile {mf1} mesi<b>{pct1_txt}</b></div>"
    "</div></div></div>"
    "</div>",
    unsafe_allow_html=True,
)

# =============================================================================
# 2. SEGNALE
# =============================================================================
nome_liv, liv = LIVELLI.get(ult["Codice"], (ult["Codice"], 0))
col_liv = COL_LIV[liv]
n = int(ult["N"])
giorni_txt = (f"{n} giorn{'o' if n == 1 else 'i'} consecutiv{'o' if n == 1 else 'i'} favorevol{'e' if n == 1 else 'i'}"
              if n else "nessun conteggio in corso")
# perche' (una riga): stato dello scenario e del prezzo
_mg = int(cfg.get("scenario_media_gg", 7))
why = ("<ul class='gm-sig-list'>"
       f"<li><b>Scenario</b> {sc:.0f} oggi, media {_mg} gg {scm:.0f} → {fascia} (favorevole da {soglia:.0f})</li>"
       f"<li><b>Prezzo</b> {'in flessione' if pz_ok else 'non in flessione'}: {_pct(ult['ScB'])} sul trend breve, "
       f"{_pct(ult['ScM'])} sul medio</li></ul>")
# Cosa fare: NON il nome del livello ripetuto, ma l'azione e cosa cambierebbe lo stato
_soglia_int = int(soglia)
AZIONI = {
    "attesa": ("Nessuna tranche consigliata.",
               ("Mancano entrambe le condizioni:<ul class='gm-sig-list'>"
                f"<li><b>scenario</b> (media {_mg} gg) almeno {_soglia_int} — oggi {scm:.0f}</li>"
                f"<li><b>prezzo</b> sotto i trend — oggi {_pct(ult['ScB'])} sul breve</li></ul>"
                if not pz_ok else
                "Il prezzo è già in flessione. Manca:<ul class='gm-sig-list'>"
                f"<li><b>scenario</b> (media {_mg} gg) almeno {_soglia_int} — oggi {scm:.0f}</li></ul>")),
    "chiusa": ("Finestra appena chiusa: nessuna nuova tranche.",
               "Il prezzo ha recuperato il trend o lo scenario è peggiorato."),
    "monitorare": ("Scenario pronto, prezzo non ancora.",
                   "Tenere d'occhio: basta una flessione del prezzo sui trend per aprire la finestra."),
    "opportunita": ("Possibile tranche tattica.",
                    "Prezzo in netta flessione sul trend medio con scenario non sfavorevole; "
                    "finestra non confermata dai fondamentali."),
    "minimo": ("Valutare una tranche.", f"Prezzo tra i più bassi degli ultimi {mf1} o {mf2} mesi."),
    "prime": ("Prime condizioni: attendere conferma.", "Scenario favorevole e prezzo in flessione da 1–2 giorni."),
    "iniziale": ("Valutare una prima tranche.", f"Condizioni favorevoli da {n} giorni consecutivi."),
    "fixing": ("Finestra utile per coperture.", f"Scenario favorevole e prezzo sotto trend da {n} giorni."),
    "trend": ("Finestra ampia: coperture più consistenti.", f"Trend favorevole consolidato da {n} giorni."),
}
do_txt, do_sub = AZIONI.get(ult["Codice"], (str(ult["Testo"]), ""))

# Termometro: 6 gradini, lo ZERO e' un gradino vero ("Nessun segnale"), sempre etichettato
GRADINI = ["Nessun segnale", "Osservare", "Occasione", "Primo segnale", "Fixing", "Finestra ampia"]
st.markdown(
    f"<div class='gm-signal' style='--sig-color:{col_liv}'>"
    "<div class='gm-label'>Segnale di oggi</div>"
    "<div class='gm-sig-grid'>"
    # 1. verdetto
    "<div class='gm-sig-col'><div class='gm-sig-head'><span class='gm-sig-ico'>🎯</span>Verdetto</div>"
    f"<div class='gm-signal-name'>{nome_liv}</div>{why}</div>"
    # 2. cosa fare
    "<div class='gm-sig-col'><div class='gm-sig-head'><span class='gm-sig-ico'>🧭</span>Cosa fare</div>"
    f"<div class='gm-sig-do'>{do_txt}<small>{do_sub}</small></div></div>"
    # 3. termometro
    "<div class='gm-sig-col'><div class='gm-sig-head'><span class='gm-sig-ico'>📶</span>Forza del segnale</div>"
    "<div class='gm-thermo'>"
    + "".join(
        f"<div class='{'on' if i <= liv else ''} {'cur' if i == liv else ''}'><i></i><span>{nome}</span></div>"
        for i, nome in enumerate(GRADINI))
    + "</div></div>"
    "</div></div>",
    unsafe_allow_html=True,
)

# =============================================================================
# 3. Stat tile delle variabili
# =============================================================================
st.markdown("<div class='gm-label' style='margin-top:18px'>Le quattro variabili dello scenario</div>",
            unsafe_allow_html=True)
tiles = ""
for k, lbl, metrica, fmt, unit, cosa in (
    ("stoccaggi", "🛢 Stoccaggi Italia", "riempimento_pct", 1, "%", "riempimento vs media 5 anni"),
    ("meteo", "🌡 Temperatura paniere", "t_media_paniere", 1, "°C", "vs norma dello stesso giorno"),
    ("lng", "🚢 LNG send-out", "lng_sendout", 0, "GWh/g", "vs media 5 anni"),
    ("geopolitica", "🌍 Rischio geopolitico", "gpr", 0, "", "indice GPR (basso = favorevole)"),
):
    v = var.get(metrica)
    tiles += branding.gm_tile(
        lbl, "n.d." if v is None else _it(v, fmt), unit, cosa,
        accent=BLU, score=p.get(k), score_label="punteggio (alto = favorevole)")
st.markdown(f"<div class='gm-grid'>{tiles}</div>", unsafe_allow_html=True)

# =============================================================================
# 4. Storico
# =============================================================================
st.markdown("<div class='gm-section'><div style='font-size:1.7rem;font-weight:800;color:#C00000;letter-spacing:-.02em;line-height:1.1'>Storico</div><span>andamento nel tempo</span></div>",
            unsafe_allow_html=True)
periodo = st.radio("Periodo", ["Mese", "3 mesi", "Da inizio anno", "12 mesi", "3 anni", "Tutto"],
                   index=1, horizontal=True, label_visibility="collapsed")
fine = df["Data"].max()
inizio = {"Mese": fine - pd.Timedelta(days=31), "3 mesi": fine - pd.Timedelta(days=92),
          "Da inizio anno": pd.Timestamp(year=fine.year, month=1, day=1),
          "12 mesi": fine - pd.Timedelta(days=366), "3 anni": fine - pd.DateOffset(years=3),
          }.get(periodo, df["Data"].min())
dfp = df[df["Data"] >= inizio].copy()

# bande: giorni favorevoli + opportunita' + minimo, livello = intensita' massima del run
dfp["Acceso"] = dfp["Fav"].fillna(False) | dfp["Codice"].isin(["opportunita", "minimo"])
dfp["Liv"] = dfp["Codice"].map(lambda c: LIVELLI.get(c, ("", 0))[1])
dfp["grp"] = (~dfp["Acceso"]).cumsum()
fin = (dfp[dfp["Acceso"]].groupby("grp")
       .agg(da=("Data", "min"), a=("Data", "max"), liv=("Liv", "max")).reset_index(drop=True))
fin["a"] = fin["a"] + pd.Timedelta(days=1)

st.markdown("**Prezzo MGP-GAS e trend**")
st.markdown(branding.gm_legend([
    ("solid", C_PREZZO, "prezzo"), ("dot", C_BREVE, f"trend breve {gg_b} gg"),
    ("dash", C_MEDIO, f"trend medio {gg_m} gg"), ("solid", C_LUNGO, f"trend lungo {gg_l} gg"),
    ("band", "#5A9FCB", "giorni con segnale (più scuro = più forte)"),
]), unsafe_allow_html=True)
strati = []
if not fin.empty:
    strati.append(alt.Chart(fin).mark_rect().encode(
        x="da:T", x2="a:T",
        color=alt.Color("liv:O", scale=alt.Scale(domain=[1, 2, 3, 4, 5], range=COL_LIV[1:]), legend=None),
        opacity=alt.value(0.32)))
base = alt.Chart(dfp).encode(x=alt.X("Data:T", title=""))
strati.append(alt.layer(
    base.mark_line(color=C_PREZZO, strokeWidth=2.2).encode(
        y=alt.Y("Prezzo:Q", title="€/MWh", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("Data:T", format="%d/%m/%Y"),
                 alt.Tooltip("Prezzo:Q", format=".2f", title="Prezzo €/MWh"),
                 alt.Tooltip("ScB:Q", format="+.1f", title="vs breve %"),
                 alt.Tooltip("ScM:Q", format="+.1f", title="vs medio %"),
                 alt.Tooltip("Codice:N", title="Segnale")]),
    base.mark_line(color=C_BREVE, strokeWidth=1.6, strokeDash=[2, 3]).encode(y="TBreve:Q"),
    base.mark_line(color=C_MEDIO, strokeWidth=1.8, strokeDash=[7, 4]).encode(y="TMedio:Q"),
    base.mark_line(color=C_LUNGO, strokeWidth=1.3).encode(y="TLungo:Q"),
))
branding.altair_it(alt.layer(*strati), width="stretch")

st.markdown("**Scenario di approvvigionamento**")
st.markdown(branding.gm_legend([
    ("solid", BLU, "scenario giornaliero"), ("dash", BLU_SCURO, f"soglia favorevole {soglia:.0f}")]),
    unsafe_allow_html=True)
ch_sc = alt.layer(
    alt.Chart(dfp).mark_area(color=BLU, opacity=0.16, line={"color": BLU, "strokeWidth": 1.6}).encode(
        x=alt.X("Data:T", title=""),
        y=alt.Y("Scenario:Q", scale=alt.Scale(domain=[0, 100]), title="0–100"),
        tooltip=[alt.Tooltip("Data:T", format="%d/%m/%Y"), alt.Tooltip("Scenario:Q", format=".0f"),
                 alt.Tooltip("ScenarioM:Q", format=".0f", title="media mobile")]),
    alt.Chart(pd.DataFrame({"y": [soglia]})).mark_rule(color=BLU_SCURO, strokeDash=[5, 4]).encode(y="y:Q"),
)
branding.altair_it(ch_sc, width="stretch")
st.caption("🗂 Fonti: GME MGP-GAS · GIE AGSI+/ALSI · Open-Meteo ERA5 · GPR Caldara-Iacoviello. "
           "Punteggi = rango percentile 2020–oggi orientato a favore dell'acquirente.")

st.divider()
st.caption("ℹ️ Le informazioni hanno scopo informativo e di supporto all'approvvigionamento; "
           "non costituiscono consulenza finanziaria. La decisione resta dell'utente.")
