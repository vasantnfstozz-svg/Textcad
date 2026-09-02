# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

TextCAD is a text-to-CAD system built on build123d/OpenCASCADE, plus **TextCAD
Studio** — a local web app (FastAPI + plain ES modules) that is the product
surface today. The founding thesis governs every design decision: **AI mistakes
must never reach the user.** Geometry is proven by the kernel and by
measurement, never by the code looking right.

> `README.md` is **stale** — it documents the original `generate.py`
> code-generation prototype (and a long-fixed API-key blocker). That pipeline
> still exists (`engine.py` / `check.py` / `generate.py`), but the live product
> is the feature-tree Studio described below. Trust this file, the
> `.claude/skills/`, and the `*-PLAN.md` docs over the README.

## Commands

```powershell
# --- run the app --------------------------------------------------------
python studio.py            # the user's server: port 8123, opens a browser tab
python dev.py               # dev server with auto-reload (requires watchfiles)
python dev.py 8124          # custom port

# --- tests --------------------------------------------------------------
python -m pytest tests -q                       # FULL suite, green before any commit (~5 min)
python -m pytest tests -q --ignore=tests/e2e    # fast inner loop (no browser)
python -m pytest tests/e2e -q                   # browser E2E only
python -m pytest tests/test_history.py -q       # one file
python -m pytest tests/test_history.py::test_the_hash_ignores_key_order -q   # one test
python -m pytest tests -q -k "extrude and not e2e"              # by keyword

# --- module self-tests (each file is runnable and self-verifying) -------
python blocks.py            # every block built + health-checked
python document.py          # feature-tree engine
python inspector.py         # the verifier
python engine.py            # Layer 1 oracle
```

There is no linter and no build step. Dependencies: `pip install -r requirements.txt`.

**Environment traps that have each cost real time:**

- **Two Pythons exist on this machine.** The one with everything installed is
  `C:\Python314\python.exe`; bare `python` may resolve to 3.12. Use the
  absolute path in configs, MCP registration, and E2E runs.
- **Git is not on PATH** — it lives at `C:\Program Files\Git\cmd\git.exe`.
- Never launch the *user's* server as a session background task — a session
  restart kills it and loses in-memory tabs. Launch it detached
  (`Start-Process -WindowStyle Hidden`), or reuse the one already running.
  Background-task launches are fine only for private test servers.
- `studio.py` refuses to bind a port that already answers (exit 3). On Windows
  several processes *can* listen on one port and replies come from whichever
  bound last — diagnose with `Get-NetTCPConnection -LocalPort N -State Listen`
  then `Get-Process -Id <OwningProcess>`, never `netstat` (it lists dead PIDs
  as LISTENING).
- `dev.py` **refuses to start without `watchfiles`**: uvicorn then falls back to
  statreload, which ignores `reload_excludes` entirely and restarts the server
  on any `designs/*.py` edit — taking every open tab with it.
