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
   (`git` is at `C:\Program Files\Git\cmd\git.exe`), then **`git push`** —
   the private backup at https://github.com/Vasan0021/textcad only protects
   what actually gets pushed (gh CLI is authenticated via keyring).
6. **Recommend the code review — say it, every time.** Right after the CODE
   commit, tell the user in one line: "recommended now: `/code-review high`"
   (the user runs it; it fans out subagents, so it is theirs to spend). It
   runs on HEAD, so recommend it BEFORE any follow-up docs/plan commit — or
   name the code commit hash in the recommendation. Worth it after every
   shipped phase or tool (the 2026-09-03 taper review found 4 real bugs the
   tests had not); skip it for docs, plan and memory commits. Order: commit →
   review → fix findings → THEN the user's five-step checklist, so the user
   never tests bugs a robot would have caught.
7. **Update memory** (the project memory file) with what shipped, the commit
   hash, and any lessons/bugs discovered.
8. Tell the user what to do to SEE it (usually Ctrl+F5) and how to verify it
   themselves in one sentence.
