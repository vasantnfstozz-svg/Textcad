# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** The Offset Plane review is CLOSED after four
> rounds (`6a4da57..2f97abf`). Round four read `692c6f5..2cba4e3` - the
> round-three fix pass and its two follow-ups - found ONE defect, reproduced
> it by measurement, fixed it in `2f97abf`, and re-measured the whole saved
> library. The next `code review` takes the first TODO row of
> `REVIEW-QUEUE.md`.

## What round four found

**P1 - the absolute-Z rule could still be walked around, with the number one
row further down.** Round three closed the case where the construction plane
holds the hardcoded height (`offset_plane(XY, 30)` + a sketch on it). It keyed
the sketch rule's exemption on "is this sketch drawn on a plane row?", so the
same distance written in the SKETCH's own `offset`, with the plane left at 0,
passed BOTH rules - the plane rule read the plane's 0, the sketch rule read
"plane row" and waved it through. Measured before the fix: a 40x30x12 base,
`offset_plane(XY, 0)`, `sketch(plane=that, offset=12)`, extrude 3. It builds
green with the boss on the base's top face at z 12..15, and changing the base
12 -> 20 BURIES it. That is the exact failure the offset method exists to
prevent. The exemption now turns on **"does this plane ride a face?"** (it has
a body input), never on "is this sketch on a plane row?" - two logic lines.

Each row still answers for the number IT holds, with its own key, so the
baseline keeps telling the user's history from the job's: the user's floating
plane and their own sketch on it are forgiven, and a sketch the JOB then draws
on that plane at its own hardcoded height is the job's and is refused.

Re-measured after: all **47 saved designs** go through `lint_baseline` with no
refusal and no crash. A plane that rides a face still exempts a sketch offset
measured from it; a formula offset is still a named number. 4 new tests, 38 in
`tests/test_offset_method.py`. Source **+12 / -2**, tests +72.

## What round four checked and cleared

- **The brief's risk 0 - the unmeasured baseline case.** A job that ADDS a
  face-based plane to a design that already carries a floating one: measured,
  two keys, no collision, `_lint_since` stays empty. And the new sentence IS
  followable - `offset_plane` is in `op_catalog()` as a `plane` kind with its
  full signature and the line "no inputs off a principal plane, 1 body off its
  face", so the author sees it even though `OP_NOTES` has no prose for it. No
  prompt note is needed.
- **Risk 1 - `_literal`.** Two callers, both asking "is this a hardcoded
  number?", which is what it answers. `9` and `"9"` flagged, `"lid_z"` and
  `True` clean, a list or None clean. Correct for both.
- **Risk 2 - `fetchPlaneFrame` now hits the server on every plane-sketch
  open.** No loop reaches it: the journeys runner and the replay path drive the
  API, not the sketcher. One awaited request on a path that already awaited one.
- **Risk 3 - the second feature's params.** Not made worse by this pass; the
  `_param_view` fix is the plan §10 P3 row, with its measurement in it.
- **The browser fix itself.** `planeFrames` is the only frame cache in
  `static/js`; `sketchplane.js` asks `planRequest` every time, and `textCache`
  / `arcKinds` are keyed on the values they describe. The e2e test is genuinely
  red on the old code (the cache returns the z=20 frame, `focusOnModel` puts
  the controls target there, the assert wants 50).

## Test state at this commit

Fast tier: **2634 passed**, and four memory-pressure failures in the full-tier
run only - `tests/test_imgtrace_loops.py` (2) and `tests/test_import_stl.py`
(2), one reporting `MemoryError` outright. Re-run alone: **75 passed**. Both
suites are mesh-heavy and unrelated to the author lint; this is the known
"never two OCCT workloads at once" box limit, not a regression. Ruff zero.
Frontend untouched by round four, so `ui v233` stands.
