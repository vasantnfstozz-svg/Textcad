# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `b17d626..275eeab` - two commits, the journey
> runner's clock and the shell result checks.
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

    b17d626..275eeab       (base b17d626, the paperwork for the kernel-worker review)

Two commits:

- `751db79` - the journey runner stops timing the hours the laptop slept, and
  asks the kernel's own budget what a hang is; 4 new tests.
- `275eeab` - a shell that hollows nothing is not a hollow: the walls are
  measured against the surface they came from; 13 new tests.

Touched by `275eeab`: `sketch.py` (+62/-3, the only product file),
`tests/journeys.py` (+41/-11), `tests/test_shell_tool.py` (+72),
`tests/test_kernel_guard.py` (+21/-3), `tests/test_journeys.py` (+70),
`tests/fixtures/my_part_5_mirror_body.brep` (new), four probes, four
`LAUNCH-PLAN.md` section 10 rows, two `bugs/` folders retired to `bugs/fixed/`.
No frontend, no `static/`, so ui stays v200.
Fast tier 1749 -> 1762, `-m library` 101, ruff zero, eslint untouched.

## What `275eeab` changes

**1. `shell_after_guards` asks OpenCASCADE for its own verdict.** It checked
`inspector.closed_shell(out)` - an edge census - and not `is_valid`. Read
through `inspector._try`, because `is_valid` is a property that can raise.

**2. `sketch.assert_walls_could_be_a_skin(solid, out, t, direction, walls)`,
new.** An inward shell's walls lie within `t` of the surface they came from, so
their volume is about `area * t`; more than `_SHELL_SKIN_FACTOR` (2.0) times
that and the result is refused as the body itself. INSIDE only; an outside
shell returns early.

**3. `tests/journeys.py replay()` can open a corpse.** When a folder has no
`before/doc/after.tcad.json` it opens the design `journey.json` names (or the
same name under `designs/`) and re-sends `steps` instead of `replay`.
`process-died` leaves `_REPLAY_BLIND`; `write_crash`'s report prints the
`--replay` line.

## Where the risk is

- **The skin ceiling is the one judgement call in this commit.** 2.0 against a
  measured ceiling of 1.056 (`probes/shell_wall_bound_corpus.py`: gauntlet
  corpus + the three committed crash bodies, nine thicknesses 0.2-8 mm, closed
  AND open). It is NOT a theorem - a mostly-concave surface has inner parallel
  faces larger than its outer ones, which is where the 1.056 comes from - so
  the question for the reviewer is whether any real body can exceed 2.0 and
  lose a correct shell. Shell's own history is three review rounds of guards
  that refused correct geometry, so this is the place to push.
- **`is_valid` is now load-bearing inside an op.** If OCCT ever calls a
  legitimate shell invalid, the op refuses where it used to build. The library
  tier (101, all 50 designs) is the evidence that it does not today.
- **The replay opens the LIVE design**, not a frozen one, for a corpse folder.
  It prints that it is doing so, but a replay whose design has moved on since
  the run is not the same repro.
- **A whole-journey replay re-sends every recorded step**, including any that
  carry ids minted per run. Only `tab-leak` is declared blind now.

## Cleared by measurement, not by argument

- The wrong result is real and reproduced: my-part-5's `j2_mirror` at a closed
  3 mm shell returns 413260.165 mm3 of 413262.875 - 2.709 mm3, 0.00066 per
  cent - valid, watertight, `health` empty. At 1.5 mm: `closed_shell` True,
  `is_valid` False.
- A volume FRACTION was measured out, not argued out: a 12 mm plate at 5.9 mm
  walls is 98.91 per cent of its body and CORRECT (0.72 of its skin), so any
  fraction threshold that catches 99.99934 per cent is within 1 per cent of
  refusing it. `area * t` separates them 0.72 against 2.72.
- Sound closed hollows measure 0.61-1.056 of their skin, sound open ones
  0.61-0.955, over the corpus at nine thicknesses.
- The two new shell tests are RED before the change (the 3 mm one builds and
  returns 413260.165; the 1.5 mm one builds an invalid solid) and green after.
- `-m library` 101 and the fast tier 1762: no live design loses a feature to
  either new check.
- s18884 is not a product bug: that shell is REFUSED by the kernel after 879 s
  standalone / 692 s through the API, under the 900 s budget, and the replayed
  journey files nothing.

## Do not re-report

- **The my-part-5 SEGFAULT itself.** `shell` open-bottom on that body kills
  OpenCASCADE at every thickness from 0.2 to 5 mm, and open-top at all but
  0.2. No bound fences it (the closed direction builds at some of the same
  thicknesses), so it is the kernel worker's to survive, which it does. The
  body is a fixture and the refusal is a test.
- **s18884 being filed at all.** It was the runner's 600 s ceiling under the
  guard's 900 s budget - the fifth of the class retired in `371c8e2` - and is
  now in `bugs/fixed/` with the measurement.
- **OUTSIDE shells not being judged by the skin ceiling.** Deliberate: their
  walls sit outside the old surface and were not measured. Section 10 P3.
- **`kernelguard`'s budget counting machine sleep** (section 10 P2, still
  open) and **the planetary-ring spin not being narrowed to an op** (P2).
- The 21 s margin between the 879 s refusal and the 900 s budget is recorded,
  not fixed; raising the budget makes the worst case worse and was left alone.
- The reviewer may of course say any of these calls was wrong.
