---
name: textcad-dev
description: House rules for ALL TextCAD development — load before writing or changing any code in this repo (geometry, backend, frontend, tests). Encodes the probe-first, test-always, verify-everything discipline this project is built on.
---

# TextCAD development house rules

TextCAD's whole purpose is "AI mistakes never reach the user." The same
discipline applies to developing it. Follow these rules on every change.

## The golden rules

1. **Probe before you build.** Never write code against a build123d/OCCT API
   from memory. Write a tiny probe script in the scratchpad, run it, confirm
   the API exists and behaves as expected, THEN write the real code. This has
   caught hallucinated APIs (`is_valid()` as method, `make_face` after
   RegularPolygon, sphere `is_manifold` false negatives) many times.
2. **Tests before commit.** `python -m pytest tests -q` must be green before
   every commit. New capability = new tests in `tests/` locking it in.
   A live smoke test through the HTTP API counts extra (see ship-check skill).
3. **Never trust, always measure.** Any claim about geometry ("the boss is on
   the face", "it's 7-fold symmetric") must be verified via `inspector`
   measurements, not assumed from the code looking right.
4. **An operation is the feature TIMES the geometry.** Testing an op on the
   shape you developed it against tests one cell of a large grid. Every op
   that eats a face/profile/body must run the corpus in `tests/gauntlet.py`
   (see the add-operation skill). Extrude+taper passed on a box, shipped, and
   then failed on a pentagon face of a FUSED body — in ONE taper direction —
   because fusing a tapered body leaves straight BSPLINE seam edges that
   OCCT's 2D offset silently turns to garbage. The corpus grows with every
   real bug; that is how the same class never ships twice.
5. **Two ways to fail, both banned.** A kernel exception reaching the user
   (OCP errors derive from `Exception`, NOT `RuntimeError` — an
   `except RuntimeError` barrier does not catch them), and a "successful"
   result that is actually an invalid or non-manifold solid. Check the health
   of what you return; a failed feature beats a silently corrupt body.

## Architecture map (where things go)

- `engine.py` — Layer 1 oracle (LLM script exec). Do not modify casually.
- `inspector.py` — Layer 2 verifier: health/measure/verify/Spec. Deterministic.
- `blocks.py` — verified block library (every fn self-tested, in EXPORTS).
- `sketch.py` — 2D sketch system (entities, extrude/revolve/loft/sweep).
- `document.py` — feature-tree engine: CREATORS/MODIFIERS/COMBINERS registries,
  rebuild, undo data, rollback.
- `author.py` — AI authoring of feature trees (validation gates + repair loop).
- `studio.py` — HTTP API ONLY (multi-tab STATE). UI lives in `static/`.
- `mcp_server.py` — MCP doorbell (5 tools). stdout is protocol — keep _quiet().
- `static/js/*.js` — one module, one job; modules talk via `bus.js` events
  ('doc-updated', 'msg', 'sketch-on-face'), shared state in `state.js`.

## Frontend rules

- After ANY JS/CSS change: bump the cache-buster `main.js?v=N` in
  static/index.html, and tell the user to Ctrl+F5.
- No frameworks, no bundlers — plain ES modules only.
- New op must be added to: `icons.js` (OP_ICONS + TOOL_NAMES) AND a ribbon tab
  in `ribbon.js` (TABS), or it is invisible to users.

## Backend rules

- The server runs as a background task; after backend changes, stop it and
  relaunch `python studio.py`, then wait ~15s before hitting endpoints.
- Windows: two Pythons exist — the right one is `C:\Python314\python.exe`.
  Git is at `C:\Program Files\Git\cmd\git.exe` (not on PATH).
- API keys live in the user environment (registry via `_user_env`), NEVER in
  files or commits.

## Commit style

- Small, focused commits with imperative messages describing capability +
  proof: "X: what it does; N new tests (M total)".
- Author: `-c user.name="Vasan Seenivasan" -c user.email="v.seenivasan@autonomiq.de"`.
