# Measure & drive — development sheet

> **Status: P0 + P1 shipped 2026-08-27** (39 new tests, both UI-verified in a
> real browser). P2 next. Design agreed with the user 2026-08-27.

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
| **P2** | Derived edits — with the *which side moves* step | — |
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

### P2 — Derived edits

When both selections resolve to drivers in *different* features, offer a move.

- **Default side:** the face whose feature is **later in the tree** moves; the
  earlier feature is almost always stock or datum. In `esp32-remote`,
  `outline_sketch` is feature #1 and the pillar islands are far later, so
  "pillar moves, wall stays" falls out correctly. The user can flip it.
- **Direction decomposition** — this is what makes it implementable without a
  constraint solver:
  - gap lies **in the sketch plane** → translate that entity's coordinates
  - gap lies **along the extrude axis** → edit `offset` / `amount`
  - anything else → refuse, and hand the chat a precise sentence
    ("move the SD pillar 2 mm toward +X so its gap to the left wall is 8 mm")
    rather than guessing. Rule 7: failures speak.

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
