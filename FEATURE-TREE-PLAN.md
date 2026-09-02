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

- **R15 (2026-08-25): an AI-authored tree cannot be edited by DELETING.**
  User's words: "once design was desiened bz ai, it comes with perfectly
  fraature tree right, lets say if i want to modify that, or if i want delete
  the some sketch or extrude its not working, i cant delete the sketch".
  Reproduced on designs/esp32-remote.tcad.json (73 features): `remove()`
  refused any feature with a dependent — "cannot remove 'outline_sketch':
  used by ['body']" — and since every AI design is one chain
  (sketch -> extrude tool -> cut -> ...), **72 of the 73 features were
  undeletable**; only the last node could go. FIXED same day, Fusion-style:
  deleting now REPAIRS the history around the node instead of refusing.
  - `Document.remove(id, mode="auto"|"cascade"|"strict")` + `remove_plan()`
    (a dry run). "auto" reconnects each dependent to the deleted node's own
    upstream body (the pass-through a suppress would give), cascades only the
    dependents that cannot be reconnected (a sketch and a solid are never
    interchangeable), and sweeps the TOOL geometry a delete orphans, so
    killing a pocket's cut does not leave its prism floating. Real bodies
    survive: deleting a fuse keeps both of its inputs (a fuse has no tool
    slot), exactly like Fusion.
  - `/api/feature/remove` takes `mode` + `dry_run` and returns the plan; the
    tree's x button dry-runs first and CONFIRMS with the names of everything
    that goes with it (rule 7: never a silent surprise). Del deletes the
    selected feature. One Ctrl+Z restores the whole group.
  - Chat can delete too ({"action":"delete"}), but refuses plans over
    CHAT_DELETE_LIMIT (6) features and points at the tree instead — a chat
    line is a poor place to approve demolishing a design.
  - Tests: tests/test_delete_repair.py (19, incl. volume proof that deleting
    a pocket gives the material back) + tests/e2e/test_tree_delete.py (5,
    real browser: confirm text, reconnect, cancel, Del key, undo).
  - Still open from the same report ("if i want to modify that"): a param the
    AI never emitted cannot be ADDED from the tree (only existing params are
    listed, and `edit()` rejects unknown keys). Extrudes are covered by Edit
    Feature; fillet/shell/pattern params are not. Needs an op-schema-driven
    param row in the tree body.

