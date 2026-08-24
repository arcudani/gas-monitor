-- ============================================================
-- Migrazione g009 — CONDIZIONE PREZZO SU MEDIA MOBILE (24/08/2026).
--
-- PROBLEMA (scoperto dal committente il 24/08/2026 guardando la dashboard EE:
-- "il PUN non può essere sceso di 32 €/MWh"): il dato era corretto — domenica
-- 23/08 il PUN ha chiuso a 128,42 contro i 160,56 di sabato, con le ore
-- centrali a 8-12 €/MWh per il fotovoltaico — ma ha rivelato che per
-- l'elettrico la condizione prezzo lavorava sul prezzo GIORNALIERO grezzo,
-- che ha un fortissimo ciclo settimanale. Media degli ultimi 90 giorni:
--   lun-ven 156-161 €/MWh · sabato 139,9 (-12%) · domenica 128,1 (-20%).
-- Risultato: ogni domenica il segnale leggeva -19% sul trend breve e -30%
-- sul medio, cioe' scambiava il weekend per una flessione del mercato.
-- Il gas non ha questo problema (MGP-GAS quota tutti i giorni senza ciclo
-- settimanale marcato).
--
-- SOLUZIONE: la condizione prezzo (tre trend, scostamenti, percentili del
-- minimo di periodo) si calcola sulla MEDIA MOBILE di N giorni, dove N e' un
-- parametro della commodity: gas N=1 (nessuna media -> comportamento IDENTICO,
-- verificato con A/B), EE N=7 (una settimana intera contiene sempre 5 feriali
-- + sabato + domenica, quindi il ciclo si annulla per costruzione).
-- Il prezzo MOSTRATO resta quello del giorno (il cliente vuole vedere il PUN
-- reale); la nuova colonna gas_segnale.prezzo_riferimento porta la media usata
-- dalle regole, con lo stesso schema gia' adottato per lo scenario
-- (valore di oggi in evidenza + media mobile su cui scattano le condizioni).
--
-- Additiva, RLS invariata.
-- ============================================================

-- ---------- PARAMETRO DI COMMODITY ----------
alter table public.gas_commodity
  add column if not exists prezzo_media_gg int not null default 1;
comment on column public.gas_commodity.prezzo_media_gg is
  'Giorni di media mobile su cui si valuta la CONDIZIONE prezzo (trend, scostamenti, percentili). 1 = prezzo giornaliero grezzo (gas). 7 = neutralizza il ciclo settimanale (energia elettrica: la domenica vale -20%).';
update public.gas_commodity set prezzo_media_gg = 7 where commodity = 'ee';

-- ---------- COLONNA DI OUTPUT ----------
alter table public.gas_segnale
  add column if not exists prezzo_riferimento numeric(12,4);
comment on column public.gas_segnale.prezzo_riferimento is
  'Prezzo su cui lavorano le condizioni: media mobile di gas_commodity.prezzo_media_gg giorni (= prezzo del giorno quando vale 1).';

-- ---------- MOTORE ----------
create or replace function public.gas_ricalcola_segnale(p_commodity text, p_dal date, p_al date)
returns integer
language plpgsql
as $$
declare
  v_cfg  jsonb;
  v_ver  int;
  n      int;
  v_soglia  numeric; v_b int; v_m int; v_l int;
  v_fless numeric; v_toll numeric; v_pend numeric; v_cad numeric; v_pmin numeric;
  v_g1 int; v_g2 int; v_g3 int; v_smg int; v_smin numeric; v_opp numeric;
  v_mf1 int; v_mf2 int; v_mpct numeric;
  v_pz_codice text; v_pzm int;
