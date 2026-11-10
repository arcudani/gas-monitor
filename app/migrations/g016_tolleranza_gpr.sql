-- g016 (10/11/2026) — tolleranza di freschezza del GPR da 7 a 10 giorni.
-- Il file .xls e' pubblicato a mano dagli autori, di norma una volta a settimana:
-- a 7 l'avviso scattava al primo giorno di ritardo. Stesso valore della mappa
-- TOLLERANZA nella Edge Function gas-monitor (v18). Idempotente.
update public.gas_variabili
   set tolleranza_gg = 10
 where variabile = 'geopolitica' and tolleranza_gg <> 10;
