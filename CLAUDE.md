# CLAUDE.md

Guidance for Claude Code working in this repository. Read this first, then
only the files the task touches. **The active workstream is
[LAUNCH-PLAN.md](LAUNCH-PLAN.md)** — its rules R1–R11 govern every change.

## What this repo is

TextCAD is a text-to-CAD system on build123d / OpenCASCADE. The product is
**TextCAD Studio**: a local web app (FastAPI backend, plain ES-module
frontend, three.js viewport) where an AI or the user builds a **feature tree**
and every feature can be re-opened and changed with the tool that made it.
The founding rule: **AI mistakes must never reach the user.** Geometry is
proven by the kernel and by measurement, never by code that looks right.

The user is not a code engineer. Explain in plain words, recommend rather than
obey when a better option exists, and confirm before anything outward or
destructive (pushes, deletes, restarts of their server).

`README.md` is the historical prototype document. How the system works is in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Commands

```powershell
python studio.py                 # the user's server: port 8123, opens a browser tab
python dev.py                    # auto-reload dev server (needs watchfiles; never for the user's server)

python -m pytest tests -q --ignore=tests/e2e    # fast tier (no browser)
python -m pytest tests/e2e -q                   # browser journeys (ship time only)
python -m pytest tests/test_history.py -q       # one file — the default while working
python -m pytest tests -m library -q            # opt-in: health of the user's LIVE designs/
```

`pytest.ini` excludes `library` tests by default; code tests read
`tests/fixtures/`, never `designs/`. No linter, no build step;
`pip install -r requirements.txt`.

**Environment facts (each one has cost real time):**

- Two Pythons exist. Everything is installed in `C:\Python314\python.exe`.
- Git is at `C:\Program Files\Git\cmd\git.exe`, not on PATH. Commit messages
  via `git commit -F <file>`; avoid `"` inside PowerShell here-strings.
- Launch the user's server DETACHED (`Start-Process ... -WindowStyle Hidden`),
  never as a session background task, never with `dev.py` (its reloader
  watches `designs/` and kills the server on a design-script edit). After a
  backend change, restart it and let it open the browser.
- Windows lets several processes listen on one port. Diagnose with
  `Get-NetTCPConnection -LocalPort 8123 -State Listen` then `Get-Process -Id`,
  never `netstat`.
- Env vars: `TEXTCAD_PORT`, `TEXTCAD_NO_BROWSER=1` (only for automated runs),
  `TEXTCAD_E2E_PORT`, `TEXTCAD_HISTORY_ROOT` (autoused by tests/conftest.py).
  API keys live in the user registry; read via `studio._user_env()`.
- Set `PYTHONIOENCODING=utf-8` for scripts that print geometry symbols.

## Before debugging anything the user saw in the browser

1. What does the status bar's `ui v<N>` say? If it is behind `main.js?v=` in
   `static/index.html`, the tab is stale — hard refresh, nothing to fix.
2. Is exactly ONE `studio.py` listening on 8123, started after the last
   backend change?
3. Only then read code. Their live `/api/doc` is the repro recipe.

## Non-negotiable rules

The detailed, learned-from-failure rules live in `.claude/skills/` — load the
relevant one before starting:

| Situation | Skill |
|---|---|
| Any code change | `textcad-dev` |
| Building or changing a modeling tool | `fusion-parity` (13 behaviour rules) |
| Adding a CAD op / a sketch entity | `add-operation` / `add-sketch-entity` |
| Before saying "it works" | `ship-check` (tempered by the token rules below) |
| After a frontend change | `ui-verify` |
| Anything broken or odd | `debug-studio` |
| Browser tests | `e2e-test` |

The five that decide whether a change is acceptable:

1. **Probe before you build** — never call a build123d/OCCT/three.js API from
   memory; probe in a script first, commit probes under `probes/`.
2. **Tests before commit** — the fast tier green; new capability = new tests.
3. **Never trust, always measure** — geometry claims are verified with
   `inspector`, not inferred.
4. **An operation is the feature TIMES the geometry** — ops that eat a face,
   profile or body run the corpus in `tests/gauntlet.py`; real bugs join it.
5. **Two ways to fail, both banned** — a kernel exception reaching the user
   (OCP errors derive from `Exception`, not `RuntimeError`) and a "successful"
   invalid or non-manifold solid. A failed feature beats a corrupt body.

Plus, from LAUNCH-PLAN.md:

- **Never re-derive a backend fact in the frontend** (R1). Axis, origin,
  frame, safe range, target body: a field on a server response, never JS math.
- **The viewport follows the document** (R3); no tool calls the refresh.
- **Frozen fixtures; red means red** (R6). Live-design health is `-m library`.
- **Every phase deletes more than it adds** (R10); record the line delta.

Two design rules the user has had to re-flag: **base first, then sketch on a
named face with an offset** (never an absolute-offset sketch once a body
exists), and **no sharp internal corners in milled parts**.

## Hooks (enforced by Claude Code itself, `.claude/settings.json` + `.claude/hooks/`)

Four house rules run automatically, so they do not depend on memory:

- **Edit/Write to `designs/*.tcad.json`, `designs/*.history/`, `.studio-session*.json` is DENIED** — the user's work is never edited by hand (stale-tab trap). Use the app's API or a generator script; test data lives in `tests/fixtures/`.
- **Every edit to `static/js/*.js` runs `node --check`**; a syntax error comes straight back.
- **`git push --force` (any form) is DENIED** — hand the command to the user.
- **Stop: uncommitted `static/` changes without a `main.js?v=` bump** block the turn with a reminder to bump.

Review or disable them with `/hooks`. Add new ones only for cheap, unambiguous checks.

## Token rules (the user's usage limit is real)

- One Claude session at a time on this checkout; a second one uses a worktree.
- Read CLAUDE.md, then only what the task touches. Plan files are history.
- Targeted test files while working; fast tier at ship; browser tier only for
  the tool being shipped. Never the full suite "to see".
- No agent fan-outs, no exploratory sweeps, no screenshot loops unless asked.
  The user runs a five-step checklist per tool instead.

## Frontend conventions

Plain ES modules, no framework. Modules talk over `bus.js` events and share
`state.js` (`S`). After ANY JS/CSS change bump `main.js?v=N` (and
`studio.css?v=N`) in `static/index.html` — read the CURRENT value first. A new
op is invisible until it is in `icons.js` (`OP_ICONS`, `TOOL_NAMES`) and a
`ribbon.js` tab.

## Commit style

Small, focused commits: capability + proof ("X: what it does; N new tests"),
author `-c user.name="Vasan Seenivasan" -c user.email="v.seenivasan@autonomiq.de"`,
then push to the private backup (github.com/Vasan0021/textcad). Force pushes
are the user's to run.

## Planning docs

`LAUNCH-PLAN.md` (active) · `BACKLOG.md` (index; §10 of the launch plan is the
ranked view) · workstream sheets `FEATURE-TREE-PLAN.md`, `MANUAL-DESIGN.md`,
`MEASURE-PLAN.md`, `VERSION-TREE-PLAN.md`, `SKETCH-MODE-PLAN.md` (history).
Priorities: P0 silent wrong geometry or data loss · P1 blocks basic design ·
P2 hurts daily use · P3 polish. Done means ship-checked, with the commit hash.
