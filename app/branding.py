"""
Branding Bros Consulenza: design system (CSS), logo, header, hero di login,
tema grafici Altair.

Linguaggio visivo "moderno": font Inter, rosso Bros come ACCENTO su scala
neutra slate, superfici bianche con rilievo soffuso (ombra a livelli), tab a
sottolineatura, KPI card con icona.

Uso in app.py:
    branding.apply_base()          # CSS + logo (sempre, prima del login)
    branding.enable_altair_theme() # tema unico per tutti i grafici
    branding.render_login_hero()   # solo pre-login
    branding.render_header()       # solo post-login (riga brand compatta)
"""
from __future__ import annotations

import base64
import functools
from pathlib import Path

import altair as alt
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
LOGO_PATH = APP_DIR / "assets" / "Logo_Bros_Consulenza.png"
LOGO_SMALL_PATH = APP_DIR / "assets" / "Logo_Bros_Consulenza_460.png"

BROS_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    /* === Palette & token Bros === */
    :root {
        --bros-red: #C00000;
        --bros-red-dark: #8B0000;
        --bros-red-50: #fef2f2;
        --bros-grey: #404040;
        --bros-yellow: #FFC000;
        --bros-green: #2E7D32;
        --gas-blue: #0F6FA8;
        --slate-900: #0f172a;
        --slate-700: #334155;
        --slate-600: #475569;
        --slate-500: #64748b;
        --slate-400: #94a3b8;
        --slate-200: #e7eaf0;
        --slate-100: #f1f5f9;
        --slate-50: #f8fafc;
        --bros-font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        --radius: 14px;
        --radius-lg: 18px;
        --shadow-soft: 0 1px 2px rgba(15,23,42,.05), 0 8px 22px rgba(15,23,42,.08);
        --shadow-red: 0 1px 2px rgba(15,23,42,.05), 0 8px 22px rgba(192,0,0,.12);
    }

    /* === Tipografia globale === */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
    .stApp, button, input, textarea, select {
        font-family: var(--bros-font) !important;
    }

    /* === Layout base === */
    .block-container { padding-top: 1.4rem !important; max-width: 1200px; }
    .stApp { background: #f6f7f9; }

    /* === Titoli (rosso come accento, non riempimento) === */
    h1, h2, h3 { font-family: var(--bros-font) !important; color: var(--slate-900) !important; letter-spacing: -.01em; }
    h1 {
        position: relative; font-size: 1.75rem !important; font-weight: 800 !important;
        margin-top: .3rem !important; padding-bottom: 10px;
    }
    h1::after {
        content: ""; position: absolute; left: 0; bottom: 0;
        width: 46px; height: 3px; border-radius: 2px; background: var(--bros-red);
    }
    h2 { font-size: 1.25rem !important; font-weight: 700 !important; margin-top: 1.2rem !important; }
    h3 { font-size: 1.05rem !important; font-weight: 700 !important; color: var(--bros-red) !important; }
    h4, h5, h6 { font-family: var(--bros-font) !important; color: var(--slate-700) !important; font-weight: 700 !important; margin: .1rem 0 .6rem !important; }

    /* === Sidebar / navigazione moduli (attivo = soft, non blocco rosso) === */
    [data-testid="stSidebarNav"] a,
    [data-testid="stSidebarNav"] li > div { border-radius: 10px; margin: 2px 8px; }
    [data-testid="stSidebarNav"] a:hover { background: var(--slate-100); }
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background: var(--bros-red-50) !important; box-shadow: inset 3px 0 0 var(--bros-red);
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] span { color: var(--bros-red) !important; font-weight: 600 !important; }
    [data-testid="stSidebarNav"] header { font-weight: 700; letter-spacing: .04em; color: var(--slate-500); }

    /* === Bottoni === */
    .stButton > button[kind="primary"],
    .stLinkButton > a[kind="primary"] {
        background-color: var(--bros-red) !important; color: #fff !important; border: none !important;
        font-weight: 600 !important; border-radius: 10px !important; box-shadow: 0 2px 8px rgba(192,0,0,.18) !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stLinkButton > a[kind="primary"]:hover { background-color: var(--bros-red-dark) !important; }
    .stButton > button[kind="secondary"] { border-radius: 10px !important; border-color: var(--slate-200) !important; }

    /* === Form di login come card centrata === */
    [data-testid="stForm"] {
        max-width: 430px; margin: 0.6rem auto 0; padding: 1.7rem 1.8rem 1.3rem;
        background: #ffffff; border: 1px solid var(--slate-200); border-radius: var(--radius-lg);
        box-shadow: 0 1px 2px rgba(15,23,42,.05), 0 18px 44px rgba(192,0,0,.08);
    }
    [data-testid="stForm"] h3 { margin-top: 0 !important; color: var(--slate-900) !important; }
    [data-testid="stForm"] .stButton > button {
        width: 100%; background: var(--bros-red) !important; color: #fff !important; border: none !important;
        font-weight: 700 !important; border-radius: 10px !important; padding: .6rem 0 !important; margin-top: .4rem;
    }
    [data-testid="stForm"] .stButton > button:hover { background: var(--bros-red-dark) !important; }
    [data-testid="stTextInput"] input { border-radius: 10px !important; }

    /* === Hero della Home === */
    .bros-hero {
        padding: 22px 26px 20px; background: linear-gradient(135deg, #ffffff 0%, #fdf6f6 60%, #fbecec 100%);
        border: 1px solid var(--slate-200); border-radius: var(--radius-lg); margin: 4px 0 22px; box-shadow: var(--shadow-soft);
    }
    .bros-hero-hi { font-size: 1.7rem; font-weight: 800; color: var(--slate-900); line-height: 1.15; letter-spacing: -.02em; }
    .bros-hero-hi .accent { color: var(--bros-red); }
    .bros-hero-sub { color: var(--slate-500); font-size: .95rem; margin-top: 4px; }
    .bros-hero-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
    .bros-chip {
        display: inline-flex; align-items: center; gap: 6px; background: #fff;
        border: 1px solid var(--slate-200); border-radius: 999px; padding: 5px 13px;
        font-size: .8rem; font-weight: 600; color: var(--slate-600);
    }
    .bros-chip b { color: var(--bros-red); }

    /* === Tile moduli (Home) === */
    div[class*="st-key-tile_"] { position: relative; }
    .bros-tile {
        position: relative; display: flex; flex-direction: column; gap: 10px; min-height: 178px;
        padding: 20px 18px 14px; background: #ffffff; border: 1px solid var(--slate-200);
        border-radius: var(--radius); box-shadow: 0 1px 2px rgba(15,23,42,.05), 0 6px 18px rgba(192,0,0,.09);
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease; overflow: hidden;
    }
    .bros-tile::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px; background: var(--tile-accent, var(--bros-red)); }
    div[class*="st-key-tile_"]:hover .bros-tile {
        transform: translateY(-4px); border-color: var(--tile-accent, var(--bros-red));
        box-shadow: 0 16px 34px rgba(192,0,0,.18), 0 4px 10px rgba(0,0,0,.07);
    }
    .bros-tile-icon { width: 52px; height: 52px; border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 1.7rem; }
    .bros-tile-title { font-size: 1.15rem; font-weight: 800; color: var(--slate-900); }
    .bros-tile-desc { font-size: .88rem; color: var(--slate-500); line-height: 1.4; flex-grow: 1; }
    .bros-tile-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 4px; }
    .bros-tile-cta { font-weight: 700; font-size: .9rem; color: var(--tile-accent, var(--bros-red)); transition: transform .18s ease; }
    div[class*="st-key-tile_"]:hover .bros-tile-cta { transform: translateX(4px); }

    /* page_link disteso e invisibile su tutta la tile (NON modificare) */
    div[class*="st-key-tile_"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {
        position: absolute; inset: 0; z-index: 6; margin: 0; width: auto !important; height: auto !important;
    }
    div[class*="st-key-tile_"] [data-testid="stPageLink"],
    div[class*="st-key-tile_"] [data-testid="stPageLink"] a {
        position: absolute; inset: 0; margin: 0; padding: 0; width: auto !important; height: auto !important;
    }
    div[class*="st-key-tile_"] [data-testid="stPageLink"] a { opacity: 0; border-radius: var(--radius); }
    div[class*="st-key-tile_"] [data-testid="stPageLink"] a:focus-visible { opacity: 1; outline: 3px solid var(--bros-red); background: transparent; }

    /* === Badge stato === */
    .bros-badge { padding: 3px 10px; border-radius: 999px; font-size: .7rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
    .bros-badge.ok { background: #e8f5e9; color: #2e7d32; }
    .bros-badge.wip { background: #fff4d6; color: #9a6b00; }

    /* === Pillole collegamenti === */
    .bros-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
    a.bros-pill {
        display: inline-flex; align-items: center; gap: 7px; padding: 9px 16px; border-radius: 999px;
        background: #fff; border: 1px solid var(--slate-200); color: var(--slate-600) !important;
        text-decoration: none !important; font-weight: 600; font-size: .88rem;
        transition: border-color .15s ease, color .15s ease, box-shadow .15s ease, transform .15s ease;
    }
    a.bros-pill:hover { border-color: var(--bros-red); color: var(--bros-red) !important; box-shadow: 0 6px 16px rgba(192,0,0,.10); transform: translateY(-1px); }

    /* === Card KPI (icona tinta + numero grande, rilievo) === */
    .bros-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 14px; margin: 6px 0 16px; }
    .bros-kpi {
        display: flex; gap: 12px; align-items: flex-start; background: #fff; border: 1px solid var(--slate-200);
        border-radius: var(--radius); padding: 14px 16px; box-shadow: var(--shadow-red);
        transition: transform .18s ease, box-shadow .18s ease;
    }
    .bros-kpi:hover { transform: translateY(-3px); box-shadow: 0 2px 4px rgba(15,23,42,.06), 0 14px 30px rgba(192,0,0,.18); }
    .bros-kpi-icon {
        width: 42px; height: 42px; border-radius: 12px; flex: 0 0 auto; display: flex; align-items: center;
        justify-content: center; font-size: 1.3rem; background: var(--slate-100);
        background: color-mix(in srgb, var(--kpi-accent, #C00000) 14%, #fff);
    }
    .bros-kpi-body { min-width: 0; }
    .bros-kpi-label { font-size: .7rem; font-weight: 600; color: var(--slate-500); text-transform: uppercase; letter-spacing: .06em; }
    .bros-kpi-value { font-size: 1.5rem; font-weight: 800; color: var(--slate-900); line-height: 1.2; margin-top: 2px; }
    .bros-kpi-sub { font-size: .78rem; color: var(--slate-400); margin-top: 1px; }

    /* === Pannello "in arrivo" === */
    .bros-soon { display: flex; gap: 18px; align-items: flex-start; padding: 22px 24px; background: #fff; border: 1px solid var(--slate-200); border-radius: var(--radius-lg); margin: 6px 0 4px; box-shadow: var(--shadow-soft); }
    .bros-soon-icon { flex: 0 0 auto; width: 72px; height: 72px; border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 2.4rem; }
    .bros-soon-title { font-size: 1.05rem; font-weight: 800; color: var(--slate-900); margin-bottom: 2px; }
    .bros-soon-desc { color: var(--slate-500); font-size: .92rem; line-height: 1.45; }
    .bros-feats { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; margin-top: 14px; }
    .bros-feat { background: #fff; border: 1px solid var(--slate-200); border-radius: 10px; padding: 10px 13px; font-size: .87rem; color: var(--slate-600); line-height: 1.35; }
    .bros-feat b { color: var(--slate-900); display: block; margin-bottom: 1px; }

    /* === CTA (modulo Offerte) === */
    .bros-cta { background: linear-gradient(135deg, var(--bros-red), var(--bros-red-dark)); border-radius: var(--radius-lg); padding: 26px 28px; color: #fff; margin: 6px 0 14px; box-shadow: 0 14px 34px rgba(192,0,0,.22); }
    .bros-cta-title { font-size: 1.35rem; font-weight: 800; margin-bottom: 4px; }
    .bros-cta-desc { font-size: .95rem; opacity: .92; margin-bottom: 16px; }
    a.bros-cta-btn { display: inline-block; background: #fff; color: var(--bros-red) !important; padding: 10px 24px; border-radius: 10px; font-weight: 800; text-decoration: none !important; transition: transform .15s ease, box-shadow .15s ease; }
    a.bros-cta-btn:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(0,0,0,.22); }

    /* === Expander / metric / tabelle / caption / divider === */
    [data-testid="stExpander"] summary { background: var(--slate-50); border-radius: 8px; font-weight: 600; color: var(--slate-700) !important; }
    [data-testid="stMetricLabel"] { font-size: .8rem !important; color: var(--slate-500) !important; font-weight: 600 !important; }
    [data-testid="stMetricValue"] { color: var(--slate-900) !important; font-weight: 800 !important; }
    [data-testid="stDataFrame"] thead th, [data-testid="stDataFrame"] th {
        background: var(--slate-100) !important; color: var(--slate-700) !important; font-weight: 600 !important;
        border-bottom: 1px solid var(--slate-200) !important;
    }
    [data-testid="stCaptionContainer"] { color: var(--slate-500) !important; }
    hr { border-color: var(--slate-200) !important; opacity: 1 !important; }

    /* === Tabs a sottolineatura (attivo = accento, non blocco rosso) === */
    .stTabs [data-baseweb="tab-list"] { position: sticky; top: 0; z-index: 100; background: #f6f7f9; gap: 4px; border-bottom: 2px solid var(--slate-200); padding-top: 4px; margin-bottom: 14px; flex-wrap: wrap; }
    .stTabs [data-baseweb="tab"] { background: transparent; border-radius: 10px 10px 0 0; padding: 10px 18px; font-weight: 800; font-size: 1.05rem; color: var(--slate-600); border-bottom: 3px solid transparent; }
    .stTabs [aria-selected="true"] { background: var(--bros-red-50) !important; color: var(--bros-red) !important; border-bottom: 3px solid var(--bros-red) !important; }
    .stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]) { color: var(--slate-900); background: var(--slate-100); }
    .stTabs [data-baseweb="tab"] p { font-size: 1.05rem !important; font-weight: 800 !important; margin: 0 !important; }

    /* === Dettagli sezioni: callout, tabelle, input, chip, pannelli === */
    [data-testid="stAlert"] { border-radius: 12px; border: 1px solid var(--slate-200); box-shadow: 0 1px 2px rgba(15,23,42,.04); }
    [data-testid="stDataFrame"] { border: 1px solid var(--slate-200) !important; border-radius: 10px; overflow: hidden; }
    [data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] { border: none !important; border-radius: 0 !important; }
    [data-testid="stDataFrame"] [data-testid="stElementToolbar"] { background: transparent; }
    [data-testid="stVegaLiteChart"] { background: transparent; padding: 4px 0; }
    [data-baseweb="select"] > div { border-radius: 10px !important; border-color: var(--slate-200) !important; }
    [data-testid="stNumberInput"] input, [data-testid="stDateInput"] input { border-radius: 10px !important; }
    [data-baseweb="tag"] { border-radius: 8px !important; background: var(--bros-red-50) !important; }
    [data-baseweb="tag"] span { color: var(--bros-red-dark) !important; }
    [data-testid="stDownloadButton"] button { border-radius: 10px !important; border-color: var(--slate-200) !important; }
    div[class*="st-key-panel_"] { background: #fff !important; border: 1px solid var(--slate-200) !important; border-radius: 14px !important; padding: 14px 16px 10px !important; box-shadow: 0 1px 2px rgba(15,23,42,.05), 0 6px 18px rgba(15,23,42,.06) !important; margin-bottom: 6px; }

    /* =====================================================================
       Gas Market Monitor — componenti di lettura rapida (design 19/08/2026)
       Principi: etichetta FUORI dal box (maiuscoletto grigio), numero che
       domina, una sola riga di contesto, colore solo sul dato (testo in
       inchiostro neutro), marks sottili. Scala del blu = intensita'.
       ===================================================================== */
    :root {
        --gas-blue: #0F6FA8; --gas-blue-dark: #0B4F78; --gas-blue-light: #7FB3D5;
        --gas-l1: #7FB3D5; --gas-l2: #5A9FCB; --gas-l3: #3D8BBF; --gas-l4: #1E6FA3; --gas-l5: #0B4F78;
    }
    .gm-grid { display:grid; gap:16px; grid-template-columns:repeat(auto-fit, minmax(220px,1fr)); margin:6px 0 14px; }
    .gm-grid.gm-2 { grid-template-columns:repeat(auto-fit, minmax(320px,1fr)); }
    .gm-label { font-size:.74rem; font-weight:700; letter-spacing:.07em; text-transform:uppercase;
                color:var(--slate-500); margin:0 0 6px 2px; }
    .gm-section { display:flex; align-items:baseline; gap:14px; margin:22px 0 12px; }
    .gm-section h2, div.gm-section > h2, .stApp .gm-section h2 {
        margin:0 !important; font-size:1.7rem !important; font-weight:800 !important;
        color:#C00000 !important; letter-spacing:-.02em; }
    .gm-section span { color:var(--slate-500); font-size:.95rem; }
    .gm-tile { background:#fff; border:1px solid var(--slate-200); border-radius:var(--radius);
               padding:16px 18px 14px; box-shadow:var(--shadow-soft); position:relative; overflow:hidden; }
    .gm-tile::before { content:""; position:absolute; left:0; top:0; bottom:0; width:4px; background:var(--tile-accent, var(--gas-blue)); }
    .gm-value { font-size:2.35rem; font-weight:800; line-height:1; color:var(--gas-blue); letter-spacing:-.02em;
                font-variant-numeric: tabular-nums; white-space:nowrap; }
    .gm-tile { display:flex; flex-direction:column; }
    /* nelle tessere la mini-griglia sta IN ALTO (posizione fissa, non dipende
       dall'altezza dei box vicini); l'ancoraggio in basso vale solo nei pannelli */
    .gm-tile .gm-mini { grid-template-columns:repeat(2, minmax(0,1fr)); margin-top:0; padding-top:0; }
    .gm-tile .gm-mini > div { white-space:normal; overflow:visible; }
    .gm-tile .gm-mini b { white-space:nowrap; }
    .gm-tile .gm-mini b small { display:block; font-size:.8rem; font-weight:600; color:var(--slate-500); margin:2px 0 0; }
    .gm-tile .gm-mini b { font-size:1.45rem; }
    .gm-grid > div { display:flex; flex-direction:column; } .gm-grid > div > .gm-tile { flex:1; }
    .gm-value small { font-size:.95rem; font-weight:600; color:var(--slate-500); margin-left:6px; letter-spacing:0; }
    .gm-sub { font-size:.84rem; color:var(--slate-500); margin-top:6px; }
    .gm-sub b { color:var(--slate-700); font-weight:600; }
    .gm-delta-up { color:var(--gas-blue-dark); } .gm-delta-down { color:var(--gas-blue); } .gm-delta-flat { color:var(--slate-400); }
    /* barra punteggio 0-100 */
    .gm-bar { height:8px; background:var(--slate-100); border-radius:4px; overflow:hidden; margin-top:10px; }
    .gm-bar > span { display:block; height:100%; background:var(--bar-color, var(--gas-blue)); border-radius:4px; }
    .gm-bar-lbl { display:flex; justify-content:space-between; font-size:.74rem; color:var(--slate-500); margin-top:4px; }
    /* pannello grande (scenario / prezzo) */
    .gm-panel { background:#fff; border:1px solid var(--slate-200); border-radius:var(--radius-lg);
                padding:20px 24px 18px; box-shadow:var(--shadow-soft); height:100%;
                display:flex; flex-direction:column; }
    /* i due pannelli della riga "Oggi" hanno la stessa altezza (grid stretch) e la
       mini-griglia dei numeri e' spinta in FONDO: i numeri dei due box poggiano
       sulla stessa linea di base, lo spazio vuoto resta sopra */
    .gm-grid.gm-2 > div { display:flex; flex-direction:column; }
    .gm-grid.gm-2 > div > .gm-panel { flex:1; }
    .gm-panel .gm-value { font-size:3.4rem; }
    .gm-panel-top { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
    .gm-tag { font-size:.74rem; color:var(--slate-500); text-align:right; line-height:1.35; white-space:nowrap;
              background:var(--slate-50); border:1px solid var(--slate-200); border-radius:999px; padding:4px 10px; margin-top:4px; }
    .gm-tag b { color:var(--slate-800); font-weight:700; }
    .gm-mini { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px 14px; margin-top:auto; padding-top:18px; align-items:end; }
    .gm-mini > div { font-size:.76rem; color:var(--slate-500); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    /* REGOLA (decisa 19/08): ogni VALORE numerico e' blu, grande o piccolo;
       il nero/grigio resta a etichette e testo. Il colore significa "dato". */
    .gm-mini b { display:block; font-size:1.6rem; line-height:1.1; color:var(--gas-blue); font-weight:800;
                 font-variant-numeric:tabular-nums; margin-top:3px; letter-spacing:-.01em; }
    .gm-mini .gm-bar { margin-top:7px; height:6px; }
    /* segnale */
    .gm-signal { background:#fff; border:1px solid var(--slate-200); border-left:6px solid var(--sig-color, var(--gas-blue));
                 border-radius:var(--radius); padding:16px 22px 18px; box-shadow:var(--shadow-soft); margin-top:16px; }
    .gm-signal .gm-label { margin-bottom:10px; }
    .gm-signal-row { display:flex; gap:24px; align-items:center; flex-wrap:wrap; }
    .gm-signal-name { font-size:1.55rem; font-weight:800; line-height:1.1; color:var(--sig-color, var(--gas-blue)); }
    .gm-signal-text { flex:1; min-width:260px; font-size:1rem; color:var(--slate-900); line-height:1.45; }
    /* box segnale: verdetto > azione > scala (gerarchia decrescente, tre colonne uguali) */
    /* verdetto leggermente piu' largo (1.3) delle altre due colonne (1 e 1) */
    /* verdetto 1.3 · cosa fare 1.2 · termometro 0.8 (ha bisogno di poco spazio) */
    .gm-sig-grid { display:grid; grid-template-columns: 1.3fr 1.2fr 0.8fr; gap:0; align-items:stretch; }
    .gm-sig-col { padding:4px 28px; }
    .gm-sig-col + .gm-sig-col { border-left:1px solid var(--slate-200); }
    .gm-sig-col:first-child { padding-left:0; }
    /* terza colonna: contenuto centrato, il separatore cade a meta' dello spazio vuoto */
    .gm-sig-col:last-child { padding-right:0; padding-left:28px; }
    .gm-sig-col:nth-child(2) { padding-right:36px; }
    .gm-sig-head { display:flex; align-items:center; gap:8px; font-size:.72rem; font-weight:700;
                   letter-spacing:.06em; text-transform:uppercase; color:var(--slate-500); margin-bottom:8px; }
    .gm-sig-col:last-child .gm-sig-head { justify-content:center; }
    .gm-sig-ico { width:26px; height:26px; border-radius:8px; display:inline-flex; align-items:center; justify-content:center;
                  background:var(--slate-100); font-size:.95rem; }
    .gm-signal-name { font-size:2.1rem; font-weight:800; line-height:1.05; color:var(--sig-color, var(--gas-blue)); letter-spacing:-.02em; }
    .gm-sig-why { font-size:.84rem; color:var(--slate-500); margin-top:8px; line-height:1.35; }
    .gm-sig-list { margin:8px 0 0; padding-left:16px; font-size:.84rem; color:var(--slate-500); line-height:1.45; }
    .gm-sig-list li { margin:2px 0; } .gm-sig-list b { color:var(--slate-700); font-weight:600; }
    .gm-sig-do { font-size:1.25rem; font-weight:700; color:var(--sig-color, var(--gas-blue)); line-height:1.3; }
    .gm-sig-do small { display:block; font-size:.84rem; font-weight:500; color:var(--slate-500); margin-top:6px; }
    /* termometro del segnale: 6 gradini (0 = nessun segnale, sempre etichettato) */
    .gm-thermo { display:flex; flex-direction:column-reverse; gap:4px; width:max-content; margin:0 auto; }
    .gm-thermo > div { display:flex; align-items:center; gap:10px; font-size:.78rem; color:var(--slate-400); }
    .gm-thermo i { display:block; width:38px; height:9px; border-radius:5px; background:var(--slate-100); border:1px solid var(--slate-200); }
    .gm-thermo .on { color:var(--slate-600); }
    .gm-thermo .on i { background:var(--sig-color, var(--gas-blue)); border-color:var(--sig-color, var(--gas-blue)); }
    .gm-thermo .cur { color:var(--sig-color, var(--gas-blue)); font-weight:700; }
    .gm-thermo .cur i { box-shadow:0 0 0 3px rgba(15,111,168,.18); }
    /* legenda grafici */
    .gm-legend { display:flex; flex-wrap:wrap; gap:14px; font-size:.8rem; color:var(--slate-600); margin:2px 0 6px; }
    .gm-legend i { display:inline-block; width:22px; height:0; border-top:2px solid var(--c); vertical-align:middle; margin-right:6px; }
    .gm-legend i.dash { border-top-style:dashed; } .gm-legend i.dot { border-top-style:dotted; border-top-width:3px; }
    .gm-legend i.band { height:10px; border:0; background:var(--c); opacity:.45; border-radius:2px; }

    /* === Responsive (mobile-first per la dashboard: RNF smartphone) === */
    @media (max-width: 760px) {
        .block-container { padding-left: .9rem !important; padding-right: .9rem !important; padding-top: 1rem !important; }
        h1 { font-size: 1.35rem !important; }
        h2 { font-size: 1.1rem !important; }
        .bros-kpis { grid-template-columns: 1fr 1fr !important; gap: 10px !important; }
        .gm-grid, .gm-grid.gm-2 { grid-template-columns: 1fr !important; gap: 10px; }
        .gm-mini { grid-template-columns: repeat(2, minmax(0,1fr)); }
        .gm-mini b { font-size: 1.3rem; }
        .gm-panel .gm-value { font-size: 2.4rem; }
        .gm-value { font-size: 1.9rem; }
        .gm-signal { padding: 14px 16px; gap: 12px; }
        .gm-sig-grid { grid-template-columns: 1fr; gap: 14px; }
        .gm-sig-col { padding: 0 !important; }
        .gm-sig-col + .gm-sig-col { border-left: 0; border-top: 1px solid var(--slate-200); padding-top: 12px !important; }
        .gm-signal-name { font-size: 1.25rem; }
        .gm-signal-text { min-width: 0; font-size: .95rem; }
        .bros-kpi { min-height: 0 !important; padding: 12px 12px !important; }
        .bros-kpi-value { font-size: 1.3rem !important; }
        .bros-hero { padding: 16px 16px 14px; }
        .bros-hero-hi { font-size: 1.25rem; }
        [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    }
    @media (max-width: 480px) {
        .bros-kpis { grid-template-columns: 1fr !important; }
    }
</style>

"""


def apply_base() -> None:
    """CSS globale + logo persistente. Chiamare sempre, prima del login."""
    st.markdown(BROS_CSS, unsafe_allow_html=True)
    if LOGO_PATH.exists():
        try:
            st.logo(str(LOGO_PATH), size="large")
        except (AttributeError, TypeError):
            pass


# === Tema grafici Altair (coerente per tutte le dashboard) ===
def _bros_altair_theme() -> dict:
    return {
        "config": {
            "font": "Inter, -apple-system, 'Segoe UI', sans-serif",
            "view": {"stroke": "transparent"},
            "axis": {
                "labelColor": "#64748b", "titleColor": "#475569",
                "gridColor": "#eef2f7", "domainColor": "#e2e8f0", "tickColor": "#e2e8f0",
                "labelFontSize": 12, "titleFontSize": 12, "titleFontWeight": 600,
            },
            "legend": {"labelColor": "#475569", "titleColor": "#334155", "labelFontSize": 12, "titleFontSize": 12},
            "bar": {"cornerRadiusEnd": 4},
            "range": {"category": ["#C00000", "#404040", "#B26A00", "#2E7D32", "#6d9eeb", "#8B0000", "#94a3b8"]},
        }
    }


# Locale italiana per assi e tooltip dei grafici (mesi, giorni, separatori)
_IT_TIME = {
    "dateTime": "%A %e %B %Y, %X", "date": "%d/%m/%Y", "time": "%H:%M:%S", "periods": ["AM", "PM"],
    "days": ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"],
    "shortDays": ["dom", "lun", "mar", "mer", "gio", "ven", "sab"],
    "months": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
               "settembre", "ottobre", "novembre", "dicembre"],
    "shortMonths": ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"],
}
_IT_NUMBER = {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["", " €"]}


def enable_altair_theme() -> None:
    """Registra e attiva il tema Bros per Altair + locale italiana (no-op se l'API cambia)."""
    try:
        alt.themes.register("bros", _bros_altair_theme)
        alt.themes.enable("bros")
    except Exception:
        pass
    try:
        alt.renderers.set_embed_options(timeFormatLocale=_IT_TIME, formatLocale=_IT_NUMBER)
    except Exception:
        pass


@functools.lru_cache(maxsize=1)
def _logo_b64() -> str:
    """Logo (versione ridotta) in base64, per centratura affidabile inline."""
    path = LOGO_SMALL_PATH if LOGO_SMALL_PATH.exists() else LOGO_PATH
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()


def render_login_hero() -> None:
    """Pre-login: logo grande centrato + titolo. Il form (card) lo rende auth."""
    b64 = _logo_b64()
    logo_html = (
        f"<img src='data:image/png;base64,{b64}' alt='Bros Consulenza' "
        f"style='width:min(210px, 55vw); height:auto; display:block; margin: 2vh auto 0;'/>"
    ) if b64 else ""
    st.markdown(
        f"{logo_html}"
        "<div style='text-align:center; margin-top:10px;'>"
        "<div style='font-size:1.85rem; font-weight:800; color:#C00000; line-height:1.1; letter-spacing:-.02em;'>"
        "Bros Consulenza</div>"
        "<div style='font-size:1rem; color:#64748b; margin-top:4px;'>Gas Market Monitor</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str, sub: str = "",
             accent: str = "#C00000", icon: str = "") -> str:
    """HTML di una card KPI (da concatenare dentro <div class='bros-kpis'>).
    icon: emoji opzionale, mostrata in un cerchietto tinto col colore accento."""
    icon_html = f"<div class='bros-kpi-icon'>{icon}</div>" if icon else ""
    return (f"<div class='bros-kpi' style='--kpi-accent:{accent};'>{icon_html}"
            f"<div class='bros-kpi-body'>"
            f"<div class='bros-kpi-label'>{label}</div>"
            f"<div class='bros-kpi-value'>{value}</div>"
            f"<div class='bros-kpi-sub'>{sub}</div></div></div>")


def render_header(sottotitolo: str = "Gas Market Monitor") -> None:
    """Post-login: riga brand compatta (il logo è già in st.logo)."""
    st.markdown(
        "<div style='display: flex; align-items: baseline; gap: 14px; "
        "margin-bottom: 6px; flex-wrap: wrap;'>"
        "<span style='font-size: 1.5rem; font-weight: 800; color: #C00000; "
        "line-height: 1; letter-spacing:-.02em;'>Bros Consulenza</span>"
        f"<span style='font-size: 0.95rem; color: #64748b; line-height: 1;'>"
        f"{sottotitolo}</span>"
        "</div>",
        unsafe_allow_html=True,
    )


# =============================================================================
# Componenti Gas Market Monitor (HTML) — design 19/08/2026
# =============================================================================

def gm_tile(label: str, value: str, unit: str = "", sub: str = "",
            accent: str = "#0F6FA8", score: float | None = None,
            score_label: str = "punteggio nello scenario") -> str:
    """Stat tile: etichetta FUORI (maiuscoletto), numero grande, una riga di
    contesto, barra 0-100 opzionale. Da concatenare dentro <div class='gm-grid'>."""
    unit_html = f"<small>{unit}</small>" if unit else ""
    bar = ""
    if score is not None:
        v = max(0.0, min(100.0, float(score)))
        bar = (f"<div class='gm-bar' style='--bar-color:{accent}'><span style='width:{v:.0f}%'></span></div>"
               f"<div class='gm-bar-lbl'><span>{score_label}</span><b>{v:.0f}/100</b></div>")
    return (f"<div><div class='gm-label'>{label}</div>"
            f"<div class='gm-tile' style='--tile-accent:{accent}'>"
            f"<div class='gm-value'>{value}{unit_html}</div>"
            + (f"<div class='gm-sub'>{sub}</div>" if sub else "") + bar + "</div></div>")


def gm_tile_mini(label: str, coppie: list[tuple[str, str]], sub: str = "",
                 accent: str = "#0F6FA8") -> str:
    """Tile con mini-griglia etichetta/valore (2 colonne), stesso stile dei
    pannelli Dashboard: per dati composti (scostamenti, min/max) che come
    numero unico andrebbero a capo."""
    celle = "".join(f"<div>{k}<b>{v}</b></div>" for k, v in coppie)
    return (f"<div><div class='gm-label'>{label}</div>"
            f"<div class='gm-tile' style='--tile-accent:{accent}'>"
            f"<div class='gm-mini'>{celle}</div>"
            + (f"<div class='gm-sub'>{sub}</div>" if sub else "") + "</div></div>")


def gm_delta(delta: float, dec: int = 1, unit: str = "") -> str:
    """Freccia + valore assoluto, colorata per direzione (scala blu, non semaforo)."""
    if delta > 0:
        cls, fr = "gm-delta-up", "▲"
    elif delta < 0:
        cls, fr = "gm-delta-down", "▼"
    else:
        cls, fr = "gm-delta-flat", "="
    v = f"{abs(delta):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"<span class='{cls}'>{fr} {v}{(' ' + unit) if unit else ''}</span>"


def gm_legend(items: list[tuple[str, str, str]]) -> str:
    """Legenda compatta: lista di (stile, colore, testo); stile in solid|dash|dot|band."""
    return ("<div class='gm-legend'>"
            + "".join(f"<span><i class='{st}' style='--c:{c}'></i>{t}</span>" for st, c, t in items)
            + "</div>")


# Etichette assi in italiano SENZA locale Vega: Streamlit 1.61 filtra
# usermeta.embedOptions (passano solo theme/renderer/padding, verificato nel
# bundle ArrowVegaLiteChart), quindi timeFormatLocale/formatLocale non arrivano
# mai al frontend. Si replica il multi-formato di default con labelExpr in
# config (che Streamlit non tocca): giorno -> "19 ago", inizio mese -> "ago",
# inizio anno -> "2026"; numeri con virgola decimale e punto per le migliaia.
_MESI_EXPR = "['gen','feb','mar','apr','mag','giu','lug','ago','set','ott','nov','dic']"
_LABEL_DATA_IT = (
    f"date(datum.value) != 1 ? date(datum.value) + ' ' + {_MESI_EXPR}[month(datum.value)]"
    f" : month(datum.value) != 0 ? {_MESI_EXPR}[month(datum.value)]"
    " : timeFormat(datum.value, '%Y')")
_LABEL_NUM_IT = ("replace(replace(replace(format(datum.value, ','), ',', '\\u00a7'), "
                 "'.', ','), '\\u00a7', '.')")


def altair_it(chart, **kwargs):
    """st.altair_chart con assi in italiano (date e numeri). Usare SEMPRE
    questa al posto di st.altair_chart."""
    kwargs.setdefault("width", "stretch")
    spec = chart.to_dict()
    cfg = spec.setdefault("config", {})
    cfg.setdefault("axisTemporal", {}).setdefault("labelExpr", _LABEL_DATA_IT)
    cfg.setdefault("axisQuantitative", {}).setdefault("labelExpr", _LABEL_NUM_IT)
    return st.vega_lite_chart(spec, **kwargs)
