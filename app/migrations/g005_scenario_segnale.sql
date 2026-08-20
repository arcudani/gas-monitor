-- ============================================================
-- Migrazione g005 — Scenario + Prezzo a tre trend + Segnale (requisiti v1.6).
--
-- Sostituisce concettualmente l'indice di pressione rialzista (g002/g003):
-- il cliente fissa tranche su contratti annuali, quindi il segnale indica
-- FINESTRE DI FIXING = scenario favorevole all'acquirente + prezzo in
-- flessione rispetto al trend, persistente per n giorni.
--
-- gas_pesi: una nuova VERSIONE con tutta la configurazione (pesi scenario,
--   soglia, orizzonti 20/60/180, %, gradini 3/5/10) + gas_parametri_doc con
--   la spiegazione descrittiva di ogni parametro (tab Admin, RF-07).
-- gas_segnale: una riga per giorno con scenario, condizione prezzo (tre
--   trend), favorevole, giorni consecutivi, codice segnale e testo.
-- gas_ricalcola_segnale(dal, al): ricalcolo vettoriale (window functions).
--
-- gas_indice resta popolata (storico + confronto) ma NON e' piu' la fonte
-- del segnale. Additiva, prefisso gas_*, RLS deny-all.
-- ============================================================

-- ---------- CONFIGURAZIONE v2 (una riga nuova, la storia resta) ----------
insert into public.gas_pesi (pesi, autore) values ('{
  "modalita_prezzo": "retro",
  "scenario": {"stoccaggi": 35, "meteo": 25, "lng": 20, "geopolitica": 20},
  "scenario_soglia": 60,
  "scenario_media_gg": 7,
  "scenario_min_opportunita": 35,
  "opportunita_medio_pct": 7.0,
  "minimo_finestra1_mesi": 6, "minimo_finestra2_mesi": 18, "minimo_percentile": 5,
  "trend_breve_gg": 20,  "trend_medio_gg": 60,  "trend_lungo_gg": 180,
  "flessione_breve_pct": 3.0,
  "tolleranza_medio_pct": 1.0,
  "pendenza_lungo_max_pct_g": 0.2,
  "caduta_libera_max_pct_g": -1.0,
  "pendenza_lungo_min_pct_g": -0.5,
  "gradino_iniziale": 3, "gradino_fixing": 5, "gradino_trend": 10
}'::jsonb, 'requisiti v1.6 (19/08/2026) — scenario+prezzo+segnale');

-- ---------- DOCUMENTAZIONE PARAMETRI (per la tab Admin) ----------
create table public.gas_parametri_doc (
    chiave      text primary key,          -- percorso nel jsonb, es. 'scenario.stoccaggi'
    ordine      int not null,
    gruppo      text not null,
    nome        text not null,
    spiegazione text not null,
    effetto     text not null,             -- cosa succede alzando / abbassando
    udm         text not null default '',
    minimo      numeric, massimo numeric, passo numeric,
    valore_default numeric
);
comment on table public.gas_parametri_doc is
    'Schede descrittive dei parametri del segnale: la tab Admin le usa per permettere la configurazione in autonomia.';

insert into public.gas_parametri_doc
  (chiave, ordine, gruppo, nome, spiegazione, effetto, udm, minimo, massimo, passo, valore_default) values
('scenario.stoccaggi', 10, 'Scenario — pesi',
 'Peso stoccaggi',
 'Quanto conta il riempimento degli stoccaggi italiani (GIE AGSI+) rispetto alla media dei 5 anni precedenti nello stesso periodo. Stoccaggi sopra media = offerta abbondante = scenario piu'' favorevole all''acquirente.',
 'Alzandolo lo scenario reagisce di piu'' al livello degli stoccaggi. I quattro pesi devono sommare 100.',
 '%', 0, 100, 5, 35),
('scenario.meteo', 20, 'Scenario — pesi',
 'Peso meteo',
 'Quanto conta lo scostamento della temperatura del paniere citta'' (Open-Meteo) dalla norma pluriennale dello stesso giorno. Piu'' mite della norma = meno domanda per riscaldamento = scenario piu'' favorevole.',
 'Alzandolo il meteo pesa di piu''; d''estate la variabile e'' meno discriminante.',
 '%', 0, 100, 5, 25),
