-- ============================================================
-- Migrazione g012 — TARATURA del segnale ENERGIA ELETTRICA (24/08/2026).
--
-- Prima taratura dedicata dell'EE (finora girava con pesi e soglia ereditati
-- dal gas: 30/15/25/15/15, soglia 60). Griglia 7 combinazioni di pesi x 3
-- soglie sul backtest 2020-2026 (finestre >=3 gg, prezzo medio — media 7 gg —
-- dei 90 gg successivi), piu' verifica di robustezza sui sotto-periodi
-- 2020-22 / 2023-24 / 2025-26. Scelta dal committente: configurazione "C".
--
--   pesi:   produzione 10 · meteo 15 · prezzo gas 30 · rinnovabili 30 · geo 15
--   soglia: 55 (lo scenario EE viaggia in media a ~49 e supera 60 di rado:
--           la soglia del gas era troppo restrittiva)
--
-- Numeri: 32 finestre, 78% buone, +15,8% (attuale: 30 / 70% / +12,8%);
-- 2020-22: 10/10 buone +34% · 2023-24: 9/12 +9,0% · 2025-26: 6/10 +6,0%
-- (attuale: +2,1% nel 2025-26); evita la finestra peggiore (feb 2025, -26%).
-- Motivazione dei pesi: il prezzo gas e' il costo marginale del PUN (30);
-- le rinnovabili catturano l'effetto-offerta senza il bias della produzione
-- ENTSO-E (che non vede il fotovoltaico distribuito) -> 30; la produzione
-- scende a 10 ma NON a zero (la variante senza produzione perdeva 3 punti
-- di guadagno). Meteo e geopolitica invariati.
--
-- La configurazione entra come NUOVA VERSIONE di gas_pesi (storia intatta,
-- reversibile da Admin); i default delle schede Admin vengono allineati cosi'
-- "Ripristina default" riporta ai valori tarati, come per il gas.
-- ============================================================

-- nuova versione EE = ultima versione EE con pesi e soglia aggiornati
insert into public.gas_pesi (commodity, pesi, autore)
select 'ee',
       pesi || jsonb_build_object(
         'scenario', jsonb_build_object(
           'produzione', 10, 'meteo', 15, 'gas', 30, 'rinnovabili', 30, 'geopolitica', 15),
         'scenario_soglia', 55),
       'g012 (24/08/2026) — taratura EE confermata dal committente: config C (10/15/30/30/15, soglia 55); backtest 32 finestre, 78% buone, +15,8%'
from public.gas_pesi where commodity = 'ee' order by versione desc limit 1;

-- default delle schede Admin allineati ai valori tarati
update public.gas_parametri_doc set valore_default = 10 where commodity='ee' and chiave='scenario.produzione';
update public.gas_parametri_doc set valore_default = 15 where commodity='ee' and chiave='scenario.meteo';
update public.gas_parametri_doc set valore_default = 30 where commodity='ee' and chiave='scenario.gas';
update public.gas_parametri_doc set valore_default = 30 where commodity='ee' and chiave='scenario.rinnovabili';
update public.gas_parametri_doc set valore_default = 15 where commodity='ee' and chiave='scenario.geopolitica';
update public.gas_parametri_doc set valore_default = 55 where commodity='ee' and chiave='scenario_soglia';
update public.gas_parametri_doc
   set spiegazione = spiegazione || ' Taratura EE del 24/08/2026 (config C): lo scenario elettrico viaggia in media a ~49 e supera 60 di rado, per questo la soglia e'' 55 e non 60 come nel gas.'
 where commodity='ee' and chiave='scenario_soglia';
