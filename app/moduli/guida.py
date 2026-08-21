"""
Modulo Guida — manuale d'uso integrato: cosa fa l'app, come leggere la
dashboard, come configurare alert e parametri admin, fonti e limiti.
Solo testo (niente query): si carica sempre.
"""
from __future__ import annotations

import streamlit as st

st.title("📖 Guida")
st.caption("Come leggere l'Energy Market Monitor e come configurarlo.")

tab_cosa, tab_dash, tab_alert, tab_admin, tab_fonti, tab_faq = st.tabs([
    "🎯 Cos'è", "📊 Leggere la dashboard", "🔔 Alert", "⚙️ Parametri (admin)", "🗂 Fonti e limiti",
    "❓ Domande frequenti"])

# =============================================================================
with tab_cosa:
    st.markdown("""
### A cosa serve
L'**Energy Market Monitor** aiuta a individuare le **finestre favorevoli per fissare il prezzo del gas e dell'energia elettrica**
(fixing su contratti annuali, tranche di approvvigionamento). Ogni mattina alle 06:30 aggiorna i dati,
ricalcola il segnale e, se hai impostato soglie, ti manda un'email.

### Tre domande, tre indicatori
| Indicatore | Domanda | Come si legge |
|---|---|---|
| **Scenario di approvvigionamento** (0–100) | I fondamentali sono dalla parte di chi compra? | ≥ 60 favorevole · 40–59 neutro · < 40 sfavorevole. Alto = stoccaggi pieni, LNG abbondante, meteo mite, contesto geopolitico calmo |
| **Prezzo MGP-GAS** (€/MWh) | Il prezzo è in flessione rispetto alla sua tendenza? | Confrontato con **tre rette di trend**: breve (20 gg, il radar), medio (60 gg, il riferimento per il fixing), lungo (180 gg, il contesto) |
| **Segnale del giorno** | È il momento? | Un livello da *Attesa* a *Trend consolidato*, con un testo in chiaro e il conteggio dei giorni favorevoli consecutivi |

### I livelli del segnale
| Intensità | Livello | Significato |
|---|---|---|
| 0 | **Attesa** / Finestra chiusa | scenario non favorevole, o finestra appena conclusa |
| 1 | **Monitorare** | scenario favorevole ma il prezzo non ha ancora ceduto |
| 2 | **Prime condizioni** | scenario favorevole *e* prezzo in flessione: 1–2 giorni |
| 2 | **Opportunità di prezzo** | prezzo in netta flessione (≥ 7% sotto il trend medio) con scenario non sfavorevole — *possibile tranche tattica, potenziale finestra di fixing-approvvigionamento* |
| 3 | **Minimo di periodo** | prezzo tra i più bassi degli ultimi 6 o 18 mesi — criterio assoluto sul livello, indipendente dal trend |
| 3 | **Segnale iniziale** | condizioni favorevoli da almeno 3 giorni — valutare una prima tranche |
| 4 | **Segnale di fixing** | da almeno 5 giorni — finestra utile per coperture |
| 5 | **Trend consolidato** | da almeno 10 giorni — finestra ampia, coperture più consistenti |

> I giorni e le soglie sono **parametri configurabili** dall'amministratore (tab Admin). Il segnale è
> **retrospettivo**: dice che il prezzo è basso rispetto al passato recente. Non prevede il futuro:
> la componente previsionale (forecast) è prevista in una fase successiva.

### Due commodity, un solo monitor
In alto nella barra laterale scegli **Gas** o **Energia elettrica**: tutte le pagine (Dashboard, Dettaglio,
Alert, Export, Admin) si riferiscono alla commodity selezionata. Il motore del segnale è lo stesso; cambiano
il **prezzo di riferimento** e le **variabili dello scenario**:

| | Gas | Energia elettrica |
|---|---|---|
| Prezzo | **MGP-GAS** (GME), €/MWh | **PUN** (GME, media delle 24 ore), €/MWh |
| Variabili dello scenario | stoccaggi · meteo · LNG · geopolitica | produzione zonale (7 zone) · meteo · prezzo gas · quota rinnovabili · geopolitica |
| Meteo | più mite = favorevole | **vicino alla norma** = favorevole (caldo e freddo anomali alzano entrambi la domanda) |

Per l'elettrico la produzione zonale e la quota rinnovabili arrivano da **ENTSO-E Transparency** (dati
trasmessi da Terna): finché una serie non è ancora caricata conta come **neutra (50/100)** nello scenario e
la Dashboard lo segnala. I pesi e le soglie dell'elettrico hanno una taratura propria (tab Admin).

### Le pagine
- **Dashboard** — la situazione di oggi e lo storico.
- **Dettaglio** — ogni variabile con il suo storico, il confronto pluriennale e il punteggio.
- **Alert** — le tue soglie email.
- **Export** — snapshot PDF e serie storiche Excel.
- **Admin** (solo amministratori) — parametri del segnale e stato della pipeline.
""")

