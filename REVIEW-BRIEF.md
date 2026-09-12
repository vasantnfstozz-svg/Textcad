# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `8f72d9e..53f5653` (two code commits, `ac5c11d`
> and `53f5653`): the journey runner's first two catches. `ac5c11d` — two
> kernel SEGFAULTS turned into sentences before the kernel, in Shell and in
> Mirror, plus the gauntlet corpus grown by the body that crashed them.
> `53f5653` — the spec check's symmetry boolean made bounded (it ran 22 minutes
> and 44 GB on one random plate and the laptop died), and the runner given
> time and memory oracles plus a hard memory ceiling per child.
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

## The range: `8f72d9e..53f5653`

- `ac5c11d` — Shell + Mirror: two kernel segfaults become sentences before the
  kernel; the clipped ball joins the corpus; 9 new tests (fast tier 1695).
  Files: `sketch.py` (+42: `assert_wall_fits_every_lump`), `pattern.py` (+51:
  `_part_ball_through`, `_assert_no_part_ball_through`, three call sites in
  `mirror`), `tests/gauntlet.py` (`clipped_ball`), `tests/journeys.py` (the
  crash recipe gains `--library` for a live design), the four gauntlet / tool
  test files, four probes.
- `53f5653` — Symmetry check: two gates before the boolean; the runner gets
  `HANG_MS`, `MEMORY_BUG_MB`, `peak_mb()`, `JobCap` and `--mem-gb`; 5 new
  tests (fast tier 1701). Files: `inspector.py` (+58: `_rotation_keeps_extent`,
  `_rotation_keeps_vertices`, `_rotation_residual`, the rewritten
  `is_rotationally_symmetric`), `tests/journeys.py` (+190), `tests/test_core.py`
  (2 tests + the bottle cap as data), `tests/test_journeys.py` (3 tests), five
  probes (`memcap.py` is a standalone tool: any command under a memory ceiling).
  The evidence folder is `bugs/fixed/20260912-220013-bottle-cap-28mm-s39331-memory/`
  (untracked, like all of `bugs/`).

## What each fixes, in one paragraph

**Shell (`ac5c11d`).** `bugs/fixed/20260912-175819-isogrid-panel-s9016-crash`:
a CLOSED inward shell (`open_face: "none"`) of a ball clipped by a box,
2.56 x 4.8 x 5.12 mm, at t = 1.8 killed the server child (0xC0000005 in
`offset()`). A thickness sweep (`probes/shell_thick_wall_sweep.py`) puts the
edge exactly at half the smallest extent: 1.27 refuses, 1.29 crashes. A closed
inward wall of half a lump's smallest bounding-box extent or more leaves
nothing hollow, so it is refused per lump before the kernel. The bound also
refuses a silent wrong result the kernel called a success (`shell(ball r 3.2,
t 5)` came back 137 -> 113 mm3 through an inverted offset sphere).

**Mirror (`ac5c11d`).** The clipped ball joined `tests/gauntlet.py` and the
mirror gauntlet segfaulted on it: Join across its own flat face fuses two
halves of ONE sphere. Measured class (`probes/mirror_clipped_ball_crash.py`):
a plain half ball -> empty invalid solid; with side clips, a 45-degree clip or
a quarter ball -> segfault, glue or not; a half-ball pocket's image CUT from
the body -> the full block, pocket gone, invalid. The guard: a SPHERE face,
centre within 1e-3 mm of the plane, centroid OFF the plane -> a sentence.
Applied to the join body and to both seed deltas.

