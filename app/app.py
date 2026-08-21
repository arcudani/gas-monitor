"""
Bros Consulenza — Gas Market Monitor — shell modulare.

Avvio locale (da dentro app\\):  python -m streamlit run app.py

La shell fa, una volta sola e nell'ordine: bridge dei segreti,
set_page_config, CSS/logo Bros, registrazione pagine (st.navigation), gate di
login, run della pagina corrente. I moduli sono script-pagina in moduli\\ e
NON devono chiamare set_page_config / login / CSS.

⚠️ La danza navigation/login è load-bearing (copiata da Bros_ERP, dove è
documentata): st.navigation va chiamata SEMPRE, SUBITO e UNA SOLA volta per
run, così un URL profondo sopravvive al giro di login; dopo l'autenticazione
in-run un singolo st.rerun() ricostruisce la sidebar visibile.
"""
from __future__ import annotations

import streamlit as st

import config
config.bridge_streamlit_secrets()  # st.secrets -> os.environ (PRIMA di db/auth)
import auth
import branding
import registro_moduli

st.set_page_config(
    page_title="Bros Consulenza — Gas Market Monitor",
    page_icon="🔥",
    layout="wide",
)

branding.apply_base()
branding.enable_altair_theme()

_gia_autenticato = bool(st.session_state.get("authentication_status"))
if _gia_autenticato:
    _ut_nav = st.session_state.get("utente_autenticato", "")
    if not _ut_nav:
        # Riautenticazione da cookie in una sessione nuova (es. dopo un
        # riavvio del server): authentication_status e' gia' True ma
        # utente_autenticato non e' ancora stato scritto dal gate di login.
        # Senza questo, is_admin("") = False e la voce Admin sparisce
        # (visto il 19/08/2026). Lo username grezzo lo mette
        # streamlit-authenticator in session_state["name"/"username"].
        _raw = (st.session_state.get("name") or st.session_state.get("username") or "").strip()
        _ut_nav = auth._canonical_username(_raw) or _raw
    pg = st.navigation(
        registro_moduli.build_navigation(_ut_nav, auth.is_admin(_ut_nav))
    )
else:
    pg = st.navigation(
        registro_moduli.build_navigation("", False), position="hidden"
    )
    branding.render_login_hero()

# Gate di login: blocca qui (st.stop) finché non autenticato.
utente_autenticato = auth.require_login()
st.session_state["utente_autenticato"] = utente_autenticato

if not _gia_autenticato:
    st.rerun()

# Selettore commodity (Gas | Energia elettrica) in sidebar, sopra le pagine:
# scrive st.session_state["commodity"], letto da tutti i moduli (g008).
import commodity  # noqa: E402  (dopo il bridge dei segreti)
with st.sidebar:
    commodity.selettore()

branding.render_header()
pg.run()
