# Sweep — tool spec (Tier 2, LAUNCH-PLAN.md §4 / §8 step 1)

> **Status: approved by default while the user was out (2026-09-17, the
> scheduled Tier 2 build — memory `tier2-build-plan`).** The user asked for
> the Tier 2 tools to be built one by one on Fable with the review deferred to
> their own `code review` chats; this page was written before the code, as
> §8 asks, and the user's first try of the tool is the approval gate.

## What you click, what you see

Draw a **profile** (a circle on the top face of a block, say) and, in a second
sketch on a plane perpendicular to it, a **path**: an open line-and-arc chain
drawn with the sketch ribbon's new **Path** tool, starting where the profile
is. Select the profile (tree row or viewport) and press **Sweep**: the path
lights up in gold, an **arrow** sits at the start of the path pointing along
it, the Distance box reads **0** — nothing is built yet. Drag the arrow and a
translucent tube of the profile follows the path as far as you pull; release,
and the real solid replaces it after one verified rebuild. Tick **Whole path**
for the full length, choose New body / Join / Cut, press **OK**.

## Inputs (parity rules 1, 2)

* **Profile**: a sketch profile (plane or face sketch), picked in the viewport,
  selected in the tree, or via the tree row's `〜` button — or a **flat face**
  of a body (`sweep_face`, a face-reference op like `revolve_face`: it never
  consumes the body). Command-then-select fallback as every tool.
