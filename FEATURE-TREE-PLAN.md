# Feature Tree — development sheet (PAUSED 2026-08-17, resume-ready)

> **PAUSE NOTE (2026-08-17, user: "not going do anything with this text to
> cad for next four weeks... everything should be recorded properly").**
> State at pause: steps 1–3 and 5–8 SHIPPED (R1–R14 all closed, suite 241
> green at `a446ad3`); every open Studio tab snapshotted uniquely into
> designs/ (my-part, my-part-2..4, untitled, t-washer, spiderman-logo) and
> pushed to the private backup https://github.com/Vasan0021/textcad.
> **To resume:** read this file top to bottom, then MEMORY (auto-loaded);
> launch the app DETACHED via
> `Start-Process C:\Python314\python.exe -ArgumentList "-u","studio.py"
> -WorkingDirectory <repo> -WindowStyle Hidden` (debug-studio skill rule 0);
> saved designs open via File → Open. Open work, in priority order:
> step 4 (incremental tool-calling authoring — needed when AI designs must
> reference existing faces), BACKLOG cross-cutting P2s (compressor rebuild
> speed), P3s (CI running pytest, vendor three.js, LICENSE).

*(original header: ACTIVE workstream, started 2026-08-04)*

**Mandate (user, 2026-08-04):** many changes are coming to the feature tree.
The manual-design workstream is parked in
[MANUAL-DESIGN.md](MANUAL-DESIGN.md) so this file can hold the feature-tree
work exclusively. Specific requirements land in "User reports / requested
changes" below as the user states them — do not invent scope.

**How to work (non-negotiable, per project skills):**
- Load skills FIRST: `textcad-dev` + `fusion-parity` (before any code),
  `ui-verify` (before claiming any frontend step done), `debug-studio` (when
  anything misbehaves), `ship-check` (before each commit).
- Probe-first: never call a build123d/three.js API from memory — scratchpad
  probe, then real code.
- After ANY JS/CSS change: bump the cache-buster in static/index.html
  (currently `main.js?v=45`, `studio.css?v=10`) and hard-refresh. After ANY
  backend change: RESTART the test server (python never hot-reloads;
  `dev.py` is the auto-reload launcher).
- Python is `C:\Python314\python.exe`. Full suite: `python -m pytest tests -q`
  (last known-good full run at commit `4f0b92c`; e2e tests in `tests/e2e/`
  share one server + one browser via conftest).
- Commit style: capability + proof, `git commit -F <msgfile>` (heredocs break
  in PowerShell), author flags per textcad-dev.
- Browser-verify harness notes (proven on the sketch workstream): import live
  module instances in `page.evaluate` — `await import('/static/js/tree.js')`
  is the SAME instance main.js uses; `window.__vp` probes the 3D scene;
  adding a feature over the API does NOT refresh the viewport (`postJSON`
  updates `S.lastDoc`, the watcher sees no change — call `loadMesh()`
  explicitly like the real UI paths do); take screenshots and LOOK at them.

---

## Current state of the feature tree (verified 2026-08-04)

**Frontend — [static/js/tree.js](static/js/tree.js) (242 lines):**
- `renderDoc(doc)` re-renders the whole panel on bus `doc-updated` (and on
  `settings-changed` for unit conversion). Full innerHTML rebuild each time —
  no incremental updates.
- Each feature is a `.node` row: expand twisty ▶, op icon (`OP_ICONS`),
  feature id, `op ← inputs` text, per-row actions, status dot
  (`.ndot ok/fail/...`).
- Row actions (`.nacts`): ✎ edit sketch (sketch/sketch_on_face only, bus
  `edit-sketch`), ⬆ extrude sketch (`openExtrude(f.id)`), ⤒/⤓ rollback bar
  (`/api/rollback`), ⏸/▶ suppress (`/api/feature/suppress`), ✕ delete
  (`/api/feature/remove`).
- Expanded body: params with inline click-to-edit (numbers/strings), real
  checkboxes for booleans (P0-1 lesson: never text-edit a bool), an editable
  points table for profile params (list-of-pairs), read-only volume row.
- Below the nodes: warnings info box (multi-body count — neutral styling, not
  an error), spec PASS/FAIL row with chips, and the verify badge
  (`#verifyBadge`: empty / ✓ verified / ✓ verified — N bodies / ✗ check
  failed).
- Selection: click row → `S.selected` + `showFeatureOverlay(fid)` in the
  viewport; click again deselects. Rollback bar renders after its feature;
  nodes past it get `.rolledback`.
- Status bar fields it owns: `#sDoc`, `#sFeatures`, `#sVolume` (RESULT body
  only — known ambiguity, see backlog candidates), `#sRebuild`.
- NOTE: `openFeatDialog` is imported but UNUSED in tree.js — there is no
  "open the full op dialog from a tree row" action today; non-sketch feature
  editing is per-param inline only.

**Backend — [document.py](document.py) (455 lines) + [studio.py](studio.py):**
- `Document`: ordered feature list; verified rebuild (two-layer check);
  rollback bar; suppress; `leaf_solid_ids()` (unconsumed solids = bodies);
  `_check_dangling()` → `doc.warnings`.
- Endpoints the tree drives: `/api/edit` (one param), `/api/feature/params`
  (several params in ONE rebuild), `/api/feature/suppress`,
  `/api/feature/remove`, `/api/rollback`.
- Existing tests: [tests/test_tree.py](tests/test_tree.py) (16 tests) plus
  API coverage in test_api.py; e2e tests in tests/e2e/ so far target the
  viewport/sketch, not the tree panel.

**What the tree does NOT have today** (facts, not commitments — scope comes
from the user): no rename, no drag-reorder, no Fusion-style folders (Origin /
Sketches / Bodies), no right-click context menu, no body show/hide toggles,
no undo/redo, no double-click-to-edit dialog for non-sketch features, no
grouping of a sketch under the feature that consumed it.

## Backlog items this workstream should probably absorb
(moved candidates — they live in MANUAL-DESIGN.md's "feature-tree-adjacent"
section; tick them THERE too when done)

- [ ] **Feature ids must be invented by hand every time.** Auto-suggest
  disc1/hole2 style defaults, editable. Quick win.
- [ ] **Feature failures are near-silent and speak developer.** No toast/chat
  on a failed rebuild — just a small red dot; errors are raw Python reprs.
  Fix: failure toast + human message templates per error class.
- [ ] **Boolean/cut dialogs don't express operand roles.** cut = "first minus
  rest" by TREE order of checked boxes — nothing says which body is kept.
  Fix: explicit "Keep / Remove" pickers.
- [ ] **Status bar volume is the RESULT body's only** — ambiguous with
  several bodies. Label it "result volume" or show total + per-body.

---

## User reports / requested changes (fill in as the user states them)

- **R1 (2026-08-04): AI-generated designs produce a collapsed, non-robust
  tree.** User's words: "when i am telling ai to design some logo, it creates
  something, then which has some feature tree, which is very collapsed, not
  robust […] if llm creating a design using tool calling, it should start
  with begin sketch extrude right, it should be properly recorded in the
  feature tree, then i can able to edit them, when if i want to change some
  parameters". Target: an AI design must be recorded the way a Fusion user
  would have built it — sketch → extrude, feature by feature, every dimension
  editable afterwards. Work "one by one".
- **R2 (2026-08-04): ONE proper feature history tree, shared by AI and
  manual design — the foundation for all editing.** User's words: "when i
  told the llm to design the spider man logo, it creted something, then i
  can able to see some feature tree, but it was not proper, if i want edit
  that parameter something like extrude, first we need a peroper feature
  histor tree, that descripbe how a design is created and well designed, we
  need something that, once we have that, we can edit what ever we want,
  this should work as well, the feature free, when i am doing manuel
  design". Reading: the tree must be a true design HISTORY (describes how
  the part was built, step by step), it must be the SAME mechanism for AI
  and manual work, and once it is right, editing anything (e.g. an extrude's
  parameters) follows from it. (The spider-man tree itself was lost in the
  server crash — chat designs are memory-only; reproduce for the artifact
  when needed.)

