"""
Modulo Alert — soglie email per utente (RF-04), multi-commodity (g008).

Ogni utente vede e gestisce SOLO le proprie regole (filtro lato server
sullo username autenticato) della commodity selezionata. Le regole sono
valutate ogni mattina dalla pipeline dopo il ricalcolo; una sola email per
utente e commodity raggruppa tutte le soglie raggiunte, con anti-duplicato
per giorno e cooldown configurabile.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import commodity
import db

COM = commodity.corrente()
INFO = commodity.info(COM)
VARS = commodity.variabili(COM)

st.title(f"🔔 Alert — {INFO['nome']}")
st.caption("Ricevi un'email quando il segnale di fixing, lo scenario, il prezzo o una "
           "variabile raggiunge le soglie che imposti. Controllo ogni mattina, dopo "
           "l'aggiornamento dei dati; l'email riporta sempre la situazione del giorno.")

utente = st.session_state.get("utente_autenticato", "")
if not utente:
    st.warning("Utente non riconosciuto.")
    st.stop()

# Livelli del segnale (per la soglia 'segnale': "sopra" = almeno quel livello)
LIVELLI = {0: "attesa / finestra chiusa", 1: "monitorare",
           2: "opportunità di prezzo / prime condizioni",
           3: "minimo di periodo / segnale iniziale", 4: "segnale di fixing",
           5: "trend consolidato"}

# grandezza -> (etichetta, udm, min, max, passo) — dall'anagrafica della commodity
GRANDEZZE = {
    "segnale":  ("🎯 Livello del segnale di fixing", "", 0.0, 5.0, 1.0),
    "scenario": ("🧭 Scenario di approvvigionamento", "/100", 0.0, 100.0, 1.0),
    "prezzo":   (f"{INFO['icona']} Prezzo {INFO['prezzo_label']}", INFO["prezzo_udm"],
                 *commodity.range_soglia(INFO["prezzo_udm"])),
}
for v in VARS:
    GRANDEZZE[v["variabile"]] = (f"{v['icona']} {v['etichetta']}",
                                 "" if v["udm"] == "indice" else v["udm"],
                                 *commodity.range_soglia(v["udm"]))
if COM == "gas":   # grandezza storica, solo per le regole gia' esistenti
    GRANDEZZE["indice"] = ("📉 Indice di pressione (storico)", "/100", 0.0, 100.0, 1.0)
COND = {"sopra": "sale sopra", "sotto": "scende sotto"}
COND_SEGNALE = {"sopra": "raggiunge almeno", "sotto": "scende sotto"}


# =============================================================================
# Dati utente
# =============================================================================

def _utente_row():
    rows = db.query(
        "SELECT id, email FROM public.gas_utenti WHERE lower(username)=lower(%s)",
        (utente,))
    return rows[0] if rows else None


def _regole(uid: int) -> pd.DataFrame:
    rows = db.query(
        "SELECT a.id, a.grandezza, a.condizione, a.soglia, a.attivo, a.cooldown_gg, "
        "       a.note, "
        "       (SELECT max(i.inviato_at) FROM public.gas_alert_inviati i "
        "         WHERE i.alert_id = a.id) AS ultimo_invio "
        "FROM public.gas_alert a WHERE a.utente_id = %s AND a.commodity = %s ORDER BY a.id",
        (uid, COM))
    return pd.DataFrame(rows, columns=[
        "id", "grandezza", "condizione", "soglia", "attivo", "cooldown_gg",
        "note", "ultimo_invio"])


try:
    u = _utente_row()
except Exception as e:
    st.error(f"📡 Impossibile leggere i dati: {e}")
    st.stop()
if not u:
    st.warning("Utente non trovato in anagrafica.")
    st.stop()
uid, email_att = int(u[0]), (u[1] or "")

# =============================================================================
# Email di destinazione (unica per utente, vale per tutte le commodity)
# =============================================================================
st.subheader("Indirizzo email")
with st.form("form_email", border=False):
    c1, c2 = st.columns([3, 1])
    nuova = c1.text_input("Le notifiche arrivano a", value=email_att,
                          placeholder="nome@azienda.it",
                          label_visibility="collapsed")
    if c2.form_submit_button("Salva email", width="stretch"):
        nuova = nuova.strip()
        if nuova and ("@" not in nuova or "." not in nuova.split("@")[-1]):
            st.error("Indirizzo email non valido.")
        else:
            with db.connect() as conn:
                conn.execute(
                    "UPDATE public.gas_utenti SET email=%s, updated_at=now() WHERE id=%s",
                    (nuova, uid))
                conn.commit()
            st.success("Email aggiornata." if nuova else
                       "Email rimossa: non riceverai notifiche.")
            st.rerun()
if not email_att:
    st.info("ℹ️ Inserisci un indirizzo email per ricevere le notifiche.")

# =============================================================================
# Nuova regola
# =============================================================================
st.subheader(f"Nuova soglia · {INFO['nome'].lower()}")
_scelte = [k for k in GRANDEZZE if k != "indice"]
with st.form("form_nuova", clear_on_submit=True, border=False):
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1.2])
    g = c1.selectbox("Grandezza", _scelte, format_func=lambda k: GRANDEZZE[k][0])
    cond = c2.selectbox("Condizione", list(COND), format_func=lambda k: COND[k])
    _, udm, vmin, vmax, step = GRANDEZZE[g]
    if g == "segnale":
        soglia = float(c3.selectbox("Livello", list(LIVELLI), index=3,
                                    format_func=lambda k: f"{k} · {LIVELLI[k]}"))
    else:
        soglia = c3.number_input(f"Soglia {udm}".strip(), min_value=vmin,
                                 max_value=vmax, value=vmin, step=step)
    cooldown = c4.number_input("Pausa (gg)", min_value=1, max_value=60, value=7,
                               help="Giorni minimi tra due email della stessa soglia")
    st.caption("Per il **segnale** la condizione \"raggiunge almeno\" scatta quando il livello "
               "del giorno è pari o superiore a quello scelto (es. 3 = da *segnale iniziale* in su).")
    if st.form_submit_button("➕ Aggiungi", type="primary"):
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO public.gas_alert "
                "(utente_id, commodity, grandezza, condizione, soglia, cooldown_gg) "
                "VALUES (%s,%s,%s,%s,%s,%s)", (uid, COM, g, cond, soglia, cooldown))
            conn.commit()
        st.success("Soglia aggiunta.")
        st.rerun()

# =============================================================================
# Regole esistenti
# =============================================================================
st.subheader(f"Le tue soglie · {INFO['nome'].lower()}")
df = _regole(uid)
if df.empty:
    st.caption("Nessuna soglia impostata per questa commodity.")
    st.stop()

for _, r in df.iterrows():
    nome, udm, *_ = GRANDEZZE.get(r["grandezza"], (r["grandezza"], "", 0, 0, 1))
    if r["grandezza"] == "segnale":
        soglia_txt = f"\"{LIVELLI.get(int(float(r['soglia'])), r['soglia'])}\""
        cond_txt = COND_SEGNALE[r["condizione"]]
    else:
        soglia_txt = f"{float(r['soglia']):g}".replace(".", ",")
        cond_txt = COND[r["condizione"]]
    ult = ("mai" if pd.isna(r["ultimo_invio"]) else
           pd.Timestamp(r["ultimo_invio"]).tz_convert("Europe/Rome").strftime("%d/%m/%Y %H:%M"))
    stato = "🟢 attiva" if r["attivo"] else "⚪ sospesa"
    c1, c2, c3, c4 = st.columns([5, 2, 1.3, 1.3])
    c1.markdown(
        f"**{nome}** {cond_txt} **{soglia_txt} {udm}**  \n"
        f"<span style='color:#64748b;font-size:.85rem'>{stato} · pausa "
        f"{int(r['cooldown_gg'])} gg · ultimo invio: {ult}</span>",
        unsafe_allow_html=True)
    if c3.button("⏯", key=f"tog_{r['id']}", help="Attiva / sospendi",
                 width="stretch"):
        with db.connect() as conn:
            conn.execute(
                "UPDATE public.gas_alert SET attivo = NOT attivo, updated_at=now() "
                "WHERE id=%s AND utente_id=%s", (int(r["id"]), uid))
            conn.commit()
        st.rerun()
    if c4.button("🗑", key=f"del_{r['id']}", help="Elimina", width="stretch"):
        with db.connect() as conn:
            conn.execute("DELETE FROM public.gas_alert WHERE id=%s AND utente_id=%s",
                         (int(r["id"]), uid))
            conn.commit()
        st.rerun()

st.divider()
st.caption("Le soglie sono valutate sul dato del giorno precedente. Una sola email "
           "al giorno per commodity raggruppa tutte le soglie raggiunte; una soglia già "
           "notificata tace per il numero di giorni di pausa impostato.")
