"""
Modulo Admin (solo ruolo 'admin') — RF-07.

Tab "Parametri del segnale": configurazione IN AUTONOMIA di pesi, soglie,
orizzonti dei trend e gradini — ogni parametro con scheda descrittiva
(cosa fa, effetto di alzarlo/abbassarlo, default) letta da
gas_parametri_doc. Il salvataggio crea una NUOVA versione in gas_pesi
(storicizzata, con autore) e ricalcola subito il segnale su tutto lo
storico, così l'effetto si vede in dashboard.
Tab "Stato pipeline": sorgenti dati e ultime esecuzioni.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

import db

st.title("⚙️ Admin")
st.caption("Configurazione del Gas Market Monitor e stato della pipeline dati.")

utente = st.session_state.get("utente_autenticato", "")

tab_pipe, tab_par = st.tabs(["📡 Stato dati e pipeline", "🎛 Parametri del segnale"])


# =============================================================================
# Helpers config
# =============================================================================

def _get(cfg: dict, chiave: str):
    """Legge 'a.b' dal jsonb annidato."""
    cur = cfg
    for k in chiave.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _set(cfg: dict, chiave: str, valore) -> None:
    parti = chiave.split(".")
    cur = cfg
    for k in parti[:-1]:
        cur = cur.setdefault(k, {})
    cur[parti[-1]] = valore


def _carica_config():
    row = db.query("SELECT versione, pesi, valido_dal, autore FROM public.gas_pesi "
                   "ORDER BY versione DESC LIMIT 1")
    doc = db.query("SELECT chiave, ordine, gruppo, nome, spiegazione, effetto, udm, "
                   "minimo, massimo, passo, valore_default FROM public.gas_parametri_doc "
                   "ORDER BY ordine")
    return row[0] if row else None, pd.DataFrame(doc, columns=[
        "chiave", "ordine", "gruppo", "nome", "spiegazione", "effetto", "udm",
        "minimo", "massimo", "passo", "default"])


# =============================================================================
# TAB 1 — Parametri
# =============================================================================
with tab_par:
    try:
        riga, doc = _carica_config()
    except Exception as e:
        st.error(f"📡 Impossibile leggere la configurazione: {e}")
        st.stop()
    if riga is None or doc.empty:
        st.warning("Configurazione non trovata: applicare la migrazione g005.")
        st.stop()

    versione, cfg, valido_dal, autore = int(riga[0]), dict(riga[1] or {}), riga[2], riga[3]
    st.markdown(
        f"Versione corrente **v{versione}** · in vigore dal "
        f"{pd.Timestamp(valido_dal).tz_convert('Europe/Rome').strftime('%d/%m/%Y %H:%M')} · "
        f"autore: *{autore or 'n.d.'}*")
    st.info(
        "Ogni modifica crea una **nuova versione** della configurazione (la storia resta) "
        "e ricalcola subito il segnale su tutto lo storico: puoi vedere l'effetto in "
        "Dashboard e tornare indietro ripristinando i default.", icon="ℹ️")

    nuovi: dict = {}
    with st.form("form_parametri", border=False):
        for gruppo, blocco in doc.groupby("gruppo", sort=False):
            st.subheader(gruppo)
            for _, p in blocco.iterrows():
                att = _get(cfg, p["chiave"])
                att = float(att) if att is not None else float(p["default"] or 0)
                c1, c2 = st.columns([2.2, 1])
                with c1:
                    st.markdown(f"**{p['nome']}**")
                    st.caption(p["spiegazione"])
                    st.caption(f"↕ *{p['effetto']}*")
                with c2:
                    passo = float(p["passo"] or 1)
                    intero = passo.is_integer() and (p["udm"] in ("giorni", "punti", "%")
                                                     and float(att).is_integer()
                                                     and float(p["minimo"] or 0).is_integer())
                    kw = dict(min_value=float(p["minimo"]) if p["minimo"] is not None else None,
                              max_value=float(p["massimo"]) if p["massimo"] is not None else None,
                              value=float(att), step=passo,
                              label=f"{p['udm'] or 'valore'} (default {p['default']:g})",
                              key=f"par_{p['chiave']}")
                    if intero:
                        kw.update(min_value=int(kw["min_value"]) if kw["min_value"] is not None else None,
                                  max_value=int(kw["max_value"]) if kw["max_value"] is not None else None,
                                  value=int(att), step=int(passo))
                    nuovi[p["chiave"]] = st.number_input(**kw)
                st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        c_a, c_b, c_c = st.columns([2, 1.2, 1.2])
        nota = c_a.text_input("Nota sulla modifica (facoltativa)",
                              placeholder="es. alzata soglia scenario dopo test estate")
        salva = c_b.form_submit_button("💾 Salva nuova versione", type="primary",
                                       width="stretch")
        reset = c_c.form_submit_button("↩ Ripristina default", width="stretch")

    if salva or reset:
        nuova_cfg = json.loads(json.dumps(cfg))  # copia profonda
        for _, p in doc.iterrows():
            v = float(p["default"]) if reset else float(nuovi[p["chiave"]])
            _set(nuova_cfg, p["chiave"], int(v) if float(v).is_integer() and p["udm"] in ("giorni", "punti") else v)
        # validazioni di coerenza
        pesi = nuova_cfg.get("scenario", {})
        somma = sum(float(pesi.get(k, 0)) for k in ("stoccaggi", "meteo", "lng", "geopolitica"))
        errori = []
        if abs(somma - 100) > 0.01:
            errori.append(f"i pesi dello scenario sommano {somma:g}, devono fare 100")
        g1, g2, g3 = (int(nuova_cfg.get("gradino_iniziale", 3)),
                      int(nuova_cfg.get("gradino_fixing", 5)),
                      int(nuova_cfg.get("gradino_trend", 10)))
        if not (g1 < g2 < g3):
            errori.append("i gradini devono essere crescenti (iniziale < fixing < trend)")
        tb, tm, tl = (int(nuova_cfg.get("trend_breve_gg", 20)),
                      int(nuova_cfg.get("trend_medio_gg", 60)),
                      int(nuova_cfg.get("trend_lungo_gg", 180)))
        if not (tb < tm < tl):
            errori.append("gli orizzonti devono essere crescenti (breve < medio < lungo)")
        if errori:
            for e in errori:
                st.error("❌ " + e)
        else:
            with st.spinner("Salvo e ricalcolo il segnale su tutto lo storico…"):
                with db.connect() as conn:
                    conn.execute("SET statement_timeout = '120s'")
                    conn.execute(
                        "INSERT INTO public.gas_pesi (pesi, autore) VALUES (%s::jsonb, %s)",
                        (json.dumps(nuova_cfg),
                         f"{utente or 'admin'}" + (f" — {nota.strip()}" if nota.strip() else "")
                         + (" [ripristino default]" if reset else "")))
                    n = conn.execute(
                        "SELECT public.gas_ricalcola_segnale(%s, current_date)",
                        ("2020-07-01",)).fetchone()[0]
                    conn.commit()
            st.success(f"✅ Nuova versione salvata e segnale ricalcolato ({n} giorni). "
                       "La Dashboard si aggiorna entro 10 minuti (o con 🔄).")
            st.cache_data.clear()
            st.rerun()

    # storico versioni
    with st.expander("📜 Storico versioni"):
        try:
            sto = db.query("SELECT versione, valido_dal, autore FROM public.gas_pesi "
                           "ORDER BY versione DESC LIMIT 20")
            dfs = pd.DataFrame(sto, columns=["Versione", "Dal", "Autore / nota"])
            if not dfs.empty:
                dfs["Dal"] = pd.to_datetime(dfs["Dal"], utc=True).dt.tz_convert(
                    "Europe/Rome").dt.strftime("%d/%m/%Y %H:%M")
            st.dataframe(dfs, width="stretch", hide_index=True)
        except Exception as e:
            st.caption(f"storico non disponibile: {e}")


# =============================================================================
# TAB 2 — Stato pipeline
# =============================================================================
with tab_pipe:
    @st.cache_data(ttl=300, show_spinner="📡 Leggo lo stato…")
    def _stato() -> dict:
        srg = db.query(
            "SELECT DISTINCT ON (sorgente) sorgente, ultima_esecuzione, esito, record_aggiornati "
            "FROM public.data_source_log ORDER BY sorgente, ultima_esecuzione DESC NULLS LAST")
        run = db.query(
            "SELECT started_at, status, duration_s, left(coalesce(error,''),120) "
            "FROM public.task_runs WHERE task_id = 'gas-monitor' "
            "ORDER BY started_at DESC LIMIT 15")
        ult = db.query(
            "SELECT variabile, metrica, max(data) FROM public.gas_serie "
            "WHERE commodity='gas' GROUP BY 1,2 ORDER BY 1,2")
        return {"sorgenti": srg, "run": run, "ultime": ult}

    try:
        s = _stato()
    except Exception as e:
        st.error(f"📡 Impossibile leggere lo stato: {e}")
        st.stop()

    st.subheader("Freschezza delle serie")
    st.caption("Ogni mattina la pipeline verifica che ogni serie abbia un dato recente: oltre la tolleranza "
               "(2 gg prezzo/segnale, 3 gg le altre fonti che pubblicano in ritardo, 7 gg il GPR che è "
               "aggiornato a mano dagli autori) il run va in errore e parte UNA email di alert interna "
               "al giorno. Qui lo stato a colpo d'occhio.")
    fr = db.query("SELECT serie, ultimo, giorni_fa FROM public.gas_freschezza() ORDER BY serie")
    TOLL = {"prezzo MGP_GAS": 2, "segnale": 2, "geopolitica gpr": 7}
    d0 = pd.DataFrame([{"Serie": se, "Ultimo giorno": ul, "Giorni fa": g,
                        "Stato": ("🟢 ok" if g is not None and int(g) <= TOLL.get(se, 3) else "🔴 in ritardo")}
                       for se, ul, g in fr])
    st.dataframe(d0, width="stretch", hide_index=True)

    st.subheader("Esecuzioni della pipeline gas-monitor")
    d2 = pd.DataFrame(s["run"], columns=["Avvio", "Esito", "Durata s", "Errore"])
    if not d2.empty:
        d2["Avvio"] = pd.to_datetime(d2["Avvio"], utc=True).dt.tz_convert(
            "Europe/Rome").dt.strftime("%d/%m/%Y %H:%M")
    st.dataframe(d2, width="stretch", hide_index=True)

    st.subheader("Sorgenti dati (job dati-mercato)")
    d3 = pd.DataFrame(s["sorgenti"], columns=["Sorgente", "Ultima esecuzione", "Esito", "Record"])
    if not d3.empty:
        d3["Ultima esecuzione"] = pd.to_datetime(d3["Ultima esecuzione"], utc=True).dt.tz_convert(
            "Europe/Rome").dt.strftime("%d/%m/%Y %H:%M")
    st.dataframe(d3, width="stretch", hide_index=True)
