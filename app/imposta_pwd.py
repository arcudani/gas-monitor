"""Crea un utente del Gas Monitor e/o ne imposta la password.

Stessa ergonomia di App_Offerte/app/imposta_pwd.py (password chiesta UNA
volta, mostrato solo il numero di caratteri, conferma s/n) ma sulla tabella
DEDICATA public.gas_utenti. La password non transita mai in chiaro nei log.

Uso (da C:\\Code\\Gas_Monitor\\app):
    .\\.venv\\Scripts\\python.exe imposta_pwd.py                       # elenca utenti
    .\\.venv\\Scripts\\python.exe imposta_pwd.py Daniele --ruolo admin # crea/aggiorna
    .\\.venv\\Scripts\\python.exe imposta_pwd.py MarioRossi            # ruolo cliente
"""
from __future__ import annotations

import argparse
import getpass
import sys

import bcrypt

import config  # noqa: F401  (carica il .env)
import db


def elenca() -> None:
    rows = db.query(
        "SELECT username, ruolo, attivo, password_hash IS NOT NULL "
        "FROM public.gas_utenti ORDER BY username"
    )
    if not rows:
        print("Nessun utente in gas_utenti. Creane uno: "
              "python imposta_pwd.py <Nome> [--ruolo admin]")
        return
    for u, ruolo, attivo, ha_pwd in rows:
        print(f"  {u:<20} ruolo={ruolo:<8} attivo={attivo} "
              f"password={'impostata' if ha_pwd else 'MANCANTE'}")


def imposta(username: str, ruolo: str) -> int:
    pwd = getpass.getpass(f"Nuova password per {username}: ")
    print(f"Ricevuti {len(pwd)} caratteri.")
    if len(pwd) < 8:
        print("ERRORE: minimo 8 caratteri.")
        return 1
    if input("Confermi? [s/n] ").strip().lower() != "s":
        print("Annullato.")
        return 1
    h = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO public.gas_utenti (username, password_hash, ruolo) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (username) DO UPDATE SET "
            "  password_hash = excluded.password_hash, "
            "  ruolo = excluded.ruolo, updated_at = now()",
            (username, h, ruolo),
        )
        conn.commit()
    print(f"OK: password di {username} impostata (ruolo={ruolo}).")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("username", nargs="?", help="utente da creare/aggiornare")
    ap.add_argument("--ruolo", choices=["admin", "cliente"], default="cliente")
    args = ap.parse_args()
    if not args.username:
        elenca()
        sys.exit(0)
    sys.exit(imposta(args.username, args.ruolo))