- **R3 (2026-08-05): editing a sketch must ISOLATE it (Fusion rollback
  behavior).** User's words: "in fusion, everything is recoederd step by
  step right, like for examble when i click sketch, i want to see only the
  sketch, when i am pressing sketch the sketch should visible in other
  color, when i want to edit the sketch, it will go to, sketch tab right,
  where i want see only the sketch not other bode or extrude as well, only
  sketch, if i want to see extrude, i can see the extrude that belongs to
  the sketch, like that, not other sketch is not need to show when i am
  editing". Reading: (a) clicking a sketch row highlights the sketch in the
  viewport in a distinct color; (b) EDITING a sketch temporarily rolls the
  model back to that sketch's point in history — the extrude it feeds (and
  everything later) disappears while editing, earlier bodies stay; other
  sketches are hidden. This is exactly Fusion's edit-sketch timeline
  rollback.
- **R4 (2026-08-05): tree order — sketch first, its extrude after.**
  User's words: "the tree order is not proper, it should start from sketch
  below extrude and then what ever i sam doing, right now the extrude is
  in the top and sketch is below that, i dont want that". Step 2's
  grouping put the consumer ABOVE its nested sketch; creation order is
  sketch → extrude and the tree must read that way.
- **R5 (2026-08-05): remove suppress + rollback from the tree UI.**
  User's words: "in the feature tree, ehast is the surpress and rolback
  bar, other option, right now, we dont need them, just remove them".
  Remove the ⏸ suppress and ⤒ rollback row actions and the rollback bar
  from the UI (backend stays — R3's edit-isolation is BUILT on the
  rollback machinery).
