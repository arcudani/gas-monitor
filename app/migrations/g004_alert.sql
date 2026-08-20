-- ============================================================
-- Migrazione g004 — alert email per utente (RF-04).
--
-- gas_alert:   regole per utente. Una riga = una soglia su una grandezza.
--              grandezza: 'indice' | 'prezzo' | 'stoccaggi' | 'meteo' |
--              'lng' | 'geopolitica' (valore della variabile, non punteggio,
--              tranne 'indice'). Condizione 'sopra' | 'sotto'.
--              Il superamento si valuta sul dato di ieri (dopo il job).
-- gas_alert_inviati: registro anti-duplicato — una notifica per regola e
--              giorno; la regola "riarma" quando il valore rientra
--              (cooldown_gg giorni minimi tra due invii della stessa regola).
--
-- Convenzioni: prefisso gas_*, SOLO ADDITIVA, RLS deny-all.
-- ============================================================

create table public.gas_alert (
    id          bigint generated always as identity primary key,
    utente_id   bigint not null references public.gas_utenti(id) on delete cascade,
    grandezza   text not null check (grandezza in
                  ('indice','prezzo','stoccaggi','meteo','lng','geopolitica')),
    condizione  text not null check (condizione in ('sopra','sotto')),
    soglia      numeric(12,3) not null,
    attivo      boolean not null default true,
    cooldown_gg int not null default 7,     -- giorni minimi tra due invii
    note        text not null default '',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
comment on table public.gas_alert is
    'Soglie di alert per utente del Gas Market Monitor (RF-04). Valutate dal job giornaliero dopo il ricalcolo.';

create table public.gas_alert_inviati (
    id         bigint generated always as identity primary key,
    alert_id   bigint not null references public.gas_alert(id) on delete cascade,
    data_dato  date not null,                -- giorno del dato che ha scattato
    valore     numeric(12,3) not null,
    inviato_at timestamptz not null default now(),
    unique (alert_id, data_dato)
);
comment on table public.gas_alert_inviati is
    'Registro invii alert: anti-duplicato per regola/giorno e base per il cooldown.';

create index idx_gas_alert_utente on public.gas_alert (utente_id) where attivo;

alter table public.gas_alert          enable row level security;
alter table public.gas_alert_inviati  enable row level security;
