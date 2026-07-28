# TextCAD backlog — the single source of truth for problems & missing tools

How this file works:
- **One entry per problem.** Every bug, friction point, or missing tool gets a line
  here the moment it is noticed — especially during dogfooding sessions.
- Each entry: what's wrong → how to reproduce/see it → why it matters.
- Priorities: **P0** = silent wrong geometry or data loss (trust killers — fix first),
  **P1** = blocks basic manual design, **P2** = hurts daily use, **P3** = release/polish.
- We work top-down. A fix is only "done" after ship-check (tests + live smoke test),
  and the entry moves to the Done section with the commit hash.

Dogfooding round 1 (2026-07-28): 5 agents built flange / L-bracket / enclosure /
stepped shaft with keyway / gasket through the UI only. All 5 parts completed with
volumes matching hand calculations to <0.1% — the geometry pipeline is solid. The
UI around it produced 36 friction items, merged below. Screenshots in scratchpad
`dogfood/<part>/`.

## To triage (dump new problems here, sort later)

- (empty — add anything that annoys you, even small things)

## P0 — silent wrong geometry / false verification / data loss

**All 6 P0 items FIXED 2026-07-28 (commit pending) — 13 regression tests in
tests/test_p0_fixes.py, verified through the real UI (12/12 Playwright checks).**
See the Done section.

## P1 — blocks basic manual design

**6 of 7 P1 items FIXED 2026-07-28 — see Done. Remaining: sketch trim tool.**

- [ ] **Sketch trim tool missing** (pre-existing). Needs curve-curve intersection;
  add/cut composition covers some cases but real 2D drafting needs trim.

## P2 — hurts daily use

- [ ] **Stale/blank viewport around rebuilds.** Busy overlay clears when the POST
  returns, but the old mesh (even of deleted features) keeps rendering for seconds
  while /api/model tessellates — screen contradicts tree; on first load it's blank
  WHITE with no spinner; loadMesh() swallows fetch errors so a failed fetch leaves
  stale geometry forever. Fix: "updating model…" indicator tied to the /api/model
  fetch, dark canvas from boot, surface fetch errors.
- [ ] **Feature failures are near-silent and speak developer.** No toast/chat on a
  failed rebuild — just a small red dot; errors are raw Python reprs; one message
  suggests `max_fillet()`, an API a mouse user can't call. Fix: failure toast +
  human message templates per error class.
- [ ] **Boolean/cut dialogs don't express operand roles.** cut = "first minus rest"
  by TREE order of checked boxes, not click order — nothing says which body is kept.
  Fix: explicit "Keep / Remove" pickers (radio + checkboxes).
- [ ] **No positioned-hole feature.** "Hole" = center-only with_center_hole (no XY),
  so two bolt holes cost sketch + extrude + cut (3 features + throwaway body).
  Add hole(x, y, radius[, depth]) op; rename ribbon label to "Center hole" meanwhile.
- [ ] **No cylinder primitive by name; radius-only entry.** A shaft is Create > "Disc"
  with a 60mm "thickness" — first-timers scan for "Cylinder" and find nothing. Alias
  the label, and consider diameter entry (ties into dialog-metadata item above).
- [ ] **Feature ids must be invented by hand every time.** Auto-suggest disc1/hole2
  style defaults, editable. Quick win.
- [ ] **Viewport camera quirks.** Fit resets to iso instead of zoom-to-fit preserving
  orientation; post-rebuild auto-fit overrides a view button clicked during load.
- [ ] **No orientation cues in viewport.** No axes triad or labeled grid — after a
  rotate you cannot tell upright from flat. Add a corner triad.
