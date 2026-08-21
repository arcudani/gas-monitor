"""
Autenticazione Energy Market Monitor — streamlit-authenticator + bcrypt.

⚠️ DIVERSAMENTE da ERP e web app Offerte, le credenziali NON stanno in
public.utenti ma nella tabella DEDICATA public.gas_utenti (decisione
requisiti 18/08/2026): gli utenti cliente del Gas Monitor non devono poter
accedere alle altre due app, e quelle app caricano public.utenti senza
filtro di ruolo. La separazione è quindi per costruzione.

Ruoli (colonna gas_utenti.ruolo): 'admin' (consulente Bros, vede tutto,
configura pesi e utenti) | 'cliente' (dashboard, dettagli, propri alert).

Il cookie di sessione ha nome e chiave propri (bros_gas_auth).
Le password si impostano con imposta_pwd.py in questo repo.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st
import streamlit_authenticator as stauth

import config
import db

COOKIE_NAME = "bros_gas_auth"
COOKIE_EXPIRY_DAYS = 7


def _cookie_key() -> str:
    key = config.auth_cookie_key()
    if not key:
        # Fallback solo sviluppo locale: sessione non persistente, NON sicura.
        return "dev-only-cookie-key-cambiami"
    return key


@st.cache_data(ttl=300, show_spinner=False)
def load_credentials() -> dict:
    """Dict credenziali per streamlit-authenticator da gas_utenti.
    Solo utenti attivi con password impostata. Cache 5 min."""
    rows = db.query(
        "SELECT username, password_hash, ruolo "
        "FROM public.gas_utenti WHERE attivo = true AND password_hash IS NOT NULL"
    )
    usernames = {}
    for username, pwd_hash, ruolo in rows:
        usernames[username] = {
            "name": username,
            "password": pwd_hash,            # già hashato (bcrypt)
            "email": "",
            "roles": [ruolo],
        }
    return {"usernames": usernames}


def get_authenticator() -> Optional[stauth.Authenticate]:
    creds = load_credentials()
    if not creds["usernames"]:
        return None
    return stauth.Authenticate(
        creds,
        COOKIE_NAME,
        _cookie_key(),
        COOKIE_EXPIRY_DAYS,
        auto_hash=False,   # gli hash sono già in DB
    )


def require_login() -> str:
    """Mostra il login e blocca l'app (st.stop) finché non autenticato.
    Ritorna lo username canonico autenticato."""
    try:
        authenticator = get_authenticator()
    except Exception as e:
        if "gas_utenti" in str(e):
            st.error(
                "⚠️ Tabella `gas_utenti` non trovata: applicare la migrazione "
                "`app/migrations/g001_utenti_aziende.sql` sul DB Supabase."
            )
            st.stop()
        raise
    if authenticator is None:
        st.error(
            "⚠️ Nessun utente con password impostata. "
            "Creare il primo admin con: python imposta_pwd.py <Nome> --ruolo admin"
        )
        st.stop()

    if not st.session_state.get("authentication_status"):
        authenticator.login(location="main")

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("❌ Username o password errati.")
        st.stop()
    if status is None:
        st.info("🔐 Inserisci le credenziali per accedere.")
        st.stop()

    # Nome canonico dal DB (streamlit-authenticator abbassa a minuscolo).
    raw = (st.session_state.get("name") or st.session_state.get("username") or "").strip()
    utente = _canonical_username(raw) or raw
    with st.sidebar:
        st.caption(f"👤 Utente: **{st.session_state.get('name', utente)}**")
        authenticator.logout("Esci", location="sidebar")
    return utente


@st.cache_data(ttl=300, show_spinner=False)
def _canonical_username(name: str) -> Optional[str]:
    name = (name or "").strip()
    if not name:
        return None
    rows = db.query(
        "SELECT username FROM public.gas_utenti "
        "WHERE lower(username) = lower(%s) LIMIT 1",
        (name,),
    )
    return rows[0][0] if rows else None


@st.cache_data(ttl=300, show_spinner=False)
def is_admin(username: str) -> bool:
    """True se l'utente ha ruolo 'admin' (consulente Bros)."""
    if not username:
        return False
    rows = db.query(
        "SELECT ruolo = 'admin' FROM public.gas_utenti "
        "WHERE lower(username) = lower(%s) LIMIT 1",
        (username,),
    )
    return bool(rows and rows[0][0])
