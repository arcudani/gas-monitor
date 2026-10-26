# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Cos'è

**Energy Market Monitor** (nome unico dal 21/08/2026; ex "Gas Market Monitor", identificatori tecnici `gas_*`/`gas-monitor` invariati) — terza app Streamlit di Bros Consulenza (dopo `C:\Code\App_Offerte` e
`C:\Code\Bros_ERP`): individua le **finestre favorevoli al fixing di gas ed energia elettrica** per clienti con
contratti annuali (selettore commodity in sidebar). Tutto in italiano (UI, commenti, testi). Requisiti e storia delle decisioni:
`G:\Il mio Drive\Code\App_Offerte\REQUISITI_Gas_Market_Monitor.md` (v1.9) — leggere la sezione
"Indice sintetico → Scenario + Prezzo + Segnale" prima di toccare il motore.

Stato: **in produzione** (20/08/2026). Repo **pubblico** `arcudani/gas-monitor` (pubblico perché
Community Cloud consente una sola app da repo privato, già usata da bros-erp — quindi MAI
committare segreti o dati cliente); app live su
`https://gas-monitor-gtspes3q3h5ry5wp3dj9rn.streamlit.app` (secrets su SCC: SUPABASE_DB_URL,
AUTH_COOKIE_KEY). **`git push` su `main` rideploya l'app** — mai push senza ok esplicito.
L'URL è cablato come fallback di `GAS_MONITOR_APP_URL` nella config ERP e nella Edge Function alert.

## Comandi (dalla cartella `app/`, con il python della venv)

venv: `C:\Code\Gas_Monitor\app\.venv\Scripts\python.exe` (Python 3.12). Su Windows anteporre
`$env:PYTHONUTF8='1'` ai comandi che stampano emoji/€.

```bash
python -m streamlit run app.py --server.port 8532     # avvio (NON streamlit.exe)
python run_tests.py                                   # tutta la suite (7 file, ~4 min)
python test_dashboard.py                              # un file (ognuno è standalone, exit 0/1)
python imposta_pwd.py Nome --ruolo admin|cliente      # crea utente / password (interattivo)
python -m py_compile moduli/dashboard.py              # check veloce prima dei test
```

I test che toccano il DB si auto-saltano se manca `SUPABASE_DB_URL` (in `app/.env`, gitignored).
Sono **AppTest su dati reali** (`test_dashboard`, `test_dettaglio`, `test_alert`, `test_admin`,
`test_export`) + smoke della shell. Non è pytest: script con `if __name__ == "__main__"`.

Preview: `.claude/launch.json` del launchpad Drive ha la config `gas-monitor` (porta **8532**).
⚠️ `registro_moduli.py` e `branding.py` **non si hot-reloadano**: dopo averli toccati riavviare il server.
La pagina è dietro login: verificare con AppTest (già nei test), non nel browser.

## Architettura

**Shell + moduli** (stesso pattern di Bros_ERP): `app.py` fa bridge secrets → `set_page_config` →
`branding.apply_base()` → `st.navigation(registro_moduli.build_navigation(...))` → gate login →
`pg.run()`. I moduli in `moduli/` sono script-pagina **solo top-level**: niente `set_page_config`,
login o CSS. Aggiungere un modulo = 1 file + 1 riga in `registro_moduli.MODULI` (poi riavvio).
La danza navigation/login in `app.py` è load-bearing (URL profondi + riautenticazione da cookie:
lo username va risolto PRIMA di costruire la nav, altrimenti `is_admin("")` nasconde Admin).

**Auth su tabella DEDICATA `public.gas_utenti`** (ruoli `admin`|`cliente`), NON su `public.utenti`:
ERP e app Offerte caricano `utenti` senza filtro di ruolo, un cliente messo lì entrerebbe ovunque.
Cookie proprio `bros_gas_auth`. `db.py` = pool psycopg con `prepare_threshold=None` (pooler Supabase).

**Il dato è tutto pre-calcolato in cloud; l'app legge e basta** (RNF: nessuna chiamata esterna a
runtime). Pipeline = quattro Edge Function Supabase (sorgente in `supabase/functions/`, **deploy via
MCP `deploy_edge_function`, NON via git** — SEMPRE `list_edge_functions`/`get_edge_function` e
confronto versione prima, altre sessioni editano lo stesso progetto):
- `gas-monitor` — cron pg_cron ogni 30' 04:00–07:30 UTC, gate interno Roma 06:30–09:30, una sola
  esecuzione `success` al giorno. Fonti: Open-Meteo (meteo), GIE AGSI+/ALSI (stoccaggi/LNG), GPR
  (delegato), prezzo MGP-GAS **già in `indici_mercato`** (lo scrive il job VPS `dati-mercato` di
  App_Offerte — non costruire un secondo scraper GME). Poi RPC `gas_ricalcola_indice` +
  `gas_ricalcola_segnale`, alert utenti, **controllo freschezza** → run `error` + email `[ALERT]`
  interna se una serie è stantia. Log in `task_runs` (CHECK status `success|error`), registrata in
  `task_attesi` → visibile nel Monitor ERP. `?force=1` bypassa gate; `?backfill=…`, `?ricalcola=1`.
