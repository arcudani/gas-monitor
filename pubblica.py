"""Pubblica in produzione (Streamlit Community Cloud) con riavvio garantito.

Perche' esiste: Streamlit Cloud, dopo un push, ricarica a caldo solo lo script
principale. I moduli importati (registro_moduli.py, branding.py, i moduli delle
pagine) restano quelli vecchi finche' l'app non viene riavviata: gli utenti
continuano a vedere la versione precedente (successo il 27/10/2026 con la
pagina "Forward e obiettivi"). Una modifica a requirements.txt, invece, forza
reinstallazione e riavvio completo. ATTENZIONE: Streamlit Cloud legge
app/requirements.txt (non quello nella radice, che delega soltanto): il timbro
va messo li', verificato nei log del 27/10/2026.

Cosa fa:
  1. verifica che la working tree sia pulita (tutto committato);
  2. aggiorna l'ultima riga di app/requirements.txt con il timbro di deploy;
  3. commit "Deploy: <nota>" e push su origin/main.

Uso (da C:\\Code\\Gas_Monitor, DOPO l'ok esplicito dell'utente al push):
    python pubblica.py "pagina Forward e obiettivi"
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RADICE = Path(__file__).resolve().parent
REQ = RADICE / "app" / "requirements.txt"   # e' QUESTO che Streamlit Cloud usa (log: "Used: uv with .../app/requirements.txt")
TIMBRO = re.compile(r"^# deploy \d{2}/\d{2}/\d{4} \d{2}:\d{2}.*$", re.M)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RADICE, check=True,
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    nota = " ".join(sys.argv[1:]).strip() or "aggiornamento"
    if git("status", "--porcelain"):
        print("ERRORE: ci sono modifiche non committate. Committa prima, poi pubblica.")
        return 1
    testo = REQ.read_text(encoding="utf-8")
    riga = f"# deploy {datetime.now():%d/%m/%Y %H:%M} — {nota} (riga che forza il riavvio su Streamlit Cloud)"
    if TIMBRO.search(testo):
        testo = TIMBRO.sub(riga, testo, count=1)
    else:
        testo = testo.rstrip("\n") + "\n\n" + riga + "\n"
    REQ.write_text(testo, encoding="utf-8", newline="\n")
    git("add", str(REQ.relative_to(RADICE)))
    msg = RADICE / ".git" / "DEPLOY_MSG"
    msg.write_text(f"Deploy: {nota}\n\nTimbro in requirements.txt per forzare il riavvio su Streamlit Cloud.\n", encoding="utf-8")
    git("commit", "-q", "-F", str(msg))
    git("push", "origin", "main")
    print(f"OK: {git('log', '-1', '--format=%h %s')} pushato. Streamlit Cloud reinstalla e riavvia (1-3 minuti).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
