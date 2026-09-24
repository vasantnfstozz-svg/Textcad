# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
> **A rewrite must carry over every PENDING range it did not review** - this
> brief exists because one did not.
>
> **Status: NOTHING PENDING** - `1294f7a` (Create Sketch's fixed pick view,
> offset planes hidden outside the pick) was reviewed on 2026-09-24 by ONE
> Opus 5.5 reviewer and fixed in the same chat at `23a7b4c`: 4 findings, all
> P3, all fixed, 0 rejected. No P0, so REVIEW-QUEUE's step 8 asks for no
> second round. The next `code review` has nothing queued here, and
> `REVIEW-QUEUE.md` is empty too (all 13 sections closed 2026-09-17).

## What was reviewed and fixed (base `e6c291c`)

| Finding | What went wrong | The fix |
|---|---|---|
| F1 P3 | A waiting Create Sketch pick outlived the command that took over. A sketch opened from the plane's tree row kept the pick's hint, the squares and the plane behind it. The row's ✎ opened the Offset Plane step over it, and a click on a square then opened a sketch under the step's lock. Measure lost its first click to it. | `sketcher.enterMode`, `sketchplane.open` and `measure.openMeasure` call `cancelPlanePick` |
| F2 P3 | A selected plane was shown nowhere after a model reload: hidden outside a pick, its row's glow is its only trace, and the reload wiped it with the row still selected. | `viewport.glowSelectedPlane`, after every redraw of the planes and on the nothing-to-fetch reload |
| F3 P3 | Under Mirror's pick, the hover lit a HIDDEN plane in front of an origin square (a raycast ignores `visible`). | `planePickHover` raycasts the visible quads only |
| F4 P3 | After a fit on a tiny sketch (fit radius about 2 mm), the pick view clipped the squares' far corners. | `framePlanePick` raises the far plane when the corner furthest back passes it |

Checked and found sound, not to be re-derived: the framing maths; navigation
is never left off (only `endPlanePick` clears the pick and it ends the
flight, and OrbitControls' pointer-up ignores `enabled`); every reader of
`fitRadius` has a floor; the folded-in `fitToObjects`; Create Sketch's click
path raycasts the hidden planes only while they are shown.

Not judged (needs the app in hand): whether a click made during the 350 ms
flight lands where the user aimed, since the camera moves under a still
cursor.

## Do not re-report

- The pick moving the camera at all diverges from Fusion: the user asked for
  it (fusion-parity rule 14).
- The "plane1" / "XZ" label overlap in the pick view (plan s10 P3 row).
- `test_adaptive_grid.py::test_zoom_subdivides_and_stops_at_the_floor` is
  red on `e6c291c` too (plan s10 P3 row).
- A selected BODY or SKETCH row loses its glow at a model reload (plan s10
  P3 row, added by this review; an offset plane re-glows).
- A model load that lands while the pick waits re-frames the view: that is
  deliberate ("an open pick's view follows its quads").

**How the review starts.** The user opens a fresh chat on Opus
(`/model claude-opus-5-5[1m]`) and types only `code review`. CLAUDE.md's
section "The review chat" tells that chat to read this status line: PENDING
means review the range named here; NOTHING PENDING means go to the queue.
