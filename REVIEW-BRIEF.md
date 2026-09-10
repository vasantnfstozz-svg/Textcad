# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — section 6 (Measure and drive) closed a P0-class
> finding, so the house rule sends a second chat over the fix commit. Review
> `3ce97a3` alone; base `98cd07e`. When it is clean, set this back to
> `NOTHING PENDING` and the queue takes section 7.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range below; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes. Everything specific to this review is below.

---

## Just done: section 6, Measure and drive (3ce97a3)

One commit, `98cd07e..3ce97a3`. 8 findings, all 8 fixed, 0 rejected, 10 new
tests, fast tier 1387 green, ruff and eslint at zero, ui v183. All 48
buildable designs rebuild with no failed feature and no wrong edge id.

The P0: over `MESH_MODE_FACES` (400) faces, `_tagged_mesh` handed the
viewport one edge id **per adjacent face, in face order**, while
`measure.resolve` indexes `part.edges()`. Twelve of the 50 saved designs are
over 400 faces, so on those every edge click measured a different edge —
silently, because the highlight looks the edge up by id and drew the right
one. On isogrid-panel a straight 210 mm edge read `⌀4.50 mm` and opened an
edit box driving `corner_hole_sketch`'s circle.

## Where the risk is, in order

1. **`measure._relocate` / `_sig_distance` / `remeasure` (new, ~90 lines).**
   This is the fix pass's own new geometry, and it decides whether a write is
   accepted or reverted — so a wrong match is a FALSE PASS: an edit that did
   not land reported as verified. The rules to attack: a round pick matches
   by axis line only (`_axis_offset`, direction to `PARALLEL_TOL`), a flat
   pick by normal plus the component of the centre offset PERPENDICULAR to
   that normal, both within `RELOCATE_TOL = 1e-3`; more than one candidate
   means keep the old index, except that a radius closer than `RELOCATE_TOL`
   to `want_r` breaks the tie. Is "slides along its own normal and nowhere
   else" always true of `plan_move`'s shift and of a rectangle width edit?
   Can a `ring` signature (a circular EDGE, no axis) ever match the wrong
   rim? Does relocating an EDGE pick among `part.edges()` stay in family?

2. **`studio.py` `_tagged_mesh`'s mesh-mode edge branch.** It now calls
   `part.edges()` whenever `rich_faces` is non-empty. For a pure triangle
   soup `rich_faces` is empty and the call is skipped — but a MIXED body (an
   STL with a few non-triangle faces) would pay `part.edges()` on a huge
   shape. Is that reachable, and how slow? Measured cost on the biggest CAD
   design: 245 ms (cam-cover-plaque, 1552 faces, 4218 edges), and overall
   meshing got faster because the duplicates went.

3. **The new `broke` guard in `measure_set`.** `was_ok` is captured before
   `_snapshot()`; a feature that was already failing is deliberately not
   counted. Does any legitimate edit make a feature fail on purpose? Does
   `_revert_last()` really restore everything when it fires (it swaps in a
   fresh `Document` and carries `_cache`/`_spec_cache` over)?

4. **`want = measurelib._r(float(req.value))`.** Rounding the request to 3 dp
   before comparing fixed the inch sizes, but it also widens the accepted
   band to half a micron. Can an edit that misses by 4e-4 now pass as exact?

5. **`_measure_one`'s new extents branch.** `face_plane().to_local_coords()`
   on a Face — probed and correct for a planar chamfer, but what does it do
   for a face the geometric planarity test accepts while `geom_type` is
   BSPLINE (a dead-flat taper wall)? The old world-bbox path is still the
   fallback.

## Do not re-report

- The eight findings themselves; they are in `REVIEW-QUEUE.md`'s done log
  with their measurements.
- `test_a_move_that_wrecks_the_part_reverts_itself` no longer reverting at
  5.0 mm. That was deliberate and is argued in the test's own docstring: the
  move lands the asked-for step exactly, so the old message was false. The
  wreck is asserted at 120 mm instead.
- That Measure still cannot measure an imported mesh body's surface. It now
  says so honestly; the capability is LAUNCH-PLAN §10 P3.
- Everything on the queue's shared "Never report" list, and the items the
  section 6 report already cleared by measurement: `_plane_cache`
  freshness, the probe caliper maths, `_to_param` against `ENTITY_DIAMETER`,
  `plan_move`'s sign rule, and "measure never raises".
