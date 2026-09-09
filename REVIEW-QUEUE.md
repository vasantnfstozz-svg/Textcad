# REVIEW-QUEUE.md - the from-scratch code review of the OLD tools

> **How this file works.** The tools shipped since 2026-09-03 were each reviewed
> right after their commit and the reviews found real bugs every time (Taper 14,
> P2 Extrude 28, Revolve 40, Hole 25, Pattern 7, Mirror ~20, Fillet 7+6). The
> older modules never had that pass. This file is the ordered queue of those
> modules, one section each, with everything a reviewer needs so that no
> section has to be re-derived in a chat.
>
> **One module per chat, on Opus.** The user opens a FRESH chat, types
> `/model claude-opus-5`, then pastes the section's paste line. The review runs,
> the report lands in the chat, and the SAME chat then runs the fix pass
> described under "After the review" at the end of this file. The next module
> waits for the next chat.
>
> The paste line names the files because old code has no diff to review. If
> the review command does not accept several paths, the fallback is this plain
> prompt in the same Opus chat:
> `Read REVIEW-QUEUE.md: the header, the shared rules, section N and "Output format". Review exactly that scope by reading the files, and put the whole report in your final answer.`
>
> `REVIEW-BRIEF.md` keeps its job for per-commit reviews of NEW code (the fixed
> line in the ship-check skill). This file is for the backlog of old code.

---

## Shared rules of engagement (every section)

1. **Read-only during the review.** No edits, no server start (the user's
   server is on port 8123; a second listener there is a known trap), nothing
   under `tests/e2e/` (those write into the design library). You MAY run the
   fast test files a section names, with `C:\Python314\python.exe -m pytest <file> -q`.
2. **Stay in scope.** Read the section's files; follow a call out of them only
   when a finding depends on it. Every other module has its own section.
3. **Comments are history, not clutter.** A comment naming what the user saw
   on which date records a real past bug. Never report a comment as noise.
4. **The frontend must not re-derive backend facts** (LAUNCH-PLAN rule R1).
   Plane frames, axes, normals, origins, safe ranges, target bodies come from
   a server response, never from JS maths. JS that computes such a fact itself
   is a finding; name the line.
5. **Two failures are banned by design:** a kernel exception reaching the
   user (OpenCASCADE errors derive from `Exception`, not `RuntimeError`), and
   a "successful" invalid, empty or non-manifold solid. A degenerate value that
   reaches build123d unchecked is a finding.
6. **The viewport follows the document** (rule R3): a tool that refreshes the
   scene itself is a finding unless the section lists it as known.
7. **No fixes, no style.** One clause of a hint is fine; a patch is not. No
   naming, formatting or refactoring remarks; Ruff and ESLint run at zero.
8. **Findings are concrete.** A finding is an input on which the code does the
   wrong thing, with the exact user action or data that triggers it. "Could be
   fragile" is not a finding.

**Never report** (already known, tracked in LAUNCH-PLAN.md section 10): the
open P1/P2/P3 rows there; the pre-existing red browser tests
(`tests/e2e/test_tree_delete.py`, five; the order-dependent revolve ring
test); two requests reaching the kernel at once (FastAPI threadpool, P2);
the browser replaying a POST on a dead keep-alive socket (P2); the
`enterMode()` race when a sketch opens (P3); `sketcher.js` and `measure.js`
calling `loadMesh()` after their own changes (P3); five tools hand-typing
"a value typed before the plan arrived waits for it" (P3); lint-class output
(unused names, two statements on a line, single-letter geometry variables).
A section may add its own known items.

---

## Output format - exactly this, nothing else

Order by severity: **P0** wrong geometry saved or data lost; **P1** blocks a
basic action; **P2** hurts daily use; **P3** polish. At most 15 findings. If
fewer than 5 have high or medium confidence, say so; do not pad the list.

```
### F1 - P<0-3> - <one line: what goes wrong>
- File: <path>:<line>  (and a second path:line if two places interact)
- Trigger: <the exact user action or the exact input data>
- Expected: <one line>
- Actual: <one line>
- Confidence: high | medium | low - <why: read the whole path / a test contradicts it / could not follow one branch>
- Evidence: <1-3 quoted lines from the file, verbatim>
```

Then two closing sections:

```
### Checked and found OK
<up to 8 one-liners: areas read fully and found sound, so they are not re-checked>

### Could not judge without running the app
<up to 5 one-liners>
```

---

## Status board

| # | Module | Effort | Status |
|---|---|---|---|
| 1 | Sketcher | high | reviewed 2026-09-09, fixed 556a611, 9/9 + 2 uncertainties promoted, 1 rejected; **re-reviewed 6e2cae9** - the fix pass itself had a P0, 8/8 fixed; **third review 5f65a7a** - THAT fix pass had a P0 too (its reorder and its deferral cancelled each other), 8/8 fixed. A fourth review of 5f65a7a is queued in REVIEW-BRIEF.md at medium |
| 2 | Document core and feature tree | high | TODO |
| 3 | Version tree and session persistence | high | TODO |
| 4 | Booleans and transforms | high | TODO |
| 5 | Primitives and shape editing | high | TODO |
| 6 | Measure and drive | high | TODO |
| 7 | Extrude as a whole module (with loft and sweep) | medium | TODO |
| 8 | Import STL and STEP | medium | TODO |
| 9 | Trace image | medium | TODO - may share a chat with 8 |
| 10 | Viewport, picking and face provenance | high | TODO |
| 11 | Tool framework core | medium | TODO |
| 12 | Server layer | medium | TODO |
| 13 | AI author, MCP and chat | medium | TODO |

Skipped on purpose: **Shell** (rebuilt on the framework next; reviewed then),
**the crash supervisor** (`supervise.py`, reviewed 517f2f6), the prototype
leftovers `assembly.py`, `impeller.py`, `engine.py`, `check.py`, `generate.py`
(not reached by Studio or the MCP server).

---

## Section 1 - Sketcher

Paste line:
```
/code-review high sketch.py sketch_trim.py sketch_snap.py sketch_corner.py static/js/sketcher.js static/js/sketch3d.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 1 and the output format
```

The 2D editor the user draws profiles with before extruding, revolving or
cutting them. Never reviewed as a whole.

| File | Lines | Role |
|---|---|---|
| `static/js/sketcher.js` | 2082 | tools (line, rectangle, circle, polygon, path with arcs, image trace), snapping (`smartSnap`, `collectSnapPoints`, `sketchSnap`), drag handles and resize (`entityHandles`, `resizeGrab`, `applyResize`, `pointerDown/Move/Up`), the scale gizmo (`scaleSel` ... `commitScale`), modify ops (`mirrorEntity`, `duplicateEntity`, `offsetEntity`), trim (`fetchTrimPieces`, `trimClick`), dimension editing (`buildDimEditor`, `drawDimFields`, `routeDigitToDrawBox`, `commitDrawDims`), enter/exit/finish/cancel and the did-anything-change test (`sameSketch`, `stableJson`, `finishEmpty`), sketching on a body face (`openSketchOnFace`, `fetchFaceOutline`) |
| `static/js/sketch3d.js` | 439 | the sketch plane inside the 3D viewport: frame, grid, flat-on view, orbit-up, screen-to-plane pointer mapping |
| `sketch.py` | 1-698 | **in scope:** `entity_schema`, `_validate_dims`, `_entity`, `_compose`, `_path_face`, `make_sketch`, `sketch_plane`, `named_face`, `face_plane`, `face_sketch_plane`, `_face_frame`, `face_outline_2d`, `pick_face`, `sketch_on_face`, `_signed_area`. **Out:** `collapse_offset` and everything below (extrude, taper, revolve, hole, loft, sweep - section 7 and the reviewed tools) |
| `sketch_trim.py` | 429 | `trim_pieces` splits entities at intersections, `trim_apply` rebuilds entities from the kept faces; `_pick_face`, `_face_contains` |
| `sketch_snap.py` | 176 | the model-snap backend of `/api/sketch/snap`: `plane_of`, `plane_of_frame`, `snap_geometry` (body edges projected into the sketch plane) |
| `sketch_corner.py` | 252 | the tree's editable path arc radius: `path_arcs`, `set_arc_radius`, `_corner_solve`, `circumradius` (a corner arc re-filleted tangent) |
| `studio.py` | - | the sketch endpoints only: `/api/sketch-mesh/{feature_id}` (l.1592), `/api/face-outline` (1638), `/api/sketch/snap` (1671), `/api/sketch/trim/pieces` (1686), `/api/sketch/arc-radius` (1697), `/api/sketch/trim/apply` (1710), `/api/sketch/kinds` (2633) |
| `toolplan.py` | - | `plan_sketch` (l.538) only: the plane frame the sketcher draws on |

