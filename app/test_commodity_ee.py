"""Test multi-commodity (g008): i moduli renderizzano anche con commodity='ee'
(energia elettrica, prezzo PUN) e gli helper di commodity.py sono coerenti.

Richiede SUPABASE_DB_URL; si auto-salta se assente. Verifica: nessuna
eccezione in Dashboard/Dettaglio/Export/Admin con st.session_state["commodity"]
= "ee", etichette PUN presenti, anagrafica con 2 commodity e 5 variabili EE.
"""
from __future__ import annotations

import os
import sys

import config  # noqa: F401
from streamlit.testing.v1 import AppTest


def test_anagrafica() -> None:
    import commodity
    codici = [c["commodity"] for c in commodity.lista()]
    assert codici == ["gas", "ee"], codici
    ee = commodity.info("ee")
    assert ee["prezzo_codice"] == "PUN_INDEX_GME" and ee["prezzo_aggregazione"] == "media_ore"
    v_ee = commodity.variabili("ee")
    assert [v["variabile"] for v in v_ee] == ["produzione", "meteo", "gas", "rinnovabili", "geopolitica"]
    v_gas = commodity.variabili("gas")
    assert [v["variabile"] for v in v_gas] == ["stoccaggi", "meteo", "lng", "geopolitica"]
    # il meteo EE legge la stessa serie del gas ma con trasformazione abs_delta
    met = next(v for v in v_ee if v["variabile"] == "meteo")
    assert met["commodity_dati"] == "gas" and met["trasformazione"] == "abs_delta"
    assert commodity.titolo("gas") == "Gas Market Monitor"
    print("OK - anagrafica commodity (2 commodity, 4 + 5 variabili)")


def _run(modulo: str, com: str, utente: str | None = None) -> AppTest:
    at = AppTest.from_file(f"moduli/{modulo}.py", default_timeout=90)
    at.session_state["commodity"] = com
    if utente:
        at.session_state["utente_autenticato"] = utente
    at.run()
    assert not at.exception, f"{modulo}[{com}]: " + "; ".join(str(e.value) for e in at.exception)
    return at


def test_dashboard_ee() -> None:
    at = _run("dashboard", "ee")
    testo = " ".join(m.value for m in at.markdown)
    assert "Prezzo energia elettrica PUN" in testo, "pannello prezzo PUN mancante"
    assert "Le cinque variabili dello scenario" in testo, "tile variabili EE mancanti"
    assert "Segnale di oggi" in testo
    print("OK - dashboard EE (PUN, 5 variabili)")


def test_dashboard_gas_invariata() -> None:
    at = _run("dashboard", "gas")
    testo = " ".join(m.value for m in at.markdown)
    assert "Prezzo gas MGP-GAS" in testo and "Le quattro variabili dello scenario" in testo
    print("OK - dashboard gas invariata (MGP-GAS, 4 variabili)")


def test_dettaglio_ee() -> None:
    at = _run("dettaglio", "ee")
    opzioni = at.selectbox[0].options
    assert any("PUN" in o for o in opzioni) and any("Prezzo gas" in o for o in opzioni), opzioni
    # variabile con sorgente 'indice' (prezzo gas dentro lo scenario EE)
    at.selectbox[0].set_value(next(o for o in opzioni if "Prezzo gas" in o)).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    # variabile senza ancora dati (produzione, in attesa del token ENTSO-E): messaggio, non errore
    at.selectbox[0].set_value(next(o for o in opzioni if "Produzione" in o)).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    print(f"OK - dettaglio EE ({len(opzioni)} variabili, indice e serie vuota gestiti)")


def test_export_ee() -> None:
    at = _run("export", "ee")
    assert len(at.get("download_button")) >= 2
    print("OK - export EE (PDF + Excel generati)")


def test_admin_ee() -> None:
    at = _run("admin", "ee", utente="test")
    testo = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "Peso produzione zonale" in testo, "schede parametri EE mancanti"
    print("OK - admin EE (parametri e freschezza)")


if __name__ == "__main__":
    if not os.environ.get("SUPABASE_DB_URL", "").strip():
        print("[SKIP] test_commodity_ee: SUPABASE_DB_URL assente")
        sys.exit(0)
    try:
        test_anagrafica()
        test_dashboard_ee()
        test_dashboard_gas_invariata()
        test_dettaglio_ee()
        test_export_ee()
        test_admin_ee()
    except AssertionError as e:
        print(f"FAIL - {e}")
        sys.exit(1)
    print("Tutti i test OK")
    sys.exit(0)