- `gas-monitor-gpr` — SOLO il parsing dell'.xls GPR (~3MB, SheetJS): in un worker separato perché
  nello stesso isolate sforava la memoria; una sub-invocazione dello stesso slug NON isola.
- `gas-monitor-alert` — valuta `gas_alert` per utente, una email Brevo per utente con la
  "Situazione odierna" + soglie raggiunte; `?preview=1` valuta senza inviare.

**Schema** (`app/migrations/g00x_*.sql`, prefisso `gas_*`, numerazione `g###` per non collidere con le
`000x` di App_Offerte sullo stesso DB condiviso, SOLO additive, RLS deny-all): `gas_utenti/gas_aziende`,
`gas_serie` (serie normalizzate data/variabile/metrica), `gas_pesi` (configurazione **versionata**,
jsonb), `gas_parametri_doc` (schede descrittive per la tab Admin), `gas_segnale` (il risultato:
una riga/giorno), `gas_indice` (indice storico, solo confronto), `gas_alert/_inviati`,
`gas_freschezza()`. I file `.sql` sono la fonte di verità ma vengono applicati via MCP
`apply_migration` o psycopg diretto; alcune funzioni sono state ri-create sul DB con delta —
in caso di dubbio confrontare `pg_get_functiondef` con il file.

**Il motore (`gas_ricalcola_segnale`)** — capire questo prima di tutto. La versione CORRENTE della
funzione è in **g013** (evoluzione g005 → g008 generico → g009/g010 medie mobili → g013 performance);
i concetti qui sotto valgono per entrambe le commodity, con i valori del gas come esempio:
- **Scenario 0–100** = media ponderata di 4 percentili (2020–oggi) orientati **a favore
  dell'acquirente**: stoccaggi sopra media 5 anni, LNG send-out sopra media, meteo più mite della
  norma 1991+, GPR basso. Le condizioni usano la **media mobile 7 gg** (il puntuale è rumoroso).
- **Prezzo**: tre rette di regressione rolling (20/60/180 gg). `prezzo_favorevole` =
  (sotto breve ≥3% **e** entro +1% del medio) **oppure** sotto medio ≥7%, con filtri di sicurezza:
  lungo non in forte salita (>+0,2%/g: rally) **né** in discesa ripida (<−0,5%/g: rientro da crisi),
  breve non in caduta libera (<−1%/g).
- **Livelli** (codice → intensità): attesa/chiusa 0 · monitorare 1 · prime/**opportunita** 2 ·
  **minimo**/iniziale 3 · fixing 4 · trend 5. `favorevole` = scenario7 ≥ 60 e prezzo favorevole,
  contato su giorni consecutivi (gradini 3/5/10). `opportunita` = medio ≤ −7% con scenario7 ≥ 35.
  `minimo` = prezzo sotto il 5° percentile degli ultimi 6 **o** 18 mesi (criterio assoluto).
- Tutti i numeri sopra sono **parametri** in `gas_pesi` (22, con scheda in `gas_parametri_doc`);
  salvare dalla tab Admin crea una nuova versione e ricalcola tutto (~1 s per 2.200 giorni).
  È stato tarato su backtest 2020–2026 (29 finestre, 25 buone): le scelte non ovvie e i casi-limite
  (dic-2022, apr-2026) sono documentati nei requisiti e nelle schede — non "correggere" senza rifare
  il backtest. `gas_ricalcola_indice` (vecchio indice di pressione) legge solo le versioni di
  `gas_pesi` col formato vecchio (chiave `prezzo`): non toccare.

