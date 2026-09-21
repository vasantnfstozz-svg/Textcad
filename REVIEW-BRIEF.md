# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — ONE code commit waits: **Sketch plane offset
> `ee102b1`** (range `1c77d9f..ee102b1`, on master, `specs/sketch-plane.md`).
> Built on Fable 2026-09-21 at the user's request ("we need a feature where I
> can move the plane ... when I am drawing or using loft I cannot draw any
> shapes on top of them"), no review yet. Small: one new frontend module, a
> ghost in `viewport.js`, two openers in `sketcher.js` gaining an `offset`
> argument, one new field on `/api/face-outline`. Strike this when it is done.

## Sketch plane offset — `ee102b1`

**What it is.** Create Sketch's pick (an origin plane or a flat face) no longer
opens the sketch at once. It lands in an **Offset step** (`static/js/
sketchplane.js`): the picked plane is drawn where the sketch will open
(translucent quad; for a face also its outline), with ONE arrow along the
plane's normal and an **Offset** box. Drag or type, OK / Enter opens sketch
mode on the shifted plane, Esc / Cancel goes back. The value is the sketch
feature's own `offset` parameter (`sketch` AND `sketch_on_face`), so it shows
in the tree as a number row and rebuilds downstream when edited. Enter with 0
is the old flow. The AI always used `offset`; the UI never exposed it, and a
hand-made face sketch did not even send the key — now it sends `offset: 0`.

**Where the risk is, ranked:**

1. **`into_sign` on `/api/face-outline`** (`sketch.face_outline_2d`):
   `-1 if outward.dot(pl.z_dir) > 0 else 1`. Measured on the six faces of a
   box (`tests/test_sketch_plane_offset.py`, moving the frame 3 mm and reading
   where it lands). Not measured: a face whose outward normal is NOT parallel
   to the canonical frame's z — a tilted flat face (a loft wall, a tapered
   extrude's side). `face_sketch_plane` snaps to a principal plane only within
   some tolerance; past it the frame follows the face and the dot product is
   still well-signed, but the sentence in the panel ("negative = into the
   material") is only true for the component along the frame's z. Also
   `picked.normal_at(picked.center())` on a face with a hole through its
   centre (a ring): `center()` is the centre of mass, which may lie in the
   hole — does `normal_at` still answer for a planar face? Probably (planar
   surface, any point), but a probe would settle it.
2. **The ghost is browser math on the plan's frame** (`viewport.beginPlaneGhost`):
   `Matrix4.makeBasis(x, y, z)` + `setPosition(origin + offset * z)`. Probed
   with a right-handed frame (`probes/plane_ghost_matrix_probe.mjs`). Not
   probed: a LEFT-handed frame — can `face_sketch_plane` ever hand back one
   (x × y ≠ z)? If yes the quad is mirrored, which is invisible for a square
   quad but shows on the face OUTLINE (the L-shaped or off-centre face would
   draw flipped). The sketch itself is unaffected: it reopens its frame from
   the server at the chosen offset.
3. **`openSketchOnFace(faceInfo, offset)` and the bus.** The bus event
   `sketch-on-face` (the pick panel's "✎ Sketch on this face" button and
   `tests/e2e/test_face_sketch_in_viewport.py`) is now wrapped as
   `info => openSketchOnFace(info)` so an extra bus argument can never land in
   `offset`. Check no other caller passed a second positional argument.
4. **Edit path keeps the offset:** `editSketch` sets `skOnFace.offset` from
   `feature.params.offset` and the edit `params` for a face sketch stay
   `{ entities }` (the offset is NOT resent), while a plane sketch's edit
   resends `{ plane, offset, entities }`. Both fine today; the asymmetry is
   worth one look — `sameSketch` compares `offset` only when `next.offset !==
   undefined`, so a face-sketch edit never trips on it.
5. **Modal lock and the shared arrow.** The step sets `S.modalTool = 'Sketch
   plane'` and uses Extrude's arrow slot (`beginExtrudeArrow`), as Shell does;
   `close()` calls `retakeSectionHandles()` as `tool.js releaseModal` does.
   Cases: Section view open, then Create Sketch → pick → Esc — does the
   section's arrow come back? `tool.js endPending()` cancels a plane PICK but
   knows nothing of the STEP; the step holds the lock so `modalGuard` refuses
   other tools first (ribbon buttons are wrapped) — but `tree.js` row actions
   (✎ edit sketch, `editSketch` guards; delete/strike do not) and the chat's
   AI edits are not guarded, hence the `doc-updated` let-go. Undo (Ctrl+Z, if
   bound outside the ribbon) while the step is open: guarded?
6. **Units.** The box uses `setLen` / `mm` (display units). `follow()` rounds
   to 0.1 **mm** before `setLen`, so in inches the box shows a rounded-mm
   value converted; cosmetic.
7. **Author lint.** `author.py` refuses a `sketch` with a nonzero absolute
   offset once a body exists (the offset method). The UI now lets the user
   make exactly that, silently. Deliberate (plan §10 P3 row); a hint would be
   the next step, not a review fix.

**Do not report** (known, decided or recorded):
- No tilted planes / construction-plane feature; no arrow on tree re-edit;
  the pick panel's own button opens at 0 — plan §10 P3 row, `specs/sketch-plane.md`.
- The `sketch_on_face` docstring says "top / +x / +y face offset < 0 INTO";
  for +y that is wrong (frame z points −Y). `into_sign` is the measured truth
  and the six-face test locks it; the docstring is text.
- Line delta: +770 / −19 — a new feature with two test files, not a phase.
- The node tests stub `viewport.js`, `sketcher.js`, `api.js` and run the real
  `tool.js`; the key-listener count subtracts `tool.js`'s own Esc listener.

**Ground rules** (as always): reproduce by measurement or a red test before
fixing; smallest fix; tests with it; commit; restart the user's server if
`sketch.py` / `studio.py` changed; then this file → `Status: NOTHING PENDING`,
a plan §10 row for anything deferred, memory. Never `--fix`.
