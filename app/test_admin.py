"""Test della tab Admin: la pagina parametri renderizza con le schede
descrittive e i valori correnti; il salvataggio NON viene esercitato qui
(creerebbe versioni reali) — si verifica solo che il form esista con tutti
i parametri documentati.

Richiede SUPABASE_DB_URL; si auto-salta se assente.
"""
from __future__ import annotations

import os
import sys

import config  # noqa: F401
import db
from streamlit.testing.v1 import AppTest


def test_admin_parametri() -> None:
    n_doc = db.query("SELECT count(*) FROM public.gas_parametri_doc")[0][0]
    at = AppTest.from_file("moduli/admin.py", default_timeout=60)
    at.session_state["utente_autenticato"] = "Daniele"
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    # un number_input per ogni parametro documentato
    n_inputs = len([w for w in at.number_input if str(w.key or "").startswith("par_")])
    assert n_inputs == n_doc, f"attesi {n_doc} parametri, trovati {n_inputs}"
    testo = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "Versione corrente" in testo
    assert "Peso stoccaggi" in testo and "Trend breve" in testo
    print(f"OK - tab Admin: {n_inputs} parametri con scheda descrittiva")


if __name__ == "__main__":
    if not os.environ.get("SUPABASE_DB_URL", "").strip():
        print("[SKIP] test_admin: SUPABASE_DB_URL assente")
        sys.exit(0)
    try:
        test_admin_parametri()
    except AssertionError as e:
        print(f"FAIL - {e}")
        sys.exit(1)
    print("Tutti i test OK")
    sys.exit(0)
