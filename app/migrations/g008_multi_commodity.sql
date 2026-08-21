-- ============================================================
-- Migrazione g008 — MULTI-COMMODITY: gas + energia elettrica (21/08/2026).
--
-- Decisione utente: il monitor EE vive NELLA STESSA APP, con selettore
-- Gas | Energia elettrica. Le tabelle gas_serie/gas_segnale/gas_indice avevano
-- gia' la colonna commodity; qui si aggiunge dove mancava e si rende il
-- motore TABLE-DRIVEN:
--   gas_commodity  : anagrafica commodity (nome, fonte prezzo, unita')
--   gas_variabili  : quali serie compongono lo scenario di ogni commodity,
--                    con quale riferimento e orientamento
--   gas_pesi       : + commodity (una storia di versioni per commodity)
--   gas_parametri_doc : + commodity (PK composta) — schede per la tab Admin
--   gas_alert      : + commodity, CHECK grandezza allargato
--   gas_ricalcola_segnale(commodity, dal, al) : motore generico; il vecchio
--     gas_ricalcola_segnale(dal, al) resta come wrapper per il gas
--   gas_freschezza(commodity) : generica; gas_freschezza() wrapper per il gas
--
-- INVARIANTE verificato in fase di applicazione: per commodity='gas' il
-- nuovo motore produce le STESSE righe del vecchio (confronto su tutta la
-- serie 2020-2026 prima di sostituire la funzione).
-- Additiva, RLS deny-all, nessuna cancellazione.
-- ============================================================

-- ---------- ANAGRAFICA COMMODITY ----------
create table if not exists public.gas_commodity (
    commodity        text primary key,          -- 'gas' | 'ee'
    nome             text not null,             -- etichetta UI
    icona            text not null default '',
    prezzo_codice    text not null,             -- codice in indici_mercato
    prezzo_label     text not null,             -- 'MGP-GAS' | 'PUN'
    prezzo_udm       text not null default '€/MWh',
    prezzo_fonte     text not null,             -- per la Guida/Dettaglio
    -- 'giorno' = una riga/giorno (ora null); 'media_ore' = media delle righe orarie
    prezzo_aggregazione text not null default 'giorno'
        check (prezzo_aggregazione in ('giorno','media_ore')),
    ordine           int not null default 0,
    attivo           boolean not null default true
);
alter table public.gas_commodity enable row level security;

insert into public.gas_commodity
  (commodity, nome, icona, prezzo_codice, prezzo_label, prezzo_fonte, prezzo_aggregazione, ordine)
values
  ('gas', 'Gas',               '🔥', 'MGP_GAS',       'MGP-GAS', 'GME — MGP-GAS, mercato del giorno prima', 'giorno',    1),
  ('ee',  'Energia elettrica', '⚡', 'PUN_INDEX_GME', 'PUN',     'GME — PUN / PUN Index GME, media aritmetica delle 24 ore', 'media_ore', 2)
on conflict (commodity) do nothing;

-- ---------- VARIABILI DELLO SCENARIO ----------
-- Una riga per (commodity, variabile). La serie sorgente puo' stare in
-- gas_serie (sorgente='serie': commodity_dati/variabile_dati/metrica_dati)
-- oppure in indici_mercato (sorgente='indice': codice_indice, media per giorno).
-- riferimento: 'media5_doy' = media dei 5 anni precedenti nello stesso giorno
--   dell'anno (±3 gg); 'norma_doy' = media pluriennale di tutto lo storico
--   nello stesso giorno dell'anno; 'nessuno' = valore assoluto.
-- trasformazione: 'delta' = valore − riferimento; 'abs_delta' = −|valore −
--   riferimento| (vicino alla norma = alto, per il meteo elettrico dove sia
--   caldo che freddo anomali alzano la domanda).
-- orientamento: +1 = valore orientato ALTO favorevole all'acquirente;
--   −1 = valore orientato BASSO favorevole (GPR, prezzo gas).
create table if not exists public.gas_variabili (
    commodity        text not null references public.gas_commodity(commodity),
    variabile        text not null,             -- chiave del punteggio (jsonb punteggi, pesi)
    ordine           int  not null default 0,
    etichetta        text not null,
    icona            text not null default '',
    udm              text not null default '',
    sorgente         text not null check (sorgente in ('serie','indice')),
    commodity_dati   text,                      -- gas_serie.commodity (es. meteo e GPR sono in 'gas')
    variabile_dati   text,
    metrica_dati     text,
    codice_indice    text,                      -- indici_mercato.codice se sorgente='indice'
    riferimento      text not null check (riferimento in ('media5_doy','norma_doy','nessuno')),
    trasformazione   text not null default 'delta' check (trasformazione in ('delta','abs_delta')),
    orientamento     smallint not null check (orientamento in (-1, 1)),
    direzione        text not null default '',  -- frase per il Dettaglio
    fonte            text not null default '',
    spiegazione      text not null default '',
    tolleranza_gg    int  not null default 3,   -- controllo freschezza
    primary key (commodity, variabile)
);
alter table public.gas_variabili enable row level security;

insert into public.gas_variabili
  (commodity, variabile, ordine, etichetta, icona, udm, sorgente, commodity_dati, variabile_dati, metrica_dati, codice_indice,
   riferimento, trasformazione, orientamento, direzione, fonte, spiegazione, tolleranza_gg)
values
-- ===== GAS (identico al motore g005) =====
('gas','stoccaggi',  1,'Stoccaggi IT','🛢','%','serie','gas','stoccaggi','riempimento_pct',null,
 'media5_doy','delta', 1,
 'riempimento SOPRA la media 5 anni → punteggio alto (favorevole)','GIE AGSI+',
 'Percentuale di riempimento degli stoccaggi italiani (GIE AGSI+). Il punteggio confronta il valore con la **media dei 5 anni precedenti nello stesso giorno (±3 gg)**: sopra media = offerta abbondante = scenario più favorevole all''acquirente.', 3),
('gas','meteo',      2,'Meteo (T paniere)','🌡','°C','serie','gas','meteo','t_media_paniere',null,
 'norma_doy','delta', 1,
 'più MITE della norma → punteggio alto (favorevole)','Open-Meteo (ERA5)',
 'Temperatura media giornaliera del paniere città pesato per consumo gas (MI 30 · RM 20 · TO 15 · BO 15 · FI 10 · VE 10; Open-Meteo/ERA5). Il punteggio è lo **scostamento dalla norma 1991–oggi dello stesso giorno dell''anno**: più mite = meno domanda per riscaldamento = scenario più favorevole.', 3),
('gas','lng',        3,'LNG send-out','🚢','GWh/g','serie','gas','lng','lng_sendout',null,
 'media5_doy','delta', 1,
 'send-out SOPRA la media 5 anni → punteggio alto (favorevole)','GIE ALSI',
 'Gas immesso in rete dai rigassificatori italiani (GIE ALSI). Il punteggio confronta con la **media 5 anni** dello stesso periodo: rigassificatori molto utilizzati = molta offerta via nave = scenario più favorevole.', 3),
('gas','geopolitica',4,'Geopolitica (GPR)','🌍','indice','serie','gas','geopolitica','gpr',null,
 'nessuno','delta',-1,
 'GPR BASSO → punteggio alto (favorevole)','GPR — Caldara & Iacoviello',
 '**Geopolitical Risk Index** giornaliero di Caldara–Iacoviello: conta gli articoli su tensioni, minacce e conflitti in 10 grandi quotidiani internazionali (base 1985–2019 = 100). Il punteggio è il rango percentile sullo storico 2020–oggi, invertito: contesto calmo = scenario più favorevole.', 7),
-- ===== ENERGIA ELETTRICA (5 variabili, da confermare dopo il backtest) =====
('ee','produzione',  1,'Produzione zonale','🏭','GWh/g','serie','ee','produzione','produzione_tot',null,
 'media5_doy','delta', 1,
 'produzione SOPRA la media 5 anni → punteggio alto (favorevole)','ENTSO-E Transparency (dati Terna)',
 'Generazione elettrica effettiva delle **7 zone di mercato italiane** (Nord, Centro-Nord, Centro-Sud, Sud, Calabria, Sicilia, Sardegna), somma giornaliera in GWh (ENTSO-E Transparency, dati trasmessi da Terna). Il punteggio confronta il totale con la **media dei 5 anni precedenti nello stesso periodo**: produzione abbondante = offerta ampia = scenario più favorevole. Il dettaglio per zona è nella pagina Dettaglio.', 3),
('ee','meteo',       2,'Meteo (T paniere)','🌡','°C','serie','gas','meteo','t_media_paniere',null,
 'norma_doy','abs_delta', 1,
 'temperatura VICINA alla norma → punteggio alto (favorevole)','Open-Meteo (ERA5)',
 'Stessa temperatura del paniere città del gas, ma letta in modo diverso: per l''elettrico **sia il freddo sia il caldo anomali** alzano la domanda (riscaldamento e condizionamento). Il punteggio premia i giorni **vicini alla norma pluriennale** e penalizza gli scostamenti in entrambe le direzioni.', 3),
('ee','gas',         3,'Prezzo gas MGP-GAS','🔥','€/MWh','indice',null,null,null,'MGP_GAS',
 'nessuno','delta',-1,
 'gas BASSO → punteggio alto (favorevole)','GME — MGP-GAS',
 'Il gas è il **costo marginale** che fissa il PUN nella maggior parte delle ore (centrali a ciclo combinato). Il punteggio è il rango percentile del prezzo MGP-GAS sullo storico 2020–oggi, invertito: gas basso = PUN atteso basso = scenario più favorevole.', 2),
('ee','rinnovabili', 4,'Quota rinnovabili','☀️','%','serie','ee','rinnovabili','quota_pct',null,
 'media5_doy','delta', 1,
 'quota SOPRA la media 5 anni → punteggio alto (favorevole)','ENTSO-E Transparency (dati Terna)',
 'Quota di generazione da **solare ed eolico** sul totale nazionale (ENTSO-E). Confrontata con la **media dei 5 anni precedenti nello stesso periodo** per depurare la stagionalità: più rinnovabili del solito = meno ore fissate dal gas = scenario più favorevole.', 3),
('ee','geopolitica', 5,'Geopolitica (GPR)','🌍','indice','serie','gas','geopolitica','gpr',null,
 'nessuno','delta',-1,
 'GPR BASSO → punteggio alto (favorevole)','GPR — Caldara & Iacoviello',
 '**Geopolitical Risk Index** giornaliero di Caldara–Iacoviello (stesso indicatore del gas): contesto calmo = meno rischio sui combustibili e sui prezzi = scenario più favorevole.', 7)
on conflict (commodity, variabile) do nothing;

-- ---------- COMMODITY SU PESI / PARAMETRI / ALERT ----------
alter table public.gas_pesi add column if not exists commodity text not null default 'gas';
create index if not exists gas_pesi_commodity_versione on public.gas_pesi (commodity, versione desc);

alter table public.gas_parametri_doc add column if not exists commodity text not null default 'gas';
alter table public.gas_parametri_doc drop constraint if exists gas_parametri_doc_pkey;
alter table public.gas_parametri_doc add primary key (commodity, chiave);

alter table public.gas_alert add column if not exists commodity text not null default 'gas';
alter table public.gas_alert drop constraint if exists gas_alert_grandezza_check;
alter table public.gas_alert add constraint gas_alert_grandezza_check
  check (grandezza in ('indice','scenario','segnale','prezzo',
                       'stoccaggi','meteo','lng','geopolitica',      -- gas
                       'produzione','gas','rinnovabili'));           -- ee
create index if not exists gas_alert_commodity on public.gas_alert (commodity, attivo);

-- ---------- CONFIGURAZIONE EE v1 (stessi parametri del gas; pesi da tarare col backtest) ----------
insert into public.gas_pesi (commodity, pesi, autore)
select 'ee', (pesi - 'scenario') || jsonb_build_object('scenario',
         jsonb_build_object('produzione', 30, 'meteo', 15, 'gas', 25, 'rinnovabili', 15, 'geopolitica', 15)),
       'g008 (21/08/2026) — prima configurazione EE, da tarare col backtest PUN'
from public.gas_pesi where commodity='gas' order by versione desc limit 1;

-- ---------- SCHEDE PARAMETRI EE ----------
-- Parametri comuni: copia delle schede gas (il testo è già neutro: "prezzo", "trend", "scenario").
insert into public.gas_parametri_doc
  (commodity, chiave, ordine, gruppo, nome, spiegazione, effetto, udm, minimo, massimo, passo, valore_default)
select 'ee', chiave, ordine, gruppo, nome, spiegazione, effetto, udm, minimo, massimo, passo, valore_default
from public.gas_parametri_doc where commodity='gas' and chiave not like 'scenario.%'
on conflict do nothing;
-- Pesi dello scenario EE
insert into public.gas_parametri_doc
  (commodity, chiave, ordine, gruppo, nome, spiegazione, effetto, udm, minimo, massimo, passo, valore_default)
values
('ee','scenario.produzione', 10,'Scenario — pesi','Peso produzione zonale',
 'Quanto conta la generazione elettrica effettiva delle 7 zone italiane (ENTSO-E/Terna) rispetto alla media dei 5 anni precedenti nello stesso periodo. Produzione sopra media = offerta ampia = scenario piu'' favorevole all''acquirente.',
 'Alzandolo lo scenario reagisce di piu'' al livello di produzione. I cinque pesi devono sommare 100.','punti',0,100,5,30),
('ee','scenario.meteo',      20,'Scenario — pesi','Peso meteo',
 'Quanto conta la temperatura del paniere citta'' rispetto alla norma pluriennale. Per l''elettrico contano SIA il caldo SIA il freddo anomali (condizionamento e riscaldamento): il punteggio premia i giorni vicini alla norma.',
 'Alzandolo il meteo pesa di piu''; nelle mezze stagioni la variabile e'' meno discriminante.','punti',0,100,5,15),
('ee','scenario.gas',        30,'Scenario — pesi','Peso prezzo gas',
 'Quanto conta il prezzo del gas MGP-GAS, costo marginale che fissa il PUN nella maggior parte delle ore. Gas basso (percentile basso sullo storico 2020-oggi) = PUN atteso basso = scenario favorevole.',
 'Alzandolo lo scenario segue di piu'' il mercato del gas. E'' la variabile piu'' legata al prezzo elettrico.','punti',0,100,5,25),
('ee','scenario.rinnovabili',40,'Scenario — pesi','Peso quota rinnovabili',
 'Quanto conta la quota di generazione solare+eolica sul totale, rispetto alla media dei 5 anni nello stesso periodo. Piu'' rinnovabili del solito = meno ore fissate dal gas = prezzi piu'' bassi.',
 'Alzandolo lo scenario premia le fasi di forte produzione rinnovabile (primavera/estate ventose e soleggiate).','punti',0,100,5,15),
('ee','scenario.geopolitica',50,'Scenario — pesi','Peso geopolitica',
 'Quanto conta il Geopolitical Risk Index (Caldara-Iacoviello). Contesto calmo = meno rischio su combustibili e prezzi = scenario favorevole.',
 'Alzandolo lo scenario reagisce di piu'' alle tensioni internazionali.','punti',0,100,5,15)
on conflict do nothing;

-- ---------- MOTORE GENERICO ----------
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
  v_pz_codice text; v_pz_agg text;
begin
  select pesi, versione into v_cfg, v_ver
  from public.gas_pesi where commodity = p_commodity order by versione desc limit 1;
  if v_cfg is null then
    raise exception 'gas_pesi: nessuna configurazione per la commodity %', p_commodity;
  end if;
  select prezzo_codice, prezzo_aggregazione into v_pz_codice, v_pz_agg
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
  -- ===== PREZZO: una riga/giorno (media delle ore se orario) =====
  pz0 as (
    select data, avg(valore)::numeric as valore
    from public.indici_mercato where codice = v_pz_codice and stato='consuntivo'
    group by data),
  pz as (select data, valore, row_number() over (order by data) as i from pz0),
  pz_reg as (
    select data, valore, i,
      regr_slope(valore, i) over (order by i rows between v_b-1 preceding and current row) as sb,
      regr_intercept(valore, i) over (order by i rows between v_b-1 preceding and current row) as ib,
      count(*) over (order by i rows between v_b-1 preceding and current row) as nb,
      regr_slope(valore, i) over (order by i rows between v_m-1 preceding and current row) as sm,
      regr_intercept(valore, i) over (order by i rows between v_m-1 preceding and current row) as im,
      count(*) over (order by i rows between v_m-1 preceding and current row) as nm,
      regr_slope(valore, i) over (order by i rows between v_l-1 preceding and current row) as sl,
      regr_intercept(valore, i) over (order by i rows between v_l-1 preceding and current row) as il,
      count(*) over (order by i rows between v_l-1 preceding and current row) as nl
    from pz),
  pz_val as (
    select data, valore as prezzo,
      case when nb >= v_b then sb*i + ib end as tb,
      case when nm >= v_m then sm*i + im end as tm,
      case when nl >= v_l then sl*i + il end as tl,
      case when nl >= v_l and (sl*i+il) <> 0 then sl / (sl*i+il) * 100 end as pend_l,
      case when nb >= v_b and (sb*i+ib) <> 0 then sb / (sb*i+ib) * 100 end as pend_b,
      (select count(*) filter (where q.valore < r.valore)::numeric / nullif(count(*),0) * 100
         from pz q where q.i < r.i and q.i >= r.i - v_mf1) as pct1,
      (select count(*) filter (where q.valore < r.valore)::numeric / nullif(count(*),0) * 100
         from pz q where q.i < r.i and q.i >= r.i - v_mf2) as pct2
    from pz_reg r),
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
    select g.data, p.prezzo, p.tb, p.tm, p.tl, p.pend_l, p.pend_b, p.pct1, p.pct2
    from giorni g left join pz_val p using (data)),
  grp_p as (select *, count(prezzo) over (order by data) as g_pz from spine_p),
  filled_p as (
    select data,
      first_value(prezzo) over w prezzo, first_value(tb) over w tb, first_value(tm) over w tm,
      first_value(tl) over w tl, first_value(pend_l) over w pend_l, first_value(pend_b) over w pend_b,
      first_value(pct1) over w pct1, first_value(pct2) over w pct2
    from grp_p window w as (partition by g_pz order by data)),
  calc as (
    select s.data, s.scenario, s.punteggi, p.prezzo, p.tb, p.tm, p.tl, p.pend_l, p.pend_b, p.pct1, p.pct2,
      case when p.tb is not null and p.tb<>0 then (p.prezzo/p.tb - 1)*100 end as sc_b,
      case when p.tm is not null and p.tm<>0 then (p.prezzo/p.tm - 1)*100 end as sc_m
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
    (data, commodity, scenario, scenario_medio, punteggi, prezzo, trend_breve, trend_medio, trend_lungo,
     scost_breve_pct, scost_medio_pct, pendenza_lungo_pct, pendenza_breve_pct,
     pct_finestra1, pct_finestra2,
     prezzo_favorevole, scenario_favorevole, favorevole, giorni_consecutivi,
     codice, testo, versione_pesi)
  select data, p_commodity, scenario, round(scen_m::numeric,2), punteggi,
    prezzo, tb, tm, tl,
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
    scenario=excluded.scenario, scenario_medio=excluded.scenario_medio, punteggi=excluded.punteggi, prezzo=excluded.prezzo,
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

-- Wrapper retro-compatibile (Edge Function gas-monitor, tab Admin): solo gas.
create or replace function public.gas_ricalcola_segnale(p_dal date, p_al date)
returns integer language sql as $$
  select public.gas_ricalcola_segnale('gas', p_dal, p_al);
$$;
revoke execute on function public.gas_ricalcola_segnale(date, date) from public, anon, authenticated;
grant  execute on function public.gas_ricalcola_segnale(date, date) to service_role;

-- ---------- FRESCHEZZA GENERICA ----------
-- Riporta le serie che hanno ALMENO un dato (una variabile mai caricata — es.
-- produzione EE prima del token ENTSO-E — non genera alert: si attiva da sola
-- al primo caricamento). Le tolleranze stanno in gas_variabili.tolleranza_gg.
create or replace function public.gas_freschezza(p_commodity text)
returns table(serie text, ultimo date, giorni_fa integer, tolleranza integer)
language sql stable as $$
  select 'prezzo ' || c.prezzo_codice, max(i.data), (current_date - max(i.data))::int, 2
    from public.gas_commodity c join public.indici_mercato i
      on i.codice = c.prezzo_codice and i.stato = 'consuntivo'
    where c.commodity = p_commodity group by c.prezzo_codice
  union all
  select 'segnale', max(data), (current_date - max(data))::int, 2
    from public.gas_segnale where commodity = p_commodity having max(data) is not null
  union all
  select v.variabile || ' ' || coalesce(v.metrica_dati, v.codice_indice), max(s.data), (current_date - max(s.data))::int, v.tolleranza_gg
    from public.gas_variabili v join public.gas_serie s
      on v.sorgente = 'serie' and s.commodity = v.commodity_dati
     and s.variabile = v.variabile_dati and s.metrica = v.metrica_dati
    where v.commodity = p_commodity
    group by v.variabile, v.metrica_dati, v.codice_indice, v.tolleranza_gg
$$;

-- Wrapper retro-compatibile (Edge Function v11, dashboard, admin): stessa forma di prima.
create or replace function public.gas_freschezza()
returns table(serie text, ultimo date, giorni_fa integer)
language sql stable as $$
  select serie, ultimo, giorni_fa from public.gas_freschezza('gas');
$$;
