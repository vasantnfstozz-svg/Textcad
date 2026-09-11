# Move and Rotate — tool spec (P4, LAUNCH-PLAN.md §8 step 1)

> **Status: in build 2026-09-11 — the sixth and seventh tools on the framework
> (`tool.js`), declared from ONE file (`static/js/move.js`) the way Fillet and
> Chamfer are.** Fusion's Move/Copy has one triad gizmo (three arrows, three
> rings) and a Move Type box; the ribbon here already has a Move and a Rotate
> button, so the two halves are two tools with one shared plan: **Move** drags
> the body along X, Y or Z with three arrows; **Rotate** turns it about X, Y or
> Z with one ring, through the body's own centre. Both ops EAT their body (the
> result is the body in its new place — no Join / Cut row), like Hole and Shell.
>
> Decisions made here without the user (say so if any is wrong):
> * **Rotate turns IN PLACE, about the body's own centre** (Fusion's default
>   pivot is the selection's bounding-box centre). The op `rotate` grows a
>   `pivot` parameter: `"center"` (the tool's choice), `"origin"` or absent
>   (the legacy behaviour — the WORLD origin — so the one live design that uses
>   `rotate`, planetary-assembly, does not move a hair; §10's P2 row said a
>   pivot needs a migration, and with the legacy default kept there is none),
>   or an explicit `[x, y, z]` (the AI / MCP path). The plan's ring centre and
>   the op's pivot come from the SAME function (`blocks.body_centre`), so the
>   handle can never sit where the body does not turn.
> * **Move is relative**, as the op always was: X / Y / Z are offsets in mm
>   from where the body is now, the honest zero is 0 / 0 / 0.
> * The **ghost** is the body itself: while a handle is dragged the body's own
>   mesh, translucent white, moves or turns with the pointer; the real body
>   follows on release after one verified rebuild. A move needs no kernel work
>   to preview and gets the live ghost every other tool has (fusion-parity:
>   "every dragged handle that changes a shape shows a ghost").
> * Axes are the WORLD axes only. Fusion also offers an edge or a face normal
>   as a rotate axis and "Point to Point" moves — later (§10).
> * No Copy box: a copy is Pattern's job (one copy at a distance) and would
>   need a second body in the tree.

## What you click, what you see

**Move.** Click a body — any face of it, flat or curved, or its row in the
tree — and press **Move**: three arrows meet at the body's centre, red along
X, green along Y, blue along Z (Fusion's colours), the boxes read **0, 0, 0** —
nothing has moved. Drag an arrow and a white ghost of the body slides with it,
the box follows; release, and the body is in its new place after one verified
rebuild. Type exact offsets, press **OK**. One `move1` row appears in the tree
under the body; double-click it and the arrows come back at the stored offsets.

**Rotate.** Click a body and press **Rotate**: a ring lies around the body's
centre in the plane of the axis (Z by default), a gold line marks the axis,
the Angle box reads **0**. Drag the ring's handle and the ghost turns with it,
snapping to whole degrees and to 45° steps; release, and the body has turned
in place. Choose X or Y in the Axis box and the ring and the line lie down to
match. Type an exact angle, press **OK**. One `rotate1` row appears.

## Inputs (rules 1, 2)

* **ONE body.** Select-then-command: the face picked when the tool is pressed
  names its body — a CURVED face counts too (the body is the input, not the
  face; `tool.js` open() takes a curved pick as its body for a tool that
  declares `anyFace` + `bodyRow`, and the command-then-select picker offers
  every face for such a tool); a body's row in the tree opens the tool on that
  body (`bodyRow`). With nothing picked the tool waits for a click on a face.
  A sketch and an edge are refused with the framework's sentences.
* **The op eats its body.** `move` and `rotate` are the body in its new place;
  no combiner, no `_cut` chip. Downstream features ride along — a sketch on a
  named face resolves on the moved body.
* **No re-pick**: a click in the viewport while the panel is open is not part
  of the tool (there is nothing to move the input to). Esc cancels.

## The handles and the panels (rules 3, 4, 5)

* **Move: three arrows** (`viewport.beginArrows`, N arrows with the extrude
  arrow's mechanics and a colour each) meeting at the body's centre PLUS the
  current offsets, so the triad rides with the body: the X arrow's base is
  `centre + (x, y, z)` and dragging it drives the X box; the other two the
  same. The plan gives the centre and the three axes (`origin`, `axes`); the
  browser adds nothing but the boxes' own values to place them. During a drag
  the ghost (the body's mesh) is offset by the change since the last build;
  on release the body rebuilds and the arrows are placed again.
* **Rotate: one ring + the axis line** (`beginTaperRing` with the plan's
  frame, `beginAxisLine`). The plan's frame is right-handed about the axis
  (Z: x→X, y→Y; X: x→Y, y→Z; Y: x→Z, y→X — probed: `rotate(Axis.Z, +90)`
  takes +X to +Y, `Axis.X` takes +Y to +Z, `Axis.Y` takes +Z to +X), so the
  ring's positive turn IS the kernel's. The ring's radius and the line's
  half-length come from the plan (the body's extent). Snapping is the ring's
  (whole degrees, 45° bands).
* **Panels** `mvDialog` (ids `mv…`: X / Y / Z (mm), all 0) and `rtDialog`
  (ids `rt…`: Axis X / Y / Z, default Z · Angle (°), 0). Operation rows
  hidden: the ops have no combiner.
* **Edit**: tree ✎ or double-click reopens on the stored values with the
  handles at them; Cancel restores verbatim — inherited. **Axis changed** →
  the plan is asked again (the ring lies down) and the feature rebuilds about
  the new axis.

## Failures speak (rule 7) — the same sentences on the AI / MCP path

| Situation | What is said |
|---|---|
| OK with 0 / 0 / 0 | "Nothing moved — the offsets were 0. Open Move again, then drag an arrow or type an offset before OK." |
| OK with angle 0 | "Nothing rotated — the angle was 0. Open Rotate again, then drag the ring or type an angle before OK." |
| `move` with a non-number (AI path) | `move: x must be a number in mm (got 'abc')` |
| `rotate` with a bad axis / pivot / angle | `rotate: axis must be "X", "Y" or "Z" (got 'W')` · `rotate: pivot must be "center", "origin" or [x, y, z] (got 'middle')` · `rotate: angle_deg must be a number in degrees (got 'lots')` |
| No body in the document | `Move needs a body — build one first, then click a face of it.` (inherited) |
| A sketch picked | `Move starts on a FLAT face of a body — click a face, not a sketch.` (inherited wording: the face names the body) |
| A body that has not built | `'b' has not built — fix that feature first, then move it` (`_pick_body`) |

## Acceptance (LAUNCH-PLAN P4)

* `static/js/move.js` ≤ 130 lines for BOTH tools, **no geometry maths**: the
  centre, the axes, the ring frame, its radius and the axis line all come from
  the plan; the browser adds the boxes' values to the arrow bases and nothing
  else.
* Backend: `blocks.rotate(part, axis, angle_deg, pivot=None)` +
  `blocks.body_centre`; `document.py` translates a bad `move` offset into a
  sentence and lists `move` among the PLACEMENT ops (a move as a pattern seed
  is the whole body — it was already, by falling through; now by name);
  `toolplan.plan_move` / `plan_rotate`; `author.OP_NOTES` for the pivot.
  `probes/move_rotate_probe.py` records the kernel facts: `Part.rotate(Axis
  (pivot, dir), deg)` turns about that pivot, the three signs, the bounding-box
  centre of a moved body, health after a pivoted turn on a sphere.
* **Tests**: `tests/test_move_tool.py` (rotate about the centre keeps the
  centre and the volume on every axis; the legacy default is unchanged — the
  same bounding box as before this change; an explicit pivot; every refusal
  as a sentence; the catalogue shows `pivot`; the document builds a move and
  a rotate and an edit rides; plan: the origin is the body's centre, the
  arrows' axes, the ring frame is right-handed and agrees with the kernel, a
  changed axis re-frames, an edit reads the stored values, refusals are
  sentences) and `tests/test_move_gauntlet.py` (every corpus body moved and
  turned about its centre on each axis: a healthy solid, the same volume, the
  centre kept / shifted by exactly the offset).
* **3 browser journeys**: click a face + Move + type X + OK (bbox shifted by
  X, one row, no chip); drag the X arrow (the ghost shows during the drag, the
  box follows, one rebuild on release), Cancel puts the body back; a body row
  + Rotate + drag the ring to ~90 (snaps to 90) + OK (the footprint's sides
  swap, the volume and the centre stay).
