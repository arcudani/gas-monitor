-- ============================================================
-- Migrazione g002 — serie dati, pesi e indice sintetico del Gas Monitor.
--
-- gas_serie: serie storiche normalizzate (RNF: data, commodity, variabile,
--   metrica, valore, fonte) scritte dalla Edge Function `gas-monitor`.
--   Il PREZZO non sta qui: vive gia' in indici_mercato (MGP_GAS).
-- gas_pesi: configurazione pesi storicizzata (RF-07); una riga per versione.
-- gas_indice: indice 0-100 giornaliero con i punteggi per variabile.
-- gas_ricalcola_indice(dal, al): rango percentile di ogni variabile sul
--   proprio storico 2020-oggi, orientato in direzione rialzista, media
--   ponderata con i pesi correnti. Variabile senza dato -> 50 (neutrale),
--   il punteggio geopolitico resta null finche' la fonte non c'e'.
--
-- Convenzioni: prefisso gas_*, SOLO ADDITIVA, RLS deny-all (l'accesso e'
-- del service_role della Edge Function e del ruolo postgres delle app).
-- ============================================================

create table public.gas_serie (
    data       date not null,
    commodity  text not null default 'gas',
    variabile  text not null,   -- meteo | stoccaggi | lng | geopolitica
    metrica    text not null,   -- t_media_paniere | riempimento_pct | iniezione | erogazione | lng_sendout | lng_giacenza | gpr
    valore     numeric(20,6) not null,
    fonte      text not null default '',
    updated_at timestamptz not null default now(),
    primary key (data, commodity, variabile, metrica)
);
comment on table public.gas_serie is
    'Serie storiche del Gas Market Monitor (multi-commodity by design). Prezzo escluso: sta in indici_mercato.';

create table public.gas_pesi (
    versione   int generated always as identity primary key,
    pesi       jsonb not null,
    valido_dal timestamptz not null default now(),
    autore     text not null default ''
);
comment on table public.gas_pesi is
    'Pesi dell''indice sintetico, storicizzati (somma=100; prezzo_sub_* e'' il sub-peso interno della variabile prezzo).';

insert into public.gas_pesi (pesi, autore) values (
    '{"prezzo":35,"prezzo_sub_mgp":70,"prezzo_sub_lng":30,"stoccaggi":25,"meteo":20,"geopolitica":20}'::jsonb,
    'seed requisiti v1.4 (18/08/2026)'
);

create table public.gas_indice (
    data          date not null,
    commodity     text not null default 'gas',
    valore        numeric(6,2) not null,        -- 0-100, pressione rialzista
    punteggi      jsonb not null default '{}'::jsonb,
    versione_pesi int not null references public.gas_pesi(versione),
    updated_at    timestamptz not null default now(),
    primary key (data, commodity)
);
comment on table public.gas_indice is
    'Indice sintetico 0-100 (piu'' alto = piu'' opportuno coprirsi) con i punteggi per variabile.';

-- ---------- RICALCOLO INDICE ----------
create or replace function public.gas_ricalcola_indice(p_dal date, p_al date)
returns integer
language plpgsql
as $$
declare
  v_pesi jsonb;
  v_ver  int;
  n      int;