**Symmetry (`53f5653`).** The spec check's proof of N-fold symmetry was
`result_shape - result_shape.rotate(360/N)`, unbounded work on arbitrary
geometry. On bottle_cap_28mm (spec `symmetry: 24`) a random 67.9 x 16.9 plate
added beside the cap and a cylinder made `Compound(3 overlapping bodies) -
rotated` run 22 minutes and 34 -> 44 GB (the stack, dumped 20 s in, is in
`ShapeUpgrade_UnifySameDomain` under `_bool_op`'s clean pass); Windows logged
four Resource-Exhaustion events and the 16 GB laptop died at 22:00. Two
NECESSARY conditions now run first, each milliseconds: a rotation that maps
the shape onto itself keeps its bounding box, and carries every (sampled, at
most 60) vertex to a point on or inside the shape. Only a shape that passes
both reaches the boolean, which runs under `SkipClean` and via `cut()`, not
`-` (`Compound.__sub__` unpacks the tool's members and read 6967 mm3 of
residue on an exactly symmetric overlapping compound; `cut` reads 0). The
plate case answers False in 11 ms; the journey's step 5 takes 203 ms; all ten
live designs with a symmetry spec keep their verdict
(`probes/symmetry_gate_corpus.py`, old vs new side by side).

**The runner (`53f5653`).** It had logged `200 1351644 ms` and written
"clean". `HANG_MS` (120 s) and `MEMORY_BUG_MB` (2 GB of peak growth in ONE
request) are findings whatever the status; every child runs inside a Windows
Job object with `--mem-gb` (default 6) so the KERNEL refuses the allocation
and the child dies instead of the box; a child that dies AT its ceiling is
filed as a `memory` finding where the same MemoryError from an uncapped child
still means "the box gave up".

## Where the risk is

1. **The two gates refuse something correct.** Both are necessary conditions
   of a true symmetry, so a false refusal needs a numerical miss: the extent
   gate compares `bounding_box()` corners at `rel_tol x largest extent`
   (0.043 mm on the cap) — build123d's `optimal=True` box was tight on every
   probed body, but a loose box on some surface kind rotated by an odd angle
   would fail a symmetric part; the vertex gate uses `distance_to` (boundary)
   OR `Solid.is_inside`, sampling every k-th vertex. Ten live designs and the
   three test shapes agree with the boolean; nothing else was measured.
2. **The vertex gate's cost.** Roughly +0.3 to +0.9 s on the heavy designs
   (sat-side-panel 2.7 -> 3.6 s, bottle cap 0.67 -> 1.3 s), paid on a
   rebuild whose leaf geometry changed while a spec is set (the result is
   cached on the spec signature). A reviewer may want the gate skipped for a
   single solid (the boolean was never the problem there) or the distance
   queries batched.
3. **`cut()` vs `-` changed the proof's arithmetic on compounds.** For one
   body they are the same call. For a multi-body result the old `-` gave a
   wrong non-zero residue on an exactly symmetric overlapping compound, so
   any multi-body design that used to fail its symmetry spec for that reason
   alone would now pass — none of the ten live ones is multi-body.
4. **The memory oracle reads a PEAK.** `grew_mb` is the peak working set
   after minus before, so a request that stays under the process's earlier
   high point reads 0; the first runaway in a child is seen, later ones only
   by the ceiling. The Job ceiling is Windows-only (`JobCap.available`), and
   `hit` is `peak >= 0.95 x cap`.
5. **OCCT under a refused allocation answered 200.** Under the 6 GB cap the
   original request still completed in 55 s with the "Boolean operation
   unable to clean" warning and a plausible verdict. The product does not
   know an allocation was refused inside the kernel; whether a degraded
   boolean can come back as a "successful" wrong solid is not measured
   (recorded in §10 as P2).
6. **Shell / Mirror (`ac5c11d`)**: the shell bound applies ONLY to the closed
   hollow in the INSIDE direction, per lump, with an axis-aligned box (fires
   LESS on a tilted body); the mirror guard reads "symmetric about the plane"
   as "the sphere face's centroid lies on the plane"; the seed path's guard
   was measured on `body - image` directly, not through `pattern.mirror(seed)`
   on a Document; the mirror gauntlet asks `pattern._part_ball_through` to
   decide `allow_failure` (the test leaning on the code it tests).

## Do not re-report

- **Shell OUTSIDE on the clipped ball still segfaults from 1.2 mm up.** Known,
  measured, §10 P1: no geometric bound applies to growing a body, every
  intersection-join flag combination crashes (`probes/shell_offset_flags_probe.py`).
- The kernel cannot shell the clipped ball at ANY thickness (OCCT, recorded in
  the shell gauntlet).
- `bugs/` is untracked except `journeys-stdout.log`; fixed folders live in
  `bugs/fixed/` so the runner's signature de-duplication cannot mask a recurrence.
- `rotational_symmetry_order` (the discovery loop, up to 24 booleans) is
  unchanged and un-gated: nothing in the app calls it (author / MCP only via
  `is_rotationally_symmetric`).
- The pre-existing red browser tests (§10) are untouched; no frontend change,
  no `ui v` bump in either commit.

## Ground rules

Ruff zero; fast tier `1700 passed` at `53f5653` before the last test file's
own fix (`1701` with it: `tests/test_journeys.py` 20 passed). Probe first;
anything that can eat memory runs under `probes/memcap.py --gb 6`. Fix in the
same chat, then this file -> `Status: NOTHING PENDING` (next review takes
REVIEW-QUEUE section 9, Trace image).