- **R6 (2026-08-05): sketch entities must be drag-resizable.** User's
  words: "when i am editing the sketch, i can simpley pick anz point just
  pull it to make it bigger or push it reduse smaller, like that i need".
  Grab a point on an entity (circle rim, rectangle corner) and drag to
  resize it live.
- **R7 (2026-08-05): on-screen dimension input while drawing.** User's
  words: "when i am drawing in the sketch tab, in the number tan should in
  the, for examble, if i am drawing a ciecrl, after picked a point, when i
  am moving out, the small box should show,a dia or radis in mm, where i
  can simpley type and press ender like that i need". Fusion's dimension
  box: after the first click of a shape, a small input follows the cursor
  showing the live dimension; typing a number + Enter commits it exactly.

- **R8 (2026-08-05): the server must not open the demo flange on every
  launch.** User's words: "what is some disc with both, everytime, its
  loading, it does not have a proper fresature tree, even i can edit".
  The hardcoded `sample_flange()` boot doc (disc + bore + bolts — an
  old-style primitive tree) confused every session start. FIXED same day:
  studio.py `__main__` boots an EMPTY "untitled" document; samples remain
  under File → Examples, saved work under File → Open.

- **R9 (2026-08-05): unit label in the dimension boxes.** User's words:
  "just add mm, in the boxes, near to taht numbers, becuase sometimes it
  feels something off". Show the unit next to every dim input
  (#skDimDraw + #skDimEdit3d).
- **R10 (2026-08-05): nested shapes must make HOLES, and new sketches on
  a body must be visible.** User's words: "when i draw a new box, or some
  shapes, if i am drwaing new shapes inside that design, its not showing
  in the design tab, its one problem, and next when i am extrding that, i
  can see the small box in the ghost box, at the end i am just getting
  some big merged box... lets sat i am drawing two circile outer circle
  and inner circle, when i am extruding, i should get a washer like that,
  instead i am just getting a solid box, its not usefull". Two parts:
  (a) a finished sketch drawn ON a body's face z-fights with the face and
  is invisible; (b) every drawn shape gets mode "add", so an inner circle
  UNIONS instead of cutting — Fusion's even-odd region rule expected
  (shape inside a shape = hole).

- **R11 (2026-08-05): finished sketches must look like what was DRAWN.**
  User's words (with screenshots): "when i draw something in the sketch
  and after finishing it, it goes completely to difeerent shape, this is
  completely different behaviour, which can not be accedpted or used".
  Root cause [sketch.py](sketch.py) `_entity`: shapes were positioned
  FIRST and then `rotate(Axis.Z)` — which spins about the PLANE ORIGIN,
  not the shape's centre. Every rotated entity (slots drawn right-to-left
  carry rotation=180, vertical ±90) point-reflected/orbited on build,
  while the editor (which rotates locally) showed it where drawn. FIXED
  same day: rotate first, then translate; regression test locks rotated
  slot/rect COM to the drawn position. Untested grid cell: rotation ≠ 0 at
  off-origin positions had no coverage (gauntlet lesson, textcad-dev §4).

