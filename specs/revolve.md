# Revolve — tool spec (P3, LAUNCH-PLAN.md §8 step 1)

> **Status: APPROVED by the user 2026-09-03 ("approved and proceed"); SHIPPED
> the same day — done-note in LAUNCH-PLAN.md §7 P3.**
> The first tool born on the framework (`tool.js`). Success metric for the whole
> plan: bugs found in Revolve's first week, compared with Extrude's history.

## What you click, what you see

Select a sketch (tree row or viewport profile) and press **Revolve**: a **gold
axis line** appears in the sketch's plane and a **ring** around it at the
profile's far edge, with the angle box at **0°** — nothing is built yet. Drag
the ring's handle and a translucent sweep of the profile follows your hand;
release, and the real solid replaces it after one verified rebuild. Type an
angle, press **Full** for 360°, choose New body / Join / Cut, press **OK**.

## Inputs (rules 1, 2)

* A **sketch profile**: a plane sketch or a face sketch, picked in the viewport,
  selected in the tree, or via the tree row's action button. Command-then-select
  fallback: press Revolve with nothing selected, then click a profile.
* **The axis is derived, not asked for.** It is one of the sketch's two in-plane
  axes through the sketch origin (`u` = the plane's x, `v` = the plane's y), so
  it RIDES the geometry when a face or offset moves. The server tests both:
  the profile must lie entirely on one side. When both work, the plan opens on
  `v` (the classic lathe axis: a profile on XZ turns about Z) and the panel
  offers **Swap axis** for the other. When neither works the tool refuses to
  open and says why (below).
* Not in P3 (P3b, after the checklist): a picked planar FACE as the profile, a
  sketch line as the axis, Two-sides / Symmetric extents, an axis offset from
  the sketch origin.

## The handle and the panel (rules 3, 4, 5)