- Env vars: `TEXTCAD_PORT`, `TEXTCAD_NO_BROWSER=1`, `TEXTCAD_E2E_PORT`,
  `TEXTCAD_HISTORY_ROOT` (autoused by `tests/conftest.py` so no test can write a
  version history into the user's `designs/` library). API keys
  (`OPENROUTER_API_KEY`) live in the user registry, read via
  `studio._user_env()` — `setx` values are invisible to already-running processes.

## Architecture

### The two walls every part must clear

```
intent -> ops from the verified registry -> deterministic rebuild
       -> LAYER 1 health   (inspector.health: a sane, single, watertight solid?)
       -> LAYER 2 verify   (inspector.verify vs a Spec: the RIGHT part?)
       -> failures come back as per-node problem strings, which feed repair
```

`inspector.py` is the whole verification story (`health` / `measure` / `verify` /
`Spec`) and is deliberately geometry-agnostic: it measures facts true of *any*
solid (mass, area, centre of mass, topology counts, manifoldness, rotational
symmetry). Nothing in it raises — a failed measurement becomes a reported
problem, never a crash.

### The feature tree is the anti-hallucination mechanism

`document.py` is the core. A design is a `Document` = an ordered list of
`Feature` nodes forming a DAG (`inputs` names upstream ids). Every node's `op`
must come from one of three registries, so an LLM **cannot invent API**:

- `CREATORS` — no geometric inputs (`plate`, `disc`, `sketch`, `import_step`, …)
- `MODIFIERS` — exactly one upstream part (`fillet`, `extrude`, `extrude_face`,
  `sketch_on_face`, `polar_pattern`, `shell`, …)
- `COMBINERS` — two or more upstream parts (`fuse`, `cut`, `intersect`, `loft`)

`KNOWN_OPS` is derived from these three dicts, which is why registering an op
there makes it legal in feature trees, in the op catalog, and over MCP
automatically.

Editing means `Document.edit(feature_id, param, value)` → deterministic rebuild
through verified blocks. **The LLM never regenerates a design during an edit** —
regeneration is exactly where other tools drift ("change the bore" quietly
becomes a different part).

Two subtleties to know before touching `rebuild()`:

- **Content-addressed cache.** A feature's signature covers its op, params, and
  its *inputs' signatures* — so renaming a feature keeps every cache entry, and
  editing one parameter invalidates exactly that feature and its descendants.
- **Rebuild cost is dominated by the checks, not the geometry.** `health()` must
  never route through `measure()` (that once ate 65% of a 22 s rebuild), and
  `is_valid` (~270 ms on a large solid) runs on the final result only —
  intermediates use `health(part, check_valid=False)`.
  `tests/test_rebuild_speed.py` guards both.

### Module map

| Layer | Files |
|---|---|
| Kernel-facing geometry | `blocks.py` (verified block library — every fn self-tested and listed in `EXPORTS`), `sketch.py` (2D entities + extrude/revolve/loft/sweep + `sketch_on_face`), `sketch_trim.py`, `sketch_snap.py`, `sketch_corner.py`, `meshrepair.py`, `imgtrace.py` (PNG → sketch) |
| Verification | `inspector.py` (Layer 2), `engine.py` (Layer 1 oracle for raw LLM scripts — do not modify casually), `check.py` (the original flange-era checker) |
| Document model | `document.py` (tree, rebuild, undo, rollback, delete/strike plans), `history.py` (per-design version tree; storage only, no HTTP and no Document import), `provenance.py` (face → the feature that made it), `measure.py` (read-only measurement kernel) |
| AI | `author.py` (natural language → feature-tree JSON, validation gates + repair loop), `generate.py` (legacy code-gen loop), `meanline.py` (compressor physics — the domain-plugin pattern) |
| Surfaces | `studio.py` (**HTTP API only**, ~50 endpoints, multi-tab `STATE`), `mcp_server.py` (6 MCP tools; stdout IS the protocol, so keep geometry calls inside `_quiet()`), `static/` (the UI) |

`studio.py` holds many open designs at once: `STATE["docs"]` maps tab-id →
`{doc, ok, rebuild_ms, history}`, and `STATE["active"]` names the tab every
`/api` call operates on. It is a module global — reset it in fixtures, and never
run E2E concurrently with anything else that touches it.

### Frontend

Plain ES modules — no framework, no bundler. Modules never import each other in
order to communicate: they talk over `bus.js` events (`doc-updated`, `msg`,
`sketch-on-face`, `settings-changed`) and share `state.js` (`S`). One module,
one job: `viewport.js` (three.js scene, picking, drag gizmos), `sketcher.js`,
`tree.js`, `extrude.js`, `measure.js`, `versions.js`, `ribbon.js`,
`provenance.js`.

**After ANY JS/CSS change, bump the cache-buster** `main.js?v=N` (and
`studio.css?v=N`) in `static/index.html`, and tell the user to Ctrl+F5. The
running app stamps its build into the status bar as `ui vN` — **check that stamp
before debugging any frontend report**, because a long-open tab still runs the
JS it downloaded days ago and no-cache headers cannot help a page that never
reloads.

A new op is invisible to users until it is in **both** `icons.js` (`OP_ICONS` +
`TOOL_NAMES`) and a ribbon tab in `ribbon.js` (`TABS`).

### Data on disk

- `designs/<slug>.tcad.json` — the design (name, spec, features). The recipe is
  the artifact, not the STEP it produces. **Git-tracked user work.**
- `designs/<slug>.history/` — `index.json` (version nodes, parents, labels,
  star, `current`) plus gzipped `vN.json.gz` snapshots. Also **git-tracked**. A
  directory rather than one file for two reasons that bite in practice:
  appending a version must not rewrite the whole history, and one corrupt
  snapshot must not take the other twenty with it.
- `imports/` — user-uploaded STL/STEP that designs reference by name; tracked,
  because a backup without them would not rebuild.
- `.gitignore` ignores `*.step` / `*.stl` / `*.tcad.json` globally and then
  re-includes those three paths. Preserve that shape when editing it.

## Non-negotiable working rules

`.claude/skills/` is the canonical, detailed source — every rule in there was
learned from a real failure. **Load the relevant skill before starting**, not
after:

| Situation | Skill |
|---|---|
| Any code change in this repo | `textcad-dev` |
| Building or changing any modeling tool (extrude, revolve, fillet, patterns…) | `fusion-parity` — **mandatory**; it prevents the "form-first" / "sketch-only" mistakes the user keeps having to correct |
| Adding a CAD operation | `add-operation` |
| Adding a 2D sketch entity | `add-sketch-entity` |
| Before saying "it works" | `ship-check` |
| After any frontend change | `ui-verify` |
| Anything broken or behaving oddly | `debug-studio` |
| Writing browser tests | `e2e-test` |

The five rules that decide whether a change is acceptable:

1. **Probe before you build.** Never write build123d/OCCT code from memory —
   run a scratchpad probe, confirm the API exists and behaves as claimed, then
   write the real code.
2. **Tests before commit.** `python -m pytest tests -q` green; new capability =
   new tests locking it in.
3. **Never trust, always measure.** Any claim about geometry gets verified
   through `inspector`, never inferred from source that looks right.
4. **An operation is the feature TIMES the geometry.** Any op that consumes a
   face, profile, or body must run the corpus in `tests/gauntlet.py` — testing
   it on the shape you developed it against covers one cell of a large grid.
   When a real bug is found, add its geometry to `BODIES` so the corpus only
   ever grows.
5. **Two ways to fail, both banned:** a kernel exception reaching the user
   (**OCP errors derive from `Exception`, not `RuntimeError`** — an
   `except RuntimeError` barrier does not catch them), and a "successful" result
   that is actually an invalid or non-manifold solid. A failed feature beats a
   silently corrupt body.

### Two design rules the user has had to re-flag repeatedly

- **BASE FIRST, THEN SKETCH ON THE BASE (the offset method).** Build the base
  body, then make every later sketch a `sketch_on_face` on the current body,
  naming its face (`face: "top"|"bottom"|"+x"|…`) with depth stated as an
  `offset` from that face. A `sketch` with a nonzero absolute offset once a body
  exists hardcodes the base thickness and strands every downstream feature —
  `author.py` lints and rejects it for AI/MCP-authored trees. Pick the datum
  carrying the invariant: a cavity is "leave a 3 mm floor"
  (`face:"bottom", offset:3`), not "9 mm deep". And a face gives a plane its
  **position, never its orientation** — frames are canonicalised to the
  principal plane so `(x, y)` means the same thing on every face.
- **No sharp internal corners in any milled design.** Real cutters are round:
  pockets need r ≥ 1.5, no rectangular clips, no wall T-junctions.

### Commit style

Small, focused commits; an imperative message stating the capability **plus its
proof** ("X: what it does; N new tests (M total)"). Author with
`-c user.name="Vasan Seenivasan" -c user.email="v.seenivasan@autonomiq.de"`.
Push after ship-check — the private backup at github.com/Vasan0021/textcad only
protects what actually gets pushed.

## Planning docs

Problems get filed the moment they are noticed, into their workstream's own
file. `BACKLOG.md` is the index and holds only cross-cutting items; the
workstream sheets are `FEATURE-TREE-PLAN.md`, `MANUAL-DESIGN.md`,
`MEASURE-PLAN.md`, `VERSION-TREE-PLAN.md`, and `SKETCH-MODE-PLAN.md` (complete,
kept for reference). Priorities: **P0** = silent wrong geometry or data loss
(trust killers), **P1** = blocks basic manual design, **P2** = hurts daily use,
**P3** = polish. An item is only "done" after ship-check, and then moves to Done
with its commit hash.
