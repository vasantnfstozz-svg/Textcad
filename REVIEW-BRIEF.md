# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `692c6f5..HEAD` — the **round-three fix pass of
> the Offset Plane review** (`692c6f5`) and its follow-up (`19ee23f`). Rounds
> one and two (`6a4da57..68b1a8a`) have now been read and are CLOSED. What is
> left is this pass, and the reason it is not closed is the second half of it:
> it put a NEW RULE into the author's history lint, and `lint_baseline` runs
> that lint over the USER's own document every time an AI job starts.

## What round three found, in one paragraph

Three findings, each reproduced before it was fixed. **(1) P1 — the browser
drew on the plane's OLD position after the plane was moved.** `sketcher.js`
caches a sketch plane's frame under `` `${plane}|${offset}` `` and called that
key "a pure function of both" — true while `plane` could only name XY / XZ /
YZ, false now that it names an `offset_plane` FEATURE, whose id does not change
when its offset does. This is the browser's copy of the very defect round two
fixed in `measure._plane_sig`. Measured in a real browser: open a sketch on a
plane at 20, press ✎ on its row and move it to 50, open a sketch on it again —
grid, model snaps and the plane every pointer ray is cast at were all still at
20 while `make_sketch` built at 50. Only the three origin planes are cached
now. **(2) P2 — the lint exemption was too broad.** Round one exempted every
sketch on a construction plane from the offset-method rule because the plane
row "rides a face or a named number"; a plane off a PRINCIPAL plane rides
nothing, so `offset_plane(XY, 30)` + `sketch(plane=that)` was the banned
absolute-Z form with one row in between, and the lint said nothing (measured
CLEAN). The exemption now requires the plane to have a body input. **(3) P1 —
the same lint line crashed on a formula.** `float(f.params["offset"])` on a
sketch whose offset names a parameter raised `ValueError` straight out of
`lint_baseline`, so asking the AI to change a design that drives a sketch
offset from a named parameter answered *"the model failed: could not convert
string to float: 'lid_z'"* — measured on a design that builds green. `_literal`
now converts what converts and treats only a real name as a named number.
Line delta **+61 / −17** in source, +103 in tests; fast tier 2632 green, ruff
and eslint zero, ui v233. No design file uses `offset_plane` (0 of 50) and no
design drives a sketch offset from a parameter, so no stored work was affected.

## Where the risk is (ranked — start at the top)

0. **The new lint rule can REFUSE an authoring step**, and a false refusal on
   the user's own design is the exact failure `lint_baseline` exists to
   prevent (27 of 50 designs once refused the AI's first correct step). The
   question for the review: is `("plane_offset", <plane id>, <offset>)` a key
   that BEHAVES like the rule beside it? Measured here: a tree that already
   carries the routed form puts that key in the baseline at rank 0, so
   `_lint_since` forgives it and a job on that design is not refused. Not
   measured: a job that ADDS a face-based plane to a design that already has a
   floating one (two planes, two keys — they do not collide, but nobody has
   run it), and what the repair loop does with the new sentence, which names
   an op (`offset_plane`) the AUTHOR PROMPT never mentions. A note in the
   prompt or `OP_NOTES` was deliberately NOT added — say so if you think the
   model needs it before it can obey.
1. **`_literal` is a new one-line door every numeric lint value goes through.**
   It answers 0.0 for anything it cannot convert, so a rule written later that
   means "is this present?" would read 0.0 as absent. Only two callers today,
   both asking "is this a hardcoded number?", which is what it answers.
   Measured: `9` flagged, `"9"` flagged (the reach the old `float()` had),
   `"lid_z"` clean, `True` clean.
2. **`fetchPlaneFrame` now hits `/api/tool/plan` on every sketch open on a
   construction plane.** One request where there used to be a cached read; the
   call was already awaited on that path, so nothing new blocks. The question
   for the review: is there a path that opens a plane sketch in a LOOP (the
   journeys runner, a replay) where that request is not free?
3. **The plane lint reads a SECOND feature's params** (`planes[plane_row]
   .params.get("offset")`). That is a new instance of the module's known
   list-params exposure, now a plan §10 P3 row with the measurement in it. It
   is not newly reachable — the first loop of `_lint_items` has always asked
   `f.params.get("entities")` unguarded — but the fix is the same `_param_view`
   for all three sites, and it was deliberately left out of this pass.

## Do not report (rounds one to three read these and decided)

- The "is there a fourth copy of which-plane-was-this-sketch-drawn-on?" that
  round two's brief asked about: the answer was YES, in the browser, and it is
  fixed here. The remaining ones are `sk.sketch_plane_of` (Revolve, reads the
  BUILT sketch) and `measure._build_plane`'s `sketch_on_face` branch, both
  correct. `sketch_snap.plane_of` only ever sees XY/XZ/YZ — measured: the
  sketcher passes an explicit `frame` for a plane-row sketch on both its
  doors (`openSketchEditor` and `editSketch`).
- `_min_inputs(op, f)` and the delete plan: re-measured this round. Deleting an
  unrelated feature leaves the plane alone; deleting the plane takes its
  sketches and their bodies; strike and unstrike round-trip clean; a face-based
  plane whose body is deleted cascades; `b = fillet(box)` then delete `b`
  rewires the plane to `box` and re-resolves the face there (the rule every
  face op lives under — round two flagged it, round three agrees).
- `offset_plane` with a body input and NO face params: refused with a sentence
  naming the four ways to say which face. Measured.
- The `move` guard, and the other doors a Plane could reach:
  `_check_modifier_input` and `_check_combiner_inputs` both refuse a plane by
  name. Measured, all three.
- `toolplan._profile` stacking: a plane-row sketch with its own non-zero
  `offset` puts the profile exactly where the kernel built it (measured, XZ at
  12 + 7). Extrude plans it; Revolve and Sweep answer their own true
  sentences about the profile.
- Measure follows a plane that moves AND a plane whose body changed thickness
  (measured 30 -> 50 and 4 -> 9).

## Ground rules for the reviewer

One reviewer, no subagents. Reproduce by measurement or a red test before
fixing; smallest fix; tests beside the code; commit, push, restart the user's
server if the backend changed. Then this file -> `Status: NOTHING PENDING`, a
plan §10 row for anything deferred, memory. Never `--fix`.