# =============================================================================
with tab_dash:
    st.markdown("""
### I due pannelli in alto
**Scenario di approvvigionamento** — il numero grande (in blu) è il **valore di oggi**. In alto a destra,
l'etichetta *media 7 gg · fascia*: la media mobile è il valore su cui scattano le regole del segnale (il valore
puntuale oscilla troppo) e la fascia (favorevole / neutro / sfavorevole) si riferisce a quella. Sotto, i quattro
punteggi che compongono lo scenario con la loro barra: stoccaggi, meteo, LNG, geopolitica — 0–100,
**alto = favorevole all'acquirente**.

**Prezzo gas MGP-GAS** — il prezzo day-ahead dell'ultimo giorno in €/MWh, la variazione sul giorno prima, in
alto a destra il verdetto *vs trend · in flessione / non in flessione*, e sotto quattro numeri allineati:
- **vs breve** (20 gg): quanto il prezzo sta sopra/sotto la retta di breve periodo — il radar
- **vs medio** (60 gg): il confronto che conta per il fixing
- **lungo** (180 gg): in salita / piatto / in discesa — il contesto
- **sui 6 mesi: più alto del X %**: il percentile del prezzo di oggi rispetto agli ultimi 6 mesi; sotto il 5 % =
  tra i più bassi (è la condizione del *minimo di periodo*)

### Il box "Segnale di oggi"
Tre colonne, dalla più importante alla più leggera:
- 🎯 **Verdetto** — il livello in grande (es. *Attesa*, *Opportunità di prezzo*, *Segnale di fixing*) e sotto, in
  elenco, il perché: scenario (oggi e media) e prezzo (scostamenti dai trend).
- 🧭 **Cosa fare** — l'azione (es. *Nessuna tranche consigliata*, *Valutare una prima tranche*) e **cosa deve
  cambiare** per salire di livello, con i numeri di oggi.
- 📶 **Forza del segnale** — un termometro a 6 gradini dal basso: *Nessun segnale · Osservare · Occasione · Primo
  segnale · Fixing · Finestra ampia*; si accende fino al livello del giorno. Lo zero è un gradino vero: se è acceso
  solo quello, non c'è segnale.
Il colore è una scala di blu (più scuro = più forte). Non è un semaforo: un segnale forte è un'**informazione**.

### Le quattro variabili
Una tessera per ciascuna, con il valore fisico (es. 79,8 % di riempimento, 26,9 °C, 538 GWh/g, GPR 144),
cosa misura e la **barra del punteggio** 0–100 (alto = favorevole).

### Lo storico
- **Prezzo e trend** — linea **rossa** = prezzo; le tre rette: grigio punteggiato = breve, **verde acqua
  tratteggiato = medio** (il riferimento per il fixing), blu scuro pieno = lungo; le **bande** azzurre sono i giorni
  con un segnale acceso: più scure = livello più alto. Legenda sopra il grafico.
  Passa il mouse sulla linea per vedere prezzo, scostamenti e segnale del giorno.
- **Scenario** — area blu del valore giornaliero e linea tratteggiata della soglia favorevole.
- Il selettore **Periodo** cambia entrambi i grafici: Mese · 3 mesi (default) · Da inizio anno · 12 mesi ·
  3 anni · Tutto dal 2020. Assi e tooltip sono in italiano.

### Da dove vengono i numeri
Tutto è **pre-calcolato** ogni mattina: la dashboard non interroga fonti esterne, si apre in pochi secondi
ed è la stessa per tutti gli utenti. "Dato del gg/mm" nel pannello prezzo indica l'ultimo giorno disponibile.
I valori degli **ultimi 1–2 giorni sono provvisori**: alcune fonti pubblicano in ritardo e l'aggiornamento
del mattino successivo li rivede — ogni numero mostrato è il **miglior dato disponibile in quel momento**
(il dettaglio nelle Domande frequenti).
""")

