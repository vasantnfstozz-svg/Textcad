# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review commit **`8fdfa5b`** — round THREE's fix for
> `REVIEW-QUEUE.md` section 8 (Import STL and STEP). It is one function
> family in `blocks.py` (`_shell_inside`, `_shell_points`, `_spread`, the
> `nested()` closure in `_solids_from_shells`), +122 -12. Round three fixed a
> P0-class regression round two had introduced, and every round of this
> section so far has found a hole in the round before it, so the queue's
> step 8 asks for one more read of THIS diff before section 9.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range named here; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes.

---

## What to review: `d94518c..8fdfa5b` (one commit)

`blocks.py` only: `_NEST_SAMPLE`, `_spread`, `_shell_points`, `_shell_inside`
(now takes `points`), and the `sampled` cache + `nested()` closure inside
`_solids_from_shells`. Two tests in `tests/test_import_stl.py`
(`test_a_body_overlapping_a_notch_is_not_a_void`,
`test_a_pin_through_two_walls_is_not_a_void`). Fast tier 1639 -> 1641.

Rounds two and three ran on Fable 5.1 at the user's call ("proceed here
itself"). Round three re-read `d94518c`: 1 finding, fixed; 1 attack cleared.

## Where the risk is

1. **"Wholly inside" is now a SAMPLE**: up to 400 unique vertices and 400
   face centres, spread by `_spread` (`1 + (k * n) // cap`). A body that
   pokes out of its container by less than one sampled point in 400 still
   reads as a void; `MakeSolid.Add` then builds an INVALID solid, which the
   deep validity pass paints red. Wrong but not silent — confirm that claim
   holds (does `_deep_valid` actually run on an import body, and what does
   the row say?). Attack the spread: a body whose only protruding part is a
   run of consecutive faces shorter than n/400 — is 400 the right cap, and
   should it scale with the shell?
2. **`_spread` is 1-based** for `TopTools_IndexedMapOfShape.FindKey`. Check
   the arithmetic at the edges: n == cap, n == cap + 1, n == 1, n == 0
   (a shell with no faces cannot be closed, but `vm.Extent()` of 0 must not
   index).
3. **Face centres are the mean of a face's unique vertices** via a nested
   `MapShapes` per face. Every lib3mf face is a planar triangle, so the mean
   is the centroid. If a face ever had more than three vertices the mean
   would still be a point on or near the face; if `sub.Extent()` were 0 it
   would divide by zero — can it be?
4. **The `sampled` cache is keyed by shell index and built lazily** only for
   shells whose box lies inside another's. Confirm `nested(i, j)` and
   `_shell_inside(..., points)` cannot disagree about which shell the points
   belong to (the points are shell i's; the solid is shell j's).
5. **Cost**: the classifier is loaded once per (i, j) pair and performs ≤ 800
   points; the sample is built once per shell (0.15 s on a 32k-triangle
   shell). A housing with 40 parts inside its BOX but outside its material
   pays 40 sample builds + 40 first-point exits. Is that still seconds on a
   plausible assembly?

## Measured, and not worth re-reporting

- `imports/liquid-piston-2-v1.stl` (88,990 triangles): **339,926.9 mm3, 3
  bodies, 21,552 triangles, health clean** on `84e7c17`, `94eb47e`,
  `d94518c` AND `8fdfa5b`; 25.2 s now.
- **No saved design uses `import_stl` or `import_step`.**
- Round three's cases on `8fdfa5b`: bracket in a notch **21,640 / 2 bodies**
  (was 20,360 / 1 on `d94518c`); pin through two walls 2 bodies; a hollow
  STL with an OUTWARD-wound cavity (MeshLab re-orient) 936 / 1 and 1936 / 2
  — lib3mf marks that solid invalid, so the as-is fast path never takes it
  (`probes/s8r3_b_outward_void.py`).
- Rounds one and two's cases all still measure right on `8fdfa5b` (they are
  tests now: hollow, inverted hollow, hollow beside a body, hollow through
  the repair path, island in a cavity, pinched cavity, pinched + flipped
  face, duplicated body, welded overlap, thin plate drift, BOM).
- Do not re-open the round-one "checked" list (format detection, winding on
  clean meshes, `-0.0` welding, the decimation ladder, name collisions, the
  upload path, `_check_pieces`) or round two's cleared items (viewport mesh
  of a solid with a void, one-piece read on the real file).

## The ground rules

Read the diff itself. One reviewer, no subagents. Reproduce by measurement
before reporting; a finding that does not reproduce is rejected with a line.
The shared rules of engagement and the output format are in `REVIEW-QUEUE.md`.

**If this round finds nothing**, set this file back to `Status: NOTHING
PENDING` and the next `code review` takes **REVIEW-QUEUE.md section 9, Trace
image**.
