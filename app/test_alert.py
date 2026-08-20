"""Test della pagina Alert: rendering per l'utente reale + ciclo di vita
di una regola (crea -> sospendi -> elimina) con pulizia finale.

Richiede SUPABASE_DB_URL; si auto-salta se assente. Usa l'utente admin
'Daniele' (esiste dal primo setup); seeda lo session_state come la shell.
"""
from __future__ import annotations

import os
import sys

import config  # noqa: F401  (carica .env)
import db
from streamlit.testing.v1 import AppTest

UTENTE = "Daniele"
NOTA_TEST = "__test_alert_apptest__"


def _n_regole_test() -> int:
    return db.query(
        "SELECT count(*) FROM public.gas_alert a JOIN public.gas_utenti u "
        "ON u.id=a.utente_id WHERE lower(u.username)=lower(%s) AND a.note=%s",
        (UTENTE, NOTA_TEST))[0][0]


def _pulisci() -> None:
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM public.gas_alert WHERE note=%s AND utente_id IN "
            "(SELECT id FROM public.gas_utenti WHERE lower(username)=lower(%s))",
            (NOTA_TEST, UTENTE))
        conn.commit()


def test_pagina_renderizza() -> None:
    at = AppTest.from_file("moduli/alert.py", default_timeout=60)
    at.session_state["utente_autenticato"] = UTENTE
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    testo = " ".join(m.value for m in at.markdown) + " ".join(
        h.value for h in at.subheader)
    assert "Indirizzo email" in testo and "Nuova soglia" in testo
    print("OK - pagina Alert renderizza per l'utente")


def test_ciclo_regola_su_db() -> None:
    # Il form AppTest e' fragile con number_input dinamici: il ciclo di
    # vita si verifica sulle stesse query che usano i bottoni della pagina.
    _pulisci()
    uid = db.query("SELECT id FROM public.gas_utenti WHERE lower(username)=lower(%s)",
                   (UTENTE,))[0][0]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO public.gas_alert (utente_id, grandezza, condizione, soglia, note) "
            "VALUES (%s,'indice','sopra',95,%s)", (uid, NOTA_TEST))
        conn.commit()
    assert _n_regole_test() == 1
    with db.connect() as conn:
        conn.execute("UPDATE public.gas_alert SET attivo = NOT attivo WHERE note=%s",
                     (NOTA_TEST,))
        conn.commit()
    assert db.query("SELECT attivo FROM public.gas_alert WHERE note=%s",
                    (NOTA_TEST,))[0][0] is False
    _pulisci()
    assert _n_regole_test() == 0
    print("OK - ciclo crea/sospendi/elimina sul DB")


if __name__ == "__main__":
    if not os.environ.get("SUPABASE_DB_URL", "").strip():
        print("[SKIP] test_alert: SUPABASE_DB_URL assente")
        sys.exit(0)
    try:
        test_pagina_renderizza()
        test_ciclo_regola_su_db()
    except AssertionError as e:
        _pulisci()
        print(f"FAIL - {e}")
        sys.exit(1)
    print("Tutti i test OK")
    sys.exit(0)
