# TextCAD backlog — the single source of truth for problems & missing tools

> **ACTIVE WORKSTREAM (2026-08-03): Fusion-parity sketch mode overhaul — see
> [SKETCH-MODE-PLAN.md](SKETCH-MODE-PLAN.md)** (root-caused: face sketches
> stuck in the flat docked editor, non-result bodies ghosted "blank", origin
> planes drawn at the model center instead of the origin, Y-up orbit in a
> Z-up world, no snapping to model edges). P2 items below resume after it.

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

- [ ] **OPEN: panning still does not work for the user** (reported 2026-08-03
  after S6 + the Shift+left follow-up; user deferred it to work on S3, so it is
  NOT diagnosed). Unknown which gesture failed — middle-drag, Shift+left, or
  both. Automated checks pass (e2e asserts the orbit TARGET moves for
  middle-drag and Shift+left in both tabs), so this is likely environmental
  rather than logic. Hypotheses in order: (1) the Shift+left code shipped after
  their last hard refresh — Ctrl+F5; (2) their mouse's wheel-press does not
  emit button 1 / is bound by the OS or mouse driver; (3) damping makes a short
  pan look like nothing moved; (4) something swallows the gesture only with a
  model loaded (the e2e runs on an empty doc). FIRST STEP when resuming: ask
  which gesture and whether they refreshed, then add a temporary on-screen
  readout of the live pointer button + resulting camera delta rather than
  guessing.

- [x] ~~Unconsumed sketch profiles may render as filled areas when viewed
  edge-on~~ **CLOSED in S3, mostly as a misread screenshot.** Checked the data:
  `/api/model` for my-part returns exactly ONE unconsumed sketch (sketch2, 4
  outline loops, correctly edge-on at x=0) and one body — no duplicate or
  misplaced profile at the source. One real client-side duplication path DID
  exist and is now fixed: `loadMesh` was async with no re-entrancy guard, so
  overlapping calls (dialogs + tabs + the 3s watcher) each added scene objects
  while only one disposed. Verified 5 parallel loads now leave exactly 1 body /
  12 edges / 5 sketch objects. Re-open if stray profiles are ever seen again.
- [ ] **Fusion navigation preset (Shift+middle orbit) not supported.** Fusion's
  own default is LEFT=select, MIDDLE=pan, **Shift+MIDDLE=orbit**, and it ships
  a preference to switch styles. We chose left-orbit-in-design + right-orbit,
  plus Shift+left=pan (S6); adding Shift+**middle**=orbit as an alias, and/or a
  Settings > Navigation dropdown, would let Fusion muscle memory work
  unchanged. Cheap now that `viewport.setLeftButton` centralises the mapping.
- [ ] **The design tab has no navigation legend.** Sketch mode got a readable
  chip in S6; the design tab still tells the user nothing about right-orbit /
  middle-pan / shift+left-pan. Put the same legend in the bottom status bar.

## P0 — silent wrong geometry / false verification / data loss

**All 6 P0 items FIXED 2026-07-28 (commit pending) — 13 regression tests in
tests/test_p0_fixes.py, verified through the real UI (12/12 Playwright checks).**
See the Done section.

## P1 — blocks basic manual design

**ALL P1 items FIXED — trim tool landed 2026-08-03, see Done.**

## P2 — hurts daily use

- [ ] **Status bar volume is the RESULT body's only.** With several bodies now
  visible (S3), "volume 40000 mm³" next to two boxes is ambiguous — it silently
  ignores the other body (and the STEP export does too). Either label it
  "result volume" or show total + per-body.
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
- [ ] **Frontend automated test coverage is minimal.** `tests/e2e/` now exists
  (first tests landed with S1 camera work, 5 tests / ~55s, one shared browser
  per module) — keep adding one per UI fix.
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

### Sketch TRIM tool — the last P1 (2026-08-03)
Fusion's Trim adapted to the closed-entity sketch model: entity outlines are
split at their crossings into pieces; hover highlights one red, click removes
it. Material always wins (trim never removes material):
- [x] Backend `sketch_trim.py` (pure functions, stateless): `trim_pieces`
  samples outlines + vectorized crossing detection; `trim_apply` classifies
  the clicked piece by probing material on both flanks — internal seam →
  dissolved (shapes union-rebuilt), enclosed gap boundary → gap filled (the
  exact arrangement CELL, clipped per entity — a U−M component can span the
  profile edge), outer boundary → refused with a clear message, crossing-free
  entity → deleted whole (Fusion parity). The overlapping CLUSTER is rebuilt
  from the exact OCCT wires as path entities (lines + true 3-point arcs;
  untouched full circles survive as parametric circles); entities outside the
  cluster stay untouched. Areas verified exact (2-circle union to 0.2mm²).
- [x] Endpoints `POST /api/sketch/trim/pieces` + `/apply` — stateless, work on
  the entity list the open editor sends, errors as {"error"} for the chat.
- [x] Frontend: ✂ Trim in the contextual sketch ribbon (own MODIFY group) +
  the face-mode palette; hover→red piece (3D scene + SVG), click→apply with
  chat narration; stale-piece guard (entities re-serialized and compared
  before any apply). main.js?v=33.