- [ ] **Sketcher precision gaps.** Hard 1mm snap (can't click-place r2.5), no typed
  dimension during placement (Fusion-style), and the hint says "grid 10mm" while
  snap is actually 1mm. Card-editing afterwards works but is per-entity busywork.
- [ ] **No sketch constraints/solver** (pre-existing, long-term; explicit dimensions
  only — revisit after the P0/P1 list is burned down).
- [ ] **Compressor sample rebuild is slow (~1–2 min)** (pre-existing). Profile;
  cache unchanged sub-parts or parallelize blade builds.
- [ ] **Frontend automated test coverage is minimal.** E2E suite exists as a skill
  plan (tests/e2e/) — every P0/P1 fix above must land with an E2E regression test.
- [ ] **No measure tools in viewport** (pre-existing): distance between two picks,
  whole-part bounding box readout.

## P3 — release preparation / later

- [ ] **Vendor three.js locally** (unpkg CDN today — app breaks offline).
- [ ] **No LICENSE file / third-party notices.** Decide license; NOTICE for
  build123d/OCCT/three.js.
- [ ] **No git remote (backup!).** `winget install GitHub.cli` + `gh auth login`
  (user), then private repo + push + CI running pytest.
- [ ] **Assemblies/joints in Studio** (assembly.py exists; UI is single-part).
- [ ] **Units/grid settings** — everything is implicitly mm; at least label it.
- [ ] **AI-flow polish** (chat edits during rollback etc.) — parked until manual
  design is robust.

## Done

### Feature: selected surface shown in the sketch editor (2026-07-28)
User ask: "if I select a surface on a body from the Create section, I want to see
the selected surface in the sketch tab." Now sketching on a picked face shows the
face's real boundary (outer + holes) as grey reference geometry in the 2D canvas.
- [x] `sketch.resolve_face()` extracted (shared) + `sketch.face_outline_2d()`
  projects the picked planar face's wires into its plane's local 2D (aligned with
  where drawn entities land). Non-planar → planar:false.
- [x] `POST /api/face-outline` resolves the face on the result solid, returns the
  outline; degrades cleanly with no solid / curved face.
- [x] Viewport stores the last-picked planar face (`S.pickedFace`); the Sketch
  ribbon tool sketches ON it when one is picked (else blank plane). Cleared on
  edge-pick / clear-pick.
- [x] Sketcher renders the outline as a grey evenodd-filled surface with holes,
  fits the view to it, and adds its corners + hole centers to the snap points.
  5 new tests (113 total); verified in the browser (grey plate outline + bore
  circle shown). main.js?v=10.

### P1 batch — dogfooding round 1 manual-design fixes (2026-07-28)
6 of 7 P1 items, probe-first, 12 new regression tests (108 total green), verified
through the real browser (12/12 Playwright checks; visual pass caught a CSS
regression the DOM checks missed).
- [x] **P1-a viewport showed only the last body** — `Document.leaf_solid_ids()`
  lists every unconsumed solid; `/api/model` returns the non-result ones as
  `bodies`; viewport renders them translucent grey (ghosts) so positioning a
  second body before a fuse is no longer blind. Fit includes ghosts.
- [x] **P1-b committed sketches uneditable** — ✎ edit action on sketch rows →
  `editSketch()` reopens the 2D editor loaded with the entities → Save posts
  `/api/feature/params` (new endpoint: set several params in ONE rebuild).
- [x] **P1-c fillet/chamfer can't hit vertical edges** — added "vertical" (the 4
  upright corner edges, via `edges().filter_by(Axis.Z)`) and "horizontal" rules
  to `_pick_edges`. Canonical "round the box corners" now works.
- [x] **P1-d bare dialogs** — `author.op_catalog()` now annotates params with
  `enum` (→ dropdowns for axis/plane/edges/open_face), `unit` (mm/deg/count/×),
  and a per-op `note` (origin-centered, relative move, etc.); dialog renders all
  three. No more guessing valid enum words or radius-vs-diameter.
- [x] **P1-e empty-server 500** — `_entry()` auto-creates an "untitled" doc when
  no tab is open instead of KeyError:None. UI boots clean from empty state.
- [x] **P1-f sketch dialog footer off-screen** — `#sketchDialog[open]` flex column,
  max-height 92vh, scrolling side panel, sticky footer. **Regression caught in
  visual verify:** first fix set `display:flex` UNSCOPED, overriding the UA
  `display:none` for a CLOSED dialog → the editor showed permanently. Fixed by
  gating on `[open]`; locked in by test_sketch_dialog_display_is_gated_by_open.

### P0 batch — dogfooding round 1 fixes (2026-07-28)
All found by the 5-agent dogfooding session; fixed top-down with probe-first
discipline, 13 new regression tests (96 total green), and a 12-check Playwright
UI verification pass.
- [x] **P0-1 extrude `both` string-truthy** — `sketch._to_bool()` strict coercion
  (rejects "maybe"/2); booleans now render as real checkboxes in the Add-Feature
  dialog (dialogs.js) AND the feature tree (tree.js). `both="false"` → single-sided.
- [x] **P0-2 slot overall vs center-to-center** — switched to `SlotOverall`; length
  is now end-to-end exactly as the canvas draws it; validates length > height. Slot
  hit-test in sketcher.js corrected to match. AI author prompt updated.
- [x] **P0-3 dangling wrong-input branch** — `Document._check_dangling()` emits
  `doc.warnings`; API exposes them; badge shows "✓ verified — ⚠ N stray bodies",
  amber box names the exact body. Dialog now default-checks the current tip so the
  common case chains correctly.
- [x] **P0-4 false sketch verification failure** — root cause: DISJOINT entities
  compose to a `Compound`, not a `Sketch`, so `is_sketch()` was false and the solid
  verifier ran on a 2D profile. `sketch._as_sketch()` rewraps to a real Sketch;
  rebuild classifies 2D by OP (`SKETCH_PRODUCERS`) not just type.
- [x] **P0-5 sketch-on-face on curved faces** — `sketch_on_face` raises a clear
  error on non-PLANE faces; viewport hides the "✎ Sketch on this face" button on
  non-flat faces and shows guidance; on-face create is now step-checked (rolls back
  partial features, no false "pocket cut" success message).
- [x] **P0-6 Esc destroys the sketch** — intercept the dialog's `cancel` event
  (Esc) → cancel the TOOL, never close; Cancel button confirms before discarding
  a non-empty sketch.
