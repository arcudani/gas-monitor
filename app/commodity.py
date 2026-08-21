"""
Commodity corrente (gas | ee) e anagrafica TABLE-DRIVEN (migrazione g008).

L'app è una sola: il selettore in sidebar (app.py) scrive
st.session_state["commodity"]; i moduli leggono `corrente()` e costruiscono
etichette, query e grandezze dalle tabelle gas_commodity / gas_variabili.
Senza selettore (AppTest sui singoli moduli, URL diretti) vale il default
'gas', quindi il comportamento storico è invariato.

Niente logica di business qui: solo lettura anagrafica + helper SQL puri.
"""
from __future__ import annotations

import streamlit as st

import db

DEFAULT = "gas"
NOME_PRODOTTO = "Energy Market Monitor"   # nome unico per gas ed energia elettrica (21/08/2026)
CHIAVE_STATO = "commodity"


# =============================================================================
# Anagrafica (cache 1 h: cambia solo con una migrazione)
# =============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def lista() -> list[dict]:
    rows = db.query(
        "SELECT commodity, nome, icona, prezzo_codice, prezzo_label, prezzo_udm, "
        "       prezzo_fonte, prezzo_aggregazione "
        "FROM public.gas_commodity WHERE attivo ORDER BY ordine, commodity")
    cols = ["commodity", "nome", "icona", "prezzo_codice", "prezzo_label", "prezzo_udm",
            "prezzo_fonte", "prezzo_aggregazione"]
    return [dict(zip(cols, r)) for r in rows]


def info(code: str | None = None) -> dict:
    code = code or corrente()
    for c in lista():
        if c["commodity"] == code:
            return c
    # fallback difensivo (anagrafica non ancora migrata): il gas storico
    return {"commodity": "gas", "nome": "Gas", "icona": "🔥", "prezzo_codice": "MGP_GAS",
            "prezzo_label": "MGP-GAS", "prezzo_udm": "€/MWh",
            "prezzo_fonte": "GME — MGP-GAS", "prezzo_aggregazione": "giorno"}


@st.cache_data(ttl=3600, show_spinner=False)
def variabili(code: str) -> list[dict]:
    rows = db.query(
        "SELECT variabile, etichetta, icona, udm, sorgente, commodity_dati, variabile_dati, "
        "       metrica_dati, codice_indice, riferimento, trasformazione, orientamento, "
        "       direzione, fonte, spiegazione, tolleranza_gg "
        "FROM public.gas_variabili WHERE commodity = %s ORDER BY ordine, variabile", (code,))
    cols = ["variabile", "etichetta", "icona", "udm", "sorgente", "commodity_dati", "variabile_dati",
            "metrica_dati", "codice_indice", "riferimento", "trasformazione", "orientamento",
            "direzione", "fonte", "spiegazione", "tolleranza_gg"]
    return [dict(zip(cols, r)) for r in rows]


def titolo(code: str | None = None) -> str:
    """Nome prodotto unico (deciso 21/08/2026) + commodity: 'Energy Market Monitor · Gas'."""
    return f"{NOME_PRODOTTO} · {info(code)['nome']}"


# =============================================================================
# Stato e selettore
# =============================================================================

def corrente() -> str:
    code = st.session_state.get(CHIAVE_STATO) or DEFAULT
    validi = {c["commodity"] for c in lista()} or {DEFAULT}
    return code if code in validi else DEFAULT


def selettore() -> str:
    """Segmented control Gas | Energia elettrica (in sidebar, da app.py).
    Con una sola commodity attiva non mostra nulla."""
    opzioni = lista()
    if len(opzioni) < 2:
        return corrente()
    nomi = {c["commodity"]: f"{c['icona']} {c['nome']}" for c in opzioni}
    if CHIAVE_STATO not in st.session_state:
        st.session_state[CHIAVE_STATO] = DEFAULT
    # key="gm_commodity": il CSS in branding.py porta questo container IN CIMA alla
    # sidebar, sopra il menu delle pagine (richiesta 21/08/2026).
    with st.container(key="gm_commodity"):
        st.markdown("<div class='gm-com-label'>Commodity</div>", unsafe_allow_html=True)
        st.segmented_control("Commodity", options=list(nomi), format_func=lambda k: nomi[k],
                             key=CHIAVE_STATO, label_visibility="collapsed")
    return corrente()