begin
  select pesi, versione into v_pesi, v_ver
  from public.gas_pesi order by versione desc limit 1;

  with
  -- PREZZO: momentum 5/20 gg del MGP-GAS, percentile sul 2020-oggi
  pz_base as (
    select data,
           avg(valore) over (order by data rows between 4 preceding and current row)
           / nullif(avg(valore) over (order by data rows between 19 preceding and current row), 0)
           - 1 as orientato
    from public.indici_mercato
    where codice = 'MGP_GAS' and stato = 'consuntivo'
  ),
  pz as (
    select data, percent_rank() over (order by orientato) * 100 as score
    from pz_base where data >= date '2020-02-01'   -- prime 20 medie parziali escluse
  ),
  -- METEO: freddo = norma pluriennale (stesso giorno dell'anno) - T paniere
  met_base as (
    select data, valore from public.gas_serie
    where commodity = 'gas' and variabile = 'meteo' and metrica = 't_media_paniere'
  ),
  met_norma as (
    select extract(doy from data) as doy, avg(valore) as t_norma
    from met_base group by 1
  ),
  met_or as (
    select b.data, (n.t_norma - b.valore) as orientato
    from met_base b join met_norma n on n.doy = extract(doy from b.data)
    where b.data >= date '2020-01-01'
  ),
  met as (
    select data, percent_rank() over (order by orientato) * 100 as score from met_or
  ),
  -- STOCCAGGI: sotto la media 5 anni (stesso giorno +-3) = rialzista
  sto_base as (
    select data, valore from public.gas_serie
    where commodity = 'gas' and variabile = 'stoccaggi' and metrica = 'riempimento_pct'
  ),
  sto_or as (
    select b.data,
           coalesce((select avg(v.valore) from sto_base v
                     where abs(extract(doy from v.data) - extract(doy from b.data)) <= 3
                       and v.data < b.data
                       and v.data >= b.data - interval '5 years'), b.valore)
           - b.valore as orientato
    from sto_base b
    where b.data >= date '2020-01-01'
  ),
  sto as (
    select data, percent_rank() over (order by orientato) * 100 as score from sto_or
  ),
  -- LNG: send-out sotto la media 5 anni = offerta debole = rialzista
  lng_base as (
    select data, valore from public.gas_serie
    where commodity = 'gas' and variabile = 'lng' and metrica = 'lng_sendout'
  ),
  lng_or as (
    select b.data,
           coalesce((select avg(v.valore) from lng_base v
                     where abs(extract(doy from v.data) - extract(doy from b.data)) <= 3
                       and v.data < b.data
                       and v.data >= b.data - interval '5 years'), b.valore)
           - b.valore as orientato
    from lng_base b
    where b.data >= date '2020-01-01'
  ),
  lng as (
    select data, percent_rank() over (order by orientato) * 100 as score from lng_or
  ),
  -- GEOPOLITICA: percentile del GPR daily (se/quando alimentato)
  geo as (
    select data, percent_rank() over (order by valore) * 100 as score
    from public.gas_serie
    where commodity = 'gas' and variabile = 'geopolitica' and metrica = 'gpr'
      and data >= date '2020-01-01'
  ),
  giorni as (
    select d::date as data from generate_series(p_dal, p_al, interval '1 day') d
  ),
  calc as (
    -- dato mancante alla data -> ultimo disponibile (RF-06)
    select g.data,
      (select score from pz  where data <= g.data order by data desc limit 1) as s_pz,
      (select score from met where data <= g.data order by data desc limit 1) as s_met,
      (select score from sto where data <= g.data order by data desc limit 1) as s_sto,
      (select score from lng where data <= g.data order by data desc limit 1) as s_lng,
      (select score from geo where data <= g.data order by data desc limit 1) as s_geo
    from giorni g
  )
  insert into public.gas_indice (data, commodity, valore, punteggi, versione_pesi)
  select data, 'gas',
    round((
        (v_pesi->>'prezzo')::numeric *
            ( (v_pesi->>'prezzo_sub_mgp')::numeric / 100 * coalesce(s_pz, 50)
            + (v_pesi->>'prezzo_sub_lng')::numeric / 100 * coalesce(s_lng, 50) )
      + (v_pesi->>'stoccaggi')::numeric   * coalesce(s_sto, 50)
      + (v_pesi->>'meteo')::numeric       * coalesce(s_met, 50)
      + (v_pesi->>'geopolitica')::numeric * coalesce(s_geo, 50)
    ) / 100, 2),
    jsonb_build_object(
      'prezzo',      round(coalesce(s_pz, 50)::numeric, 1),
      'lng',         round(coalesce(s_lng, 50)::numeric, 1),
      'stoccaggi',   round(coalesce(s_sto, 50)::numeric, 1),
      'meteo',       round(coalesce(s_met, 50)::numeric, 1),
      'geopolitica', case when s_geo is null then null
                          else round(s_geo::numeric, 1) end),
    v_ver
  from calc
  where s_pz is not null          -- niente indice prima dell'inizio delle serie
  on conflict (data, commodity) do update
    set valore = excluded.valore, punteggi = excluded.punteggi,
        versione_pesi = excluded.versione_pesi, updated_at = now();

  get diagnostics n = row_count;
  return n;
end $$;

-- Solo la pipeline (service_role) puo' eseguire il ricalcolo via RPC.
revoke execute on function public.gas_ricalcola_indice(date, date) from public;
revoke execute on function public.gas_ricalcola_indice(date, date) from anon;
revoke execute on function public.gas_ricalcola_indice(date, date) from authenticated;
grant  execute on function public.gas_ricalcola_indice(date, date) to service_role;

-- ---------- RLS: abilitata senza policy (deny-all) ----------
alter table public.gas_serie  enable row level security;
alter table public.gas_pesi   enable row level security;
alter table public.gas_indice enable row level security;
