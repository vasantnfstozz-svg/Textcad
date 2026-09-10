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
6. **Refresh `REVIEW-BRIEF.md`, then hand over — every time.** The review
   runs in a SEPARATE fresh chat on Opus 5 that starts with no context, so
   the brief is the handoff. **Rewrite it (never append):** first the line
   `Status: PENDING`, then the commit range and its base, one line per
   commit, where the risk is concentrated, this repo's ground rules for what
   counts as a finding, and the known-and-deferred list so nothing is
   re-reported. Then say in one line: "Open a new chat, type
   `/model claude-opus-5`, then type `code review`." CLAUDE.md's section
   "The review chat" tells that chat what to do: ONE reviewer, fixes in the
   same chat, brief back to NOTHING PENDING. Do this right after the CODE
   commit, before any docs/plan follow-up, and stamp the plan after the
   review. Worth it after every shipped tool or phase (2026-09-03: 4 real
   bugs the tests had not; 2026-09-07: a P0 the P0 pass itself introduced);
   skip it for docs, plan and memory commits. There is no user checklist
   after the review (retired 2026-09-10). Never `--fix`.
7. **Update memory** (the project memory file) with what shipped, the commit
   hash, and any lessons/bugs discovered.
8. Tell the user what to do to SEE it (usually Ctrl+F5) and how to verify it
   themselves in one sentence.