('scenario.lng', 30, 'Scenario — pesi',
 'Peso LNG',
 'Quanto conta il send-out dei rigassificatori italiani (GIE ALSI) rispetto alla media 5 anni. Send-out alto = molta offerta via nave = scenario piu'' favorevole.',
 'Alzandolo lo scenario segue di piu'' la disponibilita'' di GNL.',
 '%', 0, 100, 5, 20),
('scenario.geopolitica', 40, 'Scenario — pesi',
 'Peso geopolitica',
 'Quanto conta il Geopolitical Risk Index giornaliero (Caldara-Iacoviello). GPR basso = contesto calmo = scenario piu'' favorevole.',
 'Alzandolo le tensioni internazionali abbassano lo scenario piu'' rapidamente.',
 '%', 0, 100, 5, 20),
('scenario_soglia', 50, 'Scenario',
 'Soglia "scenario favorevole"',
 'Valore dello scenario (0-100) da cui in poi i fondamentali sono considerati favorevoli all''acquirente. Sotto questa soglia il conteggio dei giorni favorevoli non parte.',
 'Alzandola il segnale scatta solo con fondamentali molto buoni (meno finestre, piu'' selettive); abbassandola scatta piu'' spesso.',
 'punti', 40, 90, 1, 60),
('scenario_media_gg', 52, 'Scenario',
 'Giorni di media dello scenario',
 'Lo scenario giornaliero e'' rumoroso (GPR e meteo saltano da un giorno all''altro): per le condizioni del segnale si usa la sua MEDIA MOBILE su questi giorni, cosi'' un''oscillazione di un giorno sotto la soglia non azzera il conteggio dei giorni favorevoli. Caso reale: 6-12/08/2026, scenario 46-55 a giorni alterni con prezzo a -11% sul medio — senza media il segnale non partiva mai. Il valore puntuale resta visibile in dashboard.',
 'Piu'' giorni = scenario piu'' stabile ma piu'' lento a reagire; 1 = valore puntuale (sconsigliato).',
 'giorni', 1, 30, 1, 7),
('scenario_min_opportunita', 54, 'Scenario',
 'Scenario minimo per "opportunita'' di prezzo"',
 'Il segnale secondario "opportunita'' di prezzo" (prezzo in netta flessione sul trend medio) scatta anche con scenario NON favorevole, purche'' non sia sfavorevole: serve almeno questo valore (media mobile). Segnala una possibile tranche tattica e una potenziale finestra di fixing-approvvigionamento (se sia una copertura consistente lo dira'' il forecast, Fase 2). Default 35 (test 2020-2026: 17 finestre, 15 buone, +17,8%; a 40 giugno 2026 scattava 4 giorni dopo il minimo).',
 'Alzandolo l''opportunita'' di prezzo scatta meno spesso; a 0 basta il prezzo.',
 'punti', 0, 60, 1, 35),
('trend_breve_gg', 60, 'Prezzo — orizzonti',
 'Trend breve (giorni)',
 'Finestra della retta di tendenza di breve periodo sul prezzo MGP-GAS: e'' il "radar" che rileva una flessione in corso adesso.',
 'Piu'' corta = piu'' sensibile ai sobbalzi (piu'' falsi segnali); piu'' lunga = piu'' lenta a vedere una discesa improvvisa.',
 'giorni', 5, 60, 1, 20),
('trend_medio_gg', 70, 'Prezzo — orizzonti',
 'Trend medio (giorni)',
 'Finestra della retta di tendenza di medio periodo: il confronto "giusto" per il fixing su contratti annuali — il prezzo e'' davvero a sconto sul trimestre?',
 'Piu'' lunga = filtra meglio i rimbalzi sopra livelli gia'' cari; piu'' corta = piu'' permissiva.',
 'giorni', 30, 120, 5, 60),
