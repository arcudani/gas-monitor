"""
Modulo Forward e obiettivi — pagina SEPARATA dalla Dashboard (decisione utente
26/10/2026: "due informazioni distinte, unirle confonde").

Risponde a due domande diverse da quella dell'indicatore:
  - Mercato a termine: a quanto si potrebbe fissare OGGI ciascun periodo futuro
    (curva forward GME, prezzi di controllo: MT-GAS per il gas, MTE baseload per l'EE);
  - Obiettivo di prezzo: quel prezzo va bene PER IL CLIENTE? (obiettivo per
    trimestre impostato da Bros in Admin, confronto aritmetico, storia reale).
Nessuna previsione. Il segnale di fixing resta calcolato solo su scenario e
prezzo spot, nella Dashboard. Legge SOLO dati pre-calcolati (gas_forward,
gas_obiettivi, gas_segnale per il prezzo attuale).
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import branding
import commodity
import db

COM = commodity.corrente()
INFO = commodity.info(COM)
PZ_LBL, PZ_UDM = INFO["prezzo_label"], INFO["prezzo_udm"]
BLU, BLU_SCURO, C_PREZZO = "#0F6FA8", "#0B4F78", "#C00000"
MESI_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
           "agosto", "settembre", "ottobre", "novembre", "dicembre"]
MESI_BREVI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]

st.title(f"📈 {commodity.titolo(COM)} — Forward e obiettivi")
st.caption("La **Dashboard** dice se il momento è propizio; qui il **forward** dice a quanto si potrebbe fissare "
           "e l'**obiettivo** se va bene per il cliente. Nessuna previsione.")


def _it(v, dec=1) -> str:
    return f"{float(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# =============================================================================
# Dati (cache 10 min)
# =============================================================================

@st.cache_data(ttl=600, show_spinner="📡 Leggo la curva forward…")
def _carica(com: str) -> dict:
    # prezzo attuale: ultimi 40 giorni del prezzo di riferimento (gas = giorno; EE = media del mese in corso)
    pz = db.query("SELECT data, prezzo FROM public.gas_segnale WHERE commodity = %s ORDER BY data DESC LIMIT 40", (com,))
    # Esclusi i prodotti il cui prezzo di controllo non e' MAI cambiato dalla quotazione
    # (>= 5 sedute): e' un segnaposto GME, non un prezzo (Q-2027-01 gas a 29,855 fisso per settimane).
    fwd = db.query("SELECT f.seduta, f.prodotto, f.tipo, f.consegna_dal, f.consegna_al, f.prezzo "
                   "FROM public.gas_forward f JOIN ("
                   "  SELECT prodotto, count(*) AS n, count(DISTINCT prezzo) AS nd FROM public.gas_forward "
                   "  WHERE commodity = %s GROUP BY prodotto) s ON s.prodotto = f.prodotto "
                   "WHERE f.commodity = %s AND f.seduta = (SELECT max(seduta) FROM public.gas_forward WHERE commodity = %s) "
                   "  AND NOT (s.nd = 1 AND s.n >= 5) "
                   "ORDER BY f.consegna_dal, f.tipo", (com, com, com))
    return {"pz": [(pd.Timestamp(d), float(p)) for d, p in pz if p is not None],
            "fwd": [dict(zip(("seduta", "prodotto", "tipo", "dal", "al", "prezzo"), r)) for r in fwd]}


try:
    dati = _carica(COM)
except db.DBConfigError as e:
    st.warning(f"⚙️ {e}")
    st.stop()
except Exception as e:
    st.error(f"📡 Impossibile leggere i dati: {e}")
    if st.button("🔄 Riprova"):
        _carica.clear()
        st.rerun()
    st.stop()

if not dati["pz"]:
    st.info("⏳ Prezzo di riferimento non ancora calcolato: verificare la pipeline `gas-monitor`.")
    st.stop()
data_pz, pz = dati["pz"][0]
vetrina = INFO.get("prezzo_vetrina") or "giorno"
if vetrina == "mese":
    mese = [p for d, p in dati["pz"] if d.year == data_pz.year and d.month == data_pz.month]
    spot = sum(mese) / len(mese)
    spot_lbl = f"media {PZ_LBL} di {MESI_IT[data_pz.month - 1]}"
else:
    spot = pz
    spot_lbl = f"prezzo {PZ_LBL} del {data_pz.strftime('%d/%m')}"

# =============================================================================
# 1. MERCATO A TERMINE (curva forward GME)
# =============================================================================
st.markdown("<div class='gm-section'><div style='font-size:1.7rem;font-weight:800;color:#C00000;letter-spacing:-.02em;line-height:1.1'>Mercato a termine</div>"
            "<span>quanto costa bloccare oggi i periodi futuri</span></div>", unsafe_allow_html=True)
fwd = dati["fwd"]
if not fwd:
    st.info("⏳ Curva forward non ancora caricata.")
else:
    seduta = pd.Timestamp(fwd[0]["seduta"])
    # curva MENSILE dei 12 mesi successivi: prodotto mensile se quotato, altrimenti
    # trimestre, stagione (gas) o anno che lo contiene. A fine mese il mese
    # successivo e' solo BoM (escluso): si parte dal primo coperto, 12 punti comunque.
    PRIORITA = {"M": 0, "Q": 1, "SS": 2, "WS": 2, "CY": 3}
    curva = []
    for k in range(1, 15):
        m0 = (seduta.to_period("M") + k).to_timestamp()
        cand = sorted((r for r in fwd if pd.Timestamp(r["dal"]) <= m0 <= pd.Timestamp(r["al"])),
                      key=lambda r: PRIORITA.get(r["tipo"], 9))
        if cand:
            curva.append({"Mese": m0, "Etichetta": f"{MESI_BREVI[m0.month - 1]} {m0.year % 100:02d}",
                          "Prezzo": float(cand[0]["prezzo"]), "Prodotto": cand[0]["prodotto"]})
        if len(curva) == 12:
            break

    def _media_curva(n: int):
        v = [c["Prezzo"] for c in curva[:n]]
        return sum(v) / n if len(v) == n else None

    def _vs_spot(v) -> str:
        if v is None or not spot:
            return ""
        d = 100 * (v / spot - 1)
        return (f"<span style='display:block;font-size:.74rem;color:#64748b;margin-top:2px'>"
                f"{'+' if d >= 0 else '−'}{_it(abs(d), 1)} % vs oggi</span>")

    f12 = _media_curva(12)
    celle = [(c["Etichetta"], c["Prezzo"]) for c in curva[:3]]
    celle += [("media 3 mesi", _media_curva(3)), ("media 6 mesi", _media_curva(6))]
    cy = next((r for r in fwd if r["tipo"] == "CY" and pd.Timestamp(r["dal"]).year == seduta.year + 1), None)
    if cy:
        celle.append((f"anno {seduta.year + 1}", float(cy["prezzo"])))
    if f12 is not None and spot:
        d12 = 100 * (f12 / spot - 1)
        verso = ("sopra" if d12 > 1 else "sotto" if d12 < -1 else "in linea con")
        tag_fw = (f"<b>{'+' if d12 >= 0 else '−'}{_it(abs(d12), 1)} %</b> rispetto al prezzo di oggi "
                  f"<b>{_it(spot, 2)}</b> · prossimi 12 mesi <b>{verso}</b> il prezzo attuale")
    else:
        tag_fw = "curva incompleta"
    st.markdown(
        "<div class='gm-label'>Curva forward · informativa, non entra nel segnale</div>"
        "<div class='gm-panel'>"
        "<div class='gm-panel-top'>"
        + (f"<div class='gm-value' style='color:{BLU}'>{_it(f12, 2)}<small>{PZ_UDM} · media dei prossimi 12 mesi</small></div>"
           if f12 is not None else "<div class='gm-value' style='color:#94a3b8'>n.d.</div>")
        + f"<div class='gm-tag'>{tag_fw}</div></div>"
        f"<div class='gm-sub'>Curva GME ({'MT-GAS' if COM == 'gas' else 'MTE'}) del <b>{seduta.strftime('%d/%m/%Y')}</b>, "
        f"€/MWh · prezzo di oggi = {spot_lbl}</div>"
        f"<div class='gm-mini gm-mini-ink' style='grid-template-columns:repeat({len(celle)}, minmax(0,1fr))'>"
        + "".join(f"<div>{lbl}<b>{_it(v, 2) if v is not None else 'n.d.'}</b>{_vs_spot(v)}</div>" for lbl, v in celle)
        + "</div></div>",
        unsafe_allow_html=True,
    )
    if curva:
        dfc = pd.DataFrame(curva)
        base = alt.Chart(dfc).encode(
            x=alt.X("Etichetta:N", sort=list(dfc["Etichetta"]), title=None, axis=alt.Axis(labelAngle=0)))
        barre = base.mark_bar(color=BLU, size=26, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            y=alt.Y("Prezzo:Q", title="€/MWh", scale=alt.Scale(zero=False, padding=12)),
            tooltip=[alt.Tooltip("Etichetta:N", title="Mese"),
                     alt.Tooltip("Prezzo:Q", title="Forward €/MWh", format=",.2f"),
                     alt.Tooltip("Prodotto:N", title="Prodotto GME")])
        # valori sopra le barre (formato italiano calcolato qui: il format di Altair e' anglosassone)
        dfc["Testo"] = dfc["Prezzo"].map(lambda v: _it(v, 2))
        valori = base.mark_text(dy=-8, fontSize=12, fontWeight=600, color="#0f172a").encode(
            y=alt.Y("Prezzo:Q"), text="Testo:N")
        branding.altair_it((barre + valori).properties(height=200))
    if (data_pz - seduta).days > 7:
        st.caption(f"⚠️ Curva forward non aggiornata: ultima seduta disponibile {seduta.strftime('%d/%m/%Y')}.")
    st.caption("ℹ️ Il forward **non è una previsione**: è il prezzo a cui il mercato scambia oggi i periodi futuri "
               "(prezzi di controllo GME, indicativi).")

# =============================================================================
# 2. OBIETTIVO DI PREZZO del cliente (g015)
# =============================================================================
st.markdown("<div class='gm-section'><div style='font-size:1.7rem;font-weight:800;color:#C00000;letter-spacing:-.02em;line-height:1.1'>Obiettivo di prezzo</div>"
            "<span>il forward di ciascun trimestre va bene per il cliente?</span></div>", unsafe_allow_html=True)


def _nome_periodo(prod: str) -> str:
    if prod.startswith("Q-"):
        y, q = prod[2:].split("-")
        return f"{int(q)}° trimestre {y}"
    if prod.startswith("CY-"):
        return f"anno {prod[3:]}"
    return prod


@st.cache_data(ttl=600, show_spinner=False)
def _contesto_obiettivi(com: str, utente: str) -> dict:
    riga = db.query("SELECT azienda_id, ruolo FROM public.gas_utenti WHERE username = %s", (utente,))
    az_id, ruolo = (riga[0] if riga else (None, None))
    aziende = db.query(
        "SELECT DISTINCT a.id, a.nome FROM public.gas_obiettivi o JOIN public.gas_aziende a ON a.id = o.azienda_id "
        "WHERE o.commodity = %s AND o.attivo ORDER BY a.nome", (com,))
    return {"azienda_id": az_id, "ruolo": ruolo, "aziende": [(int(i), n) for i, n in aziende]}


@st.cache_data(ttl=600, show_spinner=False)
def _obiettivi_azienda(com: str, az_id: int) -> tuple[list[dict], pd.DataFrame]:
    ob = db.query(
        "SELECT o.prodotto, o.prezzo, o.note, f.prezzo, f.seduta, f.consegna_dal, f.consegna_al "
        "FROM public.gas_obiettivi o LEFT JOIN LATERAL ("
        "  SELECT prezzo, seduta, consegna_dal, consegna_al FROM public.gas_forward g "
        "  WHERE g.commodity = o.commodity AND g.prodotto = o.prodotto ORDER BY seduta DESC LIMIT 1) f ON true "
        "WHERE o.azienda_id = %s AND o.commodity = %s AND o.attivo ORDER BY o.prodotto", (az_id, com))
    ob = [dict(zip(("prodotto", "obiettivo", "note", "forward", "seduta", "dal", "al"), r)) for r in ob]
    prodotti = [o["prodotto"] for o in ob]
    st_ = db.query(
        "SELECT prodotto, seduta, prezzo FROM public.gas_forward WHERE commodity = %s AND prodotto = ANY(%s) "
        "AND seduta >= current_date - 365 ORDER BY prodotto, seduta", (com, prodotti)) if prodotti else []
    storia = pd.DataFrame(st_, columns=["Prodotto", "Seduta", "Forward"])
    if not storia.empty:
        storia["Seduta"] = pd.to_datetime(storia["Seduta"])
        storia["Forward"] = pd.to_numeric(storia["Forward"], errors="coerce")
        # coda iniziale piatta (segnaposto GME dopo il listing, >= 5 sedute identiche) scartata
        tenuti = []
        for prod, g in storia.groupby("Prodotto", sort=False):
            g = g.sort_values("Seduta")
            cambi = g["Forward"].ne(g["Forward"].iloc[0]).to_numpy().nonzero()[0]
            primo = int(cambi[0]) if len(cambi) else len(g)
            tenuti.append(g.iloc[primo:] if primo >= 5 else g)
        storia = pd.concat(tenuti) if tenuti else storia
    return ob, storia


_utente = st.session_state.get("utente_autenticato", "")
ctx_ob = _contesto_obiettivi(COM, _utente) if _utente else {"azienda_id": None, "ruolo": None, "aziende": []}
az_sel = ctx_ob["azienda_id"]
nome_az = next((n for i, n in ctx_ob["aziende"] if i == az_sel), None)
if az_sel is None and ctx_ob["ruolo"] == "admin" and ctx_ob["aziende"]:
    # il consulente Bros vede gli obiettivi per conto del cliente scelto
    nomi = {i: n for i, n in ctx_ob["aziende"]}
    az_sel = st.selectbox("Cliente", list(nomi), format_func=lambda i: nomi[i], key="gm_obiettivi_azienda")
    nome_az = nomi[az_sel]
if az_sel is None:
    st.info("Nessun obiettivo di prezzo associato a questo utente. Gli obiettivi li imposta Bros in Admin → Obiettivi di prezzo.")
else:
    obiettivi, storia_ob = _obiettivi_azienda(COM, int(az_sel))
    if not obiettivi:
        st.info(f"Nessun obiettivo per {nome_az or 'questo cliente'} sull'{INFO['nome'].lower()}.")
    else:
        st.markdown(f"<div class='gm-label'>Obiettivi · {nome_az or ''} · {INFO['nome'].lower()}</div>",
                    unsafe_allow_html=True)
        cols = st.columns(len(obiettivi))
        for col, o in zip(cols, obiettivi):
            with col:
                nome = _nome_periodo(o["prodotto"])
                obj = float(o["obiettivo"])
                if o["forward"] is None:
                    st.markdown(branding.gm_tile(nome, "n.d.", "", f"obiettivo <b>{_it(obj, 2)}</b> {PZ_UDM} · forward non quotato"),
                                unsafe_allow_html=True)
                    continue
                fw_ = float(o["forward"])
                delta = 100 * (fw_ / obj - 1)
                ok = fw_ <= obj
                h = storia_ob[storia_ob["Prodotto"] == o["prodotto"]]
                if len(h):
                    # quante sedute e da quando: un prodotto quotato da pochi giorni non deve
                    # sembrare "il 83% degli ultimi 12 mesi" (visto sul 4° trim. 2027, 6 sedute)
                    i_min = int(h["Forward"].idxmin())
                    storia_txt = (f"minimo <b>{_it(h.loc[i_min, 'Forward'], 2)}</b> il "
                                  f"{h.loc[i_min, 'Seduta'].strftime('%d/%m/%Y')}")
                else:
                    storia_txt = "nessuno storico"
                verdetto = ("<b style='color:#0B4F78'>raggiungibile</b>" if ok
                            else f"<b style='color:#64748b'>sopra del {_it(delta, 1)} %</b>")
                st.markdown(branding.gm_tile(
                    nome, _it(fw_, 2), PZ_UDM,
                    f"obiettivo <b>{_it(obj, 2)}</b> · {verdetto}<br>{storia_txt}", accent=BLU_SCURO if ok else "#94a3b8"),
                    unsafe_allow_html=True)
                if len(h):
                    # Asse X = DATA DI QUOTAZIONE (quando il mercato ha prezzato quel trimestre),
                    # non il periodo di consegna: va detto, altrimenti "mar-ott" si legge come il periodo.
                    # "dal gg/mm/aaaa" = prima quotazione effettiva (la coda provvisoria GME e' esclusa):
                    # senza, un prodotto quotato da 2 giorni sembra un grafico rotto
                    st.markdown(f"<div class='gm-sub' style='margin:10px 0 2px'>Andamento della quotazione · <b>{nome}</b> · "
                                f"dal {h['Seduta'].min().strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True)
                    linea = alt.Chart(h).mark_line(color=BLU, strokeWidth=2).encode(
                        x=alt.X("Seduta:T", title="data di quotazione"),
                        y=alt.Y("Forward:Q", title=None, scale=alt.Scale(zero=False)),
                        tooltip=[alt.Tooltip("Seduta:T", title="Data", format="%d/%m/%Y"),
                                 alt.Tooltip("Forward:Q", title=f"Forward {nome} ({PZ_UDM})", format=",.2f")])
                    regola = alt.Chart(pd.DataFrame({"y": [obj]})).mark_rule(color=C_PREZZO, strokeDash=[6, 4]).encode(y="y:Q")
                    branding.altair_it((linea + regola).properties(height=150))
        st.caption("ℹ️ Linea blu: la quotazione del trimestre negli ultimi 12 mesi; tratteggio rosso: l'obiettivo. "
                   "Fissare all'obiettivo **garantisce l'obiettivo, non il minimo**. Obiettivi impostati da Bros (Admin).")