**Design system** (`branding.py`, componenti `gm-*` + helper `gm_tile/gm_tile_mini/gm_delta/
gm_legend/altair_it`): etichetta FUORI dal box, numero domina, **ogni valore numerico in blu
`#0F6FA8`**, testo in inchiostro neutro, niente semaforo (la forza del segnale è una scala di blu).
Colori fissi decisi col committente: prezzo **rosso Bros `#C00000`**, trend medio **verde acqua
`#14B8A6`** tratteggiato, breve grigio `#64748b` punteggiato, lungo blu scuro pieno; titoli di
sezione "Oggi"/"Storico" rossi (stile inline: il CSS h2 di Streamlit vince sulle classi).
Grafici SEMPRE via `branding.altair_it()`: date e numeri degli assi in italiano via `labelExpr`
nel `config` della spec — le locale Vega NON funzionano (Streamlit 1.61 filtra
`usermeta.embedOptions` tenendo solo theme/renderer/padding, e `set_embed_options` non arriva
al frontend). Mobile: `@media (max-width:760px)`.

**Export** (`export_docs.py` — rinominato da `export.py` il 21/08: lo stesso nome della pagina
`moduli/export.py` creava un import circolare sotto AppTest): funzioni pure → bytes (openpyxl,
reportlab), testabili offline; `contesto(info, variabili)` porta etichette/fonti per commodity.

## Multi-commodity (g008, 21/08/2026): gas + energia elettrica nella STESSA app

Decisione utente: un'unica app con **selettore Gas | Energia elettrica** in sidebar (`app.py` →
`commodity.selettore()` → `st.session_state["commodity"]`). Tutto è **table-driven**:
- `gas_commodity` (nome, icona, codice prezzo in `indici_mercato`, aggregazione `giorno`|`media_ore`)
  e `gas_variabili` (per commodity: serie sorgente, riferimento `media5_doy`|`norma_doy`|`nessuno`,
  trasformazione `delta`|`abs_delta`, orientamento ±1, testi, tolleranza freschezza).
- `gas_pesi`, `gas_parametri_doc`, `gas_alert` hanno la colonna `commodity` (una storia di versioni
  per commodity; PK doc = (commodity, chiave)).
- Motore generico `gas_ricalcola_segnale(commodity, dal, al)`; `gas_ricalcola_segnale(dal, al)` e
  `gas_freschezza()` restano come wrapper gas. **Invariante verificato con A/B** (vecchio g005 vs
  nuovo sugli stessi dati: 0 righe diverse). ⚠️ Le CTE `val_doy/base5/exp5` sono `MATERIALIZED`
  apposta: senza, il planner sceglie un nested loop e il ricalcolo passa da 3 a 25 s (oltre gli 8 s
  di PostgREST usati dal run quotidiano).
- `commodity.py` è l'unico punto d'accesso per i moduli (anagrafica in cache, `sql_valori`,
  `sql_prezzo`, `sql_ultimi_valori`, `range_soglia`, `decimali`). Senza selettore (AppTest,
  URL diretti) il default è `gas`: il comportamento storico è invariato. `test_commodity_ee.py`
  copre l'EE.