- [x] 12 new pytest tests (tests/test_sketch_trim.py, 148 total green) +
  8/8 Playwright checks on a live server, screenshots visually confirmed.
- Honest limits (later if needed): tangent-contact shapes aren't split (no
  crossing), trim can't REMOVE material (use cut entities for that), and
  rebuilt clusters lose their original parametric kinds (like Fusion, where
  trim also breaks curves).

### Fusion-style Extrude — v1 (2026-07-29)
Built from the user's Fusion Extrude help text. v1 = profile + direction
(one/symmetric/two-sides) + flip + taper + operation (new/join/cut/intersect) +
live preview.
- [x] Backend: `sketch.extrude_sketch(amount, both, amount2, taper, flip)` —
  one-side / symmetric (both) / two-sided (amount2, opposite dir) / taper° / flip.
  8 tests (test_extrude_v1.py); op_catalog auto-exposes the new params.
- [x] Frontend: dedicated non-modal **Extrude panel** (extrude.js + #extrudeDialog)
  with Profile / Direction / Distance(+Distance2) / Taper / Flip / Operation +
  Combine-with target. LIVE PREVIEW: creates the extrude (+fuse/cut/intersect)
  feature immediately and edits it in place via /api/feature/params through the
  verified rebuild; Cancel removes the preview, OK keeps it. Create→Extrude and
  the tree sketch ⬆ action open it. main.js?v=19, css?v=8. 129 tests green.
  Verified 12/12 in the browser (panel, live volume update, symmetric/taper,
  Join adds a fuse, OK keeps, Cancel removes).
- [x] **Extrude drag-arrow (2026-07-29):** Fusion direct-manipulation — clicking
  Extrude puts a draggable orange **arrow** on the profile perpendicular to its
  plane/face (renders on top of the solid); dragging it pulls the extrusion up/
  down LIVE (throttled, one verified rebuild in flight), signed distance = drag
  direction; the small panel is the value box for exact distance + options. Built
  in viewport.js (beginExtrudeArrow/arrowGrab/arrowDrag, capture-phase grab +
  controls.enabled=false to beat OrbitControls) + extrude.js (placeArrow/onDrag).
  Verified 8/8 (arrow appears, drag 10→19.15 & solid 16000→30640, value box,
  OK/Cancel clear the arrow). main.js?v=20.
- [ ] **Extrude v2 (later):** Start=Offset, Extent=To Object/Through/All
  (`until`/`target`), Thin Extrude, Start-from-face; also give Revolve the same
  drag-handle treatment.

### Fusion sketch tab rebuild (user-driven, one-by-one) — 2026-07-29
Target from Fusion screenshots: pick a plane full-size in the viewport → canvas
fills the plane (no box) → draw tools in the TOP ribbon CREATE group → Finish
Sketch. Doing CREATE only for now; MODIFY/CONSTRAINTS later.
- [x] **Step 1: tools on top + full-plane canvas.** Contextual SKETCH tab CREATE
  group (Line/Arc, Rectangle, Circle, Polygon, Slot, Ellipse) in the ribbon with
  active-tool highlight (setTool → bus 'sketch-tool'); plane sketches
  (.docked.planemode) hide the side palette/footer/title so the canvas fills the
  work area. Verified 14/14. main.js?v=14, css?v=5.
- [x] **Step 2: viewport plane picker.** Create Sketch now shows the 3 origin
  planes (XY blue / XZ green / YZ red, translucent, hover-highlight) full-size in
  the viewport with a "Select a plane or planar face · Esc to cancel" banner;
  clicking a plane enters sketch mode on it, clicking a planar face routes to
  sketch-on-face. viewport.js `beginPlanePick()`; ribbon Create Sketch calls it;
  openSketchEditor(plane) opens on the chosen plane. Verified 5/5. main.js?v=15.
  (Polish later: XY/XZ/YZ labels on the planes.)
- [x] **Step 3: inline on-canvas dimensions.** Draw a shape → a small floating
  editor appears next to it with its size fields (circle R; rect W/H; ellipse
  Rx/Ry; slot L/H; n-gon R/N) — type exact sizes on the canvas, no side box.
  Values shown/typed in the display unit, converted to mm (settings.toMm).
  `#skDimEdit` + updateDimEditor/buildDimEditor in sketcher.js; shows in plane
  mode when an entity is selected. Also REMOVED the Extrude dialog that
  auto-popped after Finish Sketch (Fusion doesn't; use Create→Extrude when
  ready). setTool deselects. Verified 6/6. main.js?v=16, css?v=6.
- [x] **Sketch polish (2026-07-29):** XY/XZ/YZ text-sprite labels on the origin
  planes in the picker; sketch-on-face unified with the plane layout (green tab,
  CREATE tools on top, inline dims, face reference outline, slim side strip with
  only Depth + Join/Cut). Verified 7/7. main.js?v=17, css?v=7.
- [x] **Sketch grid fills the canvas (2026-07-29).** The sketch SVG used a SQUARE
  viewBox → on a wide canvas it letterboxed, so the grid sat in a small central
  square with dark empty sides. draw() now sets the viewBox to the canvas's real
  aspect ratio (ex = ext*aspect, ey = ext) and draws grid/axes/guides across the
  full extent → grid fills edge-to-edge like Fusion. Default zoom ext 60→90.
  Verified 3/3 (viewBox aspect == canvas 2.32, grid spans 1521/1556px).
  main.js?v=18.
- [ ] **Remaining sketch polish (later):** type-while-drawing dimensions (type
  before the 2nd click, Tab between fields), Spline/Point/Text tools, MODIFY +
  CONSTRAINTS ribbon groups, and edit-committed-sketch reopening the new UI.

### Fix: stale-asset caching booted the app half-dead (2026-07-29)
User reloaded after the ribbon changes and got a blank app (no tabs/ribbon/doc).
Root cause: `main.js?v=N` was cache-busted but the ES modules it imports
(settings.js, ribbon.js, …) had NO version query, so the browser served fresh
main.js + STALE cached modules → boot crash. Proven: a fresh browser loaded
8124 perfectly (4 tabs, 14 buttons, flange verified, 0 errors); only the user's
cached browser broke.
- [x] `studio.py` HTTP middleware sends `Cache-Control: no-cache, no-store,
  must-revalidate` (+ Pragma/Expires) for `/` and `/static/*`, so the browser
  never runs a stale mix again. Removes the ?v= cache-buster fragility for good.
  One Ctrl+F5 clears the already-cached copies; after that normal reloads stay
  fresh. 121 tests green.

### Fusion-style ribbon — Stage A: reorganization (2026-07-29)
User goal: make the toolbar make sense / work like Fusion 360 (they sent Fusion
SOLID + SKETCH screenshots). Stage A = regroup only (op ids unchanged, verified
pipeline untouched):
- [x] Sketch is no longer a permanent tab. "Create Sketch" moved into the Create
  tab beside the sketch-consumers. Tabs now File · Create · Modify · Inspect.
- [x] Create tab → Create (Create Sketch · Extrude · Revolve · Loft · Sweep) /
  Primitives (Box · Cylinder · Sphere · Cone · Pipe · Polygon · Hex — Fusion
  names via TOOL_NAMES) / Advanced (Turn profile · Blade).
- [x] Modify / Inspect unchanged. Welcome text updated. main.js?v=12. Verified
  in browser (5/5 checks; Create Sketch opens the editor).
### Fusion-style ribbon — Stage B: contextual sketch mode (2026-07-29)
- [x] Sketching is now a MODE. Create Sketch → the editor shows **non-modal,
  docked over the main area** (`#sketchDialog.docked`, `.show()` not
  `showModal()`; top set to the doctabs bottom). A green **"✎ Sketch"
  contextual tab** replaces the normal tabs (ribbon listens to bus
  `sketch-mode`), and the ribbon shows a FINISH group: ✓ Finish Sketch (green)
  + ✕ Cancel Sketch. Finish commits the feature and restores the normal tabs;
  Cancel discards (confirm if non-empty). sketcher exports setSketchTool/
  finishSketch/cancelSketch; Esc/Delete handled via a window keydown guarded by
  sketchActive. main.js?v=13, css?v=4. Verified in browser (8/8, 0 console
  errors; green tab, docked canvas, draw circle, Finish → feature + tabs back).
- [ ] **Stage C (later): true draw-in-3D** — draw directly on the tilted plane
  inside the 3D viewport (2D↔3D projection, camera plane-lock). Also possible
  refinement: move the draw tools into the contextual ribbon tab (Fusion has
  them there); they currently live in the docked side palette.

### Feature: Settings panel + click-to-place primitives (2026-07-28)
User ask: a settings section for units/drawing prefs, and replace the irritating
Create-dialog with click-a-point-in-the-viewport placement + a small inline popup.
- [x] **Settings** (`settings.js`, localStorage): length unit (mm/cm/inch, DISPLAY
  only — mm stays the working unit), sketch grid size, snap increment. File tab →
  Settings. Unit converts the status-bar volume, tree volume rows, and the
  sketcher's grid/snap/coords/dimension readouts (`fmtLen`/`fmtVol`, bus
  'settings-changed' re-renders). Buttons are explicit onclick (NOT native form
  submit — number-input validation silently blocks a dialog-form submit).
- [x] **Click-to-place** (`placement.js` + viewport `beginPlacement`): the 7 Create
  primitives no longer open a modal — you click a point on the Z=0 ground
  (raycast) and the shape is created there (its CENTER at the click), via creator
  + a `move` when off-origin. A modeless popup (`#placePopup`) then live-edits
  dims + x/y/z (debounced /api/feature/params); everything stays editable in the
  tree. Esc cancels; hint overlay guides. revolve_profile/curved_blade keep the
  dialog. 9 new tests (121 total; caught a bad cone default). main.js?v=11,
  studio.css?v=3. Verified in browser: unit→cm converts volume readout, Disc
  click places disc+move with the inline popup, live radius edit rebuilds.

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