# =============================================================================
with tab_alert:
    st.markdown("""
### Come funzionano
Ogni mattina, dopo l'aggiornamento dei dati, il sistema confronta il valore del giorno con le soglie che hai
impostato. Se una o più soglie sono raggiunte ricevi **una sola email** con:
- la **situazione di oggi** (scenario, prezzo con i confronti ai trend, livello del segnale e testo);
- la tabella delle soglie raggiunte (grandezza, valore, condizione).

### Impostare una soglia (pagina Alert)
1. **Indirizzo email** — inseriscilo e salva. Senza email non ricevi notifiche.
2. **Nuova soglia** — scegli:
   - la **grandezza**: *livello del segnale* (consigliata), scenario, prezzo, stoccaggi, temperatura, LNG, GPR;
   - la **condizione**: *sale sopra* / *scende sotto* (per il segnale: *raggiunge almeno*);
   - il **valore** (per il segnale scegli un livello: es. *3 · minimo di periodo / segnale iniziale*
     = avvisami quando il livello del giorno è almeno 3);
   - la **pausa** in giorni: dopo un invio, la stessa soglia tace per quel numero di giorni.
3. **Le tue soglie** — per ognuna vedi stato, pausa e ultimo invio; ⏯ sospende/riattiva, 🗑 elimina.

### Esempi utili
| Obiettivo | Soglia |
|---|---|
| "Avvisami quando c'è un'occasione, anche tattica" | Livello del segnale *raggiunge almeno* **2** |
| "Solo quando è una finestra vera" | Livello del segnale *raggiunge almeno* **4 · segnale di fixing** |
| "Se il prezzo scende sotto 45 €/MWh" | Prezzo MGP-GAS *scende sotto* **45** |
| "Se gli stoccaggi vanno sotto l'80%" | Riempimento stoccaggi *scende sotto* **80** |

### Regole anti-rumore
- Una soglia già notificata per lo stesso giorno **non viene rinviata**.
- Dopo un invio la soglia tace per i giorni di **pausa** (default 7).
- Più soglie raggiunte lo stesso giorno = **una** email.
""")