('trend_lungo_gg', 80, 'Prezzo — orizzonti',
 'Trend lungo (giorni)',
 'Finestra della retta di lungo periodo: dice in che fase del ciclo siamo (mercato in discesa o rally che riprende fiato).',
 'Serve solo come contesto: blocca il segnale se il lungo periodo sale con forza.',
 'giorni', 90, 365, 10, 180),
('flessione_breve_pct', 90, 'Prezzo — regola',
 'Flessione minima sul trend breve',
 'Di quanto il prezzo odierno deve stare SOTTO la retta di breve periodo perche'' si parli di flessione.',
 'Alzandola servono cali piu'' netti (meno segnali, piu'' sicuri); abbassandola basta un calo lieve.',
 '%', 0, 15, 0.5, 3),
('opportunita_medio_pct', 95, 'Prezzo — regola',
 'Flessione sul trend medio per "opportunita'' di prezzo"',
 'Se il prezzo sta SOTTO la retta di medio periodo almeno di questa percentuale (con i filtri di sicurezza attivi), scatta il segnale secondario "opportunita'' di prezzo" anche senza scenario favorevole. Nel test 2020-2026: 15 finestre, 13 buone, +16% medio a 90 gg; prende la flessione del 6-12/08/2026.',
 'Alzandola servono anomalie di prezzo piu'' nette (meno segnali); abbassandola scatta piu'' spesso.',
 '%', 2, 20, 0.5, 7),
('minimo_finestra1_mesi', 96, 'Prezzo — minimo di periodo',
 'Finestra 1 del "minimo di periodo" (mesi)',
 'Criterio ASSOLUTO sul livello, indipendente dal trend: se il prezzo odierno e'' tra i piu'' bassi degli ultimi N mesi (sotto il percentile indicato) scatta il livello "minimo di periodo" — momento favorevole al fixing anche se il trend non lo dice. Questa e'' la finestra corta. Test 2020-2026 (6 mesi, 5° pct): da 14 a 22 finestre, 21 buone, +18%.',
 'Piu'' corta = piu'' occasioni ma piu'' "minimi locali"; 3 mesi e'' quasi il trend breve (sconsigliato).',
 'mesi', 3, 18, 3, 6),
('minimo_finestra2_mesi', 97, 'Prezzo — minimo di periodo',
 'Finestra 2 del "minimo di periodo" (mesi)',
 'La finestra lunga dello stesso criterio: prezzo tra i piu'' bassi degli ultimi N mesi = minimo "storico" recente. Test 2020-2026 (18 mesi, 5° pct): 20 finestre, 19 buone, +18,6%. Le finestre intermedie (9-12) non aggiungono qualita''.',
 'Piu'' lunga = occasioni piu'' rare e piu'' forti.',
 'mesi', 6, 24, 3, 18),
('minimo_percentile', 98, 'Prezzo — minimo di periodo',
 'Percentile del "minimo di periodo"',
 'Il prezzo odierno deve stare sotto questo percentile dei prezzi della finestra (5 = tra il 5% dei giorni piu'' bassi, cioe'' circa 1 giorno su 20). Vale per entrambe le finestre.',
 'Alzandolo (es. 10) scattano piu'' minimi ma con piu'' falsi (test: al 10° su 6 mesi 31 finestre, 7 non buone); abbassandolo solo i minimi estremi.',
 'percentile', 1, 20, 1, 5),
('tolleranza_medio_pct', 100, 'Prezzo — regola',
 'Tolleranza sul trend medio',
 'Quando la flessione e'' rilevata dal trend BREVE, il prezzo deve comunque stare sotto la retta di medio periodo (o al massimo sopra di questa percentuale): evita di comprare un rimbalzo che resta sopra il livello del trimestre. In alternativa basta che il prezzo sia sotto il medio di almeno la "flessione sul trend medio" (vedi sotto): il trend breve tende a inseguire il prezzo e a spegnersi dopo pochi giorni, il medio no.',
 'Alzandola si accettano prezzi un po'' sopra il medio; a 0 il prezzo deve essere strettamente sotto.',
 '%', 0, 10, 0.5, 1),
