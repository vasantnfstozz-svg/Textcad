# Offset Plane — Fusion's Construct > Offset Plane (the `offset_plane` feature)

Built 2026-09-22 on Fable, replacing the sketch-plane offset of 2026-09-21
(`ee102b1` Create Sketch's Offset step, `bc136be` the SKETCH tab's Move Plane).
The user tried that design and found it the wrong tool: *"when I draw a circle
inside sketch tab, and I moved the plane, the circle also moves alongside with
the plane"* — that was Fusion's Redefine Sketch Plane, a repair tool. What they
wanted is Fusion's Offset Plane: *"offset plane only, I can just move the plane
and draw sketch whatever I want."*

## What the user sees

1. **Create tab → Construct → Offset Plane.** The viewport asks for a plane:
   an origin plane quad or a flat face of a body (the same pick Create Sketch
   uses). An existing offset plane is refused with a sentence — the op measures
   from an origin plane or a face.
2. The plane is drawn where it will land (a translucent quad; for a face, also
   that face's outline), with **one arrow** along its normal and an **Offset
   Plane** panel: *From the XY plane* / *From a face of "b"*, an **Offset** box
   (display units), and for a face *negative = into the material* (or
   positive — measured per face, `into_sign`).
3. Drag the arrow or type. Ghost, arrow and box stay in step.
4. **OK / Enter** adds an `offset_plane` feature (`plane1`, `plane2`, …): a
   tree row and an orange translucent quad in the viewport that stays on
   screen, in design AND sketch mode. **Esc / Cancel** adds nothing.
5. The new plane is the **selection**. **Create Sketch right after it opens
   on the plane** with no second pick (select-then-command, fusion-parity
   rule 2); the selection is used up by that. Any later Create Sketch can
   click the quad (outside the body's silhouette, like the origin quads — a
   body face under the cursor wins).
6. Finish Sketch stores `plane: "plane1"` on the sketch. The plane's **✎**
   (or a double-click on its row) reopens the step at its offset; OK writes the
   new offset and **every sketch on the plane moves with it**, with everything
   built from those sketches. The tree also edits `offset` as a plain number.
7. Deleting the plane takes the sketches on it along (the delete plan lists
   them), exactly as a sweep's path or a pattern's seed.

The sketch's own `offset` parameter still exists for the AI author and every
saved design (310 sketch offsets in `designs/`, untouched), and the offset
method (fusion-parity rule 11: `sketch_on_face` + `offset`) is unchanged.
There is no longer any UI that sets a sketch's offset directly.

## The feature

`offset_plane` — neither a creator nor a modifier: a third kind, `plane`.

| params | inputs | result |
|---|---|---|
| `plane: "XY"\|"XZ"\|"YZ"`, `offset` | `[]` | `sketch.sketch_plane(plane, 0).offset(offset)` |
| `face: "top"` or `face_center` / `face_normal` / `face_area`, `offset` | `[body]` | `face_sketch_plane(pick_face(...)).offset(offset)` |

The result is a build123d `Plane` (`sketch.is_plane`). The input body is a
**reference**, never consumed (`FACE_REFERENCE_OPS`), so it stays on screen. A
sketch names the plane in `plane` (`REF_PARAMS["sketch"] = ("plane",)`, the
principal names filtered out): the reference signs the sketch's cache entry,
rename follows it, delete cascades. `Document.plane_of(name)` is the ONE home
for "which plane is this": `make_sketch` (through `_plane`), `toolplan.plan_sketch`
and the doc JSON's `plane_frame` all read it. A plane off another plane, a
plane off a sketch, a plane fed to Extrude or Join, a sketch naming a
non-plane — each is a sentence, never kernel wording (`tests/test_offset_plane.py`).

## Where every fact comes from (LAUNCH-PLAN R1)

| fact | source |
|---|---|
| the base frame at offset 0 while the step is open | `POST /api/tool/plan {tool: "sketch", plane}` (plane) · `POST /api/face-outline` (face) |
| which sign goes INTO the material | `face-outline.into_sign` — measured, `-sign(outward · frame z)` |
| where the plane is drawn once it is a feature | the feature's `plane_frame` in `/api/doc` (`toolplan._frame` of the built Plane); null for a plane that did not build |
| the grid a sketch on the plane opens on | `POST /api/tool/plan {tool: "sketch", plane: "plane1", offset}` → `Document.plane_of` |
| the Join / Cut target of a sketch on a face-based plane | `toolplan._default_target` walks sketch → plane → its body, like a face sketch |

## Files

- `sketch.py` — `offset_plane`, `is_plane`, `PLANE_PRODUCERS`, `PRINCIPAL_PLANES`;
  `make_sketch(_plane=)`; `offset_plane` in `FACE_REFERENCE_OPS`.
- `document.py` — `KNOWN_OPS`, `op_params`, `numeric_params`, `_kind_of`
  ("plane"), `REF_PARAMS["sketch"]`, `param_refs` filter, `_plane_part`,
  `plane_of`, the `_eval` branch, the rebuild branch, the plane refusals in
  `_check_modifier_input` / `_check_combiner_inputs`, and the three
  solid-only filters (`leaf_solid_ids`, `_result_feature`, the blockers).
- `toolplan.py` — `plan_sketch` through `plane_of`; `_default_target`.
- `studio.py` — `plane_frame` on every feature of `/api/doc`.
- `provenance.py` — a plane has no edges; not a body for `feature_faces`.
- `author.py` — the catalog lists the op with kind `plane`.
- `static/js/sketchplane.js` — the tool: `openOffsetPlane` (ribbon),
  `stageOffsetPlane` (the pick landed), `editOffsetPlane` (tree ✎),
  `offsetPlaneStage` (tests). Takes the modal lock as `Offset Plane`.
- `static/js/viewport.js` — `drawConstructionPlanes` on `doc-updated` and on
  every model load (sized with the model), HIDDEN except while a plane pick
  waits (user, 2026-09-24: not in the background after the sketch; the tree
  row is the plane); `pickableQuads` = origin quads + construction planes;
  the overlay glows a selected plane's quad;
  `constructionPlaneInfo` / `planeQuadsAt` for tests.
- `static/js/ribbon.js` — Create tab `Construct` group; `startSketch` takes a
  selected plane row, else the pick opens the sketch directly (the Offset
  step is gone); the SKETCH tab's `Plane` group is gone.
- `static/js/sketcher.js` — `openSketchEditor(planeId)` snaps through the
  frame; `currentSketchPlane` / `setSketchPlaneOffset` / `pauseSketchInput`
  deleted. `static/js/sketch3d.js` — `setSketchPointerPaused` deleted.
- `static/js/tree.js` — ✎ / double-click on a plane row; the `select-feature`
  bus event (a tool makes its new feature the selection through `selectFeature`).
- `static/index.html` — the `planeDialog` panel re-titled; `main.js?v=232`.

## Tests

- `tests/test_offset_plane.py` (14): heights measured on the built sketch and
  extrude, a face plane riding a thickness change, edit-follows, the plan and
  the build sharing one plane, six refusals, rename / reference, the formula
  offset, the catalog and `/api/doc`.
- `tests/e2e/test_offset_plane.py` (8): the step from XY and from a face,
  Create Sketch right after, clicking the quad during a later Create Sketch,
  ✎ edit moving the plane and its sketches, a formula offset surviving an
  untouched OK (mm and inches) and being replaced by a real move, Esc, and the
  ribbon (Offset Plane present, Move Plane gone).
- `tests/test_sketch_plane_offset.py` keeps the `into_sign` and frame tests.

## Not built (plan §10)

- A plane off another plane, an angled plane, a midplane, a plane through
  three points: Fusion's other Construct entries. The feature kind is in place;
  each is an op variant plus a pick.
- Hiding a plane (Fusion's eye icon). Strike-out (✕) works today.