# =============================================================================
with tab_admin:
    st.markdown("""
### Tab "Parametri del segnale"
Tutti i parametri del motore sono modificabili in autonomia. Per ciascuno trovi **nome, spiegazione di cosa fa,
effetto di alzarlo o abbassarlo, unità e valore di default**. Il salvataggio crea una **nuova versione**
della configurazione (con il tuo nome e una nota facoltativa) e **ricalcola subito il segnale su tutto lo
storico**: puoi vedere l'effetto in Dashboard (bande, livelli) e, se non ti convince, ripristinare i default.

I gruppi:

**Scenario — pesi** (devono sommare 100): quanto contano stoccaggi (35), meteo (25), LNG (20), geopolitica (20).

**Scenario**: soglia *favorevole* (60) · giorni della media mobile (7) · scenario minimo per l'opportunità di prezzo (35).

**Prezzo — orizzonti**: giorni delle tre rette di trend, breve (20) / medio (60) / lungo (180); devono essere crescenti.

**Prezzo — regola**: flessione minima sul breve (3%) · tolleranza sul medio (1%) · flessione sul medio per
l'*opportunità* (7%) · pendenza massima del lungo (+0,2%/g: blocca i rally) · pendenza minima del lungo
(−0,5%/g: blocca il rientro da un picco di crisi) · limite di caduta libera sul breve (−1%/g).

**Prezzo — minimo di periodo**: finestra 1 (6 mesi) · finestra 2 (18 mesi) · percentile (5).

**Segnale — gradini**: giorni per *segnale iniziale* (3) / *segnale di fixing* (5) / *trend consolidato* (10); crescenti.

### Come tarare (suggerimento di metodo)
1. Cambia **un parametro alla volta**, salva con una nota che dica perché.
2. Guarda lo **storico** in Dashboard su "Tutto": le bande dovrebbero cadere sui minimi che tu, col senno di poi,
   avresti voluto fissare — e *non* sui crolli di crisi (dic-2022, mar-2023) né sui rimbalzi (mag-2026).
3. Se il risultato peggiora, **ripristina default** o torna a una versione precedente dallo storico versioni.

I default attuali sono il frutto del test 2020–2026: 29 finestre con segnale ≥ 3 giorni, 25 risultate buone
(prezzo medio dei 90 giorni successivi più alto), guadagno medio +16%.

### Tab "Stato pipeline"
Ultimo giorno disponibile per ogni serie, esecuzioni della pipeline (orario, esito, durata) e stato delle
sorgenti. Se una serie è ferma da più giorni, è lì che si vede.

### Utenti
Gli utenti dell'Energy Market Monitor hanno credenziali **proprie** (non quelle dell'ERP). Ruoli: *admin*
(tutto) e *cliente* (dashboard, dettaglio, alert, export — non i parametri). La creazione utenti e le password
si gestiscono dallo script `imposta_pwd.py` nel repo dell'app.
""")

# =============================================================================
with tab_fonti:
    st.markdown("""
### Fonti (tutte pubbliche e gratuite)
| Variabile | Fonte | Aggiornamento |
|---|---|---|
| Prezzo gas | **GME — MGP-GAS**, mercato del giorno prima, €/MWh | giornaliero (job notturno) |
| Stoccaggi | **GIE AGSI+** — riempimento %, iniezione, erogazione (Italia) | giornaliero |
| LNG | **GIE ALSI** — send-out e giacenza rigassificatori (Italia) | giornaliero |
| Meteo | **Open-Meteo / ERA5** — temperatura media del paniere città pesato per consumo gas (MI 30 · RM 20 · TO 15 · BO 15 · FI 10 · VE 10); norma dal 1991 | giornaliero |
| Geopolitica | **GPR daily** — Geopolitical Risk Index di Caldara & Iacoviello | giornaliero |

### Come nascono i punteggi
Per ogni variabile il valore di oggi viene confrontato con il suo riferimento (media dei 5 anni precedenti
nello stesso periodo per stoccaggi e LNG; norma pluriennale dello stesso giorno per il meteo; il valore stesso
per il GPR) e trasformato in **rango percentile sullo storico 2020–oggi**, orientato a favore
dell'acquirente. Lo scenario è la media ponderata dei quattro punteggi.

### Limiti da conoscere
- Il segnale è **retrospettivo**: confronta il prezzo con il suo passato, non con il futuro. Un minimo che sarà
  tale solo col senno di poi (es. la flessione di metà aprile 2026 dentro un rally) **non** viene segnalato: è il
  caso che la fase forecast dovrà coprire.
- Il mercato è **nervoso**: per questo le condizioni usano medie e filtri. Meglio perdere qualche minimo che
  comprare a metà crollo.
- Dato mancante in una fonte → si usa l'ultimo disponibile e lo si segnala.

### Disclaimer
Le informazioni hanno scopo informativo e di supporto all'approvvigionamento; **non costituiscono consulenza
finanziaria**. La decisione resta dell'utente.
""")

