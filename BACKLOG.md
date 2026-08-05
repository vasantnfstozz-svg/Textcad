# TextCAD backlog — top-level index of problems & workstreams

> **ACTIVE WORKSTREAM (2026-08-04): Feature tree — see
> [FEATURE-TREE-PLAN.md](FEATURE-TREE-PLAN.md)** (many changes incoming,
> requirements being captured there).
>
> **PARKED (2026-08-04): Manual design** — everything shipped + every open
> manual-design problem (viewport, sketch mode, extrude/modify tools,
> navigation, snapping) moved to **[MANUAL-DESIGN.md](MANUAL-DESIGN.md)**.
> The completed sketch-mode overhaul's development sheet stays in
> [SKETCH-MODE-PLAN.md](SKETCH-MODE-PLAN.md) for reference.

How this works:
- **One entry per problem, the moment it is noticed** — but file it in its
  workstream's own file (manual design → MANUAL-DESIGN.md, feature tree →
  FEATURE-TREE-PLAN.md). Only cross-cutting / unhomed items live below.
- Each entry: what's wrong → how to reproduce/see it → why it matters.
- Priorities: **P0** = silent wrong geometry or data loss (trust killers — fix
  first), **P1** = blocks basic manual design, **P2** = hurts daily use,
  **P3** = release/polish.
- We work top-down. A fix is only "done" after ship-check (tests + live smoke
  test), and the entry moves to Done with the commit hash.

Status snapshot (2026-08-04): geometry pipeline solid (dogfooding round 1,
2026-07-28: 5 agents built 5 parts through the UI, volumes <0.1% off hand
calcs). All P0 + P1 items fixed. Sketch-mode Fusion-parity overhaul S0–S6
complete. Details + Done history: MANUAL-DESIGN.md.

## To triage (dump new problems here if they don't clearly belong to a workstream file)

*(empty)*

## Cross-cutting P2

- [ ] **Compressor sample rebuild is slow (~1–2 min)** (pre-existing). Profile;
  cache unchanged sub-parts or parallelize blade builds.
- [ ] **Frontend automated test coverage is minimal.** `tests/e2e/` exists
  (shared server+browser via conftest) — keep adding one test per UI fix,
  in every workstream.

## P3 — release preparation / later

- [ ] **Vendor three.js locally** (unpkg CDN today — app breaks offline).
- [ ] **No LICENSE file / third-party notices.** Decide license; NOTICE for
  build123d/OCCT/three.js.
- [x] **No git remote (backup!)** — DONE 2026-08-05: private repo
  https://github.com/Vasan0021/textcad (gh CLI installed, device-flow auth,
  keyring). designs/*.tcad.json un-ignored so the design library is backed
  up too; ship-check now ends with `git push`. Still open: CI running
  pytest (heavy: build123d + playwright install per run — needs its own
  pass).
- [ ] **Assemblies/joints in Studio** (assembly.py exists; UI is single-part).
- [ ] **Units/grid settings** — everything is implicitly mm; at least label it.
- [ ] **AI-flow polish** (chat edits during rollback etc.) — parked until manual
  design is robust.

## Done

Moved with the manual-design workstream — see the Done section of
[MANUAL-DESIGN.md](MANUAL-DESIGN.md) (P0 batch, P1 batch, settings +
click-to-place, ribbon stages, Extrude v1 + drag arrow, trim tool, caching
fix, sketch-mode overhaul S0–S6 + follow-ups, with commit hashes).
