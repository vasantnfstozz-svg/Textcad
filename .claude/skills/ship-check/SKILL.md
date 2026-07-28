---
name: ship-check
description: The pre-commit shipping routine for TextCAD — full test suite, server restart, live API smoke test, cache-bust check, then commit. Run at the end of every feature before telling the user it works.
---

# Ship-check — run before every "it's done"

1. **Full suite**: `python -m pytest tests -q` — must be 100% green.
2. **Restart the server** if backend files changed: stop the background
   `python studio.py` task, relaunch, wait ~15s.
3. **Live smoke test** through the real HTTP API (Invoke-RestMethod):
   exercise the NEW capability end-to-end at least once — not just unit tests.
4. **Frontend changed?** Confirm `main.js?v=N` was bumped in static/index.html
   and every new JS/CSS file serves 200 from `/static/...`.
5. **Commit** with capability + proof in the message
   (`git` is at `C:\Program Files\Git\cmd\git.exe`).
6. **Update memory** (the project memory file) with what shipped, the commit
   hash, and any lessons/bugs discovered.
7. Tell the user what to do to SEE it (usually Ctrl+F5) and how to verify it
   themselves in one sentence.