('pendenza_lungo_max_pct_g', 110, 'Prezzo — regola',
 'Pendenza massima del trend lungo',
 'Se la retta di lungo periodo sale piu'' di questa percentuale al giorno, il mercato e'' in un rally strutturale: la flessione e'' probabilmente una pausa, non un''occasione, e il segnale non scatta.',
 'Alzandola si tollera un lungo periodo piu'' ripido; abbassandola il filtro e'' piu'' severo.',
 '%/giorno', 0, 2, 0.05, 0.2),
('pendenza_lungo_min_pct_g', 112, 'Prezzo — regola',
 'Pendenza MINIMA del trend lungo (rientro da crisi)',
 'Se la retta di LUNGO periodo scende piu'' di questa percentuale al giorno, il mercato sta rientrando da un picco (come dopo la crisi del 2022): il prezzo e'' "sotto trend" ogni giorno ma domani sara'' ancora piu'' basso. Il segnale non scatta finche'' la discesa non si addolcisce. Nel test 2020-2026 e'' il filtro che elimina i falsi segnali di dicembre 2022 e marzo 2023 mantenendo le finestre buone (9 finestre, 7 buone, guadagno medio 19%).',
 'Valore piu'' negativo (es. -1) = permissivo, si accettano discese piu'' ripide; piu'' vicino a 0 (es. -0,2) = severo.',
 '%/giorno', -3, 0, 0.1, -0.5),
('caduta_libera_max_pct_g', 115, 'Prezzo — regola',
 'Limite di "caduta libera" (trend breve)',
 'Se la retta di BREVE periodo scende piu'' di questa percentuale al giorno, il prezzo e'' in caduta verticale (es. rientro da un picco di crisi): domani sara'' probabilmente piu'' basso, quindi non e'' ancora il momento di fissare. Nel test storico 2020-2026 questo filtro elimina i falsi segnali di dicembre 2022 senza perdere le finestre buone.',
 'Valore piu'' negativo (es. -2) = filtro piu'' permissivo; piu'' vicino a 0 (es. -0,5) = piu'' severo, servono discese dolci.',
 '%/giorno', -5, 0, 0.1, -1.0),
('gradino_iniziale', 120, 'Segnale — gradini',
 'Giorni per "segnale iniziale"',
 'Dopo quanti giorni consecutivi favorevoli (scenario + prezzo) il segnale passa da "prime condizioni" a "segnale iniziale: valutare una prima tranche".',
 'Alzandolo il primo segnale arriva piu'' tardi ma con piu'' conferma.',
 'giorni', 1, 30, 1, 3),
('gradino_fixing', 130, 'Segnale — gradini',
 'Giorni per "segnale di fixing"',
 'Dopo quanti giorni consecutivi favorevoli il segnale diventa "segnale di fixing: finestra utile per coperture".',
 'Deve essere maggiore del gradino iniziale.',
 'giorni', 2, 45, 1, 5),
('gradino_trend', 140, 'Segnale — gradini',
 'Giorni per "trend consolidato"',
 'Dopo quanti giorni consecutivi favorevoli il segnale diventa "trend favorevole consolidato: finestra ampia, coperture piu'' consistenti".',
 'Deve essere maggiore del gradino di fixing.',
 'giorni', 3, 60, 1, 10);