- **R16 (2026-08-25): selecting a surface must point at the feature that made
  it.** User's words: "when the design is loaded [...] if i am selecting a
  surface in the design, it should go to the or highlight the feature tree,
  which sketch is that and what extrude we have over there, it should be
  robust, dont try some simple parts, we have manz examble like this remote and
  impeller trz those examble". SHIPPED as `provenance.py` +
  `/api/face-feature` + `static/js/provenance.js` (Fusion's *Find in
  Timeline*; the forward direction, feature -> highlighted geometry, already
  existed).
  - THE RULE (every clause was probed, not reasoned): a face is a trimmed
    survivor, and later features can only trim a face, never grow it. So the
    creator is the EARLIEST ancestor feature whose own cached solid had a face
    that (1) is the same surface type, (2) lies on the same infinite surface
    (orientation-canonical key — a cutting tool's cylinder and the hole it
    leaves share one key), (3) whose bounding box CONTAINS the queried face's
    box, and (4) really contains an interior point of it. Clause 3 is the
    discriminator: esp32-remote has 490 coplanar planar faces, so 1+2+4 alone
    is not an identity.
  - Answers with BOTH `origin` (where the geometry came from — a pocket's tool
    extrude, whose sketch is the profile drawn) and `applied_by` (the cut/fuse
    that put it in this body, which is what the tree reveals), plus the sketch
    and extrude behind it. The tree row is flashed AND scrolled into view; the
    rest of the chain is tinted; the pick panel lists it with clickable links.
    Selection (`S.selected`) is deliberately NOT touched — it aims the tools.
  - Face picking now defaults ON (Fusion parity rule 2: there is no "Select
    mode" in Fusion). It defaulted OFF, so on a freshly loaded design clicking
    a surface did nothing whatsoever — indistinguishable from broken, and it
    made this feature undiscoverable. `__vp.setPickMode(on)` added so tests set
    the mode instead of toggling it blind.
  - VERIFIED on the designs the user named, every face, not samples:
    esp32-remote 623/623 attributed, pump-impeller 65/65, with four invariants
    checked per face (coverage, the feature is a real ancestor, no EARLIER
    feature also hosts the face, and asking twice agrees). Blade faces trace to
    `blade_sketch`/`blade_solid` via `blade_ring` (the polar pattern), pocket
    floors to their `*_tool` extrude applied by the `*` cut, and a top face
    that survived 25 cuts still belongs to `body`, not to the last cut.
  - PERFORMANCE: 581 ms -> 13.6 ms per click on esp32-remote. Two real bugs
    behind that: the index cache compared `id(...)` values with `is` (two equal
    ints are not the same object), so the whole index was rebuilt on EVERY
    query; and the walk ran twice, once for `origin` and once for `applied_by`.
  - THE BUG UNIT TESTS COULD NOT SEE: `BRepBndLib.Add_s(face, box, True)`
    measures a face's box from its TRIANGULATION when one exists. The viewport
    tessellates every body it draws, so in the real app — and only there —
    boxes shifted, clause 3 started failing, and attribution slid onto later
    features (42 of the impeller's 65 faces collapsed onto the final fuse)
    while every unit test stayed green. Fixed by demanding exact boxes
    (`useTriangulation=False`, no measurable cost); locked in by tests that
    MESH the body first and then demand identical answers.
  - Tests: tests/test_face_provenance.py (17, impeller included) +
    tests/e2e/test_face_to_feature.py (5, real browser clicks on real triangle
    centroids — a face's centre is often not on the face at all).

- **R17 (2026-08-25): the tree must show DIMENSIONS, not entity JSON — and let
  you edit them.** User's words: "when click the feature, we dont need see to
  entities, and all, also if i am having sketch of square, i have to see lenth,
  in the feature tree, if i want change it i can do it in the feature tree
  itself, like that i can edit all shape in the feature tree as well extrude[.]
  another examble, lets saz we havre piller, i can able to change outer diameter
  and inner diameter as well, all parameter, i can scnage it in the feature
  tree, so it should be robust." (Screenshot: `lora_foot_sketch` expanded to a
  wall of raw path JSON.)
  - A sketch's `entities` no longer renders as JSON. Each shape becomes a card:
    its kind, an add/subtract dropdown (a select, not a text box — "subtract"
    typed into a text field is how holes get lost), and one editable row per
    dimension the geometry actually reads: rectangle -> width/height, circle ->
    radius, slot -> length (overall)/height, ellipse -> radius X/Y,
    regular_polygon -> radius/sides, then x/y/angle. Editing a row sends the
    whole `entities` array back through /api/edit, so it is one normal
    parameter edit: verified, rebuilt, undoable.
  - DIAMETERS everywhere a radius exists: round shapes get a "Ø diameter" row,
    and any op param matching /(^|_)r$|radius/ gets a "Ø ..." sibling (a tube
    shows Ø outer 40 / Ø inner 16 beside outer_radius 20 / inner_radius 8 —
    the user's "piller"). Typing a diameter stores radius = Ø / 2.
  - Coordinate-list shapes (`path`, `polygon`) have no dimensions to type, so
    they show an honest summary — "8 segments · 17.7 × 16.8 mm" — plus an
    "✎ edit shape" button into the sketch editor, instead of 40 coordinates.
  - SINGLE SOURCE OF TRUTH: `sketch.ENTITY_FIELDS` / `ENTITY_COMMON` /
    `ENTITY_DIAMETER` / `ENTITY_GEOMETRY` live next to `_entity()` (the only
    other place that knows these field names) and reach the UI through
    GET /api/sketch/kinds. `sketch.entity_kinds_in_code()` reads the kinds out
    of `_entity`'s own source, and a test asserts the two agree in BOTH
    directions — so a newly added entity kind cannot silently fall back to raw
    JSON, and the catalog cannot list a kind the geometry rejects. A second
    test bumps every declared field and asserts the built area changes, so a
    mis-named key cannot ship a row that does nothing.
  - P0 FOUND WHILE TESTING: build123d silently ABSOLUTISES a negative size —
    `Rectangle(-5, 40)` builds exactly the same face as `Rectangle(5, 40)`
    (probed). With dimensions now editable from the tree, a typo'd minus sign
    would have quietly produced a different part with a green check beside it.
    `sketch._validate_dims` now refuses any non-positive declared dimension,
    naming the field the way the tree labels it. All 41 designs in designs/ were
    scanned first: zero of them relied on the old behaviour.
  - Tests: tests/test_shape_params.py (9) + tests/e2e/test_tree_shape_edit.py
    (5, real browser: type 80 into `width` and the extruded volume doubles;
    type 20 into `Ø diameter` and the stored radius becomes 10).

- **R18 (2026-08-25): finishing or cancelling a sketch took ~10 s, and every
  load was slow.** User's words: "when did some changes or even no chnages in
  the sketch tab, when i am pressing finish or cancel sktch, whz does it take so
  much time to rebuilding it, most of the times, it takse a lot of times to load
  as well, solve this problem, make it more robust".
  - MEASURED FIRST on esp32-remote (73 features): a full rebuild was 6.3 s, of
    which only ~2.4 s was geometry — the rest was re-running `inspector.health`
    on every feature. Opening a sketch sets the rollback bar (rebuild #1) and
    closing it clears the bar (rebuild #2), so a sketch visit that changed
    NOTHING cost ~10 s, plus ~2.3 s of re-tessellation per viewport refresh and
    a 0.4 s STL export that nothing reads.
  - FIX 1 — content-addressed rebuild. A feature's output is a pure function of
    (op, params, input geometry), so each one gets a signature over its op, its
    params and its INPUTS' signatures. Same signature -> the part, its problems
    and its volume are all reused, skipping both the build and the health
    check. Inputs are keyed by content rather than by name, so a rename costs
    nothing and an upstream edit invalidates exactly what is downstream of it.
    Failures are cached too, so a broken parameter does not re-cost a full
    evaluation on every keystroke while the user fixes it.
  - FIX 2 — the cache is PROCESS-WIDE. Signatures are content-addressed, so an
    entry is valid for any document: reopening a design, switching tabs, or
    undoing into a fresh Document all hit geometry already built.
  - FIX 3 — numbers that mean the same must hash the same. The sketch editor
    round-trips `y: -25.0` into `-25` and `offset: 6.0` into `6`; JSON keeps
    those apart, so finishing an UNTOUCHED sketch changed the signature and
    rebuilt every feature below it (13 s for a no-op). Integral floats collapse
    to int and values round to 9 dp — OCCT's own tolerance is 1e-7 mm.
  - FIX 4 — an unchanged sketch is not an edit. `sketcher.create()` compares
    what the editor holds against what is saved (key-order-independent) and,
    when identical, does not POST at all: no rebuild, and no pointless entry on
    the undo stack.
  - FIX 5 — the viewport stops re-fetching geometry it is already drawing. The
    document carries a `geom_version` fingerprint; `loadMesh()` skips the fetch
    and the three.js scene rebuild when it has not moved (`force` for imports
    and tab switches). The 3.2 MB /api/model response is cached as BYTES by the
    same fingerprint, and tessellation is cached process-wide by OCCT shape.
  - FIX 6 — the STL export left the hot path. It cost ~0.4 s on every rebuild
    and nothing in the UI reads it (the viewport is fed by /api/model); it is
    written on demand when /api/mesh.stl is actually requested.
  - RESULT, measured in a real browser on esp32-remote:
    finish a sketch with no changes 10.7-13.6 s -> 0.5-2.2 s; cancel ~10 s ->
    0.8-1.6 s; undo 5.8 s -> 0.6 s; reopen the same design 6.4 s -> 0.5 s;
    repeat /api/model 0.57 s -> 0.01 s; a second tab of the same design 2.2 s
    -> 0.3 s. A no-change rebuild of the document itself is 0.00 s.
  - Tests: tests/test_rebuild_cache.py (12). Most of them are about STALENESS,
    not speed — an upstream edit must reach the result, a cached rebuild must
    match a cold one feature by feature, suppression/rollback/rename/undo must
    all stay correct, and the cache must stay bounded.

- **R19 (2026-08-25): switching tabs showed the WRONG design "for at least one
  minute".** User's words: "when switching design tab also takes really a lot of
  times to load the design [...] if i am switching to esp32 design tab, when for
  atleast one minue i am just seeing t washer only, its making me so irriteting
  [...] there are many delay cases like this are in the software solve these
  issues as well".
  - The tab switch itself was never the problem. Profiling it found the real
    one, which was making EVERY view of a part slow: `_tagged_mesh` meshed each
    of esp32-remote's 254 faces separately (`face.tessellate`, **8.8 s**) and
    then sampled all 609 edges off their curves at 41 points each (**2.5 s**).
    A third of a second of that was one line of my own: keying edges by
    `TShape().This()`, which costs 1.3 ms per call.
  - FIX — mesh the solid ONCE (`BRepMesh_IncrementalMesh`, angular tolerance
    0.35 rad) and read each face's slice of that triangulation, and take each
    edge's polyline from the same mesh (`PolygonOnTriangulation`). This is not
    only ~20x faster, it is BETTER geometry: independently meshed faces do not
    share nodes along their common edges, so the old shell was full of hairline
    cracks, and the outlines now sit exactly on the silhouette.
    `_tagged_mesh` 12.0 s -> **0.61 s**, payload 3.2 MB -> **0.63 MB**.
  - The angular tolerance was measured, not guessed: at 0.35 rad the smallest
    hole in esp32-remote (r=0.8 mm) still gets 37 segments around it.
  - FIX — the viewport no longer shows the previous design while the next one
    loads. Clicking a tab empties the viewport immediately, dims the tab, and
    shows "opening <name>…"; a forced load (tab switch, import, open) always
    puts up the busy overlay, because that is the one case where the wait is
    long enough to read as "nothing happened".
  - MEASURED in a browser with t-washer and esp32-remote both open: the old
    part leaves the screen in **1-7 ms** and the new one is fully up at
    **68-208 ms**.
  - WINDING IS THE RISK in this change: a REVERSED face's triangles wind the
    other way, and getting it wrong turns the part inside out under backface
    culling — which no triangle count would catch. tests/test_mesh_pipeline.py
    (11) checks the mesh as geometry instead: SIGNED volume via the divergence
    theorem (inside-out fails, and it must match the solid's volume within 2%),
    surface area, bounding box, that every face keeps a pickable id, that
    indices stay in range, that edges lie on the part, and that a small bore
    does not degenerate into a polygon. Confirmed visually as well.

- **R20 (2026-08-26): the user's own designs belong in the Examples tab.**
  User's words: "i designed water pump and esp32 remote and some box company
  logo with manz cuts, like this did manz things, collect all those design put
  it under in the examble tab". File > Examples held three hardcoded code
  samples while 27 real designs sat unlisted in File > Open beside t-washer and
  my-part-3. SHIPPED: a grouped gallery (Enclosures / Company plaques /
  Aerospace / Centrifugal pump / Planetary gear set / Simple parts), 27 designs,
  665 features, each tile with a thumbnail, a description and its feature count.
  - The catalog is DATA: designs/examples.json (group -> title -> description),
    served by /api/examples, which reads the feature count from the .tcad.json
    itself so a card can never drift, and drops an entry whose file is gone
    rather than showing a tile that fails to open.
  - Descriptions come from the project memories, so they say what the part IS:
    blind pockets only because the mill holds by vacuum, the cam covers as a
    1:3.1 relief because height never scales to the stock, the pump gasket
    printable 1:1 as a cutting template.
  - Thumbnails: 6 designs already had the user's own CAM-style renders from
    their generator scripts (untouched); the other 21 were rendered from the
    live viewport at 480x270. /api/design-preview serves them because designs/
    is not statically served — with a test that ../studio and ../../etc/passwd
    404 instead.
  - Scratch (t-washer, untitled, my-part-*, mcp-*, popup-*) and intermediate
    iterations stay out of the gallery but remain in File > Open.
  - Tests: tests/test_examples_gallery.py (10) + tests/e2e/test_examples_tab.py
    (4).

- **R21 (2026-08-26): three things the user hit in one sitting.**
  1. **"when i reduced extrude, it created a new body"** — reproduced exactly:
     `esp_pillar_trim_sketch` sits at z=7 with four O9 circles and its tool
     extrudes UP. At amount 6 the tool reaches z=13, past the top of the part,
     and shaves the pillar tops off: ONE piece. At amount 2 it reaches only z=9,
     so it removes a BAND out of each pillar and leaves four caps floating:
     FIVE pieces. The fuse/cut still returns one Part (a compound), so
     `inspector.health` called it clean and the tree stayed green.
     FIX: every feature now carries a piece count (`Feature.pieces`, a raw
     TopExp count — 0.4 ms for all 73 features), and the feature that broke the
     part is NAMED in the warnings. Only body-shaping ops can report: an extrude
     of a sketch holding 8 pilot circles is 8 prisms by design, and warning
     about those buried the signal (esp32-remote produced a dozen such notes
     before the guard, and reports zero now). The Extrude panel also says it
     LIVE, while the value is still in the user's hand. Not blocked — severing
     is sometimes intended — but never silent.
  2. **"its taking a lot of times, when i am changing the values"** — that tool
     is feature 23 of 73, so every keystroke rebuilt 49 downstream features:
     5.4 s each. FIX: editing an extrude parks the rollback bar on the feature
     that APPLIES it (its boolean), exactly as edit-sketch already does, so
     downstream waits for OK. 5.4 s -> 1.9-3.4 s per change, and the full
     rebuild happens once. The bar goes on the BOOLEAN, not the extrude, so the
     preview is the pocket applied to the body rather than a floating prism.
  3. **"i touched pillar top face, it got never selected"** — the edge-pick halo
     was `fitRadius / 60`, a MILLIMETRE distance (~1.9 mm on a 220 mm part), so
     any face under ~4 mm across sat entirely inside the halo of its own rim and
     the edge won at EVERY zoom level. Measured on esp32-remote: 0 of 24 pillar
     tops selectable. FIX: the halo is 5 SCREEN PIXELS, computed from the camera
     at the hit depth. A/B on the same faces: pillar tops 0/12 -> 12/12, pilot
     hole floors 0/20 -> 20/20, with a test that clicking ON a rim still picks
     the edge.
  4. **"why there is three [rows], i dont need the third one"** — the boolean
     now folds onto its tool's row as a CUT / FUSE chip (Fusion shows an extrude
     with a Cut operation as ONE timeline entry). esp32-remote reads as 53 rows
     instead of 73, in sketch+extrude pairs, and clicking that row highlights
     the POCKET instead of the whole body (its old row's output WAS the whole
     body, which is what the user was complaining about). The feature itself
     stays — it is what applies the pocket — and deleting the row still removes
     the pair.
  - Also fixed: OK in the Extrude panel dropped a typed value in EDIT mode if
     pressed inside the input debounce window; and folding briefly broke
     `revealFeature` for folded booleans (a picked pocket face highlighted
     nothing) — `rowFor()` resolves a feature to the row that represents it now.
  - Tests: tests/test_pieces_warning.py (7) +
    tests/e2e/test_small_face_and_fold.py (5). Suite: 387 passed, 1 skipped.

- **R22 (2026-08-26): a cut must not be able to stop INSIDE the material.**
  User, after R21 only warned about it: "if i am increasing or decreasing the
  extrude value, it should increase or decrease, it should not create a new
  body got it, i was trying with pillar, and still its happening again".
  - R21 named the problem; it did not remove it. The cause is structural: a
    cutting tool that ends inside material does not clear it, it SLICES it, and
    whatever was above the cut is left loose. `esp_pillar_trim`'s sketch is at
    z=7 and its tool goes UP, so 6 mm reaches z=13 (past the part, clean) while
    4 mm reaches z=11 and takes a band out of four pillars.
  - FIX: `through` on the extrude op — the standard CAD "through all" extent.
    It ignores the distance, keeps the direction, runs THROUGH_MM (2 m) past
    the part, and ignores taper (a 2 m tapered prism collapses). Offered in the
    Extrude panel only when the operation is Cut, where it disables the
    distance box, and toggleable straight from the tree, since the tree already
    renders boolean params as real checkboxes.
  - MEASURED on esp32-remote, distance vs through-all: at 6 mm both give one
    piece; at 4 / 2 / 0.5 mm the distance extent gives FIVE pieces and
    through-all gives one — with the same volume as the correct 6 mm cut, so it
    is not just "whole", it is the right shape.
  - What now moves the pillars: with `through` on, the distance stops
    mattering, so the height comes from the SKETCH's offset — raise it and more
    pillar survives (tested: offset 5 < 7 < 9 leaves increasing volume). The
    live warning names both cures.
  - Ruled out first: the rebuild cache was NOT lying. Cached and cold builds
    agree exactly on volume and piece count for every value tested.
    (A sweep that first looked like a cache bug turned out to be my own probe
    leaking `through=True` through the params dicts `to_data()` shares.)
  - Tests: tests/test_through_cut.py (14) — including that the original bug
    still reproduces without the flag, that through-all holds at every
    distance, and that the sketch offset is what raises and lowers the pillars.

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
