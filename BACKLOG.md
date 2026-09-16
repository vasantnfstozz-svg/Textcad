# TextCAD backlog — top-level index of problems & workstreams

> **ACTIVE WORKSTREAM (2026-09-02): [LAUNCH-PLAN.md](LAUNCH-PLAN.md)** — the
> tool framework, drag-handle tools, the AI using the same tools, and
> frozen-fixture testing, phases P0–P6. Its §10 carries the deduplicated
> open items from every sheet below with launch priorities. New problems
> still get filed here or in their workstream sheet the moment they are
> noticed; LAUNCH-PLAN.md §10 is the ranked view.
>
> The pause of 2026-08-17 ended 2026-08-18. Since then: design work for the
> SimplyMill QA parts, the version tree (VERSION-TREE-PLAN.md, P0–P6
> shipped), Measure & drive (MEASURE-PLAN.md, P0–P2 + ten feedback rounds),
> strike-out delete, STEP import/export guard, session restore. The feature
> tree sheet's remaining item (step 4, incremental AI authoring) is
> LAUNCH-PLAN.md P5.
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

- [ ] **The body-pattern health gate is retroactive: no grandfathering.**
  `pattern._body_pattern` now runs `inspector.health` on the fused union
  (c4d5961, closing a P0 where a tangent join came back as a 2-solid open
  shell "success"). It runs on EVERY rebuild, so a design saved BEFORE that
  commit whose copies happen to touch along an edge would go red the next time
  it loads, where it used to open. Raised by the `/code-review` of
  c4d5961 + 85821be (2026-09-07). **Measured clean against every design in
  `designs/` — up to 34 separate solids, all healthy — so nothing of the
  user's is affected.** Kept as-is deliberately: the alternative is handing
  back a non-manifold body in silence, which is the banned failure mode, and
  the refusal is a sentence that names the edge. The rule it sits against
  ("a saved design may never stop rebuilding") exists to stop refusals of
  geometry that is FINE; this geometry is genuinely broken. **P3** — accepted
  risk, recorded so it is not rediscovered as a surprise. If it ever bites a
  real file, the fix is to warn rather than fail for a pattern whose feature
  was saved by an older build.

- [ ] **Right-edge tool panels cover the AI-designer pane.** `#measureDialog`
  and `#extrudeDialog` are both `position:fixed; right:24px`, so an open tool
  panel sits on top of the chat column (visible in the Measure UI verification,
  2026-08-27). Harmless while one command runs at a time, but the chat is where
  failures are reported (rule 7), so hiding it while a tool is open is
  backwards. Either dock tool panels inside the viewport pane or shift them
  left of the chat. **P3** — cosmetic, pre-existing, not specific to Measure.

- [ ] **Measure: no snap to vertices or arc centres yet.** P0 measures
  face-to-face, edge-to-edge and diameters, which covers the user's request,
  but "distance between two POINTS" in their words still means picking the
  faces/edges those points belong to. Vertex picking would close the gap — the
  raycaster already has an edge threshold to copy. **P2**, tracked in
  [MEASURE-PLAN.md](MEASURE-PLAN.md).

- [x] **Version tree per design** — SHIPPED (P0–P6, see
  [VERSION-TREE-PLAN.md](VERSION-TREE-PLAN.md); tab reuse 9f41fd1, history
  storage 2c8ffa1, API 59b87bd, panel 820d158, backfill e327540, explicit
  push 073ef85, update-vs-push + trim 127d3d0). Open there: prune policy,
  per-version thumbnails.

- [ ] **autonomiq-sat-panel v3 needs a tooling pass** (audited 2026-08-26,
  after fa9bc15). The geometry verifies (1 manifold solid) but several new
  features model shapes a round cutter cannot make, which is the corner rule
  the user keeps having to re-flag:
  * **92 gear notches taper 3.20 -> 1.90mm over 2.9mm of depth and end in
    SHARP corners** (4-point polygons, no arc segments; sharpest angle
    76.9 deg). The widest cutter that fits the tip is D1.9, and it will
    leave r0.95 there — so the notch bottoms come out semicircular, not
    flat-with-corners as modelled. Either round the tips in the model to
    the chosen cutter radius, or widen the tip so a sane bit fits.
  * **Frame groove is 1.2mm wide** (PANEL_BW) and the trace slots 1.4,
    vents 1.5, hatch stripes 2.0 — so the part currently needs a sub-1.5mm
    cutter in several places. Decide the smallest bit that actually exists
    and drive these widths from it, the way esp32-remote drives its
    lettering off LOGO_TOOL_D.
  * **Blade trailing edges close to 31.8 deg.** The blade is left standing
    in an r7.8 arena pocket, so near the TE the gap between blade and arena
    wall narrows to a wedge no round cutter can enter — the mill will
    leave a fillet there, and a near-zero-thickness TE in steel is fragile
    anyway. Blunt the TE to a real width.
  Unlike the esp32 script (which gates LOGO_TOOL_D and a r>=1.5 internal
  corner minimum), the sat-panel gates only check clearances and
  collisions — no tool-size gate exists to catch any of this. Add one.