- **EE**: prezzo **PUN** (`PUN_INDEX_GME` orario, media delle 24 ore; storico 2020→ caricato il
  21/08 con `App_Offerte/app/data_updater/backfill_pun.py`, `Granularita=h` su tutto il periodo —
  il quartorario GME parte dal 01/10/2025 ma l'orario resta disponibile). Scenario a 5 variabili:
  produzione zonale (7 zone, ENTSO-E, secret `ENTSOE_API_KEY` attivo dal 24/08), meteo (stessa
  serie del gas ma `abs_delta`: caldo e freddo anomali sono entrambi sfavorevoli), prezzo gas
  (`sorgente='indice'` su MGP_GAS), quota rinnovabili (ENTSO-E), GPR. Le serie mai caricate
  contano 50/100 e NON generano alert di freschezza finché non arriva il primo dato.
  Pesi e soglia EE **tarati il 24-25/08** (g012, vedi sotto).
- Pipeline: `gas-monitor` (v16) ricalcola anche l'EE, ne controlla la freschezza e delega a
  **`gas-monitor-entsoe`** produzione e rinnovabili; `gas-monitor-alert` valuta le regole per
  commodity (una email per utente e commodity).

**ENTSO-E (token dal 24/08/2026, secret `ENTSOE_API_KEY`)** — funzione dedicata `gas-monitor-entsoe`:
documentType **A75** (actual generation per type), processType A16, dominio `10YIT-GRTN-----B`
(Italia aggregata). Scrive `produzione_tot` (GWh/g) e `quota_pct` (solare B16 + eolico B18/B19).
⚠️ **Chunk MENSILI**: un anno intero per invocazione va in `WORKER_RESOURCE_LIMIT` (XML enorme).
I punti sono UTC → si aggregano per giorno **Europe/Rome** (verifica: il 15/08 risulta il minimo
della settimana, come dev'essere). Coerenza con Terna: i totali annui sono ~92% della produzione
netta ufficiale — atteso, ENTSO-E copre solo gli impianti sopra soglia (il fotovoltaico distribuito
resta fuori); per lo scenario non conta, il punteggio è un **percentile** sulla stessa serie.
⚠️ Il **2015 ha copertura incompleta** (222 TWh contro 250 del 2016, +12% non reale): la serie
parte dal 2016.

**Taratura EE (g012, 24-25/08/2026, confermata dal committente)** — pesi 10/15/30/30/15
(produzione/meteo/gas/rinnovabili/geopolitica), **soglia scenario 55** (lo scenario EE viaggia a ~49
e supera 60 di rado). Backtest: 32 finestre, 78% buone, +15,8% (con i parametri del gas: 70%,
+12,8%); robusta sui sotto-periodi, evita la finestra peggiore (feb 2025, −26%). I default delle
schede Admin EE sono allineati ai valori tarati. NON ritoccare senza rifare griglia + robustezza
(script della sessione 24-25/08 in memoria).

**Prestazioni del motore (g013, 25/08/2026)** — dopo g010 il ricalcolo era salito a 20-26 s e i run
del mattino (RPC via PostgREST, timeout 8 s) sono falliti per un'intera mattinata. Fix doppio:
(1) `norma` e `media5` MATERIALIZED (le stime di cardinalità collassavano a rows=1 → nested loop
~10k×; stessa classe di base5/exp5) → 9,7 s, A/B 0 differenze; (2) cintura di sicurezza
`ALTER ROLE service_role SET statement_timeout = '120s'` a livello DB. ⚠️ Dopo OGNI modifica al
motore misurare il tempo di `gas_ricalcola_segnale` per entrambe le commodity: sopra ~60 s il run
quotidiano torna a rischio anche con la cintura.

**Prezzo in vetrina (g011, 24/08/2026)** — `gas_commodity.prezzo_vetrina`: `giorno` (gas) o `mese`
(EE, media del mese IN CORSO come numero grande). Motivo: dentro un mese il PUN oscilla di 55–88
€/MWh e il mese è l'unità dei contratti indicizzati; il **motore resta giornaliero** perché il
mensile è definitivo solo a mese chiuso e darebbe ~80 punti dal 2020 invece di 2.400. Dashboard:
riga "mesi precedenti" (mese scorso + stesso mese anno prima) per entrambe le commodity; Dettaglio:
barre delle medie mensili del prezzo con confronto anno su anno (solo mesi con ≥20 giorni).

**Ciclo settimanale, parte 2 (g010, 24/08/2026)** — lo stesso problema del prezzo si presenta sulle
VARIABILI elettriche: la domenica si produce meno (meno domanda) e la quota rinnovabile sale per
costruzione. Punteggi medi mer→dom PRIMA: produzione 70,0→13,0, rinnovabili 44,2→77,5, **scenario
50,1→41,5**. Fix: `gas_variabili.media_gg` (1 = valore del giorno, 7 = media settimanale) messo a 7
su `produzione` e `rinnovabili` dell'EE; la media si applica PRIMA di riferimento e percentile.
Dopo: produzione 52,1–53,1, rinnovabili 61,4–63,5. A/B gas: **0 differenze**. Il frame di una window
function dev'essere costante → la media a 7 gg si calcola sempre e si sceglie con un CASE
(`media_gg` ammette solo 1 o 7).

**Ciclo settimanale del PUN (g009, 24/08/2026)** — il PUN vale in media **−12% il sabato e −20% la
domenica** rispetto ai feriali (nelle domeniche estive le ore centrali scendono a pochi €/MWh per il
fotovoltaico). Senza correzione il segnale scambiava ogni weekend per una flessione di mercato.
Perciò la **condizione** prezzo (tre trend, scostamenti, percentili) si calcola sulla **media mobile**
di `gas_commodity.prezzo_media_gg` giorni — **gas 1** (invariato, A/B verificato), **EE 7** — mentre
il prezzo **mostrato** resta quello del giorno; la media usata è in `gas_segnale.prezzo_riferimento`.
NON togliere la media dall'EE senza rifare il backtest.

## Nuove utenze

`imposta_pwd.py Nome --ruolo admin|cliente` (interattivo, la password la digita
l'utente/Daniele, mai in chat o nei log) + email di benvenuto dal template
**`EMAIL_BENVENUTO.md`** (standard deciso 20/08/2026: bozza Gmail personale,
**sempre cc energia@brosconsulenza.com**, password mai nell'email, paragrafo
Admin solo per ruolo admin). Revoca: flag `attivo=false` in `gas_utenti`,
non cancellare.

## Gotchas già pagati

- `task_runs.status` accetta solo `success|error`; PostgREST parte con statement_timeout 8s — alzato a
  120s per `service_role` il 25/08/2026 dopo una mattinata di run falliti (57014). Resta la regola:
  i ricalcoli full-history vanno via psycopg diretto o funzioni veloci (g003 hash-join, non subquery
  correlate), e dopo ogni modifica al motore si misura il tempo per ENTRAMBE le commodity.
- GIE ALSI `inventory` è un oggetto `{lng, gwh}`; `percent_rank()` ritorna double → `::numeric`
  prima di `round`.
- Regola alert di prova (utente Daniele, `indice > 50` → energia@): RIMOSSA a settembre 2026 in
  preparazione del go-live. `gas_alert` ora e' vuota: gli alert partiranno dalle regole dei clienti.
- Email: mittente Brevo verificato `energia@`, nessun riferimento all'automazione nel testo.
- Porta 8530 bloccata da un socket zombie (si libera al riavvio PC): per questo la preview è su 8532.
- **Un controllo ACCESSORIO non deve poter far fallire il run.** `giaOkOggi()` (lo skip se la
  pipeline ha gia' girato bene oggi) passava da `sb()`, che lancia su qualunque risposta non-ok: un
  504 del gateway REST arrivava al catch esterno e scriveva `status='error'` in `task_runs`, cioe'
  un'anomalia inesistente nel digest (09 e 10/09/2026, mentre il run delle 4:30 era riuscito). La query
  non c'entrava: gira in ~1 ms (index scan su 750 righe). Dalla **v16** `sb()` ritenta i transitori
  (rete, 5xx e il 401 `PGRST303` "JWT issued at future", che e' uno sfasamento d'orologio e non una
  credenziale: 3 tentativi, pause 1s/3s; su un 4xx vero esce subito) e le due guardie non propagano piu'.
  Stessa protezione in `promemoria-annuali` v5, dove pero' l'insert su `promemoria_inviati` e'
  diventato UPSERT: ha la PK (anno, promemoria_id, tipo) e un retry avrebbe preso 409 trasformando un
  promemoria INVIATO in un errore.

## Mercato a termine (g014, 26/10/2026): curva forward GME, informazione A PARTE dal segnale

Dopo il backtest offline di Timestral (Mistral; cartella `C:\Code\Forecast_PoC`, resoconto in
`RISULTATI.md`) il forecast di prezzo e' stato **scartato**: a 3/6/12 mesi nessuna taglia del modello
batte il random walk su gas o PUN, le bande coprono solo il 40-57% nelle crisi e sul minimo di aprile
2026 prevedeva un'ulteriore discesa. Decisione utente: niente "previsioni" nell'app; al loro posto la
**curva forward del GME** come pannello informativo in Dashboard, **senza toccare scenario, prezzo,
segnale o alert** (per non peggiorare lo strumento).
- Tabella `gas_forward` (commodity, seduta, prodotto, tipo M|Q|CY|SS|WS, consegna_dal/al, prezzo):
  prezzi di CONTROLLO del GME (MT-GAS per il gas, MTE *baseload* per l'EE; BoM e peak-load esclusi).
  La scrive ogni notte il job VPS `dati-mercato` di App_Offerte (`app/data_updater/forward.py`,
  ruolo `bros_jobs`; rilegge le ultime 5 sedute, upsert idempotente; un fetch fallito e' un
  `avviso`, niente email). Storico dal 2020 caricato con `backfill-forward`.
- Dashboard (`moduli/dashboard.py`, sezione 2b, sotto il box del segnale): numero grande = media
  dei prossimi 12 mesi quotati, pillola = scostamento vs prezzo attuale (gas: prezzo del giorno;
  EE: media del mese in corso, perche' il forward mensile e' una media mensile), mini-griglia
  M+1/M+2/M+3, medie 3 e 6 mesi, anno solare prossimo; grafico a barre della curva mensile con la
  linea tratteggiata del prezzo attuale. Curva mensile = prodotto M se quotato, altrimenti Q,
  poi stagione, poi CY; nelle sedute di fine mese il mese successivo e' solo BoM e si salta
  (si prendono comunque 12 punti). Caption fissa: "non e' una previsione".
- Guida: paragrafo nel tab Dashboard + FAQ "Perche' il monitor non fa previsioni di prezzo?".
- Non ancora nel PDF/Excel di export.
