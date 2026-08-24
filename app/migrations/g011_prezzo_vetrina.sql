-- ============================================================
-- Migrazione g011 — QUALE PREZZO VA IN VETRINA (24/08/2026).
--
-- Domanda del committente: "come lo vedi di esporre come dato il PUN mensile
-- e non quello giornaliero?". Analisi: dentro un singolo mese il PUN oscilla
-- di 55-88 €/MWh (luglio 2026: da 98,71 a 186,23 con media 157,04), quindi il
-- singolo giorno dice poco sul mese, ed e' il MESE l'unita' che il cliente
-- riconosce e paga sui contratti indicizzati. Il giornaliero pero' resta
-- indispensabile al MOTORE (il mensile e' definitivo solo a mese chiuso e
-- darebbe ~80 punti dal 2020 invece di 2.400: percentili e trend perderebbero
-- significativita', e le finestre durano in media 7 giorni).
--
-- Decisione: il motore NON cambia (resta giornaliero con media mobile, g009);
-- cambia solo cosa si mette in evidenza:
--   prezzo_vetrina = 'giorno' -> numero grande = prezzo del giorno (gas:
--       MGP-GAS e' piu' stabile e il fixing gas e' piu' tattico)
--   prezzo_vetrina = 'mese'   -> numero grande = media del mese IN CORSO,
--       con giorno e media 7 gg nella riga sotto (energia elettrica: nessuno
--       compra "il PUN di lunedi'")
-- In entrambi i casi la dashboard mostra anche mese precedente e stesso mese
-- dell'anno scorso, per dare il contesto di fatturazione.
-- Additiva, RLS invariata.
-- ============================================================

alter table public.gas_commodity
  add column if not exists prezzo_vetrina text not null default 'giorno'
  check (prezzo_vetrina in ('giorno', 'mese'));
comment on column public.gas_commodity.prezzo_vetrina is
  'Valore in evidenza nel pannello prezzo: giorno = prezzo del giorno; mese = media del mese in corso (il motore resta comunque giornaliero).';

update public.gas_commodity set prezzo_vetrina = 'mese' where commodity = 'ee';
