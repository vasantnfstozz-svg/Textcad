# Measure & drive — development sheet

> **Status: P0 + P1 + P2 shipped 2026-08-27** (54 new tests, each UI-verified
> in a real browser), plus the first round of user feedback below. P3/P4
> remain. Design agreed with the user 2026-08-27.

## User feedback, round 1 (2026-08-27)

> "i tried to move the box, in piller deomo, i chnages but, still it was not
> moving, and, when i am clicking the sechond face, the selected first fase
> color is vansiheg, it should be like that, also, i can see a and b in the
> tab, but, when iam selecting first face, in top of that, a shoould appers in
> design"

Three faults, and the third explained the first.

1. **Only one pick was ever highlighted.** The pick highlight is a single
   transient object, so clicking B wiped A. Measure now paints its OWN
   persistent overlay: A in cyan, B in amber, both lit until the pair changes.
   While its panel is open it takes the highlight over entirely
   (`setPickHighlightEnabled`) so the two never fight over one face.
2. **A / B badges on the geometry**, riding their faces every frame like the
   dimension label, in the same two colours — so the panel's labels and the
   model are visibly the same two things.
3. **"it was not moving" was a real measurement of the wrong pair.** From any
   one view the two faces that FACE each other are never both visible, so the
   natural two clicks land on two faces pointing the SAME way — the far side of
   the pillar (a 25 mm step), not the 15 mm clearance in front of it. Asking
   for a small number there translates the profile far enough to push it into
   the wall, which changes the topology.

   Three changes came out of that: the step readout now says *"a step, not a
   clearance — orbit and pick the facing wall for the gap"*; a failed
   verification now **reverts** instead of leaving a wrecked part behind with a
   warning nobody reads (`_revert_last`); and every read-only measurement now
   states its reason, because a number with no edit box and no explanation
   reads as a broken tool (rule 7). Two of those were only visible because the
   badges made the wrong selection obvious.

## User feedback, round 2 (2026-08-27)

> "i can measure the distance between two seleted face, but the moving option
> is not working"

Reproduced on the first try: the pair was the two OPPOSITE WALLS of one box.
Both ends of the tape measure ride the SAME rectangle entity, so the move path
translated the whole box sideways — the width stayed 10, the endpoint's own
verification failed, the edit reverted, and the tool read as broken. Moving can
never change a distance whose two ends belong to one entity.

