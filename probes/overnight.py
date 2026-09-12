"""The overnight journey run, detached and safe.

    Start-Process C:\\Python314\\python.exe -ArgumentList "probes/overnight.py --hours 8" -WindowStyle Hidden

Keeps the machine AWAKE while it runs (the laptop enters Modern Standby on
its idle timeout — the System log showed it doing so mid-run on 2026-09-12),
writes the per-step lines to bugs/journeys-stdout.log, and passes everything
else to tests/journeys.py, whose children each run under the 6 GB Job-object
ceiling. Defaults: --library, 30 steps, until --hours.
"""
import ctypes
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
if sys.platform == "win32":
    ctypes.WinDLL("kernel32").SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)

log = (ROOT / "bugs" / "journeys-stdout.log").open("w", encoding="utf-8", buffering=1)
# at the OS level, so the CHILDREN's per-step lines land in the same file (a
# hidden window has no console: a Python-level redirect kept only the parent's)
os.dup2(log.fileno(), 1)
os.dup2(log.fileno(), 2)
sys.stdout = sys.stderr = log
args = sys.argv[1:] or ["--hours", "8"]
if "--library" not in args:
    args = ["--library"] + args

import journeys  # noqa: E402

code = journeys.main(args)
if sys.platform == "win32":
    ctypes.WinDLL("kernel32").SetThreadExecutionState(ES_CONTINUOUS)
sys.exit(code)