-- ---------- SEGNALE GIORNALIERO ----------
create table public.gas_segnale (
    data               date not null,
    commodity          text not null default 'gas',
    scenario           numeric(6,2),          -- 0-100, alto = favorevole all'acquirente
    scenario_medio     numeric(6,2),          -- media mobile usata dalle condizioni
    punteggi           jsonb not null default '{}'::jsonb,
    prezzo             numeric(12,4),         -- MGP-GAS del giorno
    trend_breve        numeric(12,4),         -- valore atteso oggi sulla retta
    trend_medio        numeric(12,4),
    trend_lungo        numeric(12,4),
    scost_breve_pct    numeric(8,3),          -- (prezzo/trend - 1)*100
    scost_medio_pct    numeric(8,3),
    pendenza_lungo_pct numeric(8,4),          -- %/giorno della retta lunga
    pendenza_breve_pct numeric(8,4),          -- %/giorno della retta breve (filtro caduta libera)
    pct_finestra1      numeric(6,2),          -- percentile del prezzo su finestra 1 (minimo di periodo)
    pct_finestra2      numeric(6,2),          -- percentile del prezzo su finestra 2
    prezzo_favorevole  boolean,
    scenario_favorevole boolean,
    favorevole         boolean,
    giorni_consecutivi int not null default 0,
    codice             text not null,         -- attesa | monitorare | opportunita | minimo | prime | iniziale | fixing | trend | chiusa
    testo              text not null,
    versione_pesi      int not null references public.gas_pesi(versione),
    updated_at         timestamptz not null default now(),
    primary key (data, commodity)
);
comment on table public.gas_segnale is
    'Segnale giornaliero di finestra di fixing: scenario + condizione prezzo a tre trend + persistenza (requisiti v1.6).';

alter table public.gas_parametri_doc enable row level security;
alter table public.gas_segnale       enable row level security;