# =============================================================================
with tab_faq:
    st.markdown("""
### Le domande che vengono più spesso

**Nel pannello Scenario vedo 48 "oggi" e accanto "media 7 gg 52": quale conta?**
Il **48** è il valore di oggi: è il numero da guardare per sapere come stanno i fondamentali adesso.
Il **52** è la media degli ultimi 7 giorni ed è il valore su cui **scattano le regole** del segnale. Perché la media?
Perché il valore giornaliero oscilla molto (il rischio geopolitico e il meteo saltano da un giorno all'altro) e con il
valore puntuale il conteggio dei giorni favorevoli si azzererebbe di continuo. Il caso che ce l'ha insegnato: 6–12
agosto 2026, scenario a giorni alterni 46/55 con prezzo a −11% sul trend medio — senza la media nessun segnale partiva.

**Ieri lo scenario segnava un valore, oggi lo stesso giorno ne mostra un altro: perché è cambiato?**
Perché alcune fonti pubblicano con 1–2 giorni di ritardo (GIE comunica stoccaggi e LNG la sera con il dato
del giorno prima). Quando un dato non è ancora uscito, il calcolo usa **provvisoriamente l'ultimo valore
disponibile**; la mattina dopo, quando arriva il dato reale, il ricalcolo — che rifà ogni giorno tutto lo
storico — **rivede gli ultimi giorni**. Ogni numero mostrato è quindi il **miglior dato disponibile in quel
momento**: meglio un valore provvisorio subito che un buco. Due conseguenze pratiche: la variazione
"vs ieri" confronta con il valore di ieri *rivisto* (non con quello che vedevi a schermo ieri), e le regole
del segnale usano la **media a 7 giorni**, che assorbe anche queste revisioni.

**Cosa significa "sui 6 mesi: più alto del 96%"?**
Che il prezzo di oggi è **più alto del 96% dei prezzi degli ultimi sei mesi** — cioè siamo vicini ai massimi del
semestre. È il "percentile" del prezzo. Serve al segnale **Minimo di periodo**, che scatta quando il prezzo è
**più basso del 95%** dei prezzi (sotto il 5° percentile) degli ultimi 6 o 18 mesi: tra i più bassi, a prescindere
dal trend. Oggi siamo all'estremo opposto.

**"vs breve +2,0 %", "vs medio −5,3 %": come li leggo?**
Sono gli scostamenti del prezzo di oggi dalle rette di tendenza: +2,0 % sopra la retta a 20 giorni, −5,3 % sotto
quella a 60. Per il segnale di fixing conta soprattutto il **medio** (il riferimento su contratti annuali); il breve è il
radar delle flessioni in corso; il lungo (in salita / piatto / in discesa) dice in che fase del ciclo siamo.

**Perché "prezzo non in flessione" se è a −5,3 % sul medio?**
Perché la condizione richiede anche che **sul breve** sia sotto di almeno il 3 % (oggi è +2 %) — oppure che sul medio sia
sotto di almeno il 7 %. Una flessione "vera" deve vedersi sul breve, o essere netta sul medio. Le soglie sono parametri
(tab Admin).

**Il verdetto dice "Attesa" e l'azione "Nessuna tranche consigliata": non è la stessa cosa?**
Il verdetto è *dove siamo*; l'azione dice *cosa fare e cosa dovrebbe cambiare* per passare a un livello superiore
(es. "manca lo scenario: almeno 60, oggi 52"). Sono distinti apposta.

**"Da inizio anno" cosa mostra?**
Dal 1° gennaio dell'anno corrente a oggi (l'inglese *YTD, year-to-date*). Serve per leggere "come sta andando
quest'anno" invece di una finestra mobile fissa.

**Perché le bande dello storico sono in blu e non verde/giallo/rosso?**
Perché un segnale forte è un'**informazione**, non un allarme: il colore indica l'intensità (più scuro = più forte), non
"buono/cattivo". Il rosso resta al marchio Bros (e alla linea del prezzo).

**Perché la finestra di aprile 2026 (prezzo a 39) non è stata segnalata?**
Perché sul momento era indistinguibile da un "coltello che cade": il trend lungo saliva con forza (rally di marzo) e il
breve crollava; inoltre 39 era al 63° percentile dei 6 mesi precedenti (l'inverno era stato più basso) — un minimo
*del rally*, non di periodo. Che fosse il minimo dell'anno si è visto solo dopo: è il caso di riferimento per il
forecast (fase successiva).
""")
