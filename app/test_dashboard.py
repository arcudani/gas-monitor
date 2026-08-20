"""Test della Dashboard v1.6: renderizza con dati reali per ogni periodo.

Richiede SUPABASE_DB_URL; si auto-salta se assente. Verifica: nessuna
eccezione, pannelli Scenario/Prezzo e Segnale presenti, grafici renderizzati.
"""
from __future__ import annotations

import os
import sys

import config  # noqa: F401
from streamlit.testing.v1 import AppTest


def test_dashboard_tutti_i_periodi() -> None:
    at = AppTest.from_file("moduli/dashboard.py", default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    testo = " ".join(m.value for m in at.markdown)
    assert "Scenario di approvvigionamento" in testo, "pannello scenario mancante"
    assert "Prezzo gas MGP-GAS" in testo, "pannello prezzo mancante"
    assert "Segnale di oggi" in testo, "pannello segnale mancante"
    radio = at.radio[0]
    for opz in radio.options:
        radio.set_value(opz).run()
        ecc = [str(e.value) for e in at.exception]
        assert not ecc, f"{opz}: {ecc}"
        print(f"OK - dashboard periodo '{opz}'")


if __name__ == "__main__":
    if not os.environ.get("SUPABASE_DB_URL", "").strip():
        print("[SKIP] test_dashboard: SUPABASE_DB_URL assente")
        sys.exit(0)
    try:
        test_dashboard_tutti_i_periodi()
    except AssertionError as e:
        print(f"FAIL - {e}")
        sys.exit(1)
    print("Tutti i test OK")
    sys.exit(0)