* **Ring**: centred on the axis, level with the profile, radius = the profile's
  far edge (min 1 mm), x pointing at the material so 0° is where the sketch
  is. A positive drag turns the way the kernel sweeps; the other way is
  negative (a sign, like Extrude's arrow). Ring frame, radius and axis come
  from `POST /api/tool/plan {tool:"revolve", sketch_id}` — no vector maths in
  JS (R1).
* **Ghost** while dragging: the profile outline swept by the current angle
  (three.js lathe of the plan's outline in the plan's ring frame). One verified
  rebuild on release.
* **Panel** `revolveDialog`, ids `rv…`: Profile · Axis (`u`/`v`, Swap) ·
  Angle (°) box, starts at **0** · **Full** button (= 360) · Operation
  (New body / Join / Cut) · Combine with (default target from the plan) ·
  Cancel / OK. Angle is clamped to ±360 in the box; 0 builds nothing.
* **Edit**: tree ✎ or double-click reopens the same tool with the ring at the
  stored angle, in isolation (rollback bar), Cancel restores verbatim —
  inherited from the framework.

## Failures speak (rule 7) — the same sentences on the AI / MCP path

| Situation | What is said |
|---|---|
| Profile crosses both candidate axes | "This profile cannot be revolved: it crosses `u` (−3.2 to 8 mm) and `v` (…). Move the profile entirely to one side of an axis in its plane." (tool does not open) |
| Angle 0 on OK | "Nothing revolved — the angle was 0. Open Revolve again, then drag the ring or type an angle before OK." |
| Result falls into pieces (Cut) | framework's pieces warning + "the revolved cut leaves material on both sides — revolve the full 360°, or move the profile" |
| Kernel refuses a build anyway | framework backstop: revert to the last angle that built, say so |
| Straddling profile / axis not in plane reaches the OP (AI path) | `ValueError` sentences from `sketch.revolve_sketch` (reuse the backup branch's guards); the AI repair loop reads them |

## Acceptance (LAUNCH-PLAN P3)

* `static/js/revolve.js` in **100–250 lines**, declares panel / op / boxes ↔
  params / ring + ghost gizmos / the two sentences above; **no geometry maths**.
* Backend: `revolve` op takes `axis` = `"u"|"v"` (sketch-local) **or** the
  legacy `"X"|"Y"|"Z"`; `angle` in (−360, 360] excluding 0; the two kernel
  guards (straddle → sentence, axis ⟂ plane → sentence, never a raw OCP error,
  never a zero-volume "success").
* `toolplan.plan_revolve`: **40+ plan tests**, every planned axis actually
  builds and the **volume is cross-checked with Pappus** (V = 2π·r̄·A·θ/360)
  on circles, rectangles and an L-profile, on XY / XZ / YZ / a face sketch.
* **3–6 browser journeys**: open from tree row, drag the ring to ~90°, Full,
  Cut into a body with the default target, edit-and-cancel restores, refusal
  sentence for a straddling profile.
* R10: `revolve.js` + `tool.js` together must be **smaller** than the 768-line
  hand-wired Extrude they replace as the pattern (the P2 exception, judged here).

## The user's five-step checklist (R9)

1. Sketch a half-profile on XZ entirely at positive x (a rectangle 10–30 by
   0–40). Revolve from the tree row: gold Z axis, ring, angle 0, nothing built.
2. Drag the ring to about a quarter turn: the ghost follows, the solid appears
   on release, the box reads ~90. Type 180: the solid is half a ring.
3. Press Full: a complete solid of revolution; OK; the tree shows one
   `revolve1`. Double-click it: the ring reopens at 360; Cancel changes nothing.
4. Draw a circle on the top face of a box, Revolve, Cut, drag: the pocket
   appears in the box (target = the box), one body, no pieces warning.
5. Draw a rectangle across the origin on XZ and press Revolve: the tool does
   not open, the chat says the profile crosses the axis and what to do.

---

# P3b — a picked face, the profile's own edges as the axis, two sides / symmetric

> **Status: built 2026-09-05 in one session, under the assumptions below; the
> user's checklist decides.** The gap the user hit: a FACE picked in the
> viewport, then Revolve — the tool said "click a sketch, not a face".

## What you click, what you see

Click a flat face of a body and press **Revolve**: the panel opens on the
face, the **Axis** list holds the face's straight edges (longest first) and the
gold line sits on the chosen one; nothing is built until you drag the ring or
type. The same list appears for a sketch profile: **u**, **v**, then every
straight edge of its outline that the profile does not cross — Fusion's "pick a
line of the profile as the axis". A **Direction** row (One side · Two sides ·
Symmetric) and, for two sides, an **Angle 2** box.

## Rules

* **Axis candidates** (server, `toolplan.plan_revolve` → `axes`): `u`, `v`
  (always listed, greyed with the reason when the profile crosses them), then
  the straight edges of the profile's OUTER wires that work, named `e1…eN`
  longest first, labelled by position (`edge at u = 10 (40 mm, along v)`).
  Inner wires are never offered (material lies on both sides of a hole's
  edge). Straight-but-BSPLINE seam edges count. **Default:** `v`, else `u`,
  else the longest working edge — so a rectangle drawn across the origin now
  opens (about one of its sides) where P3 refused it; a centred circle still
  refuses, and the sentence says to move it or give it a straight edge.
* **An edge axis is stored as a line in the sketch plane's own coordinates**,
  `axis: [[u1, v1], [u2, v2]]` — never an index or a name. It rides the plane
  exactly as `u` / `v` do (a face or offset move carries it). It does NOT
  follow a later resize of the profile: it stays where the edge was, as a
  construction line would, and the plan lists it as *the stored line* while
  it still works or explains why it no longer does (the `fallback` path). A
  parametric sketch line is the later, honest fix (a construction-line
  entity); silently jumping to "the nearest edge" is the banned failure.
* **A face profile** (`revolve_face`, a FACE-REFERENCE op like `extrude_face`:
  it never consumes the body) is resolved by geometry at every rebuild
  (centre + normal) and revolved in **its true plane**, `face_profile_plane`:
  identical to `face_sketch_plane` on the axis-aligned faces of a box, but a
  wall tilted under 25° keeps its own plane instead of snapping to the
  principal one (the snapped plane does not contain the face — the probe
  measured its edges 1.4 mm off it). `u` / `v` are that plane's axes through
  the world origin's foot, so on a centred body they cross the face and the
  edges are what is offered. Default operation Join, target the body (the
  framework's face mode).
* **Direction** (Autodesk's Revolve reference): *One side* sweeps `angle`
  (signed, the ring's sign) from the profile plane. *Two sides* adds
  `angle2 ≥ 0` the other way. *Symmetric* sweeps `angle` to **each** side
  ("a single angle to revolve in each direction") — so 90 symmetric is a
  half turn. Built as ONE sweep of the total, turned back about the axis
  (exact: the symmetric centroid lies in the profile plane, probe §5). The
  ghost sweeps both ways too. Limits are the server's one turn: the panel
  caps one side at 360, symmetric at 180 each way, two sides at 360 together,
  and says so once.

## Failures speak (added sentences)

| Situation | What is said |
|---|---|
| No axis works (centred circle) | "This profile cannot be revolved: it crosses u (…) and v (…) and its outline has no straight edge to turn about. Move the profile entirely to one side of an axis in its plane, or give it a straight edge." |
| A curved face is picked | "that face is CYLINDER (curved) — only a FLAT face can be revolved" (the tool does not open) |
| `revolve_face` without an axis (AI path) | "revolve_face needs an axis: one of the face's straight edges as a line [[u1, v1], [u2, v2]] in the face's plane, or u / v" |
| Two sides add to more than a turn | "the two sides add up to 400°, more than one full turn" (the panel caps first) |
| A negative second angle | "the second side's angle is a size, not a direction — give it as a positive number" |
| The stored line no longer works | the P3 `fallback` note: the tool opened on another axis, OK saves that, Cancel keeps the old one |

## The user's five-step checklist (P3b)

1. Make a box. Click its top face, press Revolve: the panel opens, the Axis
   list shows four edges, the gold line lies on the longest one, angle 0,
   nothing built. Drag the ring a quarter turn: a quarter-cylinder grows off
   that edge and Join makes it one body with the box.
2. Pick another edge in the list: the gold line and the ring move to it, the
   solid follows. OK. Double-click the new `revolve_face1`: it reopens on the
   same edge; Cancel changes nothing.
3. Sketch a rectangle on XZ **across the origin** and press Revolve: the tool
   opens now, about one of the rectangle's sides (u and v are greyed and say
   why). Full turn: a solid cylinder.
4. Sketch the P3 half-profile (10–30 by 0–40 on XZ), Revolve, Direction
   Symmetric, type 45: a quarter-turn solid centred on the sketch plane
   (equal amounts on both sides). Switch to Two sides, Angle 2 = 90: the
   solid extends further the other way. Full resets to one side, 360.
5. Draw a circle centred on the origin on XZ and press Revolve: the tool does
   not open; the chat says it crosses both axes and has no straight edge.
