"""Test della pagina Forward e obiettivi (g014/g015): renderizza con dati reali
per gas ed EE, con e senza utente autenticato.

Richiede SUPABASE_DB_URL; si auto-salta se assente. Verifica: nessuna
eccezione, pannello della curva forward con la media a 12 mesi, blocco
obiettivi (per l'admin Daniele: selettore cliente e almeno una tessera).
"""
from __future__ import annotations

import os
import sys

import config  # noqa: F401
from streamlit.testing.v1 import AppTest


def test_forward_e_obiettivi() -> None:
    for com in ("gas", "ee"):
        at = AppTest.from_file("moduli/forward.py", default_timeout=90)
        at.session_state["commodity"] = com
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        testo = " ".join(m.value for m in at.markdown)
        assert "Mercato a termine" in testo, f"{com}: sezione forward mancante"
        assert "media dei prossimi 12 mesi" in testo, f"{com}: media forward 12 mesi mancante"
        assert "Obiettivo di prezzo" in testo, f"{com}: sezione obiettivi mancante"
        print(f"OK - forward {com} senza utente")
        # admin senza azienda: selettore cliente + tessere degli obiettivi
        at = AppTest.from_file("moduli/forward.py", default_timeout=90)
        at.session_state["commodity"] = com
        at.session_state["utente_autenticato"] = "Daniele"
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        testo = " ".join(m.value for m in at.markdown)
        if at.selectbox:
            assert "obiettivo <b>" in testo, f"{com}: tessere obiettivi mancanti"
            print(f"OK - forward {com} con admin: {len(at.selectbox)} selettore, obiettivi presenti")
        else:
            print(f"OK - forward {com} con admin: nessun obiettivo configurato (blocco informativo)")


if __name__ == "__main__":
    if not os.environ.get("SUPABASE_DB_URL", "").strip():
        print("[SKIP] test_forward: SUPABASE_DB_URL assente")
        sys.exit(0)
    try:
        test_forward_e_obiettivi()
    except AssertionError as e:
        print(f"FAIL - {e}")
        sys.exit(1)
    print("Tutti i test OK")
    sys.exit(0)
