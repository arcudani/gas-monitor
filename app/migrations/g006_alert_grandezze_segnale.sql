-- g006: le soglie alert accettano anche 'scenario' (0-100) e 'segnale' (livello 0-5, requisiti v1.6)
alter table public.gas_alert drop constraint if exists gas_alert_grandezza_check;
alter table public.gas_alert add constraint gas_alert_grandezza_check
  check (grandezza in ('indice','scenario','segnale','prezzo','stoccaggi','meteo','lng','geopolitica'));
comment on column public.gas_alert.grandezza is
  'indice = pressione storica; scenario = 0-100 favorevole all''acquirente; segnale = livello 0 attesa,1 monitorare,2 prime,3 iniziale,4 fixing,5 trend (condizione sopra = inclusiva); altre = valore della variabile';

-- NB (19/08): gas_ricalcola_indice (g003) e' stata ri-creata sul DB con una sola
-- differenza: legge i pesi dall'ultima versione di gas_pesi CHE CONTIENE la chiave
-- top-level 'prezzo' (formato vecchio), cosi' la config v1.6 (scenario/segnale,
-- formato nuovo) non la rompe. La funzione resta solo per lo storico di confronto.
--   select pesi, versione into v_pesi, v_ver from public.gas_pesi
--   where pesi ? 'prezzo' order by versione desc limit 1;