- **R12 (2026-08-05): taper ring must narrow "untill it become a flat
  surface" (Fusion).** User's words: "i can make it wideer or closer using
  this circle option right, in our case when we are going closer, it wont
  go after certain limit right... in fusion, it will goes untill it become
  a flat surface... we can short it untill becoming a flat plate". Fixed:
  clamp factor 0.92→0.995 for HOLE-LESS profiles (probed: exact collapse
  angle is an OCCT singularity, a hair under builds a wedge/near-apex
  fine; rects even build BEYOND it); profiles with holes keep 0.92 —
  hole-wall collision genuinely breaks the kernel.
- **R13 (2026-08-05): ONE COMMAND AT A TIME — permanent rule.** User's
  words: "when pressing the exturde button, the box is pobbing out right,
  i did not see it was not open, so i went to sketch, the box was still
  open in the sketch tab... i should not go to the sketch tab, untill i am
  pressing ok or cancel to that box... this should be apply to the
  upcoming the design tools, alwazs remember this". Encoded as
  fusion-parity golden rule 9 + `dialogs.modalGuard()` on S.modalTool:
  ribbon buttons, tree actions/dblclicks/rename/param-edits and
  sketch-on-face all refuse with a chat message while the open panel
  FLASHES (.modalflash). Extrude sets/clears it; every future tool panel
  must do the same.

- **R14 (2026-08-05): "the tapper function is not working ... throwing
  some red error text" (rectangle).** Reproduced from the user's LIVE doc
  (read-only /api/doc): narrowing taper on a face extruded from the
  TILTED wall of a tapered body failed at 10° and 31° but built at
  5/20/40° — OCCT's loft-based taper intermittently flags valid geometry
  as an invalid solid. FIXED same day: `sketch._shapefix` (ShapeFix_Shape)
  heals the result, accepted ONLY when health passes with volume unchanged
  to 0.1% (a repair must never quietly change geometry). Regression sweeps
  the user's exact tree. The honest-refusal path stays for genuinely
  broken results.

## Confirmed root causes