- [ ] **P0 — clockwise polygons silently refuse to fuse** (found 2026-08-18
  designing rocky-keychain during the pause). A `polygon` sketch entity whose
  points run CLOCKWISE builds a face with a −Z normal; OCCT fuse then quietly
  keeps it as a SEPARATE face — every entity overlapping it stays disjoint, and
  the downstream extrude+cut yields a non-manifold "open shell" solid. The 2D
  intersection areas are nonzero (2–4 mm²), so nothing looks wrong until Layer 2
  fails the cut. Repro: torso polygon of rocky-keychain with reversed points.
  Fix: normalize winding to CCW in `sketch._entity` polygon branch (shoelace
  sign test, reverse if negative) + regression test. Same normalization is
  already proven in the design generator (scratchpad `rocky_probe.py`).
- [x] **P2 — /api/model has no mesh cache** — SUPERSEDED: studio.py now
  keeps a process-wide `_MESH_CACHE` plus a per-tab `model_json` cache keyed
  on the rebuild stamp (`_geom_version`). Still open from this entry: a
  visible "meshing…" state while a first tessellation runs (the viewport
  sits empty with a green tree — see the import gotchas).
- [ ] **P3 — `text` sketch entity** (build123d `Text`). rocky-keychain needed
  font lettering; had to bake Impact outlines into polygon entities offline.
  A first-class text entity (font, size, position) via the add-sketch-entity
  checklist would make name plates / engraving one entity instead of ~15.

## Cross-cutting P2

- [ ] **Compressor sample rebuild is slow (~1–2 min)** (pre-existing). Profile;
  cache unchanged sub-parts or parallelize blade builds.
- [ ] **Frontend automated test coverage is minimal.** `tests/e2e/` exists
  (shared server+browser via conftest) — keep adding one test per UI fix,
  in every workstream.

## P3 — release preparation / later

- [x] **Vendor three.js locally** — DONE 6b4c494: `static/vendor/three/0.160.0/`
  holds the exact r160 build plus the two add-ons the viewport imports and the
  project's MIT licence; the import map in `static/index.html` points at them.
  The app no longer needs the internet to draw anything.
- [x] **Third-party notices** — DONE 6b4c494: `THIRD-PARTY-NOTICES.md`, every
  licence read from the installed package's own metadata. The one with
  consequences is OCCT inside the OCP wheel (LGPL-2.1 + the Open CASCADE
  Exception), and that file is now the "prominent notice" the exception asks
  for. **Still open and deliberately so: TextCAD's OWN licence.** No LICENSE
  file is written — it is the user's decision (the options are in the report
  that came with 6b4c494).
- [x] **No git remote (backup!)** — DONE 2026-08-05: private repo
  https://github.com/Vasan0021/textcad (gh CLI installed, device-flow auth,
  keyring). designs/*.tcad.json un-ignored so the design library is backed
  up too; ship-check now ends with `git push`. Still open: CI running
  pytest (heavy: build123d + playwright install per run — needs its own
  pass).
- [ ] **A suppressed final boolean promotes its TOOL to the result.**
  Suppress the last `cut` in a sketch->tool->cut chain and `result()`
  walks back to the tool prism (a real solid, so it qualifies) instead
  of the body the user is looking at — the viewport then shows the
  cutting prism as the part. Found 2026-08-25 while testing the rebuild
  cache (tests/test_rebuild_cache.py pins the current behaviour so a
  fix is a deliberate change). Probably: prefer the last feature on the
  result body's input[0] spine over any later stray solid.
- [x] **MCP doorbell re-fires on every page load** — DONE 6b4c494. The banner
  was inferred in JS from the active tab differing from the previous poll (a
  backend fact re-derived in the frontend, R1), so every reload replayed it.
  The server holds ONE marker now: `mcp_server` posts
  `/api/open/<slug>?external=1`, `/api/doc` carries `arrival`, and
  `POST /api/arrival/ack` consumes it the moment a page has shown it; an
  arrival nobody came for goes stale after ten minutes. 8 tests in
  `tests/test_mcp_arrival.py`.
- [ ] **Assemblies/joints in Studio** (assembly.py exists; UI is single-part).
- [x] **Units label** — DONE 6b4c494: the status bar carries a quiet unit chip
  that follows Settings ▸ Length unit, and the two dimension boxes that had no
  unit at all (Extrude's "Distance 2", the Measure edit box) say mm. Still
  open, and now visible: the tool panels are hard-wired to mm and ignore the
  display unit, so choosing inches changes the readouts but not the boxes you
  type into — see LAUNCH-PLAN §10.
- [ ] **Grid settings** — sketch grid/snap are in Settings; a model-space grid
  scale is not.
- [ ] **AI-flow polish** (chat edits during rollback etc.) — parked until manual
  design is robust.

## Done

Moved with the manual-design workstream — see the Done section of
[MANUAL-DESIGN.md](MANUAL-DESIGN.md) (P0 batch, P1 batch, settings +
click-to-place, ribbon stages, Extrude v1 + drag arrow, trim tool, caching
fix, sketch-mode overhaul S0–S6 + follow-ups, with commit hashes).
