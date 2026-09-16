# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `b17d626..cc78019` - three commits: the journey
> runner's clock, the shell result checks, and the pre-kernel "thin everywhere"
> shell guard.
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

## The range

    b17d626..cc78019       (base b17d626, the paperwork for the kernel-worker review)

Three commits:

- `751db79` - the journey runner stops timing the hours the laptop slept, and
  asks the kernel's own budget what a hang is; 4 new tests.
- `275eeab` - a shell that hollows nothing is not a hollow: the walls are
  measured against the surface they came from; 13 new tests.
- `cc78019` - a shell of a body that is thin EVERYWHERE has nothing to hollow
  and is refused before the kernel; 4 new tests. Built on Fable in the
  overnight-run chat at the user's call, so it has had no second pair of eyes.

Touched by `275eeab`: `sketch.py` (+62/-3), `tests/journeys.py` (+41/-11),
`tests/test_shell_tool.py` (+72), `tests/test_kernel_guard.py` (+21/-3),
`tests/test_journeys.py` (+70), `tests/fixtures/my_part_5_mirror_body.brep`
(new), four probes.
Touched by `cc78019`: `sketch.py` (+157, the only product file: two new
functions and one call), `tests/test_shell_tool.py` (+69/-2, three new tests,
two expectations moved from after the kernel to before it),
`tests/test_kernel_guard.py` (+10, one KILLERS entry), two probes and two
probe bodies.
No frontend in any of the three, so ui stays v200.
Fast tier 1749 -> 1762 -> 1766, `-m library` 101, ruff zero, eslint untouched.

## What `cc78019` changes

**`sketch.deepest_material(solid, t, openings)`, new.** From sample points on
every face that stays (spread triangle centroids plus the face's own centre
when it lies on the face) a ray runs along the inward normal to the first
face it meets; stations along that chord (0.25, 0.5, 0.75; towards an OPENING
also 0.9 and 1.0), and every point of the opening faces themselves, are
candidates; each candidate's distance to the compound of staying faces is
measured with `BRepExtrema_DistShapeShape`, best-bound first, stopping at the
first that is `>= t - tol`. Returns `(depth, point, tol)`.

**`sketch.assert_something_would_be_hollowed(solid, t, openings, walls)`,
new, called from `shell()` for the INSIDE direction, open or closed, after
`assert_wall_fits_every_lump`.** Refuses when no candidate is deep enough:
"nothing would be hollowed — walls of N mm meet in the middle of this body
everywhere: no point of it is more than D mm from the faces that stay (near x,
y, z), so walls must be under D mm; use a thinner wall or open a face".

## What `275eeab` changes

**1. `shell_after_guards` asks OpenCASCADE for its own verdict** (`is_valid`
through `inspector._try`, because it is a property that can raise).

**2. `sketch.assert_walls_could_be_a_skin`, new.** An inward shell's walls lie
within `t` of the surface they came from, so their volume is about `area * t`;
more than `_SHELL_SKIN_FACTOR` (2.0) times that is refused as the body itself.

**3. `tests/journeys.py replay()` can open a corpse** (a folder with no
before-document re-sends the journey's steps against the live design).

## Where the risk is

- **`cc78019` is a SAMPLING guard, and a pre-kernel refusal is final.** The
  rule itself is a certainty (a point of material survives as wall exactly
  when it is within `t` of a staying face, so an empty offset has no point
  `t` from all of them), but the points are sampled: a body whose only deep
  material is small and sits away from every face centre, chord station and
  opening point could be refused with a cavity the kernel would have built.
  The first draft of this guard asked the opposite question and refused 11
  correct shells before the corpus caught it - the reviewer should assume the
  same kind of hole can exist in the sampling and look for a body that has it
  (a deep pocket of material reachable from no face's inward normal; a
  non-convex opening whose centre is off the face - `is_inside` drops that
  centre, so the opening's material is then only its triangle centroids).
- **`face.tessellate(tol)` inside an op.** Meshing every face of the body per
  shell call: 0.02-0.7 s up to 60 faces, `per_face` falls as `1/n^2` so a
  700-face body gets one ray per face. Not measured on the 675-face
  autonomiq-panel body - the one shell that already takes 692 s - so the added
  cost there is unknown, and a body where `tessellate` itself is slow would be
  slow at the guard, before the worker's budget starts.
- **The tolerance is the tessellation's, applied as slack on the refusal
  (`depth >= t - tol` allows).** `max(1e-3, 1e-4 * diagonal)`: on a 5 m body
  that is 0.5 mm of slack, so a wall that meets in the middle by less than
  that goes to the kernel as before. Deliberate, but a number.
- **The skin ceiling in `275eeab` is the one judgement call there.** 2.0
  against a measured 1.056; a mostly-concave surface is where the 1.056 comes
  from.
- **`is_valid` is now load-bearing inside an op** (`275eeab`).

## Cleared by measurement, not by argument

- `cc78019`: the crash boundary on the finding body is exactly half its wall
  (0.64 builds, 0.66 segfaults; `probes/shell_thin_wall_probe.py`), the guard
  reads 0.65 closed and 1.3 open on it. Over the gauntlet corpus, the four
  committed crash bodies and both finding bodies at seven thicknesses, closed
  and open (`probes/shell_thin_wall_corpus.py`): 238 cases, ZERO refusals of
  a shell the kernel built sound; 24 refusals where the kernel crashed
  (impeller, open, 5 mm), stalled, or refused after 0.5-30 s. Depths read
  exact on every analytic body (box 15 closed / 25 open, cylinder 20 / 25,
  hex prism 12.5 / 25, l-bracket 10, plate with hole 5 / 10).
- `cc78019`: the 4 mm rib, 4 mm pin and 4 mm web bodies build SOUND at 2.5
  and 3 mm and are now a test (`test_a_thin_part_of_a_thick_body_is_the_
  kernels_to_fill_not_a_refusal`), so the first draft's mistake cannot come
  back quietly.
- `275eeab`: the wrong result is real and reproduced (my-part-5 `j2_mirror` at
  3 mm: 2.709 mm3 removed, valid, watertight); sound closed hollows measure
  0.61-1.056 of their skin, sound open ones 0.61-0.955.
- `-m library` 101 and the fast tier 1766: no live design loses a feature.

## Do not re-report

- **The my-part crash itself (1.1 mm, top open, on 1.3 mm walls) still
  reaching the kernel.** It is a legitimate 0.2 mm recess in the lid - the
  lid's material is 1.3 mm from the cavity ceiling - so no pre-kernel rule
  refuses it without refusing correct geometry. The worker catches it and it
  is `test_kernel_guard.py` KILLERS `shell_twice`.
- **The my-part-9 stall** (`bugs/20260916-011919-my-part-9-s96223-step19/`,
  still in `bugs/`): 1.5 and 1.7 refused in 12-30 s, 1.6 and 1.8-5 stall,
  thinnest web 3.856 mm, deepest material 15.6 mm. Not a wall problem; section
  10 P2, with the candidates named.
- **The lone-rib expectation moving from "nothing was hollowed" (kernel) to
  "nothing would be hollowed" (guard)** in `test_a_lump_the_wall_does_not_fit_
  is_refused_not_left_a_solid_block` and the `thickness=40` row: the same
  refusal, one step earlier.
- **The my-part-5 SEGFAULT itself** (`275eeab`'s body): the worker's.
- **OUTSIDE shells not being judged by either new check.** Deliberate.
- **`kernelguard`'s budget counting machine sleep** (section 10 P2) and **the
  planetary-ring spin not being narrowed to an op** (P2).
- The reviewer may of course say any of these calls was wrong.
