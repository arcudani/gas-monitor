"""Smoke test della shell (headless, streamlit.testing.v1.AppTest).

Come negli altri repo Bros: script semplice con runner __main__, exit 0/1,
stampa righe "OK - ...". Va seminato session_state (authentication_status +
utente) o la shell cicla sul login. Senza SUPABASE_DB_URL i controlli che
toccano il DB si limitano a verificare la degradazione senza eccezioni.
"""
from __future__ import annotations

import sys

from streamlit.testing.v1 import AppTest


def test_shell_carica_senza_eccezioni() -> None:
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["authentication_status"] = True
    at.session_state["name"] = "TestAdmin"
    at.session_state["username"] = "testadmin"
    at.session_state["utente_autenticato"] = "TestAdmin"
    at.run()
    # La dashboard degrada con warning/errore informativo se il DB manca,
    # ma la shell NON deve sollevare eccezioni non gestite.
    eccezioni = [str(e.value) for e in at.exception]
    assert not eccezioni, f"Eccezioni in app: {eccezioni}"
    print("OK - shell senza eccezioni")


def test_admin_visibile_dopo_riautenticazione_cookie() -> None:
    """Sessione nuova con cookie valido: authentication_status True ma
    utente_autenticato ASSENTE. La nav deve comunque includere Admin per un
    admin reale (bug 19/08/2026). Richiede DB: si salta senza."""
    import os
    if not os.environ.get("SUPABASE_DB_URL", "").strip():
        print("[SKIP] admin dopo cookie: SUPABASE_DB_URL assente")
        return
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["authentication_status"] = True
    at.session_state["name"] = "daniele"        # minuscolo, come fa streamlit-authenticator
    at.session_state["username"] = "daniele"
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    # st.session_state["utente_autenticato"] viene scritto dal gate: canonico
    assert at.session_state["utente_autenticato"] == "Daniele"
    print("OK - riautenticazione da cookie: utente canonico risolto (Admin in nav)")


def test_guida_renderizza() -> None:
    at = AppTest.from_file("moduli/guida.py", default_timeout=30)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(at.tabs) >= 5
    print("OK - guida: 5 tab renderizzate")


def test_import_moduli_puri() -> None:
    import config          # noqa: F401
    import registro_moduli
    assert any(m.default for m in registro_moduli.MODULI)
    assert any(m.solo_admin for m in registro_moduli.MODULI)
    url = registro_moduli.url_di(registro_moduli.MODULI[0])
    assert url == "/"
    print("OK - registro moduli coerente")


if __name__ == "__main__":
    try:
        test_import_moduli_puri()
        test_guida_renderizza()
        test_shell_carica_senza_eccezioni()
        test_admin_visibile_dopo_riautenticazione_cookie()
    except AssertionError as e:
        print(f"FAIL - {e}")
        sys.exit(1)
    print("Tutti i test OK")
    sys.exit(0)
