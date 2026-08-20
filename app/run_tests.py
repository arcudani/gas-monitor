"""Esegue tutta la suite (ogni test_*.py è anche eseguibile standalone).

    python run_tests.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FILES = sorted(Path(__file__).parent.glob("test_*.py"))

if __name__ == "__main__":
    # stdout UTF-8 nei sottoprocessi: i test stampano emoji/€ e su Windows
    # la console cp1252 farebbe fallire il print (non il test).
    env = {**os.environ, "PYTHONUTF8": "1"}
    esiti = {}
    for f in FILES:
        print(f"\n=== {f.name} ===")
        r = subprocess.run([sys.executable, str(f)], env=env)
        esiti[f.name] = r.returncode
    print("\n--- Riepilogo ---")
    for nome, rc in esiti.items():
        print(f"  {'OK ' if rc == 0 else 'FAIL'} {nome}")
    sys.exit(1 if any(esiti.values()) else 0)
