# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — review the range **`6b9fa0e..36ee69c`** (ONE code
> commit, `36ee69c`, on branch `worktree-sweep-tool`; merged into master by the
> build session if the main checkout was clean, else still on the branch — see
> the merge note at the bottom). Base `6b9fa0e`. Built on Fable by the
> scheduled Tier 2 build of 2026-09-17 with **no review yet** — the user asked
> for the tools to be built one by one and the reviews to wait for their own
> `code review` chats (LAUNCH-PLAN §11, 2026-09-17). More Tier 2 tools may
> queue here before this is read; they are listed oldest first.

## 1. Sweep tool — `36ee69c` (`specs/sweep.md`)

**What it is.** The first Tier 2 tool: a profile (sketch or flat face) swept
along a PATH sketch. New concepts: an OPEN `path` entity (`closed: false`,
drawn by the sketch ribbon's new Path tool), a PATH SKETCH (a Sketch of edges,
area 0, carrying its wires on `_tc_paths`), and a `path` parameter that is a
REFERENCE (`document.REF_PARAMS`, like a pattern's seed).

**Where the risk is, ranked:**

1. **`sketch._place_sketch` now sits under EVERY sketch and sketch_on_face.**
   Measured: all 47 live designs (50 leaf bodies) rebuild to identical volumes
   and warnings against master (`probes/sweep_library_drift.py`, two runs, diff
   ignores timings). But `compose()` now filters open paths and raises a new
   sentence for an all-open list; `_as_sketch(pl * compose(...))` is unchanged
   for the closed case. A Sketch built as `Sketch(children=[*faces, *edges])`
   (closed shapes AND an open path in one sketch) is a new kernel shape: probe
   6 showed extrude ignores the loose edges; revolve, hole, trim
   (`/api/sketch/trim/pieces`), the tree's entity editor and `cornerlib` were
   NOT measured with one. Worth one probe each.
2. **`sweep_geometry`'s bend and mitre guards refuse BEFORE the kernel.** The
   rule this project keeps relearning: a guard that refuses correct geometry
   is a bug. The bend rule (arc radius ≤ profile reach → refuse) is exact for a
   profile centred on the path; a profile OFFSET from the path (the path
   starts off-centre but on the plane) is judged by the same reach from the
   centre, which over-refuses on the outer side and — check this — may
   UNDER-refuse on the inner side, because the kernel moves the path to the
   centre anyway (probe 4), so the geometry it sweeps IS centred. The mitre
   rule (`leg < reach·tan(turn/2)`) was measured on 90° corners only (legs 1,
   2, 3 invalid; 4+ fine with reach 3). Obtuse and acute turns: a probe.
3. **The Pappus check** (`|V − A·L| > 2 %` refuses) runs for ONE-face profiles
   whose start slant ≤ 2°. Could a correct sweep fail it? A closed LOOP path
   (probe 2: exact), an arc path (exact), a spline path — `path_points` with
   `smooth` — was NOT measured against A·L (probe 1's spline was slanted at
   the start, so it was excluded by the angle). A legacy smooth `path_points`
   tree that starts perpendicular and whose volume is honestly ≠ A·L would be
   refused; no design in `designs/` uses `sweep` at all.
4. **The frontend `onRow` hook** (tool.js): `waitForRow` is armed in `begin()`
   and `openEdit()`; `dropRowWait` runs in `hide()`. Pattern's edges/feature
   modes already had their own waiters — check no tool ends up with TWO waiters
   (waitForRow drops the previous one, so the last armed wins; is that ever the
   wrong one?).
5. **`_check_modifier_input`'s new branch** calls `part.faces()` on any
   `is_sketch(part)` for extrude/revolve/sweep — a Compound of disjoint islands
   is not a Sketch instance and takes the old path; fine. A sketch with faces
   AND paths passes (faces non-empty). A sketch of paths only fed to `sweep` as
   the PROFILE: the gate says "path sketch … needs a closed profile" before the
   op's own sentence — two sentences for one case, the gate's wins.
6. **The kernel placement rule** (probe 3/4): the swept solid starts at the
   profile's CENTRE OF MASS. A profile with holes (a ring) — is `Sketch.center()`
   the mass centre of the face-with-hole (yes for one face) — and does the
   kernel use the same point? Measured on a circle and an off-centre rectangle
   only.
7. **`_reverse_wire`** rebuilds `Wire([e.reversed() for e in reversed(edges)])`
   — measured on lines and one arc. A reversed wire's `tangent_at(0)` is the
   old end's tangent negated; the code reads it after reversal, fine.

**Ground rules for the review:** one reviewer, medium effort, read the diff of
`36ee69c` and probe; fix in the same chat; browser tier only
`tests/e2e/test_sweep_tool.py`; never the full suite "to see".

**Do not re-report** (known, deliberate, in LAUNCH-PLAN §10 P3 "Sweep's
loose ends"): the Add Feature dialog's `path` text box; the arrow sliding
along the local tangent during a drag; no Pappus check for multi-face
profiles; the corner-radius editor untested on open paths; no
orientation/taper/twist. Also deliberate: `SWEEP_SLANT_DEG = 2` is a NOTE
threshold, not a refusal (8° costs 1 % of the volume — measured on the
gauntlet's tapered wall); the in-plane refusal starts at 80°.

**Merge note.** The build session merges the branch into master only if the
main checkout has no modified tracked files at that moment (the user's Opus
bug-fix chat shares the checkout). If the bottom of this file says the branch
is unmerged, review it on the branch: `git log master..worktree-sweep-tool`.

**How the review starts.** The user opens a fresh chat on Opus
(`/model claude-opus-5[1m]`) and types only `code review`. CLAUDE.md's section
"The review chat" tells that chat to read this status line: PENDING means
review the range named here; NOTHING PENDING means go to the queue (which is
empty since 2026-09-17).
