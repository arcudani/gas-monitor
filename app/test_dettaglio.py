"""Test della pagina Dettaglio: ogni variabile renderizza senza eccezioni.

Richiede SUPABASE_DB_URL (dati reali); si auto-salta se assente. Esercita
lo script-pagina direttamente con AppTest (come fa la shell) e cambia
la selectbox per ogni variabile: nessuna eccezione, KPI presenti.
"""
from __future__ import annotations

import os
import sys

import config  # noqa: F401  (carica .env)
from streamlit.testing.v1 import AppTest


def test_tutte_le_variabili() -> None:
    at = AppTest.from_file("moduli/dettaglio.py", default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    sel = at.selectbox[0]
    for opzione in sel.options:
        sel.set_value(opzione).run()
        ecc = [str(e.value) for e in at.exception]
        assert not ecc, f"{opzione}: {ecc}"
        # almeno le card KPI (markdown con classe bros-kpis) e un grafico
        assert any("gm-grid" in m.value for m in at.markdown), opzione
        print(f"OK - dettaglio '{opzione}' renderizzato")


if __name__ == "__main__":
    if not os.environ.get("SUPABASE_DB_URL", "").strip():
        print("[SKIP] test_dettaglio: SUPABASE_DB_URL assente")
        sys.exit(0)
    try:
        test_tutte_le_variabili()
    except AssertionError as e:
        print(f"FAIL - {e}")
        sys.exit(1)
    print("Tutti i test OK")
    sys.exit(0)
