# Manual Design — workstream file (PARKED 2026-08-04)

**This file is the single home for everything about the manual-design tools**
(viewport, sketch mode, extrude/modify tools, navigation, snapping): what has
been shipped, and every open problem to come back to. It was split out of
BACKLOG.md on 2026-08-04 because the **feature tree** became the active
workstream — see [FEATURE-TREE-PLAN.md](FEATURE-TREE-PLAN.md). Nothing here is
lost; work resumes top-down from the OPEN section when manual design becomes
active again.

Priorities (same scheme as BACKLOG.md): **P0** silent wrong geometry / data
loss · **P1** blocks basic manual design · **P2** hurts daily use · **P3**
polish. A fix is only "done" after ship-check (tests + live smoke test).

## Where things stand (2026-08-04)

- Geometry pipeline is solid: dogfooding round 1 (2026-07-28, 5 agents, 5
  parts through the UI only) matched hand-calculated volumes to <0.1%.
- **All P0 and P1 items are FIXED** (see Done below).
- **The Fusion-parity sketch-mode overhaul (S0–S6) is COMPLETE** — full
  development sheet with root causes, fixes, and verify-harness lessons in
  [SKETCH-MODE-PLAN.md](SKETCH-MODE-PLAN.md). Commits: S0 `e79529c`,
  S1 Z-up `89a1648`, S6 mouse mapping `9cd9c75`+`1892ecf`, S3 all-bodies-solid
  `7821e33`, S2 origin planes `38923b9`, S5 model snapping `22b901f`,
  S4 face-sketch-in-viewport (docked editor deleted) `6671d14`.
- **Post-overhaul follow-ups also shipped:** adaptive zoom-subdividing sketch
  grid `f5e0c0a`, Fusion-true grids on both tabs + finite growing ground plate
  `0b2212e`, face sketches never consume their body + Fusion pick box
  `0650250`, sketch profiles as first-class picks + Extrude op is the user's
  choice + "separate bodies" wording fixed `cbb14cb`, Cut defaults INTO the
  body (pockets) + face-sketch extrude ghost/taper ring + Intersect locked
  `4f0b92c`.
- Frontend cache-buster at `main.js?v=45`, `studio.css?v=10` (check
  static/index.html before bumping — the feature-tree work will move these).

## Resume checklist (read before touching manual design again)

1. Load skills: `textcad-dev` + `fusion-parity` first, `ui-verify` before
   claiming any frontend change works, `debug-studio` when anything
   misbehaves, `ship-check` before every commit.
2. Probe-first: never call a build123d/three.js API from memory.
3. Backend change → RESTART the server (`dev.py` auto-reloads; a manually
   launched `uvicorn` does not). JS/CSS change → bump `?v=` + hard refresh.
