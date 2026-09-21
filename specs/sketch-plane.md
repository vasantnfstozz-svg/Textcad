# Sketch plane offset — "move the sketch plane" (Create Sketch's Offset step)

Built 2026-09-21 on Fable, from the user's report: *"if I want to draw shapes
on top of the body or sketch I need to move the sketch plane, which is not
available in the tool right now, because when I am drawing or using loft I
cannot draw any shapes on top of them."* Not a new operation: the sketch
feature always carried `offset` (the AI uses it every day); the UI never let a
person set it, and a face sketch made by hand did not even send the key.

## What the user sees

1. **Create Sketch**, hover an origin plane or a flat face, click it — as before.
2. The sketch does **not** open yet. The picked plane is drawn where the
   sketch will open (a translucent quad; for a face, also that face's
   outline), with **one arrow** along its normal and a **Sketch plane** panel:
   *On the XY plane* / *On a face of "b"*, an **Offset** box (display units),
   and for a face the sentence *negative = into the material* (or positive).
3. Drag the arrow or type. Ghost, arrow and box stay in step.
4. **OK / Enter** opens sketch mode on the shifted plane. **Esc / Cancel** goes
   back with nothing drawn. Enter with 0 is exactly the old flow.
5. Finish Sketch stores `offset` on the feature (`sketch` and
   `sketch_on_face` alike). The tree shows it as an ordinary number row, so
   it can be changed later and everything downstream rebuilds.

The pick panel's own "✎ Sketch on this face" button still opens at 0 — it is
the shortcut; Create Sketch is the way with the offset.

### Move Plane — inside an open sketch (second session, same day)

The user's follow-up: *"when I draw some shapes in the sketch tab and then
want to move the plane in the same sketch, how can I do that?"* The SKETCH
tab has a **Plane → Move Plane** button. It opens the same step over the OPEN
sketch, starting at its current offset (header *Move sketch plane*); OK
re-planes the sketch: the frame is fetched from the server at the new offset,
the 3D plane is rebuilt under the SAME entities (they are plane-local, so they
ride along), the model snaps are fetched again. Finish stores the new offset
— also when the sketch was reopened from the tree (the face-sketch edit path
now resends `offset`). While the step is open the sketch takes no pointer
input (`sketch3d.setSketchPointerPaused`), because the arrow's grab is a
pointerdown on the same canvas and would otherwise also drop a point. Leaving
sketch mode closes the step. A sketch authored by NAME (`face: "top"`) carries
that name into the lookup — it has no picked centre.

## Why an offset on the sketch and not a construction plane

Fusion makes an **Offset Plane** feature and sketches on it. Here the number
already lives on the sketch, the server already builds and plans with it, and
all 50 saved designs are untouched. The tree stays one row shorter. What this
cannot do is a **tilted** plane — a real construction-plane feature can be
added later without undoing any of this.

## Where every fact comes from (LAUNCH-PLAN R1)

| fact | source |
|---|---|
| the plane's frame at offset 0 (origin, x, y, z) | `POST /api/tool/plan {tool: "sketch", plane}` (plane) · `POST /api/face-outline` (face) |
| which sign of the offset goes INTO the material | `face-outline.into_sign` — **measured** as `-sign(outward · frame z)`. The frame is canonical (`face_sketch_plane`), so it is NOT one sign per axis pair the way `sketch_on_face`'s docstring says: on a **+y** face the frame z points −Y and **positive** goes in. Locked by `tests/test_sketch_plane_offset.py` on all six faces. |
| where the ghost sits while dragging | the frame's origin + offset × frame z — the same move `Plane.offset` makes on the server |
| the grid the sketch opens on | fetched **again** from the server at the chosen offset (`fetchPlaneFrame(plane, offset)` / `fetchFaceOutline({offset})`) — never the ghost's matrix |

## Files

- `static/js/sketchplane.js` — new, the step (fetch frame → panel + arrow +
  ghost → OK opens the sketch). Takes the modal lock as `Sketch plane`
  (fusion-parity rule 9); Esc in capture phase; lets go on `doc-updated`.
- `static/js/viewport.js` — `beginPlaneGhost / setPlaneGhost / endPlaneGhost`
  (`ghostPart` quad + outline `LineSegments`, frame matrix via
  `Matrix4.makeBasis`, probed in `probes/plane_ghost_matrix_probe.mjs`);
  `planeGhostInfo` on `window.__vp` for tests.
- `static/js/sketcher.js` — `openSketchEditor(plane, offset)`,
  `openSketchOnFace(info, offset)`, `fetchFaceOutline` exported, a new face
  sketch sends `offset`, edit keeps it.
- `static/js/ribbon.js` — Create Sketch's pick goes to `stageSketchPlane`;
  the SKETCH tab's `Plane → Move Plane` calls `moveSketchPlane`.
- `static/js/sketch3d.js` — `setSketchPointerPaused`.
- `static/index.html` — the `planeDialog` panel; `main.js?v=229`.
- `sketch.py` — `face_outline_2d` returns `into_sign`.

## Tests

- `tests/test_sketch_plane_offset.py` — six faces × into_sign (measured by
  moving the frame 3 mm inside the box), frame moves along z, `sketch_on_face`
  places the profile where the frame says, `offset` is an editable parameter
  that rebuilds, two XY sketches at 0 and 20 (the loft case); and two **node**
  tests running the SHIPPED `sketchplane.js` against stubs (plane → typed 20 →
  OK opens at 20 and releases everything; Esc; face carries −3; doc change
  lets go; Move Plane over a face sketch at −2 → −6 re-planes, pauses and
  resumes the sketch's input, closes when the sketch ends).
- `tests/e2e/test_sketch_plane_offset.py` — real browser: typing moves ghost
  and arrow, Enter opens with the grid at z = 20, Finish stores 20; a face
  sketch at −5 with the outline ghost; Esc releases the modal lock; Move Plane
  inside an open sketch keeps the drawn rectangle and stores 15; Move Plane
  while editing a NAMED face sketch stores −4.

## Loose ends, deliberately not built

- (a) No **tilted** planes (a construction-plane feature).
- (b) The arrow is Extrude's shared arrow, so the Section view's arrow goes
  with it and is handed back on close (`retakeSectionHandles`), as tools do.
- (c) Re-opening a sketch (tree ✎) does not show the arrow by itself; the
  offset is changed in the tree row, or with Move Plane once the sketch is open.
- (d) A plane sketch with a nonzero offset once a body exists is exactly what
  the offset method warns against (it hardcodes the base thickness). The AI
  lint (`author.py`) refuses it for authored trees; the UI lets the user do
  it and says nothing — a one-line hint in the panel would be the next step.
