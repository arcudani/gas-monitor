-- ============================================================
-- Migrazione g001 — utenti e aziende del Gas Market Monitor.
--
-- Tabelle DEDICATE, separate da public.utenti (decisione requisiti
-- 18/08/2026): ERP e web app Offerte caricano public.utenti senza filtro di
-- ruolo, quindi un utente cliente messo lì entrerebbe ovunque. Qui invece
-- gli utenti del Gas Monitor sono isolati per costruzione.
--
-- Convenzioni repo: prefisso gas_*, numerazione g###_ (per non collidere con
-- le 000x_ di App_Offerte sullo stesso DB), SOLO ADDITIVA (DB condiviso con
-- la produzione). RLS abilitata senza policy (deny-all via PostgREST; l'app
-- si connette col ruolo postgres come le altre due).
-- ============================================================

-- ---------- AZIENDE (clienti e prospect) ----------
create table public.gas_aziende (
    id                 bigint generated always as identity primary key,
    nome               text not null unique,
    contrattualizzata  boolean not null default false,  -- false = prospect
    note               text not null default '',
    created_at         timestamptz not null default now()
);
comment on table public.gas_aziende is
    'Aziende degli utenti del Gas Market Monitor (anche prospect non contrattualizzati).';

-- ---------- UTENTI ----------
create table public.gas_utenti (
    id            bigint generated always as identity primary key,
    username      text not null unique,
    password_hash text,                                  -- bcrypt; NULL = mai impostata
    ruolo         text not null default 'cliente'
                  check (ruolo in ('admin','cliente')),  -- admin = consulente Bros
    azienda_id    bigint references public.gas_aziende(id),
    email         text not null default '',              -- per gli alert (RF-04)
    attivo        boolean not null default true,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);
comment on table public.gas_utenti is
    'Utenti del Gas Market Monitor. SEPARATI da public.utenti: chi sta qui NON accede a ERP/app Offerte.';
comment on column public.gas_utenti.ruolo is
    'admin = consulente Bros (tutto); cliente = dashboard/dettagli/propri alert/export.';

-- ---------- RLS: abilitata senza policy (deny-all) ----------
alter table public.gas_aziende enable row level security;
alter table public.gas_utenti  enable row level security;
