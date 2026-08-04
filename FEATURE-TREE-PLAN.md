# Feature Tree — development sheet (ACTIVE workstream, started 2026-08-04)

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
- [ ] **Step 3 — AI records the same history**: sketch-first authoring
  contract in author.py + tree lint gate (blob trees rejected, model
  retries). Capture one real logo tree as the before-artifact first.
- [ ] **Step 4 (later) — incremental tool-calling authoring**: the AI drives
  the same endpoints as the ribbon, verified per step; needed once AI
  designs reference existing faces.
