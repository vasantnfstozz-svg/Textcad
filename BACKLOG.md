# TextCAD backlog — top-level index of problems & workstreams

> **PROJECT PAUSED 2026-08-17 (~4 weeks, may resume anytime).** Everything
> is committed + pushed to https://github.com/Vasan0021/textcad (private).
> All open Studio tabs were snapshotted into designs/. Resume by reading
> [FEATURE-TREE-PLAN.md](FEATURE-TREE-PLAN.md)'s pause note (top of file).
>
> **WORKSTREAM AT PAUSE: Feature tree — see
> [FEATURE-TREE-PLAN.md](FEATURE-TREE-PLAN.md)** (steps 1–3, 5–8 shipped;
> R1–R14 closed; step 4 incremental tool-calling authoring is next).
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

- [ ] **Version tree per design** (agreed with the user 2026-08-26, planned in
  [VERSION-TREE-PLAN.md](VERSION-TREE-PLAN.md), nothing built yet). Every design
  edit spawns a new tab and overwrites the previous state, so after ten
  iterations there are ten identical tabs and no way back to v3. P0 (tab reuse
  in /api/open) is a ~20-line quick win that is worth doing on its own.

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
- [ ] **P2 — /api/model has no mesh cache; complex designs blank the viewport
  ~25 s per page load.** rocky-keychain (5 letters sampled to 100-pt polygons)
  tessellates ~25 s on EVERY /api/model call; the viewport is empty with no
  progress hint meanwhile (looks exactly like "model disappeared"). Cache the
  tagged mesh keyed on rebuild stamp, and/or show a "meshing…" state.
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

- [ ] **Vendor three.js locally** (unpkg CDN today — app breaks offline).
- [ ] **No LICENSE file / third-party notices.** Decide license; NOTICE for
  build123d/OCCT/three.js.
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
- [ ] **Assemblies/joints in Studio** (assembly.py exists; UI is single-part).
- [ ] **Units/grid settings** — everything is implicitly mm; at least label it.
- [ ] **AI-flow polish** (chat edits during rollback etc.) — parked until manual
  design is robust.

## Done

Moved with the manual-design workstream — see the Done section of
[MANUAL-DESIGN.md](MANUAL-DESIGN.md) (P0 batch, P1 batch, settings +
click-to-place, ribbon stages, Extrude v1 + drag arrow, trim tool, caching
fix, sketch-mode overhaul S0–S6 + follow-ups, with commit hashes).
