# TextCAD backlog — the single source of truth for problems & missing tools

How this file works:
- **One entry per problem.** Every bug, friction point, or missing tool gets a line
  here the moment it is noticed — especially during dogfooding sessions.
- Each entry: what's wrong → how to reproduce/see it → why it matters.
- Priorities: **P1** = blocks basic manual design today, **P2** = hurts daily use,
  **P3** = release/polish/later.
- We work top-down. A fix is only "done" after ship-check (tests + live smoke test),
  and the entry moves to the Done section with the commit hash.

## To triage (dump new problems here, sort later)

- (empty — add anything that annoys you, even small things)

## P2 — found during first Playwright dogfooding (2026-07-28)

- [ ] **Viewport is blank WHITE for several seconds while the model loads** —
  /api/model tessellation takes ~3-6s on first load and the viewport shows plain
  white with no spinner; first impression is "broken". Fix: dark canvas from the
  start + a small "loading model…" indicator until the mesh arrives. (A transient
  broken-image icon also flashes top-left of the viewport during load — investigate
  while in there.)

## P1 — blocks basic manual design

- [ ] **Sketch trim tool missing.** Deferred at SK-P5 because it needs curve-curve
  intersection. Workaround is add/cut composition, but real 2D drafting needs trim.
  Repro: draw two overlapping lines in the sketcher — no way to cut one at the crossing.
- [ ] **Picked edge → fillet/chamfer not wired.** Viewport edge picking is
  inspect-only; fillet/chamfer only take rule-based groups ("all/top/bottom").
  Repro: Select mode → click an edge → no action offered. Face picking already has
  "Sketch on this face"; edges need the same treatment (needs a stable geometric
  edge reference, like face centers gave us for faces).
- [ ] **Plane-sketch flow is still two-step.** Sketch on a face auto-opens the
  boss/pocket dialog, but a plane sketch requires manually finding Extrude on the
  Sketch tab afterwards. New users get lost between the two steps.

## P2 — hurts daily use

- [ ] **No sketch dimensions editing after creation / no constraints.** Sketcher v1 is
  explicit-dimension only (by design, E5 deferred). Minimum viable step before a real
  solver: click a committed entity dimension label → retype the value.
- [ ] **Compressor sample rebuild is slow (~1–2 min).** 13 curved blades, tree-union.
  Any edit to that sample feels frozen. Profile → cache unchanged sub-parts or
  parallelize blade builds.
- [ ] **Frontend has zero automated tests.** 12 ES modules, all verified by hand only.
  Most "not robust" feelings live here. Fix: Playwright E2E suite (see e2e-test skill),
  starting with: load flange sample → edit param → rebuild → PASS badge.
- [ ] **No measure tools in viewport.** Can pick a face/edge and see area/length, but
  no distance-between-two-picks, no bounding box readout for the whole part.
- [ ] **No units/grid settings.** Everything is implicitly mm; sketch grid fixed at
  1 mm snap. Fine for now, but must at least be labeled in the UI.

## P3 — release preparation / later

- [ ] **Vendor three.js locally.** static/index.html loads from unpkg CDN
  (line ~182) — app breaks offline. Copy three@0.160.0 into static/vendor/.
- [ ] **No LICENSE file / third-party notices.** Repo is "all rights reserved" by
  default. Decide license, add NOTICE for build123d/OCCT/three.js.
- [ ] **No git remote (backup!).** Work exists only on this PC. Install gh CLI
  (`winget install GitHub.cli`), `gh auth login`, create private repo, push.
  Then: GitHub Actions CI running pytest on push.
- [ ] **Assemblies/joints in Studio.** assembly.py exists (fuse/fit verify) but the
  Studio UI is single-part only. E5-scale work.
- [ ] **Constraint solver for sketches** (SolveSpace binding or similar). The real
  Fusion-grade answer to sketch editing; only after manual design basics are solid.
- [ ] **Chat/AI authoring of edits during rollback** and other AI-flow polish — park
  until manual design is robust (current priority is manual tools first).

## Done

- (fixes move here with commit hash + date)
