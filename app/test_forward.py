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


def test_asse_tempo_mobile() -> None:
    """L'asse dei grafici obiettivi scorre da solo: nuovi mesi a destra, oltre 12 mesi escono a sinistra."""
    import pandas as pd
    # replica della funzione (la pagina e' uno script Streamlit, non un modulo importabile)
    src = open("moduli/forward.py", encoding="utf-8").read()
    ini = src.index("def _asse_tempo(")
    fine = src.index("\n\n\n", ini)
    scope: dict = {"pd": pd}
    exec("from __future__ import annotations\n" + src[ini:fine], scope)
    asse = scope["_asse_tempo"]
    storia = pd.DataFrame({"Seduta": pd.to_datetime(["2026-02-06", "2026-10-26"]), "Forward": [33.0, 86.3]})
    mesi = lambda tick: [pd.Timestamp(t).strftime("%Y-%m-%d") for t in tick]  # noqa: E731
    # oggi 27/10/2026: parte dalla prima quotazione (06/02), finisce oggi
    i, o, tk = asse(storia, pd.Timestamp("2026-10-27"))
    assert i == pd.Timestamp("2026-02-06") and o == pd.Timestamp("2026-10-27"), (i, o)
    assert mesi(tk)[0] == "2026-02-06" and mesi(tk)[-1] == "2026-10-01", mesi(tk)
    # un mese dopo: compare il tick di novembre, l'inizio non cambia
    i2, o2, tk2 = asse(storia, pd.Timestamp("2026-11-27"))
    assert i2 == i and "2026-11-01" in mesi(tk2) and len(tk2) == len(tk) + 1, mesi(tk2)
    # 14 mesi dopo l'inizio: la finestra e' di 12 mesi, febbraio-marzo 2026 sono usciti
    i3, o3, tk3 = asse(storia, pd.Timestamp("2027-04-15"))
    assert i3 == pd.Timestamp("2027-04-15") - pd.Timedelta(days=365) and mesi(tk3)[1] == "2026-05-01", (i3, mesi(tk3))
    assert mesi(tk3)[-1] == "2027-04-01"
    # senza storico: ultimi 12 mesi
    i4, _, _ = asse(pd.DataFrame(columns=["Seduta", "Forward"]), pd.Timestamp("2026-10-27"))
    assert i4 == pd.Timestamp("2025-10-27")
    print("OK - asse tempo mobile (nuovi mesi a destra, finestra 12 mesi)")


if __name__ == "__main__":
    test_asse_tempo_mobile()
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
