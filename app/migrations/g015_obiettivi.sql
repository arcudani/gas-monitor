-- ============================================================
-- Migrazione g015 — OBIETTIVI DI PREZZO per cliente (26/10/2026).
--
-- Decisione utente (dopo le analisi del 26/10): l'indicatore dice se il momento
-- di mercato e' propizio (spot), il forward dice a quanto si potrebbe fissare
-- oggi, l'OBIETTIVO dice se quel prezzo va bene per il cliente. Niente
-- previsioni: confronto aritmetico tra il forward del periodo e un prezzo
-- obiettivo che Bros imposta per conto del cliente, per trimestre (prodotto
-- della curva, es. Q-2027-01) e distinto per commodity, in €/MWh di materia prima.
-- ============================================================

create table if not exists public.gas_obiettivi (
    id          bigint generated always as identity primary key,
    azienda_id  bigint not null references public.gas_aziende(id),
    commodity   text   not null check (commodity in ('gas', 'ee')),
    prodotto    text   not null,                -- prodotto della curva forward: Q-YYYY-QN (o CY-YYYY)
    prezzo      numeric(10,3) not null check (prezzo > 0),   -- €/MWh materia prima
    note        text   not null default '',
    attivo      boolean not null default true,
    autore      text   not null default '',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (azienda_id, commodity, prodotto)
);
comment on table public.gas_obiettivi is
    'Prezzi obiettivo per cliente e periodo (trimestre della curva forward), impostati da Bros: il forward e'' confrontato con questi.';
alter table public.gas_obiettivi enable row level security;