Tests for orientation (fast): `tests/test_e2_sketch.py`, `test_e5_sketch_on_face.py`,
`test_sketch_corner.py`, `test_sketch_snap.py`, `test_sketch_trim.py`,
`test_face_outline.py`. Browser (read, do not run):
`tests/e2e/test_face_sketch_in_viewport.py`, `test_sketch_empty_exit.py`,
`test_sketch_scale.py`, `test_model_snap.py`.

Finding classes, in order of harm:
- **The saved sketch differs from what was drawn** - coordinates, arc
  via-points, path closure, entity `mode` (add/cut), the `x, y` offsets that
  some entities carry and others do not.
- **A change silently dropped or silently applied** - `sameSketch` /
  `stableJson` decide whether an edit rebuilds; a false "same" loses an edit.
  Typed values (`commitDrawDims`, `routeDigitToDrawBox`) versus dragged ones.
- **Snapping moves a point the user did not intend** - a stale model point
  after the body changed, a point on another plane, past the 0.1 mm grid
  floor; exact circle centres and design-centre snaps are meant to be exact.
- **A pointer state machine that gets stuck** - draw, resize, scale, trim,
  path and image trace share one canvas and one `pointerDown/Move/Up`; a
  tool switch, Escape, double-click or lost `pointerup` that leaves a flag set.
- **Async races** - `openSketchOnFace`, `fetchFaceOutline`, `fetchPlaneFrame`,
  `fetchTrimPieces` are awaited while the user can still click. The
  `enterMode` race is known; report a *different, concrete* one only.
- **Trim** - pieces computed from one sketch state and applied to another;
  `_pick_face` / `_face_contains` tolerances; entities returning from
  `trim_apply` with a different kind or orientation.
- **Corner arcs** - `set_arc_radius` on a corner whose neighbours are too
  short for the radius, on a closed path's first/last corner, or on a path
  whose arc list and point list disagree in length.
- **Face sketches** - the outline and frame come from the server; any JS that
  derives a normal, an axis or an "up" itself (rule R1).
- **Validation gaps in `sketch.py`** - zero radius, zero-length line,
  self-intersecting or open path, a polygon with two identical points, NaN or
  string numbers from the JSON, reaching build123d unchecked.

Where to look hardest: `pointerDown/Move/Up` and what `setTool` /
`cancelSketch` reset; `commitDrawDims` and `applyResize` (two writers of the
same fields); `sameSketch` / `stableJson`; `openSketchOnFace` -> `enterMode`
when the plan or outline arrives after the user moved on;
`sketch_trim._pick_face`; `sketch_corner._corner_solve`.

Section-specific known items: `face_sketch_plane` snaps a face tilted under
25 degrees to the nearest principal plane (deliberately parked, section 10
P2); the five `loadMesh()` calls (P3).

---

## Section 2 - Document core and feature tree

Paste line:
```
/code-review high document.py static/js/tree.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 2 and the output format
```

The feature tree and the document that rebuilds it. Every tool sits on this;
a wrong body after an edit, rename, delete or strike is the P0 class. Only
single fixes were reviewed (36584e1: tree wipe on delete, refusals as 400,
clockwise polygons), never the module.

| File | Lines | Role |
|---|---|---|
| `document.py` | 1481 | `Feature` (l.291), `Document` (l.319): `add`, `edit`, `edit_many`, `check_params`, `param_names`, `param_refs`, `rename`, `remove`, `remove_plan`, `_delete_plan`, `_orphan_sweep`, `_passthrough`, `strike`, `unstrike`, `rebuild`, `_eval`, `_signature`, `_cache_get/_put`, `_mark_stale`, `_heal_stranding_cuts`, `_check_pieces`, `_check_dangling`, `_result_feature`, `result*`, `consumed_ids`, `leaf_solid_ids`, `to_data`, `from_data`, `save`, `load`. Module helpers `op_params`, `_min_inputs`, `_kind_of`, `_deep_valid`, `n_solids`, `_canon_number`, `_delete_summary`, `SEEDED_OPS`, `REF_PARAMS`. **Out:** the boolean semantics of `_fuse/_cut/_intersect/_loft` themselves (section 4) |
| `static/js/tree.js` | 1006 | `renderDoc`, `buildRow`, `buildBody`, `selectFeature`, `beginEdit` / `beginEditWith` / `applyEntity`, `beginRename`, `strikeFeature` / `restoreFeature`, `deleteFeature`, `revealFeature`, the parameter editors (`genericFields`, `genericRadius`, `genericGeometry`, `pointsTable`, `pathArcRows`, `entRow`, `modeToggle`), `renderWarnings` / `failMessage`, `applyTreeFilter` / `initTreeFind`. **Out:** the shape catalogue editors (`shapeCatalog`, `diameterRow`, `shapeList`, section 5) |
| `studio.py` | - | `/api/doc` (987), `/api/edit` (1625), `/api/feature/params` (1719), `/api/feature/add` (1734), `/api/feature/remove` (2128), `/rename` (2153), `/suppress` (2168), `/strike` (2182), `/api/undo` (2216), `/redo` (2241), `/rollback` (2268) |

Tests for orientation (fast): `test_tree.py` 23, `test_delete_repair.py` 20,
`test_strike.py` 6, `test_strike_visibility.py` 3, `test_p0_fixes.py` 13,
`test_p1_fixes.py` 12, `test_rebuild_cache.py` 13, `test_core.py` 16,
`test_pieces_warning.py` 7, `test_polygon_winding.py` 7, `test_api.py` 25.
Browser (read only): `tests/e2e/test_tree_delete.py` (five red, known),
`test_tree_history.py`, `test_tree_shape_edit.py`.

Finding classes:
- **A rebuild serves a stale body** - `_signature` / `_cache_get` /
  `_mark_stale` after a param edit, rename, strike, suppress or reorder; a
  cache key that ignores a field the op reads.
- **Delete and strike take too much or too little** - `_delete_plan`,
  `_orphan_sweep`, `_passthrough`, `_heal_stranding_cuts`: a healed or
  re-pointed cut is a changed result the user did not ask for; the
  2026-08-31 tree wipe is the class.
- **References not walked** - `REF_PARAMS` / `SEEDED_OPS`: rename, delete,
  strike, unstrike must reach every seed, target, face and sketch reference;
  a dangling reference that resolves to *something else* instead of failing.
- **The edit guard** - `op_params` / `check_params`: a key the op cannot take
  accepted, a legal one refused, a number arriving as a string or with a
  unit; `edit_many` applying half a batch.
- **File round trip** - `from_data` on an older file changing meaning (legacy
  forms of axis, plane, seed), `to_data` dropping a field, `load` of a file
  with an unknown op.
- **Health verdicts** - `_deep_valid`, `n_solids`, `_check_pieces`,
  `_check_dangling`: a multi-solid or invalid result reported as one healthy
  body, or a healthy one refused.
- **tree.js editors** - `applyEntity` and the generic editors writing into the
  wrong field, the wrong entity index, or with a string type; a struck or
  suppressed row that still accepts an edit; `renderDoc` losing the selection
  or the open editor on a doc event.