# =============================================================================
# Helper puri per i moduli
# =============================================================================

def confronto_breve(v: dict) -> str:
    """Riga di contesto sotto il valore nelle tile (Dashboard)."""
    if v["riferimento"] == "media5_doy":
        return "vs media 5 anni"
    if v["riferimento"] == "norma_doy":
        return ("distanza dalla norma dello stesso giorno" if v["trasformazione"] == "abs_delta"
                else "vs norma dello stesso giorno")
    return "valore assoluto (basso = favorevole)" if int(v["orientamento"]) < 0 else "valore assoluto"


def tipo_confronto(v: dict) -> str:
    """Mappa per la pagina Dettaglio: 'media5' | 'norma' | 'anno_prec'."""
    return {"media5_doy": "media5", "norma_doy": "norma"}.get(v["riferimento"], "anno_prec")


def sql_valori(v: dict) -> tuple[str, tuple]:
    """SELECT (data, valore) giornaliero della serie sorgente di una variabile."""
    if v["sorgente"] == "indice":
        return ("SELECT data, avg(valore) AS valore FROM public.indici_mercato "
                "WHERE codice = %s AND stato = 'consuntivo' GROUP BY data ORDER BY data",
                (v["codice_indice"],))
    return ("SELECT data, valore FROM public.gas_serie "
            "WHERE commodity = %s AND variabile = %s AND metrica = %s ORDER BY data",
            (v["commodity_dati"], v["variabile_dati"], v["metrica_dati"]))


def sql_prezzo(i: dict) -> tuple[str, tuple]:
    """SELECT (data, valore) del prezzo di riferimento (media delle ore se orario)."""
    return ("SELECT data, avg(valore) AS valore FROM public.indici_mercato "
            "WHERE codice = %s AND stato = 'consuntivo' GROUP BY data ORDER BY data",
            (i["prezzo_codice"],))


def sql_ultimi_valori(code: str) -> tuple[str, tuple]:
    """Ultimo valore disponibile di ogni variabile della commodity: (variabile, valore)."""
    return ("""
        SELECT v.variabile, coalesce(s.valore, i.valore) AS valore
        FROM public.gas_variabili v
        LEFT JOIN LATERAL (
            SELECT x.valore FROM public.gas_serie x
            WHERE v.sorgente = 'serie' AND x.commodity = v.commodity_dati
              AND x.variabile = v.variabile_dati AND x.metrica = v.metrica_dati
            ORDER BY x.data DESC LIMIT 1) s ON true
        LEFT JOIN LATERAL (
            SELECT avg(y.valore) AS valore FROM public.indici_mercato y
            WHERE v.sorgente = 'indice' AND y.codice = v.codice_indice AND y.stato = 'consuntivo'
              AND y.data = (SELECT max(z.data) FROM public.indici_mercato z
                            WHERE z.codice = v.codice_indice AND z.stato = 'consuntivo')) i ON true
        WHERE v.commodity = %s ORDER BY v.ordine""", (code,))


def range_soglia(udm: str) -> tuple[float, float, float]:
    """(min, max, passo) per il number_input delle soglie alert, per unità."""
    return {
        "%": (0.0, 100.0, 0.5), "°C": (-15.0, 40.0, 0.5), "GWh/g": (0.0, 3000.0, 10.0),
        "€/MWh": (0.0, 500.0, 0.5), "indice": (0.0, 1000.0, 5.0), "/100": (0.0, 100.0, 1.0),
    }.get(udm, (0.0, 1_000_000.0, 1.0))


def decimali(udm: str) -> int:
    return 2 if udm == "€/MWh" else (0 if udm in ("GWh/g", "indice") else 1)
