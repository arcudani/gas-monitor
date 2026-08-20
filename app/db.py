"""
Helper di connessione PostgreSQL (Supabase) — psycopg 3.

Ripreso da App_Offerte (app/data/db.py) e snellito: il Gas Monitor usa il DB per
`gas_utenti` (login proprio) e le serie di mercato `indici_mercato`. La connection
string è letta SOLO da env `SUPABASE_DB_URL` (segreto, mai nel repo).
"""
from __future__ import annotations

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row, tuple_row

try:
    from psycopg_pool import ConnectionPool
except ImportError:  # senza psycopg-pool si apre una connessione per query
    ConnectionPool = None  # type: ignore[assignment,misc]

import config


class DBConfigError(RuntimeError):
    pass


def conn_str() -> str:
    s = config.supabase_db_url()
    if not s:
        raise DBConfigError(
            "SUPABASE_DB_URL non impostata. Inseriscila nel file .env "
            "(Supabase > Project Settings > Database > Connection string > URI)."
        )
    return s


# Pool di connessioni condiviso per processo: evita l'handshake TCP/TLS verso
# Supabase (Francoforte) a OGNI query. Il Transaction pooler (pgbouncer)
# multiplexa lato server, al client bastano poche connessioni.
_POOL = None


def _pool():
    global _POOL
    if _POOL is None:
        _POOL = ConnectionPool(
            conn_str(),
            min_size=1,
            max_size=2,
            max_idle=300,
            check=ConnectionPool.check_connection,
            kwargs=dict(row_factory=dict_row, prepare_threshold=None,
                        connect_timeout=15),
            open=True,
        )
    return _POOL


@contextmanager
def connect(autocommit: bool = False):
    """Presta una connessione dal pool (row_factory=dict_row).
    prepare_threshold=None disabilita i prepared statement lato server:
    necessario per il Transaction pooler di Supabase (pgbouncer)."""
    if ConnectionPool is None:
        with psycopg.connect(
            conn_str(), row_factory=dict_row, connect_timeout=15,
            prepare_threshold=None, autocommit=autocommit,
        ) as conn:
            yield conn
        return
    with _pool().connection() as conn:
        conn.autocommit = autocommit
        yield conn


def query(sql: str, params=None) -> list[tuple]:
    """Esegue una SELECT e ritorna righe come TUPLE posizionali.
    Lettura in autocommit + retry con backoff sui problemi transitori
    (drop del pooler, blip DNS/rete)."""
    import time
    last_err = None
    for _attempt in range(3):
        try:
            with connect(autocommit=True) as conn:
                cur = conn.cursor(row_factory=tuple_row)
                cur.execute(sql, params or ())
                return cur.fetchall()
        except psycopg.OperationalError as e:
            last_err = e
            time.sleep(0.6 * (_attempt + 1))  # backoff: 0.6s, 1.2s
    raise last_err


def ping() -> bool:
    """Verifica rapida di connettività."""
    with connect() as conn:
        conn.execute("SELECT 1")
    return True
