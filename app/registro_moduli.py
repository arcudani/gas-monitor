"""
Registro dei moduli Gas Market Monitor — aggiungere un modulo = 1 file in
moduli\\ + 1 riga qui (stesso pattern del registro Bros ERP).

Ogni modulo è uno script-pagina Streamlit (file-based st.Page): codice
top-level, NIENTE st.set_page_config / login / CSS (li fa la shell app.py).
L'utente autenticato si legge da st.session_state["utente_autenticato"].
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import streamlit as st


@dataclass(frozen=True)
class Modulo:
    file: str                 # percorso dello script-pagina, relativo ad app/
    titolo: str
    icona: str                # emoji (o :material/...:)
    descrizione: str = ""
    url_path: Optional[str] = None   # segmento URL (None = dal nome file)
    sezione: str = "Moduli"   # gruppo nella sidebar ("" = fuori dai gruppi)
    default: bool = False     # pagina di atterraggio
    attivo: bool = True       # False = segnaposto "in arrivo"
    colore: str = "#0F6FA8"   # accento (blu gas — deciso 18/08/2026)
    solo_admin: bool = False
    visibile: Optional[Callable[[str, bool], bool]] = None  # (utente, is_admin) -> bool


MODULI: list[Modulo] = [
    Modulo("moduli/dashboard.py", "Dashboard", "📊",
           descrizione="Scenario, prezzo e segnale di fixing",
           sezione="", default=True),
    Modulo("moduli/dettaglio.py", "Dettaglio", "🔎",
           descrizione="Storico e confronti di ciascuna variabile",
           url_path="dettaglio"),
    Modulo("moduli/alert.py", "Alert", "🔔",
           descrizione="Soglie email su segnale, scenario, prezzo e variabili",
           url_path="alert"),
    Modulo("moduli/export.py", "Export", "📤",
           descrizione="Snapshot PDF e serie storiche Excel",
           url_path="export"),
    Modulo("moduli/guida.py", "Guida", "📖",
           descrizione="Come leggere la dashboard e configurare alert e parametri",
           url_path="guida"),
    Modulo("moduli/admin.py", "Admin", "⚙️",
           descrizione="Parametri del segnale e stato pipeline",
           url_path="admin", solo_admin=True, colore="#404040"),
]


def url_di(m: Modulo) -> str:
    """URL interno della pagina del modulo."""
    if m.default:
        return "/"
    return "/" + (m.url_path or Path(m.file).stem)


def moduli_visibili(utente: str, is_admin: bool) -> list[Modulo]:
    out = []
    for m in MODULI:
        if m.solo_admin and not is_admin:
            continue
        if m.visibile is not None and not m.visibile(utente, is_admin):
            continue
        out.append(m)
    return out


def build_navigation(utente: str, is_admin: bool) -> dict[str, list]:
    """Costruisce l'argomento di st.navigation: {sezione: [st.Page, ...]}."""
    sezioni: dict[str, list] = {}
    for m in moduli_visibili(utente, is_admin):
        kwargs = dict(title=m.titolo, icon=m.icona, default=m.default)
        if m.url_path:
            kwargs["url_path"] = m.url_path
        sezioni.setdefault(m.sezione, []).append(st.Page(m.file, **kwargs))
    return sezioni