But that distance IS a driven dimension: opposite walls of a rectangle are
exactly its `w` (or `h`). So `resolve_pair_driver` now runs before the move
path: same feature + same entity + opposed normals → the entity dimension
spanning the measurement direction becomes the driver (transform `value`), and
the panel shows a plain edit box — no side chooser, because nothing moves. The
direction is mapped into the sketch plane and UN-ROTATED by the entity's own
rotation (a 90° rectangle's `w` runs along local Y — probed on all eight walls
of a straight and a rotated rectangle). Covered: rectangle `w`/`h`, slot
`height`. A same-entity pair with no such dimension (a polygon's walls) is
refused with the reason, and `resolve_move` carries a backstop guard so the
no-op translate can never be offered again.

This closes the plate-width / cavity-width / boss-width cases in one stroke:
"how wide is this thing" measured between its own two walls is now typeable.

## User feedback, round 3 (2026-08-31)

> "when i am going for circle, i want to know the diameter, its not robust …
> when i am selecting that face, i can simply see the inner dia and outer dia
> … we dont need to mentions body … the information regarding how we created
> this feature right, just hide it … like an option so that we can expand it"

The pick box, reworked as a dimensions-first readout:

1. **Face-boundary diameters.** `_tagged_mesh` now tags every face with its
   FULL circular boundary radii (`circles`, largest first), so clicking an
   annular face reads "outer ⌀ 20.00 / inner ⌀ 8.00" with no round trip, and a
   pocket floor names its bore. Partial circles are excluded — someone asking
   "what is this bore" does not mean the corner-fillet radius (locked by
   `test_corner_fillet_arcs_are_not_reported_as_diameters`). The Measure
   panel's single-face readout carries the same rows (`_full_circles`).
2. **The body row shows only with several bodies on screen** — its original
   reason. With one body it was noise.
3. **The "Created by" chain is collapsed** behind `▸ Created by <feature>`,
   expandable in place; the open/closed choice sticks for the session. The
   one-line answer (who made it) survives collapsed; the sketch→extrude→cut
   chain is a click away. The E2E provenance tests now expand it the way a
   user does before reading the chain.

## User feedback, round 4 (2026-08-31)

> "this says the distance right, just move [it] a little further from that
> measurement line, because it hides the line. 2nd thing, i want move the line
> … the measurement always measure from the center, but i dont know the closest
> distance and longest distance … if i can [move] the line, i can see the live
> value in the box, same this works for the circle and a box, to measure wide"

1. **The value label sits BESIDE the line now**, offset perpendicular to the
   line's on-screen direction (biased upward, so the side is predictable) —
   centred on the midpoint it hid the very line it measured.
2. **The dimension line is draggable.** The witness pair is one sample of many:
   between a slanted wall and a boss, or around a cylinder, the distance varies
   along the geometry. With two picks and at least one face, the value label
   becomes a grab handle — dragging it raycasts onto ONLY the picked face's
   triangles (an invisible probe mesh, so the drag cannot wander onto a
   neighbouring surface) and each position calls `POST /api/measure/probe`,
   which answers with the KERNEL's exact minimum distance from that point to
   the other selection plus the witness point, so the line follows the drag and
   the panel reads "distance at this spot" live. One request in flight, latest
   drag position wins — the extrude preview's throttle discipline. Read-only,
   asserted: a probe per pointermove must never snapshot or rebuild.
   Also deduped the cylinder pick box (its rim circles repeated the wall's own
   ⌀, printing the same diameter twice — visible in the user's screenshot).

Verified with a real mouse drag: grabbing the label and sliding it around a
boss read 8 distinct kernel values (25.18 → 28.62 mm) with the line following.

### Round 4 follow-up: the blade-gap stutter (2026-08-31)

> "i can move the line, but it not moving countinesly, kind of strucking …
> i am measuring the gas between two blades"

Benchmarked before touching anything: the kernel probe is **5 ms median** on
the compressor's blade faces — the server was never the bottleneck. The freeze
was geometric: the drag only updated while the ray HIT the picked face, and a
blade face is a thin curved strip. Measuring a blade gap, the cursor naturally
rides the channel *between* the blades — off the strip — and the line froze
until it wandered back on. Three fixes in the drag loop:

1. **miss-tolerant**: on a ray miss, sample the ray at the last hit depth and
   snap to the nearest point ON the face (its triangles are precomputed at
   probe arm time; skipped above 20k triangles);
2. **frame-coalesced**: one raycast per animation frame, not per pointermove —
   a gaming mouse fires hundreds of moves a second;
3. **zero-latency tracking**: the grabbed end of the line follows the cursor
   immediately (`nudgeDimFrom`), with the exact kernel value and witness point
   overwriting a couple of frames later.

Verified on the compressor itself: a sweep along the channel produced 9
distinct kernel values (27.3 mm down to 1.17 mm at the blade convergence) with
no freeze, where the same path previously stalled.

### Round 4 follow-up 2: ACROSS, not just nearest (2026-08-31)

> "when i am moving in x axis, the line size should increase, to extend for
> the curved surface … in simple words the line should move accoring to the
> surface"

Nearest-point pivots the line toward one spot on the other shape; dragging
along a wall past a bore, the user expects the gap AT this station — a ray
from the probe point along the source face's normal, stretched until it meets
the other surface. The probe now has two modes, named in the panel:

* **across** — `BRepIntCurveSurface_Inter` on the target with a `gp_Lin` from
  the probe point along `source.normal_at(P)` (flipped toward the target using
  the min-distance witness); the smallest positive parameter is the distance
  and its point is where the line ends, so the far end RIDES the curve
  (probed: 25.0 / 26.0 / 29.0 sliding a wall past an r=5 bore). The nearest
  distance rides along as a footnote row.
* **nearest** — past the surface's shadow the ray misses and the probe falls
  back to minimum distance, so the drag never goes blank.

Verified as an E2E test on the suite's own server
(`tests/e2e/test_measure_probe.py`) after two lessons about the LIVE server:
verifying there raced the other agent switching tabs mid-drag (the picks
landed on a different design entirely — Face 51 on a 7-face part was the
tell), and the e2e port is now overridable (`TEXTCAD_E2E_PORT`) because two
suite runs on one Windows port both LISTEN and answers come from whichever
bound last. Also: exact rim points are knife-edge picks (50/50 between the
cylinder, the top face and nothing) — aim into the bore at the far inner wall
instead.

### Round 4 follow-up 3: clamp at the curve's limit (2026-08-31)

> "the line is dancing or vibrating when i am moving to curvature … the 2nd
> dot extended according to the curvature right, that is the limit … after
> that no need to move"

The dance was the across↔nearest flip at the tangent boundary: the across ray
grazes, then misses, and the nearest fallback TELEPORTS the far dot to the
closest point — every micro-move across the boundary jumped it back and forth.
Once across has been seen for a pair, a miss now CLAMPS the whole line at its
last real crossing — both dots hold, the length stops growing — and it
unfreezes the moment the cursor comes back into range. The zero-latency nudge
freezes with it (`setDimProbeFrozen`), or the grabbed dot would run away from
its own frozen line and snap back every frame. Approaching from outside,
before any across exists, nearest still shows (honest, and the only number
there is). E2E: entering=nearest, inside=across 25→27, leaving=clamped at 27.0
labelled "at the curve's limit".

## The problem, in the user's words

> "we dont have proper scale to measure distance between two point … if i am
> clicking a line of circle, it should show the diameter, and i want to see the
> distance between two faces … here is the intersting part, after selecting
> those point or line, we can see the values right, in the design, i can able
> to chnage it, then the design has to change to that vale … in esp 32 remote,
> distanse bewteen a pillar to wall is 10[mm], and i am changine the it 8, the
> pillar should move to wall"

Two features wearing one costume:

1. **Measurement.** There is no measure tool at all. Picking already produces
   rich data — [studio.py:884](studio.py) tags every face with `center`,
   `normal`, `area`, `planar` and cylinder `radius`, and every edge with `type`
   and `length` — but nothing lets the user ask *"how far is A from B?"*.
2. **Driving geometry from the measured number.** Typing into the readout and
   having the model follow.

## The distinction that decides the whole design

**Driven dimensions** — the measured number *is* one param in the tree:

| Pick | The number is | Edit means |
|---|---|---|
| Cylindrical hole face / circular edge | the `r` of a `circle` sketch entity | `r = new/2` |
| Pocket floor ↔ its rim | the extrude `amount` | set `amount` |
| Sketch plane ↔ the face it sits on | the `sketch_on_face` `offset` | set `offset` |

Exact, reversible, one number in → one param out.

**Derived dimensions** — the number is a *consequence* of two independent
literals. The user's pillar-to-wall gap is this: the pillar lives in
`isl1_sketch`, the wall in `outline_sketch`, and **10 mm is stored nowhere**.
Change it to 8 and the system cannot know whether the pillar moves, the wall
moves, or both.

**The core invariant: never guess which one you are looking at.** A driven
dimension gets an editable box naming what it drives. A derived one gets the
number plus an explicit *which side moves?* choice. Silently picking a side is
the hallucination failure mode this whole project exists to prevent — it would
look like it worked and quietly move the wrong wall.

## Probe results (2026-08-27, measured not assumed)

Run against build123d in `C:\Python314`:

- `edge.arc_center` → `(0, 0, 5)` ✅ but **`edge.center()` → `(-5, 0, 5)`, a
  point ON the circle, not its centre.** Using `center()` for a hole's position
  is a silent 1-radius error. Same trap on cylinder faces: `face.center()` is on
  the surface; **`face.axis_of_rotation`** gives the true axis.
- `BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)` → `IsDone()`, `Value()`,
  `PointOnShape1(1)` / `PointOnShape2(1)`. True minimum distance including the
  witness points, so the readout can draw the line it measured.

## The gotcha that shapes P3

**Face IDs are array indices, not identities.** [studio.py:839](studio.py)
assigns them by `enumerate(all_faces)`. Any edit rebuilds the model and face 47
becomes a different face. Therefore:

- After an edit the selection is **re-acquired, never reused** — otherwise the
  readout shows a confident number for a face the user never picked.
- Anything persisted (P3 pinned dimensions) is stored against the **provenance
  chain** (feature id + entity index), never a face id.

## Phases

| Phase | Ships | State |
|---|---|---|
| **P0** | Measure, read-only: diameter, length, distance, angle, thickness | **shipped** |
| **P1** | Driven edits — **diameter** (depth/offset deferred, see below) | **shipped** |
| **P2** | Derived edits — with the *which side moves* step | **shipped** |
| **P3** | Pinned dimensions that survive rebuild | — |
| **P4** | Named parameters (`wall_gap = 8`) | design only |

### P0 — Measure, read-only

New `measure.py`, `POST /api/measure`, new `static/js/measure.js`.

Request takes one or two selections; a selection is
`{body, kind: "face"|"edge", id}`. Response is one measurement:

```json
{"kind": "diameter", "value": 8.0, "unit": "mm",
 "label": "⌀8.00 mm", "rows": [["radius", "4.00 mm"]],
 "from": [x,y,z], "to": [x,y,z]}
```

`from`/`to` are the witness points so the viewport can draw the dimension line.

**One selection**

- circular edge → **diameter** (from `arc_center` + `radius`)
- cylindrical face → **diameter**
- line edge → **length**
- planar face → **area** + bbox extents

**Two selections**

- two parallel planar faces → **distance** along the normal, split three ways
  by what is actually between them (see "What P0 learned" below):
  **thickness** (opposed normals, material between), **gap** (opposed normals,
  open space), **step** (co-directional normals — a pocket floor under its
  rim, where the number is the pocket depth)
- two non-parallel planar faces → **angle** + minimum distance
- two circular edges / cylindrical faces → **centre-to-centre** distance
  (using `arc_center`, per the probe)
- anything else → OCCT minimum distance

Backend also enriches the mesh payload: `arc_center`/`radius` on CIRCLE edges,
`axis` on CYLINDER faces, so the frontend can label a pick before any round
trip.

**Interaction (Fusion parity).** Measure is a tool with a panel, so it obeys
rule 9: it sets `S.modalTool` / `S.modalToolPanel` on open, clears them on
close, and calls `dialogs.modalGuard()` at entry. Select-then-command (rule 2):
whatever is already picked becomes selection A. Esc cancels. The tool does not
mutate the document at all in P0.

### What P0 learned (both found by driving the real UI, not by tests)

1. **Co-directional normals are a step, not a thickness.** The first rule only
   checked the sign of `n·(c2-c1)`, so measuring a pocket floor against the top
   face it sits under reported "5.00 mm thick" — confidently claiming material
   in the middle of an empty pocket. Thickness/gap now requires the normals to
   be *opposed*; two faces looking the same way are a **step**, and that number
   is the pocket depth. Locked by
   `test_co_directional_faces_are_a_step_not_a_thickness`.
2. **The dimension line must anchor on the smaller face.** Drawn from face A's
   centre, a pocket-floor measurement anchored on the *plate's* centroid, so
   the line and its label floated beside the pocket the user had clicked. It
   now anchors on whichever face is smaller — the local feature — projected on
   to the other plane. Locked by
   `test_dimension_line_anchors_on_the_smaller_face`.

Neither was visible from the numbers alone: both measurements returned the
correct *value* and the wrong *meaning*.

### P1 — Driven edits

`measure.py` additionally resolves a **driver**:

```json
"driver": {"feature": "isl1_sketch", "path": ["entities", 2, "r"],
           "current": 4.0, "transform": "half",
           "label": "isl1_sketch · circle #2 radius"}
```

`transform: "half"` means the displayed diameter is twice the stored param.
**No driver ⇒ no edit box** — a read-only number is correct and honest; a wrong
edit box is not.

**Resolution.** Which sketch to look in comes from
[provenance.py](provenance.py)'s existing face→feature attribution; the entity
inside it is then matched in the sketch's *own* plane (`Plane.to_local_coords`),
comparing in-plane `x`/`y` and radius. Local Z is ignored, so a pocket's mouth
rim, its bottom rim and its bore wall all resolve to the same entity. Six
identical holes at six positions still resolve, because position tells them
apart; two genuinely coincident entities do not, and read-only is the answer.

A hole with no sketch behind it (`with_center_hole`, an imported STL) correctly
reports its diameter and offers no edit box.

**Writeback** is `POST /api/measure/set`, not `/api/feature/params`: the target
is a *nested* path (`entities[2].r`) and the transform (diameter → radius) must
live in one tested place rather than being recomputed in JS. It plans the write
before touching anything — so a refusal leaves the document byte-identical and
no undo entry behind — then snapshots, writes, rebuilds, and **re-measures the
same selection**, returning `achieved` beside `requested`. Writing a param is
not proof the geometry moved (house rule 3); if they disagree the panel says so
and the edit is on the undo stack.

### What P1 learned

1. **Scanning every sketch cost 660 ms per click.** Resolving a
   `sketch_on_face` plane means re-finding its named face over the whole base
   solid, so doing it for all 24 sketches of a test design made a diameter
   click take two thirds of a second. Asking provenance which sketch made the
   face resolves exactly **one** plane: **96 ms**, and the planes are then
   cached per rebuild the way `provenance._cache` caches faces.
2. **Two bugs the tests could not see**, both caught in the browser:
   - `applyEdit` set the module's `busy` flag and then called the re-read,
     which early-returns on exactly that flag. The edit landed and the readout
     kept showing the *old* diameter.
   - nothing reloaded the mesh. `postJSON` only broadcasts the document; every
     mutating tool calls `loadMesh()` itself. Without it the readout said
     30 mm and the status bar showed the new volume while the viewport still
     drew the old hole — and the stale pick panel sat underneath contradicting
     the readout with the pre-edit radius.

**Deferred from P1:** depth (extrude `amount`) and plane offset. Both are
driven in principle, but the measured step only equals `amount` when the
sketch plane coincides with the face being measured from, so each needs its own
predicate before it can be offered honestly. Diameter had no such caveat, so it
shipped first.

### P2 — Derived edits (shipped)

A derived distance has no param to overwrite, so `/api/measure/set` changes it
by **moving one side** — and never without naming which.

**Wall vs cap.** A rectangle entity makes four walls, so "which entity made
this face" is not answerable from the face alone. `_face_role` answers it in
the sketch's own plane: each entity's 2D face is rebuilt with `sketch._entity`
(which applies its rotation and position) and the wall belongs to the entity
whose boundary passes through the wall's projected centre. Probed — the four
walls of a 20×20 boss and a round boss's wall each resolved to their own entity
at distance 0.0, while the host plate's own walls sat 20–40 mm from every entity
and correctly resolved to none.

The same function separates a **wall** (normal lies in the sketch plane; its
position across the plane *is* the entity's x/y, so it can move) from a **cap**
(normal looks along the plane; its position is the extrude depth, so moving the
profile sideways would not shift it at all). That distinction is what lets the
tool answer "change the extrude distance or the sketch offset" instead of the
misleading "nothing here can move".

**Which side moves.** Default: the wall whose sketch is later in the tree — in
`esp32-remote` `outline_sketch` is feature #1 and the pillar islands come far
later, so "the pillar moves, the wall stays" falls out of tree order rather than
from a guess. The panel shows an A/B choice whenever both sides could move, and
`side` overrides the default.

**One direction formula for all three cases.** With `along = nA·(cB - cA)` the
measured distance is `|along|`, and shifting the chosen side by `s` along `nA`
lands `|along + s| = target` when

```
s = sign(along) · (target - current)          (negated when A is the mover)
```

Verified on a gap (shrinks by moving B toward A), a thickness (thins the other
way) and a step. The shift is then mapped into the sketch plane; a non-zero
local Z means the distance is depth-controlled and the edit is refused.

**Both coordinates are written as one list.** `write()` applies a plan's
`writes` array, so a one-param edit (a diameter) and a two-param edit (x *and*
y) share the same code and an entity can never end up half-moved.

#### What P2 learned

`applyEdit`'s guard still demanded a `driver`, so pressing Set on a perfectly
movable gap returned **silently** — the number stayed put with no explanation,
the one thing rule 7 forbids. Only the browser showed it; every backend test
passed throughout. The guard now accepts either a driver or a movable side.

#### Still derived, still refused

- non-parallel faces (no single distance to set)
- faces with no sketch behind them (a primitive, an imported body)
- depth-controlled distances (a pocket floor to the part's underside)

Each refuses with its own reason and leaves the document byte-identical.

#### Not built, deliberately

The original plan had a third branch: when a distance is depth-controlled,
*hand the chat a sentence* ("move the SD pillar 2 mm toward +X…") so the AI
could do it. P2 refuses with the reason instead. The sentence is a good idea but
it is a chat feature, not a measurement one, and wiring it here would mean
Measure quietly delegating an edit the user did not ask the AI for. Worth
revisiting as an explicit "ask the AI to do this" button.

### P3 — Pinned dimensions

Keep a measurement on screen across rebuilds, re-evaluated each time, stored
against the provenance chain (see the face-ID gotcha). Doubles as regression
detection: "this gap was 8.0, your edit made it 6.2".

### P4 — Named parameters

The durable fix. Today every number is a literal, so a gap set to 8 mm silently
drifts when the wall later moves — nothing *remembers* it should be 8. Fusion's
User Parameters is the correct answer, and it composes with this tool: measure →
"make this a parameter" → name it `wall_gap` → other features reference it.
P0's readout reserves room for a `⛓ make parameter` button so this lands
without rework.

## Test plan

Every phase adds tests to `tests/`, following house rule 2.

- `tests/test_measure.py` — the measurement kernel against known geometry: a
  40×30×10 box with a ⌀10 hole has diameter 10.0, thickness 10.0, and a
  centre-to-centre distance that uses `arc_center` (the probe's trap).
- `tests/test_measure_api.py` — the endpoint over HTTP, including the
  no-driver case returning `driver: null`.
- `tests/test_measure_drive.py` (P1) — set a diameter, rebuild, re-measure,
  assert the geometry actually changed to the requested value.
- E2E in `tests/e2e/` once the UI exists.