-- ---------- RICALCOLO ----------
create or replace function public.gas_ricalcola_segnale(p_dal date, p_al date)
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
begin
  select pesi, versione into v_cfg, v_ver
  from public.gas_pesi order by versione desc limit 1;
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
  -- ===== SCENARIO: percentili orientati A FAVORE dell'acquirente =====
  met_base as (
    select data, valore from public.gas_serie
    where commodity='gas' and variabile='meteo' and metrica='t_media_paniere'),
  met_norma as (select extract(doy from data) as doy, avg(valore) as t_norma from met_base group by 1),
  met as (   -- piu' mite della norma = favorevole
    select data, percent_rank() over (order by orientato)*100 as score
    from (select b.data, (b.valore - nr.t_norma) as orientato
          from met_base b join met_norma nr on nr.doy = extract(doy from b.data)
          where b.data >= date '2020-01-01') x),
  sto_doy as (
    select data, extract(doy from data) as doy, valore from public.gas_serie
    where commodity='gas' and variabile='stoccaggi' and metrica='riempimento_pct'),
  sto_exp as (select b.data, b.valore, (b.doy + o.off) as chiave
              from sto_doy b cross join generate_series(-3,3) as o(off)),
  sto_media as (
    select b1.data, avg(e.valore) as media5 from sto_doy b1
    join sto_exp e on e.chiave=b1.doy and e.data<b1.data and e.data>=b1.data-interval '5 years'
    where b1.data >= date '2020-01-01' group by b1.data),
  sto as (   -- sopra la media 5 anni = favorevole
    select data, percent_rank() over (order by orientato)*100 as score
    from (select b.data, b.valore - coalesce(m.media5, b.valore) as orientato
          from sto_doy b left join sto_media m using (data)
          where b.data >= date '2020-01-01') x),
  lng_doy as (
    select data, extract(doy from data) as doy, valore from public.gas_serie
    where commodity='gas' and variabile='lng' and metrica='lng_sendout'),
  lng_exp as (select b.data, b.valore, (b.doy + o.off) as chiave
              from lng_doy b cross join generate_series(-3,3) as o(off)),
  lng_media as (
    select b1.data, avg(e.valore) as media5 from lng_doy b1
    join lng_exp e on e.chiave=b1.doy and e.data<b1.data and e.data>=b1.data-interval '5 years'
    where b1.data >= date '2020-01-01' group by b1.data),
  lng as (   -- send-out sopra media = offerta abbondante = favorevole
    select data, percent_rank() over (order by orientato)*100 as score
    from (select b.data, b.valore - coalesce(m.media5, b.valore) as orientato
          from lng_doy b left join lng_media m using (data)
          where b.data >= date '2020-01-01') x),
  geo as (   -- GPR basso = favorevole
    select data, percent_rank() over (order by valore desc)*100 as score
    from public.gas_serie
    where commodity='gas' and variabile='geopolitica' and metrica='gpr'
      and data >= date '2020-01-01'),
  -- ===== PREZZO: tre rette di regressione (finestre rolling) =====
  pz as (
    select data, valore,
           row_number() over (order by data) as i
    from public.indici_mercato where codice='MGP_GAS' and stato='consuntivo'),
  pz_reg as (
    select data, valore, i,
      -- breve
      regr_slope(valore, i) over (order by i rows between v_b-1 preceding and current row) as sb,
      regr_intercept(valore, i) over (order by i rows between v_b-1 preceding and current row) as ib,
      count(*) over (order by i rows between v_b-1 preceding and current row) as nb,
      -- medio
      regr_slope(valore, i) over (order by i rows between v_m-1 preceding and current row) as sm,
      regr_intercept(valore, i) over (order by i rows between v_m-1 preceding and current row) as im,
      count(*) over (order by i rows between v_m-1 preceding and current row) as nm,
      -- lungo
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
  -- ===== SPINE + fill-forward dei punteggi scenario =====
  giorni as (select d::date as data from generate_series(date '2020-01-01', p_al, interval '1 day') d),
  spine as (
    select g.data, met.score s_met, sto.score s_sto, lng.score s_lng, geo.score s_geo,
           p.prezzo, p.tb, p.tm, p.tl, p.pend_l, p.pend_b, p.pct1, p.pct2
    from giorni g
    left join met using (data) left join sto using (data)
    left join lng using (data) left join geo using (data)
    left join pz_val p using (data)),
  grp as (
    select *, count(s_met) over w g_met, count(s_sto) over w g_sto,
              count(s_lng) over w g_lng, count(s_geo) over w g_geo,
              count(prezzo) over w g_pz
    from spine window w as (order by data)),
  filled as (
    select data,
      first_value(s_met) over (partition by g_met order by data) s_met,
      first_value(s_sto) over (partition by g_sto order by data) s_sto,
      first_value(s_lng) over (partition by g_lng order by data) s_lng,
      first_value(s_geo) over (partition by g_geo order by data) s_geo,
      first_value(prezzo) over (partition by g_pz order by data) prezzo,
      first_value(tb) over (partition by g_pz order by data) tb,
      first_value(tm) over (partition by g_pz order by data) tm,
      first_value(tl) over (partition by g_pz order by data) tl,
      first_value(pend_l) over (partition by g_pz order by data) pend_l,
      first_value(pend_b) over (partition by g_pz order by data) pend_b,
      first_value(pct1) over (partition by g_pz order by data) pct1,
      first_value(pct2) over (partition by g_pz order by data) pct2
    from grp),
  calc as (
    select data, s_met, s_sto, s_lng, s_geo, prezzo, tb, tm, tl, pend_l, pend_b, pct1, pct2,
      round(((
          (v_cfg->'scenario'->>'stoccaggi')::numeric * coalesce(s_sto,50)::numeric
        + (v_cfg->'scenario'->>'meteo')::numeric     * coalesce(s_met,50)::numeric
        + (v_cfg->'scenario'->>'lng')::numeric       * coalesce(s_lng,50)::numeric
        + (v_cfg->'scenario'->>'geopolitica')::numeric * coalesce(s_geo,50)::numeric
      ) / 100)::numeric, 2) as scenario,
      case when tb is not null and tb<>0 then (prezzo/tb - 1)*100 end as sc_b,
      case when tm is not null and tm<>0 then (prezzo/tm - 1)*100 end as sc_m
    from filled
    where prezzo is not null),
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
  -- giorni consecutivi favorevoli: gruppi di run
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
  select data, 'gas', scenario, round(scen_m::numeric,2),
    jsonb_build_object('stoccaggi', round(coalesce(s_sto,50)::numeric,1),
                       'meteo', round(coalesce(s_met,50)::numeric,1),
                       'lng', round(coalesce(s_lng,50)::numeric,1),
                       'geopolitica', case when s_geo is null then null else round(s_geo::numeric,1) end),
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

revoke execute on function public.gas_ricalcola_segnale(date, date) from public, anon, authenticated;
grant  execute on function public.gas_ricalcola_segnale(date, date) to service_role;
