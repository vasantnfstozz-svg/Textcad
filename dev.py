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
import os
import sys
import webbrowser
from pathlib import Path

import uvicorn

REPO = str(Path(__file__).resolve().parent)

# designs/ holds the user's WORK, not code: the generator scripts are .py, and
# every recorded version writes into <slug>.history/. Watching it restarts the
# server mid-session and takes every open tab with it — which is what "the
# webserver crashes many times" turned out to be.
EXCLUDE = ["designs/*", "designs/**", "*.tcad.json", "*.step", "*.stl"]

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    url = f"http://127.0.0.1:{port}"

    try:
        import watchfiles                                     # noqa: F401
    except ImportError:
        # Without watchfiles uvicorn falls back to statreload, which polls every
        # *.py under reload_dirs and IGNORES reload_excludes — so the list above
        # would quietly do nothing (measured on uvicorn 0.51.0). Refuse rather
        # than hand back a reloader that eats the user's open tabs.
        print("watchfiles is not installed, so auto-reload cannot skip "
              "designs/.")
        print("Editing a design script would restart the server and close "
              "every open tab.")
        print("  pip install watchfiles     (then dev.py is safe)")
        print("  python studio.py           (no auto-reload, nothing to lose)")
        sys.exit(2)

    print(f"TextCAD Studio (dev, auto-reload) -> {url}")
    if os.environ.get("TEXTCAD_NO_BROWSER") != "1":
        try:
            webbrowser.open(url, new=2)          # 2 = a TAB, not a new window
        except Exception:
            pass
    uvicorn.run("studio:app", app_dir=REPO, host="127.0.0.1", port=port,
                reload=True, reload_dirs=[REPO], reload_excludes=EXCLUDE,
                log_level="warning")