4. Reusable browser-verify harness + its gotchas: top of
   [SKETCH-MODE-PLAN.md](SKETCH-MODE-PLAN.md) (bus-driven sketching, `window.__vp`
   camera/scene probes, SETTLE-before-baseline, "a body drawn as a ghost
   passes every DOM check").

---

## OPEN — resume here (top-down)

### Needs diagnosis FIRST (user-reported, not root-caused)

- [ ] **Panning still does not work for the user** (reported 2026-08-03 after
  S6 + the Shift+left follow-up; user deferred it, so it is NOT diagnosed).
  Unknown which gesture failed — middle-drag, Shift+left, or both. Automated
  checks pass (e2e asserts the orbit TARGET moves for middle-drag and
  Shift+left in both tabs), so likely environmental rather than logic.
  Hypotheses in order: (1) the Shift+left code shipped after their last hard
  refresh — Ctrl+F5; (2) their mouse's wheel-press does not emit button 1 /
  is bound by the OS or mouse driver; (3) damping makes a short pan look like
  nothing moved; (4) something swallows the gesture only with a model loaded
  (the e2e runs on an empty doc). FIRST STEP when resuming: ask which gesture
  and whether they refreshed, then add a temporary on-screen readout of the
  live pointer button + resulting camera delta rather than guessing.

### P2 — hurts daily use

- [ ] **Fusion navigation preset (Shift+middle orbit) not supported.** Fusion's
  own default is LEFT=select, MIDDLE=pan, **Shift+MIDDLE=orbit**. We chose
  left-orbit-in-design + right-orbit, plus Shift+left=pan (S6); adding
  Shift+middle=orbit as an alias, and/or a Settings > Navigation dropdown,
  would let Fusion muscle memory work unchanged. Cheap now that
  `viewport.setLeftButton` centralises the mapping.
- [ ] **The design tab has no navigation legend.** Sketch mode got a readable
  chip in S6; the design tab still tells the user nothing about right-orbit /
  middle-pan / shift+left-pan. Put the same legend in the bottom status bar.
- [ ] **Snapping ignores plane∩FACE sections (S5 limit).** `sketch_snap` only
  looks at EDGES, so a sketch plane cutting through a cylinder/bore gets no
  circle to snap to — just the single arbitrary point where the cylindrical
  face's seam edge crosses. Proper fix is a section curve (plane ∩ faces),
  which is also the groundwork for a real "Project Geometry" command.
  Meanwhile a hole IS snappable when sketching on the face its circular edge
  lies in.
- [ ] **Plane-picker labels may sit off-screen.** The XY/XZ/YZ sprites are
  offset 0.72×quad-size from the quad centre; in a tight view (a small part
  filling the viewport) they were not visible in the S2 screenshot. Not
  confirmed as a bug — check whether they should be clamped into view or
  anchored to the quad corner nearest the camera.
- [ ] **Stale/blank viewport around rebuilds.** Busy overlay clears when the
  POST returns, but the old mesh (even of deleted features) keeps rendering
  for seconds while /api/model tessellates — screen contradicts tree; on
  first load it's blank WHITE with no spinner; loadMesh() swallows fetch
  errors so a failed fetch leaves stale geometry forever. Fix: "updating
  model…" indicator tied to the /api/model fetch, dark canvas from boot,
  surface fetch errors.
- [ ] **No positioned-hole feature.** "Hole" = center-only with_center_hole
  (no XY), so two bolt holes cost sketch + extrude + cut (3 features +
  throwaway body). Add hole(x, y, radius[, depth]) op; rename ribbon label to
  "Center hole" meanwhile.
- [ ] **No cylinder primitive by name; radius-only entry.** A shaft is
  Create > "Disc" with a 60mm "thickness" — first-timers scan for "Cylinder"
  and find nothing. Alias the label, and consider diameter entry.
- [ ] **Viewport camera quirks.** Fit resets to iso instead of zoom-to-fit
  preserving orientation; post-rebuild auto-fit overrides a view button
  clicked during load.
- [ ] **No orientation cues in viewport.** No axes triad — after a rotate you
  cannot tell upright from flat (S1's Z-up fixed the feel; the corner triad
  widget is still worth doing).
- [ ] **Sketcher precision gaps.** Hard 1mm snap (can't click-place r2.5), no
  typed dimension during placement (Fusion-style), and the hint says "grid
  10mm" while snap is actually 1mm. Card-editing afterwards works but is
  per-entity busywork.
- [ ] **No sketch constraints/solver** (pre-existing, long-term; explicit
  dimensions only).
- [ ] **No measure tools in viewport** (pre-existing): distance between two
  picks, whole-part bounding box readout.

### P2 — feature-tree-adjacent (check FEATURE-TREE-PLAN.md before starting —
### these are likely to be absorbed by the active feature-tree workstream)

- [ ] **Status bar volume is the RESULT body's only.** With several bodies
  visible, "volume 40000 mm³" next to two boxes is ambiguous — it silently
  ignores the other body (and the STEP export does too). Either label it
  "result volume" or show total + per-body.
- [ ] **Feature failures are near-silent and speak developer.** No toast/chat
  on a failed rebuild — just a small red dot; errors are raw Python reprs;
  one message suggests `max_fillet()`, an API a mouse user can't call. Fix:
  failure toast + human message templates per error class.
- [ ] **Boolean/cut dialogs don't express operand roles.** cut = "first minus
  rest" by TREE order of checked boxes, not click order — nothing says which
  body is kept. Fix: explicit "Keep / Remove" pickers (radio + checkboxes).
- [ ] **Feature ids must be invented by hand every time.** Auto-suggest
  disc1/hole2 style defaults, editable. Quick win.

### Deferred "later" work from shipped features

- [ ] **Extrude v2:** Start=Offset, Extent=To Object/Through All
  (`until`/`target`), Thin Extrude, Start-from-face; give Revolve the same
  drag-handle treatment as Extrude's arrow.
- [ ] **Intersect is LOCKED in the Extrude operation menu** (`4f0b92c`) —
  pending a real workflow to design/verify it against. Unlock only with a
  worked Fusion-parity example.
- [ ] **Remaining sketch polish:** type-while-drawing dimensions (type before
  the 2nd click, Tab between fields), Spline/Point/Text tools, CONSTRAINTS
  ribbon group (MODIFY exists: Trim/Mirror/Duplicate/Offset).
- [ ] **Trim honest limits** (fine to leave — Fusion behaves the same way):
  tangent-contact shapes aren't split (no crossing), trim can't REMOVE
  material (use cut entities), rebuilt clusters lose their parametric kinds.
- [ ] **Fusion-style auto-Join when a new extrude's profile touches an
  existing body** — explicitly parked nicety from S3; today the user picks
  Join in the Extrude panel.

### P3 — release prep items that live in manual design

- [ ] **Vendor three.js locally** (unpkg CDN today — app breaks offline).
- [ ] **Units/grid settings** — everything is implicitly mm; at least label
  it (Settings has display units; the working unit is silent).

---

## DONE (history — moved verbatim from BACKLOG.md 2026-08-04)

### P0 (2026-08-25): emptying a sketch was a DEAD END — the delete could never be saved
User's words: "in my design i just want to delete a name, i clicked delete in
the sketch mode, but i cant save the sketch, and go to the normal tab, because
it says something."

Root cause: `sketcher.create()` (Finish Sketch) bailed with "⚠ The sketch is
empty — pick a shape and click on the canvas to draw first" and RETURNED without
leaving sketch mode. Sketch mode owns the tab strip (only the green contextual
tab renders, `ribbon.renderTabs`), so with the last shape deleted there was no
way forward: Finish refused forever and Cancel discards the edit. Deleting the
only content of a sketch was therefore unsaveable.

Fix: `sketcher.finishEmpty()` — an empty sketch is a real intent.
- A COMMITTED sketch (edit-sketch) means "this sketch should go": dry-run
  `/api/feature/remove`, confirm with the plan's summary (it NAMES the extrude
  and cut that go with it), release the edit-isolation rollback, leave sketch
  mode, delete. One Ctrl+Z restores the whole group.
- Declining the confirm keeps the sketch open to redraw (and says so) — never a
  dead end in either direction.
- A brand-new sketch with nothing drawn just leaves the mode.
Built on the R15 delete-repair work (see FEATURE-TREE-PLAN.md).

Verified: tests/e2e/test_sketch_empty_exit.py (3 — written RED first: the old
code timed out waiting to leave sketch mode) + a live browser probe (delete the
art, Finish, normal tabs back, plate intact at 40000 mm³, no console errors).
Full e2e + sketch suites green (82).

### Fusion-parity sketch mode overhaul S0–S6 (2026-08-03) + follow-ups (2026-08-04)
The whole workstream lives in [SKETCH-MODE-PLAN.md](SKETCH-MODE-PLAN.md) with
per-step root causes, fixes, verification, and harness lessons. Headlines:
Z-up orbit everywhere (`89a1648`); one mouse mapping for both tabs + Shift+left
pan (`9cd9c75`, `1892ecf`); every leaf body renders as a real pickable solid —
no more "first box goes blank" (`7821e33`); origin-plane quads sit exactly on
their true planes (`38923b9`); model corners/hole-centres/edge-crossings snap
while sketching (`22b901f`); face sketches happen IN the viewport and the
docked 2D editor is deleted (`6671d14`); adaptive snap-everywhere grids on
both tabs over a finite growing ground plate (`f5e0c0a`, `0b2212e`); face
sketches never consume their body + Fusion's pick-priority box (`0650250`);
sketch profiles are first-class picks for Extrude (`cbb14cb`); Cut makes
pockets INTO the body by default + face-sketch extrude ghost/taper ring
(`4f0b92c`).

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
- Taper hardening (2026-08-03): flat-BSPLINE seam failure fixed + operation
  gauntlet corpus (`8e9f519`); collapse-on-narrowing fixed (`d931d4b`); taper
  barrier + ghost visible inside the body (`5905d1d`).

### Fusion sketch tab rebuild (user-driven, one-by-one) — 2026-07-29
Target from Fusion screenshots: pick a plane full-size in the viewport → canvas
fills the plane (no box) → draw tools in the TOP ribbon CREATE group → Finish
Sketch. (The docked-editor parts of this were superseded by S4, which moved ALL
sketching into the 3D viewport.)
- [x] **Step 1: tools on top + full-plane canvas.** Contextual SKETCH tab CREATE
  group (Line/Arc, Rectangle, Circle, Polygon, Slot, Ellipse) in the ribbon with
  active-tool highlight (setTool → bus 'sketch-tool'). Verified 14/14.
- [x] **Step 2: viewport plane picker.** Create Sketch shows the 3 origin planes
  (XY blue / XZ green / YZ red, translucent, hover-highlight) full-size in the
  viewport with a banner; clicking a plane enters sketch mode on it, clicking a
  planar face routes to sketch-on-face. viewport.js `beginPlanePick()`.
- [x] **Step 3: inline on-canvas dimensions.** Draw a shape → a floating editor
  appears next to it with its size fields (circle R; rect W/H; ellipse Rx/Ry;
  slot L/H; n-gon R/N) — type exact sizes on the canvas. Values in the display
  unit, converted to mm. Also REMOVED the Extrude dialog that auto-popped after
  Finish Sketch (Fusion doesn't).
- [x] **Sketch polish:** XY/XZ/YZ text-sprite labels on the origin planes;
  sketch-on-face unified with the plane layout.
- [x] **Sketch grid fills the canvas.** viewBox now matches the canvas's real
  aspect ratio — grid spans edge-to-edge like Fusion.

### Fix: stale-asset caching booted the app half-dead (2026-07-29)
User reloaded after the ribbon changes and got a blank app (no tabs/ribbon/doc).
Root cause: `main.js?v=N` was cache-busted but the ES modules it imports
(settings.js, ribbon.js, …) had NO version query, so the browser served fresh
main.js + STALE cached modules → boot crash.
- [x] `studio.py` HTTP middleware sends `Cache-Control: no-cache, no-store,
  must-revalidate` (+ Pragma/Expires) for `/` and `/static/*`, so the browser
  never runs a stale mix again. One Ctrl+F5 clears the already-cached copies;
  after that normal reloads stay fresh. 121 tests green.

### Fusion-style ribbon — Stage A: reorganization (2026-07-29)
- [x] Sketch is no longer a permanent tab. "Create Sketch" moved into the Create
  tab beside the sketch-consumers. Tabs now File · Create · Modify · Inspect.
- [x] Create tab → Create (Create Sketch · Extrude · Revolve · Loft · Sweep) /
  Primitives (Box · Cylinder · Sphere · Cone · Pipe · Polygon · Hex — Fusion
  names via TOOL_NAMES) / Advanced (Turn profile · Blade).
### Fusion-style ribbon — Stage B: contextual sketch mode (2026-07-29)
- [x] Sketching is a MODE: a green **"✎ Sketch" contextual tab** replaces the
  normal tabs (bus `sketch-mode`), ribbon shows FINISH group (✓ Finish / ✕
  Cancel). Esc/Delete handled via window keydown guarded by sketchActive.
  (The docked-dialog half of Stage B died in S4 — sketching is in-viewport.)

### Feature: Settings panel + click-to-place primitives (2026-07-28)
- [x] **Settings** (`settings.js`, localStorage): length unit (mm/cm/inch,
  DISPLAY only — mm stays the working unit), sketch grid size, snap increment.
  File tab → Settings. Unit converts the status-bar volume, tree volume rows,
  and the sketcher's readouts (`fmtLen`/`fmtVol`, bus 'settings-changed').
- [x] **Click-to-place** (`placement.js` + viewport `beginPlacement`): the 7
  Create primitives no longer open a modal — click a point on the Z=0 ground
  and the shape is created there (CENTER at the click), via creator + a `move`
  when off-origin. A modeless popup (`#placePopup`) live-edits dims + x/y/z.
  Esc cancels. 9 new tests (121 total; caught a bad cone default).

### Feature: selected surface shown in the sketch editor (2026-07-28)
- [x] `sketch.resolve_face()` extracted (shared) + `sketch.face_outline_2d()`
  projects the picked planar face's wires into plane-local 2D.
- [x] `POST /api/face-outline` resolves the face on the result solid, returns
  the outline; degrades cleanly with no solid / curved face.
- [x] Viewport stores the last-picked planar face (`S.pickedFace`); sketch-on-
  face renders the outline as reference geometry + snap points. 5 new tests.

### P1 batch — dogfooding round 1 manual-design fixes (2026-07-28)
6 of 7 P1 items, probe-first, 12 new regression tests (108 total green),
verified through the real browser (12/12 Playwright checks; visual pass caught
a CSS regression the DOM checks missed).
- [x] **P1-a viewport showed only the last body** — `Document.leaf_solid_ids()`
  + `/api/model` `bodies`; viewport renders non-result bodies (upgraded to full
  solids later in S3).
- [x] **P1-b committed sketches uneditable** — ✎ edit action on sketch rows →
  `editSketch()` reopens the editor loaded with the entities → Save posts
  `/api/feature/params` (new endpoint: several params in ONE rebuild).
- [x] **P1-c fillet/chamfer can't hit vertical edges** — added "vertical" and
  "horizontal" rules to `_pick_edges`.
- [x] **P1-d bare dialogs** — `author.op_catalog()` annotates params with
  `enum` (→ dropdowns), `unit` (mm/deg/count/×), and a per-op `note`.
- [x] **P1-e empty-server 500** — `_entry()` auto-creates an "untitled" doc.
- [x] **P1-f sketch dialog footer off-screen** — flex column + sticky footer.
  **Regression caught in visual verify:** `display:flex` UNSCOPED overrode the
  UA `display:none` for a CLOSED dialog → editor showed permanently. Gated on
  `[open]`.

### P0 batch — dogfooding round 1 fixes (2026-07-28)
All found by the 5-agent dogfooding session; 13 new regression tests (96 total
green) + a 12-check Playwright UI verification pass.
- [x] **P0-1 extrude `both` string-truthy** — `sketch._to_bool()` strict
  coercion; booleans render as real checkboxes in dialogs AND the tree.
- [x] **P0-2 slot overall vs center-to-center** — switched to `SlotOverall`;
  length is end-to-end exactly as the canvas draws it.
- [x] **P0-3 dangling wrong-input branch** — `Document._check_dangling()` emits
  `doc.warnings`; API exposes them; badge + info box name the exact body.
- [x] **P0-4 false sketch verification failure** — DISJOINT entities compose to
  a `Compound`; `sketch._as_sketch()` rewraps; rebuild classifies 2D by OP.
- [x] **P0-5 sketch-on-face on curved faces** — clear error on non-PLANE faces;
  step-checked creation (rolls back partial features).
- [x] **P0-6 Esc destroys the sketch** — intercept the dialog `cancel` event →
  cancel the TOOL, never close; Cancel button confirms before discarding.

### Closed triage items
- [x] ~~Unconsumed sketch profiles may render as filled areas when viewed
  edge-on~~ **CLOSED in S3, mostly as a misread screenshot.** One real
  client-side duplication path DID exist and is fixed: `loadMesh` was async
  with no re-entrancy guard, so overlapping calls each added scene objects
  while only one disposed. Now generation-guarded (`loadSeq`). Re-open if
  stray profiles are ever seen again.
