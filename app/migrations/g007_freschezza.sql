-- g007: freschezza delle serie (monitoraggio caricamenti, richiesta utente 19/08)
-- Una riga per serie: ultimo giorno disponibile e giorni trascorsi. Usata dalla
-- pipeline (run in errore + email interna se oltre tolleranza) e dalla dashboard (banner).
create or replace function public.gas_freschezza()
returns table (serie text, ultimo date, giorni_fa int)
language sql stable as $$
  select 'prezzo MGP_GAS', max(data), (current_date - max(data))::int from public.indici_mercato where codice='MGP_GAS' and stato='consuntivo'
  union all select 'segnale', max(data), (current_date - max(data))::int from public.gas_segnale where commodity='gas'
  union all select variabile || ' ' || metrica, max(data), (current_date - max(data))::int
    from public.gas_serie where commodity='gas'
      and metrica in ('t_media_paniere','riempimento_pct','lng_sendout','gpr')
    group by variabile, metrica
$$;
grant execute on function public.gas_freschezza() to service_role;