- **Undo / redo / rollback** - a snapshot restored into the wrong tab, or a
  refused step leaving the redo line inconsistent (`_unsnapshot`).

Where to look hardest: `_delete_plan` with `_orphan_sweep`; `_signature` and
what it omits; `strike` / `unstrike` with struck ancestors and the folded
combiner that has no tree node; `applyEntity`; the `suppress` endpoint's
effect on a final boolean.

Section-specific known items: a suppressed final boolean promotes its TOOL to
the result (section 10, P1) - report it only if you name the line that does it.

---

## Section 3 - Version tree and session persistence

Paste line:
```
/code-review high history.py backfill.py static/js/versions.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 3 and the output format
```

Per-design version history in `designs/<name>.history/`, the version panel,
and the tab session that survives a server restart. Data loss is the P0 class
here. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `history.py` | 807 | `History` (l.221): `_load`, `_save`, `_write_atomic`, `snapshot`, `append`, `set_current`, `star`, `relabel`, `amend`, `delete_after`, `delete`, `rename`, `protected`, `prune`, `repair`, the tree queries (`children`, `roots`, `ancestors`, `leaves`, `branch_points`, `depths`, `tree_lines`); `diff_snapshots`, `content_hash`, `_change_note` |
| `backfill.py` | 254 | migration of pre-history designs into `.history/` |
| `static/js/versions.js` | 414 | `paint`, `row`, `descendantsOf`, `removeAfter`, `remove`, `toggleDiff`, `rename`, `restore`, `refresh`; the dirty dot and the three-way close prompt |
| `studio.py` | - | the tab model and session: `_new_tab` (140), `_find_tab` (163), `_tabs_json` (231), `_persist_session` (263), `_restore_session` (278), `/api/tabs` (996), `/switch` (1001), `/close` (1015), `/api/new` (1028), `/api/open/{file}` (2570), `/api/designs` (2556); the versions API: `/api/save` (2283), `/api/versions` (2298), `/diff` (2317), `/restore` (2341), `/star` (2409), `/amend` (2426), `/delete_after` (2456), `/delete` (2474), `/label` (2493) |

Tests for orientation (fast): `test_history.py` 73, `test_version_api.py` 60,
`test_session_restore.py` 5, `test_tab_reuse.py` 13, `test_backfill.py` 21.
Browser (read only): `tests/e2e/test_version_panel.py`, `test_tree_history.py`,
`test_recovery.py`. Design notes: `VERSION-TREE-PLAN.md`.

Finding classes:
- **A version is not what was saved** - `content_hash` vs the snapshot
  written, `amend` (update vN in place) vs `append` (push vN+1) choosing wrong,
  the dirty flag lying in either direction.
- **A version or the current pointer is lost** - `delete`, `delete_after`
  (renumbers), `prune`, `repair`, `protected`; restore of a version whose
  snapshot file is missing or unreadable; `_write_atomic` on Windows when the
  target exists or is open in another tab.
- **Two tabs, one design** - the same design open twice, or the same
  `.history/` written by two tabs; `_find_tab` reuse rules.
- **Session restore** - a tab restored on the wrong design or version, unsaved
  edits dropped or duplicated after a restart, the per-port session file, the
  supervisor's `TEXTCAD_RECOVERED` / `TEXTCAD_SAFE_RESTORE` path read here.
- **Open and save** - a design written under another name (the path
  sanitising itself is known P2; a *wrong file written* is a finding),
  `/api/new` colliding with an existing name.
- **versions.js** - the row acted on differs from the row shown
  (`descendantsOf`, `removeAfter`, `restore` after a `refresh`), the close
  prompt discarding when it said keep, `toggleDiff` on a stale pair.
- **backfill** - a migrated design whose v1 differs from the file it came
  from.

Where to look hardest: `delete_after` and `repair`; `_persist_session` when
the server is mid-request; `restore_version` (studio.py 2342) and what it
does to the tab's dirty state; `versions.js` `remove` / `removeAfter`.

---

## Section 4 - Booleans and transforms

Paste line:
```
/code-review high document.py blocks.py toolplan.py - read REVIEW-QUEUE.md first: the header, the shared rules, section 4 and the output format; in these three files review ONLY the functions section 4 names
```

Join, Cut, Intersect, Loft as combiners; Move, Rotate, Scale as transforms;
the default cut target. These change bodies silently, which is why they rank
here. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `document.py` | 60-110 | the ops table, `_fuse`, `_cut`, `_intersect`, `_loft`, `COMBINERS`, `_kind_of`, `_min_inputs`; the combiner folding (a combiner that has no tree node), `_result_feature`, `consumed_ids`, `leaf_solid_ids`, `_check_pieces`, `_heal_stranding_cuts` as they apply to booleans |
| `blocks.py` | 196-222 | `rotate`, `scale_uniform`, the `move` entry of the ops table (l.933); `mirror_copy` (204) is the legacy form now owned by Mirror, reviewed - read for context only |
| `toolplan.py` | 149-207 | `_latest_descendant`, `_default_target`, `_pick_face`, `_flat_or_raise`, `_pick_body`: which body a cut or a face pick lands on when several exist |

Tests for orientation (fast): `test_s3_bodies.py` 6, `test_e1_ops.py` 10,
`test_core.py` 16, `test_delete_repair.py` 20 (cuts self-heal),
`test_pieces_warning.py` 7, `test_export_guard.py` 18 (multi-body), and the
corpus in `tests/gauntlet.py` (read it; do not run every gauntlet).

Finding classes:
- **A boolean result that is several solids reported as one body**
  (`n_solids`, `_check_pieces`), or the TOOL body surviving as the result.
- **Touching, not overlapping** - fuse or cut of bodies that share a face or
  an edge producing a non-manifold or invalid "success" (rule 5); an
  intersect with no overlap returning an empty solid as OK.
