# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** The review of `53f5653..0eaf9a2` is DONE
> (2026-09-13, one round, commit `edd60a9`). The next `code review` takes
> `REVIEW-QUEUE.md` section 9, **Trace image**, which is the first status-board
> row still marked TODO.
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

## What the last review found (`53f5653..0eaf9a2`, closed 2026-09-13)

ONE finding, fixed in `edd60a9`; 15 new tests (fast tier 1734 -> 1749),
`-m library` 101 passed, ruff and ESLint zero, ui v200.

**P1 — the blend guard refused correct geometry on a sharp corner.** The volume
half of `blocks._assert_is_a_blend` (`77bc7fa`) was flat in
`value^2 x edge length`, which is the 90-degree case. A round moves
`r^2 x (tan(a/2) - a/2)` per mm of edge, where `a` is the angle between the two
faces — so on any corner sharper than about 26 degrees a CORRECT round was
called "not a blend of this body" and the user was told their part carried
sliver faces. Measured on the user's own designs: spiderman-logo has a
160.5-degree crease where a 0.2 mm round moves 0.0628 mm3 of a 26707 mm3 body
(0.0002 per cent, bounding box untouched, BRepCheck valid, health empty) and was
refused; rocky-balboa carries two more. Each picked edge is now counted by its
corner, floored at 1.0 (nothing is tighter than before) and capped at 100. A
bevel is counted plainly — it removes `d^2 x sin(a) / 2` at any angle, largest
at a right angle, so the flat bound was already its worst case.

Safe because the two halves are ANDed and the BOX half is the decisive one on
the body the guard exists for: across rims 0/2/4 of `sliver_intersect_plate` at
every radius from 0.05 to 0.79, the crash-class results retreat 49.6-50.0 mm
against a 1.2-9.5 mm limit — 5x to 40x — and the volume half still refuses 11 of
12 on its own. All eight rims are still refused at every radius.

Plus one P3, fixed in the same commit: the busy overlay told anyone waiting
past 90 s that "this step stops itself if it runs too long". Only a round, a
bevel and a hollow have that budget; the overlay is shown for every request.

**Cleared by measurement, not by argument** (the brief's own named risks, so
they need not be re-asked):

- The `.brep` round trip of a TESSELLATED body is exact to the last decimal in
  volume and in every face and edge fingerprint.
- `hash(TopoDS_Shape)` IS stable across both routes a pick arrives by: the same
  edge taken from `part.edges()` and from `face.edges()` hashes equal even
  though their orientations are opposite (FORWARD against REVERSED). So
  `kernelguard.indices`' hash path is sound and the linear fallback is
  belt-and-braces, not load-bearing.
- `_cap_memory` really does cap: a child under a 0.5 GB ceiling gets
  `MemoryError`, not the machine.
- The two locks cannot deadlock: no thread that holds `kernelguard._LOCK` ever
  asks for `studio._KERNEL_LOCK`, and `shutdown()` is called from a probe only.
- `build123d.fillet` takes its target from `object_list[0].topo_parent`, and
  build123d propagates the TOP parent through `face.edges()` — so the
  in-process path and the worker path fillet the same body, not a face.
- `plain_cause` passes the crash sentence through unchanged: `_KERNEL_WORDS`
  contains no form of "kernel", so the journey runner's `CRASH_PHRASE` oracle
  really does see it.

Known and deliberately left (already rows in `LAUNCH-PLAN.md` section 10): the
900 s budget stopping autonomiq-panel's 1195 s shell; a transient refusal not
being cached, so a crashing feature pays a worker restart on every rebuild; and
the guard not covering booleans, 2D offsets or tessellation.
