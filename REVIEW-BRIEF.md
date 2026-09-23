# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review the range `6a4da57..HEAD` — the **fix pass of
> the Offset Plane review** (round one). ONE commit. The Offset Plane build
> itself (`6a4da57`, `specs/offset-plane.md`) has now been reviewed; what is
> left to read is the fix, because it changed the DELETE PLAN, which every
> op in the tree goes through.

## What round one found, in one paragraph

Four findings, all reproduced by measurement first and all fixed in the same
chat. **(1) P0 — any delete or ✕ silently swept every offset plane away.** The
delete plan's "does this feature still have enough inputs?" rule answered `1`
for every op that is not a creator. An `offset_plane` off a principal plane
has NO inputs, so it failed that test on every pass: deleting one unrelated
feature removed the plane, every sketch on it and every body built from those
— measured as 4 rows deleted for a delete of 1, with the summary calling them
"3 dependent features that cannot be kept without it". `Document.strike` runs
the same plan, so the ✕ struck them out too. **(2) P0 — a face named without a
body built quietly off XY.** `offset_plane` with `face: "top"` and no input
ignored the face and measured from the principal plane at the same number,
status `ok` — a plane at z −6 where the user asked for one 6 mm into a top
face at z 20. Reachable from the Add Feature dialog, which hides the inputs
box for this op (`inputs: 0` in the catalog). **(3)** `move` of a plane put
`AttributeError: 'Plane' object has no attribute 'volume'` in the feature row:
`move` is the one modifier that skips `_check_modifier_input`. **(4)** The
offset-method lint called a sketch on a plane row "floats at absolute Z", and
counted an `offset_plane` as "a body already exists". Line delta **+69 / −6**
in source, +105 in tests; fast tier green, ruff zero. No design file uses
`offset_plane` yet (0 of 50), so no stored work was damaged.

## Where the risk is (ranked — start at the top)

1. **`_min_inputs` is no longer a function of the op alone.** It now takes the
   FEATURE (`_min_inputs(op, f)`) and answers `0` for a plane with no inputs,
   `1` for a plane that has one. One caller, `remove_plan`'s healing loop at
   `document.py:1476`. The question for the review: does any delete of a
   feature that a plane depends on now heal where it should cascade? Measured:
   deleting the body under a face-based plane still takes the plane and its
   sketches (`test_deleting_the_body_under_a_face_plane_takes_the_plane_along`),
   and `_passthrough` still refuses to reconnect across a kind change
   (`_kind_of` answers "plane"). Not measured: a face-based plane whose body is
   deleted but whose UPSTREAM survives (`b = fillet(box)`, delete `b`) — the
   plane rewires to `box` and re-resolves its face there. That is the right
   answer for a pick that still exists on `box`, and the wrong one for a face
   the fillet created. It is the same rule every face op already lives under,
   so it was left alone; say so if you disagree.
2. **The new refusal in `sketch.offset_plane` is at the OP's door**, so it
   applies to the UI, the MCP, the AI author and the file loader at once. It
   fires on `face or face_center or face_normal` with no `solid`. Check that no
   caller legitimately passes a face name with no body — the browser's `ok()`
   always sends `inputs: [owner]` for a face pick, and `editOffsetPlane` writes
   only `offset`.
3. **The author lint now reads a sketch's `plane`.** `_lint_items` computes
   `on_plane_row` for every sketch feature in an authored tree. `f.params.get`
   on params a file holds as a LIST would raise — but the line directly below
   it has always done the same, so this is the module's existing exposure, not
   a new one. Worth one look anyway.
4. **The `move` guard is in `_eval`, not `_check_modifier_input`.** `move`
   deliberately stays out of that helper (it reads a missing offset as 0), so
   the plane check sits inline in the move branch. Anything else that will ever
   skip `_check_modifier_input` needs its own.

## Do not report (round one read these and decided)

- The three sites the brief asked about are clean: `document.py:2337` (pieces
  warnings — planes have `pieces = None` AND are filtered by the
  COMBINERS/MODIFIERS test), `document.py:1817` (deep validity — walks
  `leaf_solid_ids`, which excludes planes), `_orphan_sweep` (a plane is in
  `FACE_REFERENCE_OPS`, so its body edge is skipped).
- The formula door: `CREATORS.get(op) or MODIFIERS.get(op)` exists in exactly
  two places outside `probes/`, `op_params` and `numeric_params`, and both
  learned the op. Grepped.
- `sketch_snap.py:132` (a Plane has no `.edges()`; the try/except takes it),
  `provenance._sketch_behind`, `_loft_candidates`, `tool.js solids()` (filters
  `volume != null`), the tree's sketch-nesting: all already exclude planes.
- `_carry_face_picks`: a sketch on a plane has no inputs, so the `param_refs`
  change cannot reach `_hands_on_the_move`. A face-based plane's own pick DOES
  ride the move, correctly.
- A plane behind the rollback bar: `_parts` is cleared, so `plane_frame` is
  null and the quad is not drawn. Measured.
- Tool plans with a plane selected (shell, fillet, pattern, mirror, extrude):
  every one answers a plain sentence. Measured.
- The two cosmetic viewport lags (a quad not re-sized in a body-less document;
  a quad keeping its hover brightness after a pick ends on a face) are plan
  §10 P3 (e), not fixed.
- The tool.js inch round trip, `into_sign`, the sketch's own `offset`, and the
  Construct entries that do not exist yet: unchanged, plan §10.

## Ground rules for the reviewer

One reviewer, no subagents. Reproduce by measurement or a red test before
fixing; smallest fix; tests beside the code; commit, push, restart the user's
server (the backend changed). Then this file → `Status: NOTHING PENDING`, a
plan §10 row for anything deferred, memory. Never `--fix`.
