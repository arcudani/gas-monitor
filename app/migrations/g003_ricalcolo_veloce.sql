-- ============================================================
-- Migrazione g003 — riscrittura di gas_ricalcola_indice.
--
-- La versione g002 usava subquery correlate per giorno (media 5 anni e
-- carry-forward dell'ultimo punteggio): O(n^2), andava in statement
-- timeout sul ricalcolo full-history 2020-oggi. Questa versione usa:
--  - join aggregato sul giorno-dell'anno (+-3) per le medie 5 anni
--  - fill-forward con il trucco count()-over + first_value() per gruppo
-- Due fix inclusi rispetto al testo g002 originale: cast ::numeric prima
-- di round() (percent_rank ritorna double) e stesso comportamento
-- funzionale per il resto.
-- ============================================================

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
    from pz_base where data >= date '2020-02-01'
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
  met as (
    select data, percent_rank() over (order by orientato) * 100 as score
    from (select b.data, (nr.t_norma - b.valore) as orientato
          from met_base b join met_norma nr on nr.doy = extract(doy from b.data)
          where b.data >= date '2020-01-01') x
  ),
  -- STOCCAGGI: sotto la media 5 anni (stesso giorno +-3) = rialzista
  sto_doy as (
    select data, extract(doy from data) as doy, valore from public.gas_serie
    where commodity = 'gas' and variabile = 'stoccaggi' and metrica = 'riempimento_pct'
  ),
  sto_exp as (
    -- espansione doy+-3 in chiavi discrete: il join diventa hash su
    -- uguaglianza (il join su abs(doy) era un nested loop quadratico)
    select b.data, b.valore, (b.doy + o.off) as chiave
    from sto_doy b cross join generate_series(-3, 3) as o(off)
  ),
  sto_media as (
    select b1.data, avg(e.valore) as media5
    from sto_doy b1
    join sto_exp e on e.chiave = b1.doy
                  and e.data < b1.data
                  and e.data >= b1.data - interval '5 years'
    where b1.data >= date '2020-01-01'
    group by b1.data
  ),
  sto as (
    select data, percent_rank() over (order by orientato) * 100 as score
    from (select b.data, coalesce(m.media5, b.valore) - b.valore as orientato
          from sto_doy b left join sto_media m using (data)
          where b.data >= date '2020-01-01') x
  ),
  -- LNG: send-out sotto la media 5 anni = offerta debole = rialzista
  lng_doy as (
    select data, extract(doy from data) as doy, valore from public.gas_serie
    where commodity = 'gas' and variabile = 'lng' and metrica = 'lng_sendout'
  ),
  lng_exp as (
    select b.data, b.valore, (b.doy + o.off) as chiave
    from lng_doy b cross join generate_series(-3, 3) as o(off)
  ),
  lng_media as (
    select b1.data, avg(e.valore) as media5
    from lng_doy b1
    join lng_exp e on e.chiave = b1.doy
                  and e.data < b1.data
                  and e.data >= b1.data - interval '5 years'
    where b1.data >= date '2020-01-01'
    group by b1.data
  ),
  lng as (
    select data, percent_rank() over (order by orientato) * 100 as score
    from (select b.data, coalesce(m.media5, b.valore) - b.valore as orientato
          from lng_doy b left join lng_media m using (data)
          where b.data >= date '2020-01-01') x
  ),
  -- GEOPOLITICA: percentile del GPR daily (se/quando alimentato)
  geo as (
    select data, percent_rank() over (order by valore) * 100 as score
    from public.gas_serie
    where commodity = 'gas' and variabile = 'geopolitica' and metrica = 'gpr'
      and data >= date '2020-01-01'
  ),
  -- spine completa dal 2020: serve al fill-forward anche quando p_dal e' recente
  giorni as (
    select d::date as data
    from generate_series(date '2020-01-01', p_al, interval '1 day') d
  ),
  spine as (
    select g.data, pz.score as s_pz, met.score as s_met, sto.score as s_sto,
           lng.score as s_lng, geo.score as s_geo
    from giorni g
    left join pz  using (data)
    left join met using (data)
    left join sto using (data)
    left join lng using (data)
    left join geo using (data)
  ),
  -- dato mancante alla data -> ultimo disponibile (RF-06):
  -- count(col) over cresce solo sui non-null e identifica il gruppo,
  -- first_value del gruppo e' il valore da propagare.
  grp as (
    select data, s_pz, s_met, s_sto, s_lng, s_geo,
           count(s_pz)  over w as g_pz,
           count(s_met) over w as g_met,
           count(s_sto) over w as g_sto,
           count(s_lng) over w as g_lng,
           count(s_geo) over w as g_geo
    from spine
    window w as (order by data)
  ),
  filled as (
    select data,
           first_value(s_pz)  over (partition by g_pz  order by data) as s_pz,
           first_value(s_met) over (partition by g_met order by data) as s_met,
           first_value(s_sto) over (partition by g_sto order by data) as s_sto,
           first_value(s_lng) over (partition by g_lng order by data) as s_lng,
           first_value(s_geo) over (partition by g_geo order by data) as s_geo
    from grp
  )
  insert into public.gas_indice (data, commodity, valore, punteggi, versione_pesi)
  select data, 'gas',
    round(((
        (v_pesi->>'prezzo')::numeric *
            ( (v_pesi->>'prezzo_sub_mgp')::numeric / 100 * coalesce(s_pz, 50)::numeric
            + (v_pesi->>'prezzo_sub_lng')::numeric / 100 * coalesce(s_lng, 50)::numeric )
      + (v_pesi->>'stoccaggi')::numeric   * coalesce(s_sto, 50)::numeric
      + (v_pesi->>'meteo')::numeric       * coalesce(s_met, 50)::numeric
      + (v_pesi->>'geopolitica')::numeric * coalesce(s_geo, 50)::numeric
    ) / 100)::numeric, 2),
    jsonb_build_object(
      'prezzo',      round(coalesce(s_pz, 50)::numeric, 1),
      'lng',         round(coalesce(s_lng, 50)::numeric, 1),
      'stoccaggi',   round(coalesce(s_sto, 50)::numeric, 1),
      'meteo',       round(coalesce(s_met, 50)::numeric, 1),
      'geopolitica', case when s_geo is null then null
                          else round(s_geo::numeric, 1) end),
    v_ver
  from filled
  where s_pz is not null
    and data between p_dal and p_al
  on conflict (data, commodity) do update
    set valore = excluded.valore, punteggi = excluded.punteggi,
        versione_pesi = excluded.versione_pesi, updated_at = now();

  get diagnostics n = row_count;
  return n;
end $$;