* **Path**: a sketch holding an OPEN path — the `path` entity with
  `closed: false`, drawn by the sketch ribbon's **Path** tool (the existing
  Line/Arc tool auto-closes into a profile; this one ends where you
  double-click, and clicking its own start point closes it into an ordinary
  profile). Such a sketch builds no face: its kernel object is a Sketch of
  edges (area 0) that carries the path wires; the tree calls it a path sketch
  and Extrude / Revolve refuse it with a sentence naming Sweep.
  The panel's **Path** list holds every path sketch of the design (the plan's
  `paths`), newest first; a click on a path sketch's tree row while the panel
  is open chooses it too. **The path is stored as a REFERENCE** (`path: <id>`,
  in `document.REF_PARAMS` like a pattern's `seed`): rename follows it,
  deleting the path sketch takes the sweep along, the path sketch is never
  "consumed" (it can serve several sweeps).
* **Where the path must start** — measured, not assumed
  (`probes/sweep_api_probe3/4.py`): the kernel moves the path so its START sits
  at the profile's centre and the profile follows the path's SHAPE. A path
  that neither starts nor ends on the profile's plane produced solids in
  places no one asked for (an L 20 mm away swept 50 mm high), so:
  - the path's start must lie on the profile's plane (within max(0.1 mm,
    0.1 % of the path length)); if only its END does, the path is read from
    that end and the plan says so once;
  - a start farther from the profile's centre than the profile reaches is
    allowed, and the plan says the sweep runs from the profile's centre.
* **Distance** in mm along the path, stored as `distance`; **Whole path**
  stores `full: true` (a path edited longer stays fully swept — a stored mm
  figure would silently become partial). Dragging the arrow to the end of the
  path ticks Whole path.

## The handle and the panel (rules 3, 4, 5)

* **Gold path line**: the whole path, where the sweep will actually run (the
  plan's `path` points — translated to the profile's centre when the path was
  drawn elsewhere on the plane).
* **Arrow**: at the current end of the sweep, pointing along the path's
  tangent there; a drag along it adds to the distance, the arrow rides along
  the path (`stations`: the plan's sampled points with their tangents and
  transported frames — the browser picks the nearest, it computes no
  geometry, R1). Clamped to 0 … path length; at the end Whole path ticks.
* **Ghost**: the profile's outline loops placed at every station up to the
  distance and skinned between them (`viewport.beginSweepGhost`) — white,
  translucent, replaced by the real solid on release.
* **Panel** `sweepDialog`, ids `sw…`: Profile · Path (select) · Distance (mm)
  · Whole path (checkbox) · Operation (New body / Join / Cut) · Combine with
  (the plan's default target: the body the profile lives on) · Cancel / OK.
  Distance 0 builds nothing.
* **Edit**: tree ✎ or double-click reopens the tool on the stored path and
  distance, in isolation; Cancel restores verbatim (framework).

## Failures speak (rule 7) — the same sentences on the AI / MCP path

Every one measured first (`probes/sweep_api_probe*.py`), then refused BEFORE
the kernel where a number decides, and AFTER it where only the result can:

| Situation | Measured | What is said |
|---|---|---|
| No path sketch in the design | — | "Sweep needs a path: open a sketch on a plane perpendicular to the profile and draw one with the Path tool, starting on the profile" (the tool does not open) |
| Path starts and ends off the profile's plane | an L 20 mm off swept to z 50 where the path reached 40 | "the path starts 20 mm off the profile's plane — start it on the profile (snap to the profile's centre or its plane)" |
| Path leaves within the profile's plane | volume 0.0, `is_valid` True | "the path runs along the profile instead of away from it — draw the path on a plane perpendicular to the profile" (also for a tangent within 10° of the plane) |
| Path leaves at a slant (10° … 80°) | 45°: A·L·cos 45° exactly | builds; a NOTE: "the path leaves the profile at 45° — the section is thinner by that angle; a path perpendicular to the profile keeps the profile's true shape" |
| A bend tighter than the profile reaches | r_bend 2 with r_profile 3: A·L exactly, `is_valid` True, health [] — the inside of the bend folded over itself | "the bend of radius 2 mm is tighter than the profile reaches (3 mm) — the inside of the bend folds over itself; widen the bend or shrink the profile" |
| A straight corner with a leg shorter than the reach | (probe 5) | the same fold sentence, naming the leg |
| Distance 0 on OK | — | "Nothing swept — the distance was 0. Open Sweep again, then drag the arrow or type a distance before OK." |
| Distance beyond the path | — | clamped in the panel to the path length (Whole path ticks) |
| The profile sketch holds only a path | — | "'p2' is a path sketch (open lines, no closed shape) — a profile needs a closed shape; Sweep uses a path sketch as its path" |
| Extrude / Revolve of a path sketch | — | the same sentence, from the modifier gate |
| Kernel refuses / broken result | — | "sweep: the kernel could not sweep this profile along the path — …" / "the swept solid came back broken (…)"; never raw OCP text, never a zero-volume success |
| Result volume off A·L by > 2 % with a perpendicular start on a planar path | Pappus says A·L exactly for any planar path a section follows perpendicularly | "the swept solid folded over itself (its volume is 61 % of what the path's length allows) — a bend or a corner is tighter than the profile" |

Sharp corners use the RIGHT (mitred) transition: the default TRANSFORMED
silently swept only the first leg (half the volume, status ok), ROUND rounds
the corner and undershoots (probe 1 and 2).

## Acceptance

* `static/js/sweep.js` in 100–250 lines, declares panel / ops (`sweep`,
  `sweep_face`) / boxes ↔ params / path line + arrow + ghost gizmos; no
  geometry maths.
* Backend: `sweep` op takes `path` (a path sketch id — the document hands the
  op the sketch), `distance` (mm) or `full: true`; the legacy `path_points`
  list still works for saved AI trees (none exist in `designs/`).
* `toolplan.plan_sweep`: 30+ plan tests — every planned station lies on the
  kernel's own wire, the volume of every partial sweep is A·L to 1e-6 on
  straight, bent and looped paths, on XY / XZ / YZ and a face sketch; every
  refusal above is a red test.
* Gauntlet: a circle on every flat face of every corpus body swept along a
  perpendicular L path: a healthy solid or a sentence.
* 3 browser journeys: open from the tree row + drag the arrow (volume A·L),
  Whole path + OK + edit-and-cancel, the refusal sentence when no path exists.