- **Transforms about the wrong point** - `rotate` / `scale_uniform` about the
  world origin when the body sits off-origin, or about a centre that moves
  with an earlier edit; a transform of a body that carries a sketch plane
  (the Mirror lesson: `Shape.mirror` copied the sketch's plane along).
- **The default target** - `_default_target` / `_pick_body` choosing a body
  other than the one under the sketch when several exist, or a struck one.
- **Input order after a delete or strike** - a cut whose tool and target
  swap, or a fuse that loses one input silently.
- **Loft** - profiles on the same plane, mismatched vertex counts, a loft of
  a single profile, reaching the kernel unchecked.

Where to look hardest: `_cut` and `_heal_stranding_cuts` together;
`_default_target`; `_check_pieces` thresholds; `scale_uniform`'s centre.

Section-specific known items: a suppressed final boolean promotes its tool
(P1) - name the line if you find it; `blocks.py` calling `is_valid()` as a
method inside a bare except (section 10 P2, line has shifted since) belongs to
section 5.

---

## Section 5 - Primitives and shape editing

Paste line:
```
/code-review high blocks.py static/js/tree.js static/js/placement.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 5 and the output format; in blocks.py and tree.js review ONLY the functions section 5 names
```

The primitives (Box, Cylinder, Sphere, Cone, Pipe, Hex, Polygon, Turn
profile, Blade, Centre bore, Bolt circle), the shape editors in the tree, and
placing a new primitive in the viewport. The AI's main building path; a
dimension landing in the wrong parameter is the P0 class. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `blocks.py` | 52-183, 599-668, 945-1012 | `plate`, `disc`, `ball`, `cone`, `tube`, `polygon_plate`, `hex_plate`, `revolve_profile`, `curved_blade`, `_tall_cutter`, `with_center_hole`, `with_bolt_circle`; the legacy `polar_pattern` (183) and `linear_pattern` (222) that the AI may still emit; `_plain_cause`, `_finish` (the health check every op returns through), `api_summary`, `_signature`, the ops table (933). **Out:** the fillet/chamfer, edge and face resolvers (reviewed), import (section 8), `shell_out` (rebuilt next) |
| `static/js/tree.js` | - | `shapeCatalog`, `shapeList`, `diameterRow`, `genericFields`, `genericRadius`, `genericGeometry`, `staleCatalogNote`, `renderSpecRow`, `round`, `circumR` |
| `static/js/placement.js` | 115 | `PLACEABLE`, `startPlacement`, `closePlacePopup`; with `viewport.beginPlacement` / `cancelPlacement` (viewport.js 472-480) |
| `studio.py` | - | `/api/ops` (2640), `/api/feature/add` (1734) for blocks |

Tests for orientation (fast): `test_shape_params.py` 9,
`test_placement_defaults.py` 2, `test_e1_ops.py` 10, `test_core.py` 16,
`test_api.py` 25. Browser (read only): `tests/e2e/test_tree_shape_edit.py`,
`test_washer_resize.py`, `test_bodies_visible.py`.

Finding classes:
- **A tree edit lands in the wrong parameter or unit** - `diameterRow` is
  exactly the radius/diameter seam; `round` and `circumR` (hex and polygon
  size conventions); a field shown for one op and written to another.
- **Degenerate parameters reaching the kernel** - zero or negative height,
  `tube` inner >= outer, `cone` top >= bottom, a bolt circle whose holes
  overlap the bore or each other, a blade with zero chord: rule 5 both ways.
- **Placement re-deriving the frame** - `placement.js` computing where the
  primitive lands from viewport maths instead of the plan (rule R1); a
  placed primitive whose stored origin differs from the ghost shown.
- **`_finish` and `_plain_cause`** - a kernel message reaching the user
  verbatim, a wrong sentence, or an invalid result passing `_finish`; the
  `is_valid()` method-vs-property fast path (say what it does now).
- **The legacy patterns** - `polar_pattern` / `linear_pattern` in blocks.py
  versus the Pattern tool's `pattern.py`: a design file naming the legacy op
  rebuilding differently.
- **`api_summary` / `_signature`** - the catalogue the AI and the tree read
  disagreeing with what the op accepts.

Where to look hardest: `diameterRow` and `genericFields`; `_finish`;
`with_bolt_circle`; `startPlacement`.

---

## Section 6 - Measure and drive

Paste line:
```
/code-review high measure.py static/js/measure.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 6 and the output format
```

The measure tool and type-a-dimension drive. A driven dimension REWRITES a
feature parameter, so a wrong resolver is silent wrong geometry. The rule is
driven-vs-derived (`MEASURE-PLAN.md`). Never reviewed.

| File | Lines | Role |
|---|---|---|
| `measure.py` | 1340 | `resolve`, `_measure_one`, `_measure_two`, `_full_circles`, `_min_distance`, `_closest_on_axis`, `_plane_cache` / `_plane_sig` / `_sketch_plane` / `_build_plane`, `_face_index_for`, `_hole_driver`, `_diameter_driver`, `resolve_driver`, `_face_role`, `_entity_dim_for_direction`, `resolve_pair_driver`, `resolve_move`, `plan_move`, `plan_set`, `_to_param`, `write`, `probe`, `measure` |
| `static/js/measure.js` | 460 | `openMeasure`, `cancelMeasure`, `run`, `paintPicks`, `armProbe` / `paintProbe` / `sendProbe`, `showEdit` / `applyEdit` / `readOnlyReason` |
| `static/js/viewport.js` | 1995-2114, ~2190 | `showDimension`, `clearDimension`, `setDimProbe`, `setDimProbeFrozen`, `clearDimProbe`, `initDimDrag`, `nudgeDimFrom`, `paintDimLabel`, `dimEnd` |
| `studio.py` | - | `/api/measure` (2010), `/api/measure/probe` (2047), `/api/measure/set` (2061) |

Tests for orientation (fast): `test_measure.py` 32, `test_measure_api.py` 10,
`test_measure_drive.py` 23, `test_measure_move.py` 11. Browser (read only):
`tests/e2e/test_measure_picks.py`, `test_measure_probe.py`, `test_dim_box.py`.

Finding classes:
- **A typed value writes the wrong parameter** - `resolve_driver`,
  `resolve_pair_driver`, `_to_param`, `write`: wrong feature, wrong key, wrong
  sign or offset (a distance to a face vs a sketch offset), a diameter written
  as a radius.
- **Derived offered as driven** - `readOnlyReason` and `_face_role`: a
  dimension that depends on two features editable as if it drove one.
- **The number is wrong** - curved-to-curved minimum distance, axis offsets,
  a full circle vs an arc (`_full_circles`), `_plane_cache` serving a plane
  from before a rebuild (`_plane_sig`).
- **Move** - `resolve_move` / `plan_move` moving a different feature or by a
  vector in the wrong frame (rule R1 applies on the JS side too).
- **Stale picks** - a pick on a body id from before a rename or rebuild
  answering on another body.
- **The probe** - `probe` and `sendProbe` disagreeing on units or frame; a
  frozen probe surviving a doc change.

Where to look hardest: `resolve_driver` and `_diameter_driver`; `_to_param`;
`_plane_cache`; `applyEdit`.

Section-specific known items: `measure.js`'s one awaited `loadMesh()` (P3);
MEASURE-PLAN P3/P4 (pinned dimensions, named parameters) are not built, so
their absence is not a finding.

---

## Section 7 - Extrude as a whole module (with loft and sweep)

Paste line:
```
/code-review medium sketch.py toolplan.py static/js/extrude.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 7 and the output format; in sketch.py and toolplan.py review ONLY the functions section 7 names
```

Extrude was reviewed three times as a DIFF (taper dae2c5f, the framework
rebuild 6cc526a, direction/panel fixes) but never as one module, and loft and
sweep (AI-only ops, no tool UI) were never reviewed at all. Fresh eyes go to
the cut and through paths, `_shapefix`, `collapse_offset`, loft and sweep.

| File | Lines | Role |
|---|---|---|
| `sketch.py` | 699-1122, 1478-1510, 1631-1668 | `collapse_offset`, `_apex_cap`, `_taper_offset_problem`, `_tapered_extrude`, `_tapered_extrude_face`, `_same_side`, `_taper_loft`, `_shapefix`, `extrude_face`, `_fusion_taper`, `extrude_sketch`, `face_profile`; `through_reach`, `material_depth` (shared with Hole); `loft_sketches`, `sweep_sketch`, `is_sketch` |
| `toolplan.py` | 207-340 | `plan_extrude`, `_edit_input`, `_sketch_part`, `_profile`, `_coincides`, with `_limits` / `_collapse` (93-135) |
| `static/js/extrude.js` | 266 | the tool declaration: `openExtrude`, `initExtrude` |
| `static/js/viewport.js` | 978-1250, 1449-1491 | the arrow, second arrow, ghost and taper ring (`beginExtrudeArrow` ... `secondArrowAxisScreen`, `projectAmount`, `arrowGrab/Drag/Release`) |
| `studio.py` | - | `/api/face-feature` (1994): extrude_face from a picked face |

Tests for orientation (fast): `test_extrude_v1.py` 15, `test_through_cut.py` 18,
`test_taper_apex.py`, `test_taper_direction.py`, `test_face_workflow.py` 6,
`test_offset_method.py`, `test_toolplan.py` 15. Gauntlet: `test_taper_gauntlet.py`
(read; run only if a fix touches taper). Browser (read only):
`tests/e2e/test_edit_extrude.py`, `test_extrude_cut_target.py`,
`test_extrude_direction.py`, `test_extrude_ok_commits.py`, `test_modal_taper.py`,
`test_face_to_feature.py`, `test_small_face_and_fold.py`.

Finding classes:
- **A through cut that does not go through** - `through_reach` /
  `material_depth` measured on a body that a later feature extends; a cut that
  stops a hair short and leaves a skin.
- **The wrong target** - when several bodies exist (also section 4's
  `_default_target`), or a cut that finds nothing and reports success.
- **Extents** - Two sides / Symmetric measured or signed wrong; an amount of
  0 or a negative amount reaching the kernel.
- **`_shapefix`** - a repaired solid is a DIFFERENT solid; repair that
  changes volume beyond tolerance without a note (rule 5, quietly).
- **`collapse_offset`** - a face sketch's offset folded into the extrude on the
  wrong side, or twice.
- **Loft and sweep** - profiles on one plane, mismatched vertex counts, one
  profile, a self-intersecting path, reaching build123d unchecked; a sweep
  along a path that is not planar.
- **The arrow** - `projectAmount` vs the plan's axis (rule R1); the arrow's
  amount and the box disagreeing after a drag ends off-canvas.

Section-specific known items: the taper ring can start off-canvas (P3); the
25-degree face snap (P2); "a value typed before the plan arrived" (P3).

---

## Section 8 - Import STL and STEP

Paste line:
```
/code-review medium meshrepair.py blocks.py static/js/dialogs.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 8 and the output format; in blocks.py and dialogs.js review ONLY the functions section 8 names
```

An external STL becomes a solid through a repair pipeline; a STEP becomes an
exact body. The invalid-solid class (rule 5) is the risk. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `meshrepair.py` | 359 | `parse_binary_stl`, `to_binary_stl`, `edge_counts`, `duplicate_triangles`, `signed_volume`, `is_clean`, `drop_duplicate_walls`, `split_components`, `collapse_repair`, `voxel_remesh`, `decimate_guarded`, `repair_stl_mesh` |
| `blocks.py` | 696-943 | `_stl_triangles`, `_ascii_stl_to_binary`, `_stl_bytes_to_solids`, `_read_stl_solids`, `_resolve_stl_path`, `import_stl`, `_resolve_step_path`, `import_step`, `import_stl_report` |
| `static/js/dialogs.js` | 80-128 | `actionImportStl` (one button, routed by extension) |
| `studio.py` | - | `/api/import-stl` (1932, `import_stl_file`), `/api/import-step` (1885, `import_step_file`) |

Tests for orientation (fast): `test_import_stl.py` 19, `test_import_step.py` 8,
`test_mesh_pipeline.py` 9.

Finding classes:
- **A wrong solid reported as OK** - inverted normals (`signed_volume` sign),
  `is_clean` thresholds, a multi-shell STL imported as one body or the
  largest shell only without saying so.
- **Repair that changes the part silently** - `voxel_remesh`,
  `decimate_guarded`, `collapse_repair`: how far did the surface move, and is
  that in the report (`import_stl_report`)?
- **Format detection** - a binary STL whose header starts with `solid`; an
  ASCII STL with Windows line endings; a STEP with several solids or a
  compound; a zero-triangle file.
- **Paths** - `_resolve_stl_path` / `_resolve_step_path` escaping `imports/`,
  name collisions overwriting an earlier import (the 48 leftover files are
  known, section 10 P2; the collision is not).
- **The body in the tree** - a `Part` wrapping a compound with volume 0
  (recorded gotcha), body ids after import, the forced mesh reload.
- **Cost** - only if quadratic in triangles (`edge_counts`,
  `duplicate_triangles`).

---

## Section 9 - Trace image

Paste line:
```
/code-review medium imgtrace.py static/js/sketcher.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 9 and the output format; in sketcher.js review ONLY the image-trace functions section 9 names
```

"Trace Image" in the sketch ribbon: a PNG/JPG/SVG becomes polygon entities
in the open sketch, auto-fitted to a face sketch including a 90-degree
auto-rotate. Small; may share a chat with section 8. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `imgtrace.py` | 216 | `_mask_from_image`, `artwork_aspect`, `_bridge_pieces`, `_chaikin`, `_round_pts`, `_poly_entity`, `image_to_entities` |
| `static/js/sketcher.js` | - | the trace tool only (grep `trace`): rasterising SVG/JPG in the browser, the fit to the face outline, the auto-rotate, the insert into the sketch |
| `studio.py` | - | `/api/trace-png` (1832) |

Tests for orientation (fast): `test_trace.py` 9.

Finding classes:
- **Entities that section 1 would refuse** - self-intersecting polygons,
  duplicate consecutive points, fewer than 3 points, produced here and handed
  to `sketch.py`.
- **Orientation** - image y-down vs sketch y-up; the auto-rotate applied
  twice, or not at all, on a face sketch; mirror-image artwork.
- **Scale and fit** - `artwork_aspect` vs the face outline; a fit that
  overflows the face; sub-0.1 mm points after `_round_pts`.
- **Holes in the artwork** - nested contours: inner loops as `cut`, outer as
  `add`, and the nesting depth beyond two.
- **Input limits** - a huge image, an image with alpha only, a JPG with no
  dark pixels: a sentence, not a stack trace.

---

## Section 10 - Viewport, picking and face provenance

Paste line:
```
/code-review high static/js/viewport.js provenance.py static/js/provenance.js static/js/grid3d.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 10 and the output format; in viewport.js skip the per-tool gizmos section 10 lists as out of scope
```

The three.js scene, face/edge/body picking, the model loading that follows the
document (R3), and the face-to-feature attribution behind a click. The fillet
picking half was reviewed (4f15f66, 9bed191, e5ffb8d); the rest never.

| File | Lines | Role |
|---|---|---|
| `static/js/viewport.js` | 2443 | **picking first:** `pickAt`, `selectProfile`, `selectFace`, `selectEdge`, `faceGeometry`, `showPick`, `answerPick`, `profilePickAt`, `edgeHitAt`, `faceInfoAt`, `ndcFrom`, `planePickAt` / `planePickHover`, `buildOriginPlanes` / `clearOriginPlanes`, `hoverFaceAt`, `pickWhat`, `beginProfilePick` / `cancelProfilePick`, `beginEdgePick` / `endEdgePick`, `beginPlanePick` / `cancelPlanePick`. **Then the model side:** `loadMesh` (1752), `loadModel`, `addBodies` / `bodyMeshes`, `addSketches` / `sketchMeshes`, `disposeModel` / `disposeParts`, `follow`, `fitToObjects`, `clearMesh`, `showFeatureOverlay`, `showSelectionOverlay` / `clearSelectionOverlay`, `setView` (1596), `holdViewport` (1729), `buildControls`, `setOrbitUp`, `zoomFloor` / `wheelNotches` / `onWheelZoom`, `placeGround` / `groundFootprint` / `updateGroundGrid`, `modelExtent`. **Out:** the per-tool gizmos - extrude arrow and ghost, taper ring, axis line, plane quad, hole marker, revolve ghost, the dimension probe (sections 6, 7 and the reviewed tools); `visibleEdgeHit` / `ownFaceHit` (reviewed; re-check only how the two pickers share them) |
| `provenance.py` | 658 | which feature made this face: `topo_faces`, `surface_key`, `interior_point`, `OnFace`, `picked_faces`, `feature_index`, `edge_feature`, `attribute_face`, `_chain`, `_explain`, `_hosts`, `_sketch_behind`, `_extrude_behind`; `feature_faces` (369) was reviewed in e5ffb8d - read for context |
| `static/js/provenance.js` | 145 | `render`, `clear`: the face-to-feature answer shown to the user |
| `static/js/grid3d.js` | 140 | `gridStepFor`, `planeHalfFor`, `buildGridLines`, `viewFootprintOn`, `patchFor` |
| `studio.py` | - | `/api/mesh.stl` (1061), `/api/model` (1515), `/api/feature-mesh/{id}.stl` (1606), `/api/face-feature` (1994) |

Tests for orientation (fast): `test_face_provenance.py` 17,
`test_face_workflow.py` 6, `test_mesh_pipeline.py` 9. Browser (read only):
`tests/e2e/test_camera_zup.py`, `test_adaptive_grid.py`, `test_zoom_limits.py`,
`test_origin_planes.py`, `test_bodies_visible.py`, `test_model_snap.py`.

Finding classes:
- **The click lands on something else** - depth-only rules where topology is
  needed (the fillet lesson), the ground plane or a sketch mesh eating a
  click, a hidden face selected, `ndcFrom` off by the canvas offset after a
  resize.
- **Stale ids** - body ids after a rename or rebuild (`geom_version`), a
  highlight or overlay on the wrong body, `follow` skipping a doc event.
- **Attribution** - `attribute_face` naming the wrong feature:
  `surface_key` tolerances, `interior_point` on coplanar faces, a trimmed
  survivor after a later cut, a face two features could claim.
- **Rule R1** - any frame, normal, axis or origin derived in JS from mesh
  geometry instead of a plan or doc field.
- **Rule R3** - the scene refreshed by a tool, or refreshed twice for one
  doc event, or not at all for an event kind.
- **Camera** - orbit-up flip, `zoomFloor` trapping the user on a small part,
  `fitToObjects` on an empty scene.
- **Disposal** - geometries and materials not disposed per rebuild (only if
  it grows per rebuild).

Section-specific known items: a tree row click's own STL highlight racing a
face click's plan on the kernel (P2); the R3 `loadMesh` calls in sketcher and
measure (P3); the `enterMode` race (P3).

---

## Section 11 - Tool framework core

Paste line:
```
/code-review medium static/js/tool.js toolplan.py static/js/dialogs.js static/js/api.js static/js/ask.js static/js/ribbon.js static/js/main.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 11 and the output format; in toolplan.py review ONLY the shared helpers and plan() that section 11 names
```

The framework every tool declares itself on, the plan request path, the
dialogs and the API layer. Reviewed only piecemeal, tool by tool.

| File | Lines | Role |
|---|---|---|
| `static/js/tool.js` | 1028 | `tool()`, `fill`, `currentSelection`, `waitForRow` / `dropRowWait`, `boolOf`, `isolateFor` / `releaseIso`, `pickedBody`, `activeToolFeature`, `toolSessionOpen`, `canEdit`, `editFeature`, `cancelTool`, `humanProblem`, `setBox`, `num`, `say`; the one-way Cancel/OK guard and Esc |
| `toolplan.py` | 51-207, 1242 | `_vec`, `_frame`, `_axis_name`, `_project_wire`, `_loops`, `_limits`, `_collapse`, `_world`, `_feature`, `_solids`, `_latest_descendant`, `_default_target`, `_pick_face`, `_flat_or_raise`, `_pick_body`, `plan()`; with the `ToolPlanReq` model and `/api/tool/plan` (studio.py 1660) |
| `static/js/dialogs.js` | 423 | `modalGuard`, `actionNew` / `Save` / `Open` / `Export` / `Undo` / `Redo` / `Examples`, `loadSample`, `openFeatDialog`, `initDialogs`, `actionSpec` |
| `static/js/api.js` | 135 | `setBusy` / `clearBusy` / `isBusy`, `getJSON`, `postJSON`, `planRequest` (the queue), `waitForServer`, `noteRecovery` |
| `static/js/ask.js` | 125 | `askText`, `askConfirm`, `askThree`, `askNumber` (no native dialogs) |
| `static/js/ribbon.js`, `main.js`, `bus.js`, `state.js`, `icons.js` | 225, 108, 10, 15 | the tabs and buttons, boot order, the event bus, shared state `S` |

Tests for orientation (fast): `test_toolplan.py` 15, `test_launch_rules.py` 5,
`test_api.py` 25. Browser (read only): `tests/e2e/test_user_workflow.py`,
`test_extrude_ok_commits.py`, `test_recovery.py`.

Finding classes:
- **Cancel / OK / Esc** - a preview feature removed twice or left behind, an
  OK that commits after a Cancel, Esc during an awaited plan.
- **The plan queue** - `planRequest`: a stale plan answering a newer click,
  a busy flag stuck after a failed request, two tools' plans interleaved.
- **Edit** - `editFeature` reverting to the wrong params on Cancel, or the
  select following a default instead of the stored value (known for five
  tools as P3; report only a NEW instance).
- **`ToolPlanReq`** - a field a tool sends that pydantic drops (the `own_id`
  lesson); a field typed wrong (string for a number).
- **Dialogs** - `modalGuard` letting two dialogs stack, `askNumber` returning
  a string, a dialog action running on the wrong tab.
- **Recovery** - `noteRecovery` and `waitForServer` after a supervisor
  relaunch: a stale tab list, a request replayed.
- **Ribbon** - a button reaching a tool in the wrong mode; an op missing from
  `icons.js` so it is invisible in the tree.

Section-specific known items: five tools hand-type the plan wait (P3); tool
panels cover the chat column (P2); the one-way Cancel/OK guard and Esc were
done in P4 (recheck, do not re-report the design).

---

## Section 12 - Server layer

Paste line:
```
/code-review medium studio.py - read REVIEW-QUEUE.md first: the header, the shared rules, section 12 and the output format; skip the endpoints other sections own
```

The FastAPI app minus the endpoints owned by other sections: setup, error
handling, refusals, the remaining endpoints, export, static serving. The STEP
export was reviewed (753c24c); recheck only the guard's blind spots.

| File | Lines | Role |
|---|---|---|
| `studio.py` | 2797 | app setup and middleware, `_user_env()` (API keys from the registry), the refusal path (`_refused`, every refusal answers 400), exception handlers; `/` (982), `/api/spec` (2200), `/api/examples` (2507), `/api/design-preview/{file}` (2545), `/api/sample/{name}` (2613), `/api/ops` (2640), `/api/export` (2646, `export_step`, `_export_blockers`), `/api/chat` (2688, the HTTP side only; the author is section 13), the supervisor handshake (`TEXTCAD_SERVER_CHILD`, `TEXTCAD_RECOVERED`, `TEXTCAD_SAFE_RESTORE`, the checkpoint), static file serving and cache-busting |
| `supervise.py` | 224 | reviewed (517f2f6) - read for context only |

Tests for orientation (fast): `test_api.py` 25, `test_export_guard.py` 18,
`test_tab_reuse.py` 13, `test_examples_gallery.py` 10, `test_supervisor.py`.
Browser (read only): `tests/e2e/test_examples_tab.py`, `test_recovery.py`.

Finding classes:
- **A wrong status** - 200 with `ok: false`, a 500 carrying a kernel message,
  a refusal as 200 (rule 5 at the HTTP layer).
- **Paths** - `/api/design-preview`, `/api/sample`, `/api/examples` building
  file paths from request data (open and export are known P2; the others are
  new).
- **Export** - `_export_blockers` missing a case (the multi-body lesson: 4 of
  50 designs once exported as little as 0.1%), a file name collision, the
  export of a struck or suppressed tree.
- **Concurrency** - a request mutating a tab another request reads (the
  kernel race itself is known; a *lock that is missing on a specific path* is
  new).
- **Secrets** - an API key in a log line, a response or an error page.
- **Binding** - the server reachable from outside the machine.

---

## Section 13 - AI author, MCP and chat

Paste line:
```
/code-review medium author.py mcp_server.py meanline.py static/js/chat.js - read REVIEW-QUEUE.md first: the header, the shared rules, section 13 and the output format
```

The front door for the founding rule ("AI mistakes must never reach the
user"): the catalogue the AI reads, the parser of what it returns, the lint,
the MCP tools an outside AI calls, and the chat column. Never reviewed.

| File | Lines | Role |
|---|---|---|
| `author.py` | 518 | `op_catalog`, `_catalog_text`, `_annotate`, `_parse`, `lint_tree`, `_to_document`, `author_design` |
| `mcp_server.py` | 227 | `_safe_name`, `_notify_studio` (the doorbell), `_report`, `list_operations`, `build_design`, `design_part`, `measure_step`, `verify_step`, `design_compressor` |
| `meanline.py` | 237 | the compressor design the MCP tool builds from (`design`, `to_spec`, `build_from_design`) |
| `static/js/chat.js` | - | the chat column: sending, applying the answer, showing warnings (recorded: chat warnings go unread) |
| `studio.py` | - | `/api/chat` (2688) |

Tests for orientation (fast): the author is exercised through `test_api.py`,
`test_offset_method.py`, `test_p1_fixes.py`, `test_tree.py`,
`test_extrude_v1.py`, `test_export_guard.py` (grep `author`); there is no
dedicated MCP test.

Finding classes:
- **Catalogue vs op** - `op_catalog` advertising a key the op refuses, or
  omitting one it needs; `document.op_params` is meant to be the single
  source (8b37426) - check the author reads it and nothing else.
- **The parser** - `_parse` accepting malformed or partial JSON and building
  something other than what the model said; a numeric string kept as a string.
- **Two entries, one guard** - `_to_document` and `build_design` bypassing the
  strict add that `/api/feature/add` enforces (unknown keys refused, health
  gate), so an AI tree lands unchecked.
- **The lint** - `lint_tree` letting through what it is meant to refuse
  (absolute-offset sketches once a body exists), or refusing a legal tree.
- **MCP** - `_safe_name` and path traversal on design names, `build_design`
  overwriting an existing design, the doorbell re-firing on every page load
  (known P1, section 10 - name the line if you find the cause).
- **Chat** - the model's answer applied to the tree without the health gate;
  a missing API key producing a stack trace instead of a sentence; a warning
  shown where the user does not look.
- **Claims** - `measure_step` / `verify_step` reporting a number or verdict
  that `inspector` would not give.

---

## After the review - the fix pass, in the SAME Opus chat

The user pastes this second line once the report is in the chat:
```
Now do the fix pass exactly as REVIEW-QUEUE.md says under "After the review", for the section you just reviewed.
```

1. Load the `textcad-dev` skill; `fusion-parity` too if the module is a
   modeling tool. Read CLAUDE.md's environment facts (two Pythons, detached
   server, hooks).
2. Take the findings in severity order. **Reproduce each by measurement
   first**: a probe under `probes/` or a test that shows the wrong number,
   the wrong body, the lost edit. A finding that does not reproduce is
   REJECTED with a one-line reason; it is not fixed "just in case".
3. For each confirmed finding: a test that is RED before the fix, then the
   smallest fix. Never `/code-review --fix`.
4. Run the section's fast test files plus `tests/test_launch_rules.py`. Run an
   op's gauntlet file only when the fix touches that op. `python -m ruff check .`
   on the changed Python; the edit hook runs `node --check` on JS. If anything
   under `static/` changed, bump `main.js?v=` (and `studio.css?v=` for CSS) in
   `static/index.html` after reading the current value.
5. One commit: `<Module> review fixes: N of M findings fixed, K rejected (<why, in a few words>); T new tests` with the project author flags, then push to
   the private backup. Record the line delta in the message.
6. If the backend changed, restart the user's server detached per CLAUDE.md
   and let it open the browser.
7. Update THIS file: the status board row (`reviewed <hash>, fixed <hash>,
   N/M`), and a "Done log" entry below with the rejected findings and their
   reasons. Add a LAUNCH-PLAN.md section 10 row only for a finding that was
   deferred rather than fixed or rejected.
8. A second review round happens only if a P0 was fixed: rewrite
   `REVIEW-BRIEF.md` for the fix commit and tell the user to run the ship-check
   skill's fixed line at `medium`. Otherwise tell the user in one line: next
   is their five-step checklist for this module, then the next section in a
   fresh Opus chat.

Token rules apply (LAUNCH-PLAN section 9): targeted test files, no gauntlet
sweeps, no screenshot loops, browser tests only if a fix changed a journey.

## Done log

### Section 1 - Sketcher (reviewed and fixed 2026-09-09, commit 556a611)

9 findings, all reproduced by measurement first
(`probes/sketcher_review_probe.py`). **9 fixed, 1 rejected**, and 2 of the
review's 5 "could not judge without running the app" items turned out to be
real and were fixed with them.

| # | P | What it was | Fix |
|---|---|---|---|
| F1 | P0 | a hole drawn BEFORE its outer became solid material - `create()` forced entity 0 back to `add`. Measured 2827.43 mm2 where the editor drew a 2513.27 washer | the flip is gone; modes go up exactly as drawn |
| F2 | P0 | even-odd modes were right but the entities were never reordered; `_compose` is sequential, so an island drawn last was cut away. Measured 1570.80 vs 1884.96 mm2 | `_compose` composes OUTERS BEFORE THE HOLES INSIDE THEM, by measured containment (`_nesting_depth`) |
| F3 | P1 | an interactive Scale survived Cancel Sketch and owned the next sketch's keyboard; Escape wrote the DISCARDED entities into it | `scaleDrag` cleared in `exitMode()` and `resetEditor()` |
| F4 | P1 | `_path_face` had no validation: `Standard_TypeMismatch('TopoDS::Face')`, `StdFail_NotDone` and "Face can only be created with closed wires" reached the tree verbatim | `_validate_path` names the four real mistakes; a catch-all around `make_face()` keeps any other OCCT text out |
| F5 | P2 | Modify -> Offset grew a slot's height only, and at Offset 12 Finish blamed the slot | both dimensions grow, floored at `height + 0.5` |
| F6 | P3 | `rotation` on a polygon/path was built but never drawn: outline, handles, hit-test and snap read the raw points while `entSamplePts` rotated | one `entToSketch` helper; `applyResize` writes back through the local frame it already computes |
| F7 | P3 | the tree re-derived corner-vs-arc and got a CLOSED path wrong, promising a tangent round `set_arc_radius` does not give (R1) | new `POST /api/sketch/path-arcs` serves `path_arcs`, the same function the edit acts on; the row says "curve" until it answers |
| F8 | P3 | a bore's parameter seam was offered as a model "corner" and its antipode as a "midpoint" | closed edges give their centre only; arcs keep their real ends |
| F9 | P3 | reopening a path/polygon-only sketch framed the world origin | `entSamplePts`, not `[e.x, e.y]` |

**Promoted from "could not judge" to fixed:**

- the 8-sample `containedIn` walk really can call a mostly-nested shape (a
  traced outline with a spike) contained and turn it into a hole - it now
  tests every point, which is free at 48-96 points on an edit;
- an OCCT error really can escape `/api/sketch/trim/pieces` (it builds every
  entity's face and catches only `KeyError`/`ValueError`) - and it is the
  LIKELY case, since a crossing path is what a user reaches for Trim to
  clean up. F4's `ValueError` closes it; locked in by a test.

**Settled by reading, no change needed:**

- `commitScale()`'s stale readout is NOT hidden by `placeFloat`'s pane clamp -
  it goes to the chat via `bus.emit('msg', 'bot', ...)`, so it was plainly
  visible. Folded into F3.
- `sketch_on_face`'s docstring contradicted `face_sketch_plane` on the offset
  SIGN: it still promised "offset < 0 INTO the material ... on every face",
  a rule abandoned on 2026-08-27 because it silently mirrored the esp32
  cavity. Docstring corrected to the rule the code follows.

**REJECTED (1):**

- *the un-awaited `releaseIsolation()` in `exitMode()` leaving the viewport
  rolled back*. `postJSON` never rejects - it catches a dead server and
  returns `{error}` (`api.js:124`) - and in the edit path the release is the
  LAST request in flight, so its response is what sets the viewport. The only
  overlap needs a click during `cancelSketch`, which is the already-tracked
  "two requests reaching the kernel at once" item.

**Not done, deliberately:** a full circle still offers no QUADRANT snaps.
Fusion has them; adding one would need a new snap kind in the frontend's
rank table and dot rendering, which is a feature, not this review's business.

### Section 1 again - the FIX PASS re-reviewed (2026-09-09, commit 6e2cae9)

A P0 fix earns a second review; this one found a P0 of its own. 8 findings,
8 fixed, all measured against `designs/` before and after.

| # | P | What it was | Fix |
|---|---|---|---|
| G1 | P0 | F2's reorder iterated in SORTED order but still refused a subtraction as the first entity of THAT order. `esp32-remote/logo_1_sketch` built at 4.37 mm2 before the fix pass and raised `ValueError` after it - red sketch, red everything downstream, and `-m library` cannot collect so nothing caught it | a sort by DEPTH is not an ordering constraint. `_compose_order`: a stable topological order over measured containment - an outer before what is nested inside it, drawing order everywhere else. A leading subtraction (it may CONTAIN an add) waits for the first add |
| G2 | P1 | F4's catch-all wrapped only `make_face()`, so `StdFail_NotDone: GC_MakeArcOfCircle` came straight out of `ThreePointArc` - kernel text in the tree, 500 from `/api/sketch/trim/pieces`. The very failure F4 existed to close | translated per segment, naming the arc. No threshold of ours: OCCT accepts a via 1e-6 off a 100 mm chord (probed), so the kernel judges and we translate |
| G3 | P1 | `_nesting_depth`'s bbox skip NEVER fired - `BoundBox.is_inside` is `not(STRICTLY inside)` and a sketch box is flat in Z, so always True. Every pair ran a full boolean: +4128 ms per rebuild of `rocky-balboa/field_sketch` | `_box_within`, X and Y only. 4128 -> 538 ms; `rocky-keychain/words_sketch` 1513 ms -> out of the top six |
| G4 | P1 | `entSamplePts` read `e.start[0]` / `e.points` unguarded; a path with no `start` is legal on the backend, so Edit on one threw `TypeError` in an unawaited handler before `enterMode()` - sketch mode silently never opened | `|| []` / `|| [0, 0]` like every sibling reader |
| G5 | P3 | `arcKindsSeen` was keyed before the await, so one failed fetch pinned a row at "curve N R"; both label maps were keyed by bare feature id (unique only within a document) and never shrank | key stored after the answer arrives; both maps dropped when the design on screen changes |
| G6 | P3 | `askJSON` ignored `r.ok`, so a 422 body read as a successful "no arcs" | `!r.ok` returns an `error`; still silent to the user, never to the caller |
| G7 | P3 | a closed ELLIPSE edge (an elliptical pocket's floor rim) got no snap point at all - F8 suppressed the seam and the centre was added only under `if circle` | `arc_center` for ellipses too (probed: the true centre, where `center()` answers a sampled centroid and lies). A closed BSPLINE has no defined centre and is still left alone |

**Accepted, not a defect:** `esp32-remote/logo_0_sketch` 277.16 -> 280.46 mm2.
Entity 8 sits inside the subtract 9, so the island survives - F2's rule
working as designed, and the only area in the library that changes.

### Section 1, round three - the DEFERRAL re-reviewed (2026-09-09, commit 5f65a7a)

The second round's P0 fix earned a third review, and it found a P0 of its own -
in the same few lines, for the third time. 8 findings, 8 fixed, 0 rejected,
every one reproduced first in `probes/sketcher_review3_probe.py`.

The lesson worth keeping: **the two mechanisms cancelled each other.**
`_compose_order` hoists a subtraction in FRONT of the add nested inside it
*precisely so that add survives as an island*. The deferral then held that
subtraction back to just after the first add and subtracted it from exactly
the add the order existed to save. Each half was defensible alone; together
they restored the drawing-order answer the whole reorder was built to replace,
and the round-two goal that produced them ("it cuts exactly what it cut
before") was itself the bug - preserving a live design's number was treated as
the target when the number was wrong.

**Ground truth, settled by reading the renderer** (worth not re-deriving): the
sketcher paints every entity on its own - `add` fills GREEN, `subtract` fills
RED (`sketcher.js:1611`). There is NO even-odd canvas fill; `assignModes()`
only assigns the modes, and only when the user edits. So "what the editor
shows" means: a green region is material and must be in the built profile.

| # | P | What it was | Fix |
|---|---|---|---|
| H1 | P0 | the deferral, above. `[r20 subtract, r10 add]` built area **0.0** and reported `ok` - a successful empty sketch, banned failure 2. Three identical bars inside one subtract blob built 144.0 instead of 216.0, the FIRST bar silently missing and the other two there. `esp32-remote/logo_1_sketch` built 4.3671 where the editor paints 7.6656 | a leading subtraction removes NOTHING - nothing is composed yet, so there is nothing to cut - and a note in the feature says so instead of the cut vanishing silently |
| H2 | P1 | a profile cut away to nothing reached `_as_sketch` as an empty Compound; `pl * <empty>` is a plain `list`, so the tree showed `AttributeError: 'list' object has no attribute 'faces'`. The right message (`"sketch is empty"`, document.py:868) was unreachable | `_area_of` after every step: empty is not failed, so the next add starts the profile again, and a sketch that ENDS empty says "the cuts removed everything that was drawn" |
| H3 | P2 | a cut applied to an already-empty result raised build123d's `ValueError: Dimensions of objects to subtract from are inconsistent` verbatim (rule 5) | same fix as H2 - the kernel is never handed an empty shape to subtract from |
| H4 | P2 | `tree.js loadArcKinds` never re-checked the document after its `await`: a reply that landed after a design switch repainted the NEW design's rows, because the selector matches feature id alone and ids like `sketch1` are unique only within one document. A free curve got a `corner` label and the tangency promise the backend will not keep | the design is captured before the await and compared after |
| H5 | P2 | `sketcher.js scaleEntity` still read `e.start[0]` and iterated `e.segments` unguarded - round two's `entSamplePts` fix made that path reachable, so Scale on a start-less path threw TypeError mid-drag, in an unawaited handler | the same `\|\| []` / `\|\| [0, 0]` guards as its siblings |
| H6 | P2 | a `path` entity with no `start` was built from the origin, while `outlinePts`, `hitTest`, `entityHandles` and `collectSnapPoints` all guard `&& e.start` and drew NOTHING - invisible, unclickable, and saved anyway | refused, in a sentence. Defaulting is inventing geometry nobody drew; the AI author's own schema (author.py:333) documents `start` as part of a path |
| H7 | P3 | `pathArcRows` calls `loadArcKinds` once per path entity, and round two moved the dedupe key after the await, so N path entities fired N identical POSTs per render, each carrying the whole entity list | an in-flight key, dropped again the moment the answer or the failure lands - dedupe restored without pinning a row on a failed fetch |
| H8 | P3 | an arc segment with no `via` at all reported "the middle point lies on the straight line between its ends" - a sentence about a point that is not there. `_validate_path` cannot catch it either: it guards with `s.get("via")` | `via` is read OUTSIDE the translator's try, and a missing one is named |

**Nothing rejected.** All eight reproduced.

**Four tests from round two asserted the defective contract** and were
corrected in place, each recording why in its docstring - they are the reason
the P0 survived a review:

- `LOGO_1_AREA = 2 * math.pi * 9  # the two clear adds; the nested one is eaten`
  wrote the eaten island down as the expected area;
- `test_the_deferred_subtraction_still_subtracts` asserted the island was gone
  (now `test_the_leading_subtraction_keeps_the_island_it_contains`);
- `test_a_path_entity_without_a_start_is_legal` asserted the opposite of H6;
- two message regexes ("first entity cannot be a subtraction") named a mistake
  that is no longer a mistake.

**The library, measured:** exactly one sketch's arithmetic moves -
`esp32-remote/logo_1_sketch` 4.3671 -> 7.6656 - and all six of that design's
`logo_*` features are SUPPRESSED, so no built geometry in `designs/` changes
at all. (Round two's accepted `logo_0_sketch` 277.16 -> 280.46 was suppressed
too, so that never reached the part either.) All 81 features rebuild `ok`.
1239 fast tests pass, ruff and eslint at zero, ui v177.
