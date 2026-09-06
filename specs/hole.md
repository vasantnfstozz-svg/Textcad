# Hole — tool spec (P4, LAUNCH-PLAN.md §8 step 1)

> **Status: built 2026-09-06 (5336c82), code-reviewed the same day and all 25
> findings fixed (0c49c42, ui v157 — see "What the code review changed"
> below); LAUNCH-PLAN §7 P4 stamped. The five-step checklist at the end is the
> user's to run.** The fourth tool on the
> framework (`tool.js`), the first whose op EATS its body (the result is the
> body with the hole — no Join / Cut row) and the first whose input is a POINT
> on a face, so the framework grew two things every later point tool (Shell's
> open face, Pattern's seed) inherits: the face pick carries where it was
> clicked, and a session can re-pick its input while the panel is open.
>
> Decisions made here without the user (say so if any is wrong): the diameter
> is typed, not dragged (Fusion has a diameter handle — §10); the hole moves by
> clicking another point on the face, not by dragging its centre; a blind hole
> has a flat bottom (Fusion's default drill point is a 118° tip — §10);
> extents are Distance and All ("To" a face — §10); no tapped / clearance
> types. Autodesk's Hole reference (Placement · Extents · Hole Type · Drill
> Point · Diameter / Depth · counterbore ⌀ / depth · countersink ⌀ / angle) is
> the vocabulary.

## What you click, what you see

Click a flat face of a body where the hole should go, press **Hole**: a gold
circle sits on the face exactly where you clicked, an arrow points from it
INTO the material, the Depth box reads **0** — nothing has been cut. Drag the
arrow in and the box follows; release, and the hole is there after one
verified rebuild. Type an exact depth, or tick **Through all**, choose
Counterbore or Countersink and fill the seat's size, press **OK**. One `hole1`
row appears in the tree under the body; double-click it and the circle, the
arrow and the boxes come back at the stored values. Click another point on
the face while the panel is open and the hole moves there.

## Inputs (rules 1, 2)

* **A flat face of ONE body and a point on it.** Select-then-command: the face
  already picked when you press Hole is the face, and the point is where you
  clicked it (the viewport pick now carries `point`; the plan turns it into the
  face's own coordinates — R1). With nothing picked the tool waits for a click
  on a face (command-then-select); a sketch profile is refused with a sentence
  (Fusion's "From Sketch" placement is not this tool, yet). A curved face is
  refused with the usual sentence; tilted flat faces are fine.
* **The point is stored as `at: [x, y]` in the face's own frame**
  (`face_profile_plane`, the frame P3b's edge axes use) — on the axis-aligned
  faces of a box exactly the x / y a sketch drawn on that face uses (probed:
  (5, 7, 10) on a top face → (5, 7); (5, 7, −10) on the bottom → (5, 7)). It
  rides the face when an upstream dimension moves it; the face itself is
  resolved by geometry at every rebuild (`face_center` + `face_normal`, or by
  NAME — `face: "top"` — on the AI path). The centre must lie ON the face; the
  hole may run out over an edge (a notch), the centre may not.
* **The op eats its body.** `hole` is a modifier like `fillet`: input the body,
  output the body with the hole. No combiner, no `_cut` chip in the tree. One
  feature per hole (Fusion's single-hole placement); a bolt pattern is a
  Pattern of one hole once Pattern lands, and until then several holes.

## The handle and the panel (rules 3, 4, 5)

* **Arrow** at the hole's centre, pointing INTO the material (the plan's
  `axis` = minus the outward normal), the same arrow Extrude and Fillet use;
  dragging it sets the depth, negative clamps to 0 (a depth has no sign).
  **Through all** takes the arrow away (nothing to drag) and brings it back
  when unticked. The gold **circle** is the plan's `frame` at the hole's
  centre scaled to the diameter, so it follows the Diameter box as you type
  and it is drawn from the server's frame, not from JS geometry.
* **No ghost**: the real hole appears on release (one verified rebuild); a cut
  is drawn only by the kernel.
* **Panel** `holeDialog`, ids `ho…`: Face (locked) · Type: Simple /
  Counterbore / Countersink · Diameter (mm), starts at the last hole's size
  (6 mm the first time — a size is not an amount, so it is not a lie) · Depth
  (mm), starts at **0** · Through all ☐ · Counterbore ⌀ + depth, or
  Countersink ⌀ + angle (90°), shown for their type only · Cancel / OK. The
  Operation row is hidden: the op has no combiner.
* **Edit**: tree ✎ or double-click reopens with the circle and arrow at the
  stored point and depth; Cancel restores verbatim — inherited.
* **Move**: while the panel is open, a click on a flat face of the same body
  moves the hole there (the framework's `repick`: the plan is asked again for
  the new point and the feature follows). Another body's face is refused with a
  sentence.
* **Framework extensions this tool forces** (§8 step 5): `eats` (a face tool
  whose op consumes its body: Operation stays "new", no Target); a face-only
  tool (`ops: {face}` without a profile op — the picker refuses sketches);
  `repick` (a session-long face pick); the face selection carries `point`.
  Extrude / Revolve get the point for free (unused).

## Failures speak (rule 7) — the same sentences on the AI / MCP path

| Situation | What is said |
|---|---|
| Depth 0 on OK | "Nothing drilled — the depth was 0. Open Hole again, then drag the arrow or type a depth (or tick Through all) before OK." |
| Diameter 0 / depth 0 (not through) / unknown type | `hole: diameter must be positive (got 0) — type a diameter` · `hole: depth must be positive (got 0) — drag the arrow or type a depth, or tick Through all` · `hole: kind must be one of […]` |
| Counterbore seat not wider / not shallower than the hole | `hole: the counterbore diameter (5 mm) must be larger than the hole diameter (6 mm)` · `hole: the counterbore depth (9 mm) must be less than the hole depth (8 mm) — or tick Through all` |
| Countersink seat not wider, angle out of range, cone deeper than the hole | `hole: the countersink diameter …` · `hole: the countersink angle must be between 0° and 180° (got 200) — 90° is the usual seat` · `hole: the countersink (⌀20 at 90°) is 7.00 mm deep and reaches past the hole's depth (2 mm) — deepen the hole or shrink the countersink` |
| The point is not on the face (a stored point after the face shrank, an AI coordinate) | `hole: the point (40, 0) is not on the face — the hole's centre must lie on it; click a point on the face` (the feature fails, the body stays whole) |
| The centre sits inside an existing hole (the centre of an annular face is such a point — probed: the cutter there removes 0 mm³ and the kernel calls it a success) | caught as a point off the face: `hole: the point (0, 0) is not on the face — …`. Behind it the backstop: `hole: nothing was cut — the ⌀6 hole at (0, 0) finds no material under the face; move it onto solid material` (an ABSOLUTE floor: a cutter that misses leaves the volume unchanged to the last bit, while a real ⌀1 hole in a 200 × 100 × 50 block removes 0.79 mm³ — a floor relative to the body refused it) |
| The result is an open shell (a ⌀60 hole on a 50 mm face swallows it — probed: OCCT returns it as a "success") | `hole: the ⌀60 hole at (0, 0) leaves a broken solid (an open shell, not watertight) — it is wider than the face allows or runs out through an edge; use a smaller diameter or move it inward`; the framework puts back the last value that built |
| A blind depth past the material under the point | allowed (it comes out the other side, as in Fusion); the chat says once that the material there is N mm and Through all says it on purpose (`limits.material`, kernel-measured — asked for the first time a blind depth needs it, never for a through hole) |
| A seat kind chosen, or Through all unticked, before the numbers are there | nothing is applied and nothing is reverted: the tool says once what it waits for (`Counterbore: type a seat ⌀ wider than 6 mm, and a seat depth.` · `The hole is unchanged until it has a depth — drag the arrow or type one (or tick Through all).`). Choosing Counterbore / Countersink SEEDS a seat that fits the hole, so the usual case builds at once |
| A through hole that cuts the part in two | the framework's pieces warning; the remedy: "the hole cuts the part in two — move it, or make it smaller." |
| Curved face | `the picked face is CYLINDER (curved) — a hole starts on a FLAT face; tilted flat faces are fine` |
| Kernel exception | `hole: the kernel could not cut the ⌀6 hole at (5, 5) here — move the hole or change its size` (the kernel's class name stays out of the sentence) |

## Acceptance (LAUNCH-PLAN P4)

* `static/js/hole.js` in **100–150 lines**, **no geometry maths**: the circle
  and the arrow come from the plan's `frame`, `origin`, `axis`; `at` and the
  stored face from the plan. (193 after the review: the seeded seat sizes, the
  half-made states the tool holds back, and the lazily-asked material — the
  geometry is still all the plan's.)
* Backend: `sketch.hole` (the op, registered as a MODIFIER), `sketch.hole_frame`
  shared by op and planner, `sketch.material_depth` (the plan's `limits`),
  `toolplan.plan_hole`. `probes/hole_probe.py` records the kernel facts:
  build123d's own `Hole` objects are double-length builder-mode tools (not
  used), a hand-built cutter cuts exact volumes on every corpus face, a hole
  wider than its face comes back an open shell, `Face.is_inside` and
  `Edge ∩ Solid` answer "on the face" and "how thick".
* **Tests**: `tests/test_hole_tool.py` (op guards, volumes against formulas,
  the bottom / tilted face, riding an upstream change, the catalogue; plan
  tests: point → origin / axis / at / marker frame / material) and
  `tests/test_hole_gauntlet.py` (every corpus body, every flat face, three
  types, blind + through, at the centre and toward a vertex — a healthy solid
  or a sentence, never a raw kernel error; every face of the box must build).
* **6 browser journeys**: click the face + press Hole + type + OK; drag the
  arrow then Through all; Counterbore, then edit-and-cancel restores; a second
  click on the face moves the hole; a seat kind chosen on a BUILT hole stays
  chosen; Through all unticked with no depth waits instead of re-ticking.

## What the code review changed (2026-09-06, 25 findings)

The review of the P4 commit (`e4a9d05..5336c82`) is in the git history; the
fixes that changed BEHAVIOUR, so this spec stays true:

* **A click while editing MOVES the hole.** The plan overwrote the request with
  the stored point, so the re-pick the tool arms in edit mode did nothing. The
  request is the answer now; the stored values are the fallback.
* **A hole that never said `at` opens where it cuts.** The plan defaulted to the
  face centre while the op defaults to (0, 0), so opening an AI-authored hole
  drew the marker elsewhere and OK moved the cut. One default, `sketch.HOLE_AT`.
* **The face is stored in ONE form** — a name, or a pick's centre + normal. A
  name beat a centre in the op, so an authored hole could never be moved.
* **Seat kinds and Through all no longer undo themselves** (see the table).
* **A small hole in a big part is a hole**, not "nothing was cut".
* **A through hole may have a seat**: the two "shallower than the hole"
  comparisons are for a blind one; the reach is `sketch.through_reach` — the
  shared `THROUGH_MM` (2 m) and past the far side of anything bigger, so
  "through" can never quietly become blind on a body deeper than the constant.
* **Measure can drive a hole's diameter** (and its counterbore / countersink ⌀):
  the bore has no sketch circle behind it, and measure said so in words that
  were not true.
* **The marker frame is right-handed**, the drilling direction stays in `axis`.
* **The plan is cheaper**: no dead fields, no bounding box, and the material
  under the point is measured only when the tool asks (`measure_material`).
* **The legacy `with_center_hole` button is "Centre bore"** — two buttons were
  called Hole.
* R10: line delta recorded in the commit; `sketch_on_face`'s face branch and
  `toolplan._pick_face` collapse onto one `sketch.pick_face`.

## The user's five-step checklist (R9)

1. Build a 60 × 40 × 12 box. Click its top face somewhere off-centre, press
   **Hole**: a gold circle sits where you clicked, an arrow points down into
   the box, Depth reads 0, Diameter 6, the box is unchanged.
2. Drag the arrow into the box to about 5: the box follows; release and a
   ⌀6 hole 5 deep is there. Type 8: it deepens to exactly 8. Type 20: the
   chat says the material there is 12 mm and the hole comes out underneath.
3. Tick **Through all**: the arrow goes, the hole runs through. Untick it: the
   arrow is back at 20. Click another spot on the top face: the hole moves
   there. OK: one `hole1` in the tree, no cut chip.
4. Press Hole with nothing selected: the hint asks for a face; click a sketch
   or a curved face and the chat says why not; click the box's side face,
   choose **Counterbore**, ⌀6, seat ⌀10 × 2 deep, depth 15: a counterbored
   hole in the side. Double-click `hole2`: the circle and arrow come back at
   the stored values; change the diameter to 8 (the seat follows the type's
   rule), then Cancel: the hole is ⌀6 again.
5. Open `hole1` and type a diameter of 60: the chat says the hole leaves a
   broken solid, and the body keeps the diameter that did build. Choose
   Countersink with ⌀12 at 90° on a depth of 2: the chat says the countersink
   reaches past the hole's depth. Esc closes the panel — once.
