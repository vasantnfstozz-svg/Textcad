"""TextCAD Studio — development launcher with AUTO-RELOAD.

    python dev.py            -> http://127.0.0.1:8123
    python dev.py 8124       -> custom port

Unlike `python studio.py`, this watches the repo's .py files and restarts the
backend automatically whenever the code changes — so a running server can never
silently serve stale logic (the frontend already ships with no-cache headers).
Note: a code reload resets in-memory state (open tabs); the app auto-creates an
'untitled' document on first use.

The __main__ guard is REQUIRED on Windows: uvicorn's reloader spawns a
subprocess via multiprocessing spawn, which re-imports this file.
"""
import sys
import webbrowser
from pathlib import Path

import uvicorn

REPO = str(Path(__file__).resolve().parent)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    url = f"http://127.0.0.1:{port}"
    print(f"TextCAD Studio (dev, auto-reload) -> {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    uvicorn.run("studio:app", app_dir=REPO, host="127.0.0.1", port=port,
                reload=True, reload_dirs=[REPO], log_level="warning")