- **R1a — authoring treats sketch→extrude as a fallback, primitives as
  primary.** [author.py:194](author.py#L194): "SKETCH WORKFLOW (for shapes
  the primitives don't cover)". For 2D-artwork-like requests (logos) the
  model either fuses primitive plates/discs (a pile of move/fuse nodes) or
  emits ONE `sketch` feature with every entity crammed into its `entities`
  param plus one extrude — a 2-node tree with all real geometry buried in
  JSON. Both outcomes are the reported "collapsed" tree. Static analysis of
  the prompt; user's report is the live evidence — capture one real logo
  tree as the artifact before building (single authoring call).
- **R1b — the AI path is one-shot JSON, not tool calling.**
  [studio.py:800-816](studio.py#L800-L816) chat "create" →
  `author.author_design` emits the whole tree in one response (repair loop
  retries whole trees). [mcp_server.py:95](mcp_server.py#L95) `build_design`
  likewise takes a complete tree. Nothing forces (or even lets) the model
  design step-by-step — begin sketch → verify → extrude — the way the user
  describes and the way the manual UI records.
- **R1c — even a well-formed sketch→extrude tree displays collapsed.**
  [static/js/tree.js](static/js/tree.js): flat rows only — a sketch's
  entities (each circle r / rect w/h) are not editable params in the tree
  (only ✎ opens the sketch editor); no Fusion grouping of a sketch under its
  consuming feature; ids are whatever the model invented; no rename.
- **R2a — history exists but cannot be RE-ENTERED.** The data model is
  already one shared history (Document = ordered feature list; manual UI and
  AI both write it), but a tree node cannot be reopened with the tool that
  created it: `openFeatDialog` is imported and UNUSED in tree.js — editing a
  non-sketch feature (e.g. extrude) is inline text per-param only; there is
  no Fusion "Edit Feature" that reopens the Extrude dialog with its drag
  arrow on the existing feature. Sketches are the one exception (✎ →
  edit-sketch). North star for the workstream: **every feature in the tree
  must be re-openable with the same tool that created it** — that single
  rule is what makes one history serve both manual and AI design.

- **R3a — clicking a sketch row highlights NOTHING.**
  [viewport.js:1062](static/js/viewport.js#L1062) `showFeatureOverlay`
  fetches `/api/feature-mesh/{id}.stl` — STL export of a 2D Sketch fails →
  silent catch. Worse: consumed sketches aren't even in the scene
  ([studio.py:375](studio.py#L375) `_sketches_json` ships UNCONSUMED only),
  so there is nothing to color. Fix: per-sketch tessellation endpoint +
  sketch branch in the overlay.
- **R3b — edit-sketch shows everything.** [sketcher.js:213](static/js/sketcher.js#L213)
  `editSketch` never touches the model state — the consuming extrude's body
  sits exactly on top of the sketch being edited. Fusion rolls the timeline
  back to the sketch. We HAVE that machinery: `doc.rollback` + `/api/rollback`
  build-to-here — set it transiently on edit, restore on finish/cancel.
- **R4 — step 2's grouping renders consumer first, nested sketch after**
  ([tree.js](static/js/tree.js) makeNode loop). Creation order is sketch →
  extrude; swap to child-first.
- **R5 — suppress/rollback row actions + rollbar** built in tree.js
  buildRow/renderDoc; remove from UI, keep backend (R3b uses rollback).
- **R6 — no drag-resize:** sketcher select mode drags entities by CENTER
  only (drag-move); no handle/point grabbing to change r/w/h.
- **R7 — no dimension input while drawing:** sketcher shows live dims as
  SVG text (dimensionSVG) but there is no typable box; exact sizes require
  editing the entity card afterwards.

## Steps

- [x] **Step 1 — Edit Feature for extrude** (`9721185`, 2026-08-04). ✎ on an
  extrude/extrude_face row or double-click reopens the REAL Extrude dialog on
  that feature: seeded params, arrow/ghost/taper-ring gizmos, live verified
  preview, OK keeps, Cancel restores the exact original params.
  Profile/Operation rows locked in edit mode (rewiring = later step).
  Proof: tests/e2e/test_edit_extrude.py (3 tests, suite 214 green),
  ui-verified with screenshots.
- [x] **Step 2 — tree reads like a history** (`a0a1a22`, 2026-08-04).
  Double-click a feature's NAME to rename (Document.rename rewrites id in
  inputs/rollback/part-cache — never breaks the tree; /api/feature/rename,
  undoable, charset [A-Za-z0-9_-]{1,40}); Add Feature dialog auto-suggests
  op-numbered ids; consumed sketches nest as CHILD rows under their
  consumer; newly-failed features post a HUMAN chat message (reprs
  unwrapped, kernel errors translated; extrude panel's live feature
  excluded). Hard-won: selection must toggle classes IN PLACE — a full
  re-render between a double-click's two clicks makes Chromium never fire
  dblclick. Proof: 3 backend tests + 4 e2e (test_tree_history.py), suite
  221 green, screenshot-verified.
- [x] **Step 3 — AI records the same history** (`9f5559a`, 2026-08-05).
  AUTHOR_PROMPT: "RECORD A DESIGN HISTORY" — sketch→extrude primary,
  flat-artwork recipe, no transform chains, meaningful ids; `lint_tree()`
  gate in `_to_document` (>10-entity sketches, one-sketch blobs >4
  entities, generic ids → rejected pre-geometry, repair loop feeds back);
  generate.py max_tokens 2000→8000 (truncated history trees read as
  "unterminated string" JSON errors). Before/after on "the spider man
  logo": 10 features/0 sketches (ball+tubes+rotate chains) → 13 features,
  5 named sketch→extrude pairs + patterns + fuse, verified, recognizable
  emblem (designs/spiderman-logo.tcad.json). 5 new tests, suite 226.
- [ ] **Step 4 (later) — incremental tool-calling authoring**: the AI drives
  the same endpoints as the ribbon, verified per step; needed once AI
  designs reference existing faces.
- [x] **Step 5 — tree order + declutter + sketch highlight** (`d14adde`,
  2026-08-05): consumed sketch renders ABOVE its consumer (creation
  order); suppress/rollback UI removed (backend kept); clicking a sketch
  row colors it orange in the viewport — consumed sketches too, via new
  GET /api/sketch-mesh/{id}, depth-ignoring overlay glows through the body.
- [x] **Step 6 — edit-sketch isolation** (`d14adde`, 2026-08-05): editing
  a sketch transiently sets doc.rollback to it (extrude + later features
  vanish, earlier bodies stay), floating sketches hidden in sketch mode
  (viewport listens to 'sketch-mode'); released on Finish/Cancel — save
  runs under the bar, release does the one full rebuild. e2e: real ✎
  click → bodyCount 1→0, rollback=sk1 → Finish → 1, rollback=None.
- [x] **Step 7 — on-screen dimension input while drawing** (R7,
  2026-08-05): #skDimDraw follows the cursor after the first click with
  live dims (circle R, rect W/H, ellipse Rx/Ry, slot L/H, N-gon R/N, path
  segment L); first digit typed anywhere routes into the box, Tab hops
  fields, Enter commits exact (rect anchors at clicked corner toward
  cursor; slot/path direction from cursor); second click / Esc unchanged.
  3 e2e tests, suite 232. Note: live values show the SNAPPED radius (the
  value a click would land at) — typed values are exact and unsnapped.
- [x] **Step 8 — drag-resize + even-odd holes + mm labels + z-fight fix**
  (2026-08-05, R6+R9+R10): resize handles on the selected shape (circle/
  N-gon rim → radius, rect corner → resize about OPPOSITE corner, ellipse
  cardinals, slot ends re-aim, polygon/path vertices); `assignModes()`
  even-odd rule — a shape drawn inside another auto-becomes a HOLE (two
  circles = washer; containment by OUTLINE sampling, NOT centroid —
  concentric circles broke the centroid version; never recomputed on
  merely opening a sketch); unit labels in both dim boxes; finished
  sketches get polygonOffset so on-face sketches stop z-fighting.
  4 e2e tests incl. the user's exact washer flow (volume within 1% of
  π(R²−r²)h). Lesson: e2e "page" fixture boots BEFORE fresh_doc resets —
  never hardcode auto-generated ids; resolve them from /api/doc.
