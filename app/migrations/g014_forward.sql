-- ============================================================
-- Migrazione g014 — Curva FORWARD del GME (26/10/2026).
--
-- Informazione A PARTE rispetto al segnale (decisione utente 26/10/2026,
-- dopo il backtest Timestral: nessun modello batte il random walk, quindi
-- niente "previsioni"; il forward e' invece un PREZZO OSSERVATO: quanto
-- costa oggi bloccare i mesi futuri). Non entra in scenario, prezzo,
-- segnale ne' alert: la dashboard lo mostra in un pannello informativo.
--
-- Fonte: prezzi di controllo del GME sui mercati a termine
--   gas: MT-GAS (prodotti M-, Q-, SS-, WS-, CY-)
--   ee : MTE baseload (prodotti BL-M, BL-Q, BL-Y -> normalizzati a M, Q, CY)
-- Scritti ogni notte dal job VPS `dati-mercato` (App_Offerte
-- app/data_updater/forward.py) col ruolo a privilegi minimi `bros_jobs`:
-- stesso pattern di indici_mercato (migrazione 0008 di App_Offerte).
-- ============================================================

create table if not exists public.gas_forward (
    commodity    text        not null,          -- 'gas' | 'ee'
    seduta       date        not null,          -- giorno di negoziazione
    prodotto     text        not null,          -- M-2026-11, Q-2027-01, CY-2027, SS-2027, WS-2026/2027
    tipo         text        not null,          -- M | Q | CY | SS | WS
    consegna_dal date        not null,
    consegna_al  date        not null,
    prezzo       numeric(10,3) not null,        -- €/MWh, prezzo di controllo GME
    fonte        text        not null default 'GME',
    updated_at   timestamptz not null default now(),
    primary key (commodity, seduta, prodotto),
    check (commodity in ('gas', 'ee')),
    check (consegna_al >= consegna_dal)
);
create index if not exists gas_forward_seduta_idx on public.gas_forward (commodity, seduta desc);

comment on table public.gas_forward is
    'Curva forward GME (prezzo di controllo, €/MWh) per seduta e prodotto: informazione a parte, non entra nel segnale.';

-- RLS deny-all come le altre gas_* + accesso del ruolo VPS bros_jobs
alter table public.gas_forward enable row level security;
grant select, insert, update on public.gas_forward to bros_jobs;
create policy bros_jobs_sel_forward on public.gas_forward
    for select to bros_jobs using (true);
create policy bros_jobs_ins_forward on public.gas_forward
    for insert to bros_jobs with check (true);
create policy bros_jobs_upd_forward on public.gas_forward
    for update to bros_jobs using (true) with check (true);
