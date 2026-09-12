# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `8f72d9e..ac5c11d` (one commit, `ac5c11d`): the
> fix of the journey runner's first catch — two kernel SEGFAULTS turned into
> sentences before the kernel, in Shell and in Mirror — and the gauntlet corpus
> grown by the body that crashed them.
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

## The range: `8f72d9e..ac5c11d`

- `ac5c11d` — Shell + Mirror: two kernel segfaults become sentences before the
  kernel; the clipped ball joins the corpus; 9 new tests (fast tier 1695).
  Files: `sketch.py` (+42: `assert_wall_fits_every_lump`), `pattern.py` (+51:
  `_part_ball_through`, `_assert_no_part_ball_through`, three call sites in
  `mirror`), `tests/gauntlet.py` (`clipped_ball`), `tests/journeys.py` (the
  crash recipe gains `--library` for a live design), the four gauntlet / tool
  test files, four probes.

## What it fixes, in one paragraph each

**Shell.** `bugs/fixed/20260912-175819-isogrid-panel-s9016-crash`: a CLOSED
inward shell (`open_face: "none"`) of a ball clipped by a box, 2.56 x 4.8 x
5.12 mm, at t = 1.8 killed the server child (0xC0000005 in `offset()`). The
scale was innocent: the same shape unscaled and ten times bigger crash the
same way, and a thickness sweep (`probes/shell_thick_wall_sweep.py`) puts the
edge exactly at half the smallest extent: 1.27 refuses, 1.29 crashes. A closed
inward wall of half a lump's smallest bounding-box extent or more leaves
nothing hollow (every point is within that distance of the boundary), so it
is refused per lump before the kernel. The bound also refuses a silent wrong
result the kernel called a success: `shell(ball r 3.2, t 5)` came back
137 -> 113 mm3 through an inverted offset sphere.

**Mirror.** The clipped ball joined `tests/gauntlet.py` and the mirror gauntlet
segfaulted on it: Join across its own flat face fuses two halves of ONE
sphere. Measured class (`probes/mirror_clipped_ball_crash.py`): a plain half
ball -> empty invalid solid; with side clips, a 45-degree clip or a quarter
ball -> segfault, glue or not; a half-ball pocket's image CUT from the body
-> the full block, pocket gone, invalid (and `_repeat`'s health check does
not ask `is_valid`). A full ball centred on the plane, a part ball SYMMETRIC
about it (the clipped ball across its mid Y / Z), a part ball whose centre is
5 mm off the plane and a half cylinder through its axis all fuse exact. The
guard: a SPHERE face, centre within 1e-3 mm of the plane, centroid OFF the
plane -> a sentence. Applied to the join body and to both seed deltas.

## Where the risk is

1. **The shell bound refuses something correct.** It applies ONLY to the
   closed hollow (no openings) in the INSIDE direction, per lump, with
   `bounding_box()` — an axis-aligned box, so for a tilted body the extent is
   an over-estimate and the guard fires LESS, never more. Check the sign of
   that argument, and that `2t >= dmin - 1e-6` at exactly half (the box at
   t = 15) is the right side of the edge (the kernel returns an unchanged
   body there — measured in the sweep).
2. **The mirror guard's centroid clause.** "Symmetric about the plane" is
   read as "the sphere face's centroid lies on the plane". A part-sphere face
   that is asymmetric yet has its centroid on the plane is conceivable (two
   asymmetric holes in a sphere face); whether the kernel crashes on it is
   not measured. Also: `BRepAdaptor_Surface(face).Sphere()` on a face whose
   `geom_type` is SPHERE — probed on these bodies only.
3. **The seed path.** `_assert_no_part_ball_through(removed / added)` runs
   before `_repeat`; a seed whose delta has a part-sphere face NOT centred on
   the plane is untouched. The cut case was measured on `body - image`
   directly, not through `pattern.mirror(seed=...)` on a Document.
4. **The corpus grew**, which is rule 4 working: `clipped_ball` runs in every
   gauntlet. Fillet's "changed nothing" check went from `pytest.approx`
   (relative) to an absolute 1e-6 floor because a 0.5 round on the 160-degree
   cap edge removes 0.017 mm3 — real work. The shell gauntlet records the body
   in `KERNEL_CANNOT_SHELL` (every route is a sentence, measured). The mirror
   gauntlet asks `pattern._part_ball_through` to decide `allow_failure` for
   the one face — the test leaning on the code it tests; a reviewer may prefer
   an explicit face list.

## Do not re-report

- **Shell OUTSIDE on the clipped ball still segfaults from 1.2 mm up.** Known,
  measured, in §10 as a new P1 row: no geometric bound applies to growing a
  body, and every intersection-join flag combination crashes
  (`probes/shell_offset_flags_probe.py`). The supervisor recovers the tab.
- The kernel cannot shell the clipped ball at ANY thickness, opening or not;
  that is OCCT, recorded in the shell gauntlet.
- `bugs/` is untracked; the fixed folder moved to `bugs/fixed/` so the
  runner's signature de-duplication cannot mask a recurrence.
- The pre-existing red browser tests (§10) are untouched; no frontend change,
  no `ui v` bump.

## Ground rules

Ruff zero; fast tier `1695 passed` at `ac5c11d`. Probe first (the four probes
run every case in a CHILD process — a segfault cannot be caught in-process).
Fix in the same chat, then this file -> `Status: NOTHING PENDING` (next
review takes REVIEW-QUEUE section 9, Trace image).