begin
  select pesi, versione into v_cfg, v_ver
  from public.gas_pesi where commodity = p_commodity order by versione desc limit 1;
  if v_cfg is null then
    raise exception 'gas_pesi: nessuna configurazione per la commodity %', p_commodity;
  end if;
  select prezzo_codice, greatest(coalesce(prezzo_media_gg, 1), 1)
    into v_pz_codice, v_pzm
  from public.gas_commodity where commodity = p_commodity;
  if v_pz_codice is null then
    raise exception 'gas_commodity: commodity % non definita', p_commodity;
  end if;

  v_soglia := (v_cfg->>'scenario_soglia')::numeric;
  v_b := (v_cfg->>'trend_breve_gg')::int;
  v_m := (v_cfg->>'trend_medio_gg')::int;
  v_l := (v_cfg->>'trend_lungo_gg')::int;
  v_fless := (v_cfg->>'flessione_breve_pct')::numeric;
  v_toll  := (v_cfg->>'tolleranza_medio_pct')::numeric;
  v_pend  := (v_cfg->>'pendenza_lungo_max_pct_g')::numeric;
  v_cad   := coalesce((v_cfg->>'caduta_libera_max_pct_g')::numeric, -1.0);
  v_pmin  := coalesce((v_cfg->>'pendenza_lungo_min_pct_g')::numeric, -0.5);
  v_g1 := (v_cfg->>'gradino_iniziale')::int;
  v_g2 := (v_cfg->>'gradino_fixing')::int;
  v_g3 := (v_cfg->>'gradino_trend')::int;
  v_smg := coalesce((v_cfg->>'scenario_media_gg')::int, 7);
  v_smin := coalesce((v_cfg->>'scenario_min_opportunita')::numeric, 35);
  v_opp := coalesce((v_cfg->>'opportunita_medio_pct')::numeric, 7);
  v_mf1 := coalesce((v_cfg->>'minimo_finestra1_mesi')::int, 6) * 30;
  v_mf2 := coalesce((v_cfg->>'minimo_finestra2_mesi')::int, 18) * 30;
  v_mpct := coalesce((v_cfg->>'minimo_percentile')::numeric, 5);

  with
  vars as (select * from public.gas_variabili where commodity = p_commodity),
  -- ===== valori grezzi di ogni variabile (gas_serie o indici_mercato, una riga/giorno) =====
  valori as (
    select v.variabile, s.data, s.valore::numeric as valore
    from vars v join public.gas_serie s
      on v.sorgente='serie' and s.commodity=v.commodity_dati
     and s.variabile=v.variabile_dati and s.metrica=v.metrica_dati
    union all
    select v.variabile, i.data, avg(i.valore)::numeric
    from vars v join public.indici_mercato i
      on v.sorgente='indice' and i.codice=v.codice_indice and i.stato='consuntivo'
    group by v.variabile, i.data),
  -- MATERIALIZED + base5: senza, il planner sceglieva un nested loop sull'espansione
  -- ±3 gg (59k x 4.8k righe) e il ricalcolo passava da 3 a 25 s (21/08/2026).
  val_doy as materialized (select variabile, data, extract(doy from data)::int as doy, valore from valori),
  -- riferimento 'norma_doy': media di tutto lo storico nello stesso giorno dell'anno
  norma as (
    select variabile, doy, avg(valore) as rif from val_doy group by 1, 2),
  -- riferimento 'media5_doy': media dei 5 anni precedenti, stesso doy ±3 gg
  base5 as materialized (
    select b.variabile, b.data, b.doy from val_doy b
    where b.data >= date '2020-01-01'
      and b.variabile in (select variabile from vars where riferimento = 'media5_doy')),
  exp5 as materialized (
    select b.variabile, b.data, b.valore, (b.doy + o.off) as chiave
    from val_doy b cross join generate_series(-3,3) as o(off)
    where b.variabile in (select variabile from vars where riferimento = 'media5_doy')),
  media5 as (
    select b1.variabile, b1.data, avg(e.valore) as rif
    from base5 b1 join exp5 e on e.variabile = b1.variabile and e.chiave = b1.doy
                             and e.data < b1.data and e.data >= b1.data - interval '5 years'
    group by b1.variabile, b1.data),
  rif as (
    select b.variabile, b.data, b.valore, v.riferimento, v.trasformazione, v.orientamento,
      case v.riferimento
        when 'norma_doy'  then n.rif
        when 'media5_doy' then m.rif
      end as rif
    from val_doy b join vars v using (variabile)
    left join norma  n on v.riferimento='norma_doy'  and n.variabile=b.variabile and n.doy=b.doy
    left join media5 m on v.riferimento='media5_doy' and m.variabile=b.variabile and m.data=b.data
    where b.data >= date '2020-01-01'),
  orientati as (
    select variabile, data,
      orientamento * (case trasformazione
        when 'abs_delta' then -abs(valore - coalesce(rif, valore))
        else case riferimento
               when 'nessuno' then valore
               else valore - coalesce(rif, valore)
             end
      end) as orientato
    from rif),
  scores as (
    select variabile, data,
           percent_rank() over (partition by variabile order by orientato) * 100 as score
    from orientati),
  -- ===== PREZZO =====
  -- pz_g: prezzo del giorno (media delle ore se orario) — quello MOSTRATO.
  -- pz:   prezzo su cui lavorano le condizioni = media mobile di v_pzm giorni
  --       (g009: 1 per il gas = identico al giornaliero, 7 per l'EE per
  --       neutralizzare il ciclo settimanale).
  pz_g as (
    select data, avg(valore)::numeric as prezzo_giorno
    from public.indici_mercato where codice = v_pz_codice and stato='consuntivo'
    group by data),
  pz as (
    select data, prezzo_giorno,
           avg(prezzo_giorno) over (order by data rows between v_pzm-1 preceding and current row) as valore,
           count(*) over (order by data rows between v_pzm-1 preceding and current row) as n_med,
           row_number() over (order by data) as i
    from pz_g),
  pz_reg as (
    select data, prezzo_giorno, valore, i,
      regr_slope(valore, i) over (order by i rows between v_b-1 preceding and current row) as sb,
      regr_intercept(valore, i) over (order by i rows between v_b-1 preceding and current row) as ib,
      count(*) over (order by i rows between v_b-1 preceding and current row) as nb,
      regr_slope(valore, i) over (order by i rows between v_m-1 preceding and current row) as sm,
      regr_intercept(valore, i) over (order by i rows between v_m-1 preceding and current row) as im,
      count(*) over (order by i rows between v_m-1 preceding and current row) as nm,
      regr_slope(valore, i) over (order by i rows between v_l-1 preceding and current row) as sl,
      regr_intercept(valore, i) over (order by i rows between v_l-1 preceding and current row) as il,
      count(*) over (order by i rows between v_l-1 preceding and current row) as nl,
      n_med
    from pz),
  pz_val as (
    select data, prezzo_giorno as prezzo, valore as prezzo_rif,
      case when nb >= v_b then sb*i + ib end as tb,
      case when nm >= v_m then sm*i + im end as tm,
      case when nl >= v_l then sl*i + il end as tl,
      case when nl >= v_l and (sl*i+il) <> 0 then sl / (sl*i+il) * 100 end as pend_l,
      case when nb >= v_b and (sb*i+ib) <> 0 then sb / (sb*i+ib) * 100 end as pend_b,
      (select count(*) filter (where q.valore < r.valore)::numeric / nullif(count(*),0) * 100
         from pz q where q.i < r.i and q.i >= r.i - v_mf1) as pct1,
      (select count(*) filter (where q.valore < r.valore)::numeric / nullif(count(*),0) * 100
         from pz q where q.i < r.i and q.i >= r.i - v_mf2) as pct2
    from pz_reg r
    where n_med >= v_pzm),          -- scarta i primi giorni con media incompleta
  -- ===== SPINE giorni × variabili + fill-forward dei punteggi =====
  giorni as (select d::date as data from generate_series(date '2020-01-01', p_al, interval '1 day') d),
  spine_v as (
    select g.data, v.variabile, s.score
    from giorni g cross join vars v
    left join scores s on s.variabile = v.variabile and s.data = g.data),
  grp_v as (
    select *, count(score) over (partition by variabile order by data) as g
    from spine_v),
  filled_v as (
    select data, variabile,
           first_value(score) over (partition by variabile, g order by data) as score
    from grp_v),
  scen as (
    select data,
      round((sum(coalesce((v_cfg->'scenario'->>variabile)::numeric, 0) * coalesce(score, 50)::numeric) / 100)::numeric, 2) as scenario,
      jsonb_object_agg(variabile, case when score is null then null else round(score::numeric, 1) end) as punteggi
    from filled_v group by data),
  -- prezzo: fill-forward sui giorni senza quotazione
  spine_p as (
    select g.data, p.prezzo, p.prezzo_rif, p.tb, p.tm, p.tl, p.pend_l, p.pend_b, p.pct1, p.pct2
    from giorni g left join pz_val p using (data)),
  grp_p as (select *, count(prezzo) over (order by data) as g_pz from spine_p),
  filled_p as (
    select data,
      first_value(prezzo) over w prezzo, first_value(prezzo_rif) over w prezzo_rif,
      first_value(tb) over w tb, first_value(tm) over w tm,
      first_value(tl) over w tl, first_value(pend_l) over w pend_l, first_value(pend_b) over w pend_b,
      first_value(pct1) over w pct1, first_value(pct2) over w pct2
    from grp_p window w as (partition by g_pz order by data)),
  calc as (
    select s.data, s.scenario, s.punteggi, p.prezzo, p.prezzo_rif, p.tb, p.tm, p.tl,
      p.pend_l, p.pend_b, p.pct1, p.pct2,
      -- scostamenti SEMPRE del prezzo di riferimento dalle rette (coerenti tra loro)
      case when p.tb is not null and p.tb<>0 then (p.prezzo_rif/p.tb - 1)*100 end as sc_b,
      case when p.tm is not null and p.tm<>0 then (p.prezzo_rif/p.tm - 1)*100 end as sc_m
    from scen s join filled_p p using (data)
    where p.prezzo is not null),
  calc2 as (
    select *, avg(scenario) over (order by data rows between v_smg-1 preceding and current row) as scen_m
    from calc),
  cond as (
    select *,
      (scen_m >= v_soglia) as scen_ok,
      (sc_b is not null and sc_m is not null and pend_l is not null
       and pend_l <= v_pend and pend_b >= v_cad and pend_l >= v_pmin
       and ((sc_b <= -v_fless and sc_m <= v_toll) or sc_m <= -v_opp)) as pz_ok,
      (sc_b is not null and sc_m is not null and pend_l is not null
       and pend_l <= v_pend and pend_b >= v_cad and pend_l >= v_pmin
       and sc_m <= -v_opp) as opp_ok,
      (pend_l is not null and pend_l >= v_pmin and pend_b >= v_cad
       and (pct1 <= v_mpct or pct2 <= v_mpct)) as min_ok
    from calc2),
  fav as (
    select *, (scen_ok and pz_ok) as favorevole,
           (not (scen_ok and pz_ok) and opp_ok and scen_m >= v_smin) as opportunita,
           (not (scen_ok and pz_ok) and min_ok and scen_m >= v_smin) as minimo
    from cond),
  runs as (
    select *, sum(case when favorevole then 0 else 1 end) over (order by data) as grp_run
    from fav),
  cons as (
    select *,
      case when favorevole then row_number() over (partition by grp_run order by data) else 0 end as ncons,
      lag(favorevole) over (order by data) as fav_prec
    from runs),
  seg as (
    select *,
      case
        when favorevole and ncons >= v_g3 then 'trend'
        when favorevole and ncons >= v_g2 then 'fixing'
        when favorevole and ncons >= v_g1 then 'iniziale'
        when favorevole then 'prime'
        when minimo then 'minimo'
        when opportunita then 'opportunita'
        when coalesce(fav_prec,false) and not favorevole then 'chiusa'
        when scen_ok and not pz_ok then 'monitorare'
        else 'attesa'
      end as codice
    from cons)
  insert into public.gas_segnale
    (data, commodity, scenario, scenario_medio, punteggi, prezzo, prezzo_riferimento,
     trend_breve, trend_medio, trend_lungo,
     scost_breve_pct, scost_medio_pct, pendenza_lungo_pct, pendenza_breve_pct,
     pct_finestra1, pct_finestra2,
     prezzo_favorevole, scenario_favorevole, favorevole, giorni_consecutivi,
     codice, testo, versione_pesi)
  select data, p_commodity, scenario, round(scen_m::numeric,2), punteggi,
    prezzo, round(prezzo_rif::numeric,4), tb, tm, tl,
    round(sc_b::numeric,3), round(sc_m::numeric,3), round(pend_l::numeric,4), round(pend_b::numeric,4),
    round(pct1::numeric,2), round(pct2::numeric,2),
    pz_ok, scen_ok, favorevole, ncons, codice,
    case codice
      when 'trend'     then format('Trend favorevole consolidato da %s giorni: finestra ampia, valutare coperture più consistenti.', ncons)
      when 'fixing'    then format('Segnale di fixing: scenario favorevole e prezzo sotto trend da %s giorni — finestra utile per coperture.', ncons)
      when 'iniziale'  then format('Segnale iniziale: condizioni favorevoli da %s giorni — valutare una prima tranche.', ncons)
      when 'prime'     then 'Scenario favorevole e prezzo in flessione: prime condizioni per una finestra di fixing.'
      when 'minimo' then format('Minimo di periodo: prezzo tra i più bassi degli ultimi %s mesi — momento favorevole al fixing-approvvigionamento, da valutare con una tranche.', case when pct2 <= v_mpct then v_mf2/30 else v_mf1/30 end)
      when 'opportunita' then format('Opportunità di prezzo: prezzo in netta flessione (%s%% sul trend medio) con scenario non sfavorevole — possibile tranche tattica, potenziale finestra di fixing-approvvigionamento.', round(sc_m::numeric,1))
      when 'chiusa'    then 'Finestra chiusa: il prezzo ha recuperato il trend o lo scenario è peggiorato.'
      when 'monitorare' then 'Scenario favorevole, ma il prezzo non ha ancora ceduto rispetto al trend: monitorare.'
      else 'Scenario sfavorevole o neutro all''approvvigionamento: attendere.'
    end,
    v_ver
  from seg
  where data between p_dal and p_al
  on conflict (data, commodity) do update set
    scenario=excluded.scenario, scenario_medio=excluded.scenario_medio, punteggi=excluded.punteggi,
    prezzo=excluded.prezzo, prezzo_riferimento=excluded.prezzo_riferimento,
    trend_breve=excluded.trend_breve, trend_medio=excluded.trend_medio, trend_lungo=excluded.trend_lungo,
    scost_breve_pct=excluded.scost_breve_pct, scost_medio_pct=excluded.scost_medio_pct,
    pendenza_lungo_pct=excluded.pendenza_lungo_pct, pendenza_breve_pct=excluded.pendenza_breve_pct,
    pct_finestra1=excluded.pct_finestra1, pct_finestra2=excluded.pct_finestra2,
    prezzo_favorevole=excluded.prezzo_favorevole, scenario_favorevole=excluded.scenario_favorevole,
    favorevole=excluded.favorevole, giorni_consecutivi=excluded.giorni_consecutivi,
    codice=excluded.codice, testo=excluded.testo, versione_pesi=excluded.versione_pesi,
    updated_at=now();

  get diagnostics n = row_count;
  return n;
end $$;

revoke execute on function public.gas_ricalcola_segnale(text, date, date) from public, anon, authenticated;
grant  execute on function public.gas_ricalcola_segnale(text, date, date) to service_role;
