# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)

> **Status: NOTHING PENDING for a review chat — the work below was already
> reviewed as it was built.** 2026-09-17/19, at the user's explicit direction
> ("fix all p1s to p3s, fix all of them, using agents ... and again review
> until we running out of bugs"), LAUNCH-PLAN section 10 was worked by
> file-fenced agents in worktrees, and **every fix pass was re-read by a fresh
> reviewer before it was merged**. 112 commits, base `337f947`.

## What the sweep did

Six streams, each fixed then re-reviewed to exhaustion:

| stream | files | rounds | stopped because |
|---|---|---|---|
| picture tracing | `imgtrace.py`, `studio.py` | 4 + one running | still finding; round 5 in flight |
| shell guards | `sketch.py`, `kernelguard.py` | 3 + one running | still finding; round 4 in flight |
| op catalogue / document core | `blocks.py`, `document.py`, `author.py`, `pattern.py` | 5 | round 5 found no P0; severity trending down |
| compressor meanline | `meanline.py`, `impeller.py`, `samples.py` | 4 | a P0 in each of rounds 1-3, none in 4 |
| tool panels / browser | `static/**` | 4 | yield 8, 4, 4, 2 - round 4 recommended stopping |
| trim speed | `sketch_trim.py` | 2 | identity proved structurally, not empirically |

## The ten P0s, and the one thing they have in common

Every one was found by a **reviewer re-reading a fix pass that was already
written, tested and green** - never by the agent that wrote it. That is the
whole argument for the re-read rule and it now has ten data points.

1. The compressor's shaft bore was not a hole - blades fused over it, 67.266
   mm3 inside a 2 mm bore, `ok=True`, watertight, `health []`, symmetric. The
   commit an hour earlier had turned that band's loud crash into this quiet
   wrong body.
2. A wheel published an `exit_width` it did not have - 17.29 mm against a
   measured 12.480, 39% wrong on the number that sets what the machine flows,
   handed to an AI through MCP.
3. A wheel published an inlet eye that is solid metal - a 112.30 mm2 ring
   where the passage is 3.51 mm2, on an ordinary 5 g/s blower (Mach 3.4).
4. The published blade angle is not the angle in the metal - up to 77.6 deg
   out; at one blessed backsweep the blade leans the other way.
5. `sketch {"offset": null}` built silently at Z = 0 and `{"offset": true}` at
   Z = 1, both green.
6. `move {"x": true}` moved the body 1 mm, green - invisible to every census
   because a move does not change a volume.
7. A sweep's path was not in the rebuild signature: editing the rail left the
   solid at 1570.80 where it must be 3141.59, and **two documents were served
   one solid** - one design handed another design's geometry.
8. `_pull_apart` measured in one direction only: a vertex of the BIGGER loop
   landing mid-edge on a smaller one walked through, giving `is_valid` True
   with `health` "not manifold/watertight (open shell)".
9. The art-centring shift landed off the 0.001 mm grid, so the final rounding
   re-crossed an outline `_uncross` had just cleaned - **reachable with every
   default**: a 1600 px picture at 8 mm builds 20.023 mm3 OCCT calls invalid.
10. The skin ceiling could only see a handback while the wall was THIN
    (`walls/(area.t)` IS `volume/(area.t)` when the body comes back whole): at
    t = 2.5 a perforated plate came back with 12.0 mm3 removed where 971.8 had
    to go - valid, watertight, health clean, green, saved.

## Two guards were caught REFUSING correct geometry

The opposite error, and just as bad: `_R2_MAX_MM` 2000 refused a 4-pole-motor
wheel the kernel builds sound; Trim refused **every word of two or more
letters** (32 of 90 printable characters) and died on any sketch containing an
`O`. Both fixed.

## The lesson worth keeping, in one line

**Every constant in a guard was calibrated on a corpus somebody chose. Ask
what that corpus held constant, and vary it.** That question alone found
findings 10, the plateau residual, and the coarea overlap. Both skin constants
are now documented as *overlapping populations no constant can separate*; what
makes the shell guard safe is a theorem (the deepest material must end up in
the cavity), not a calibrated number.

## What must NOT be re-reported

- The trace ground rule (`probes/imgtrace_r4_corpus.py`: old 55, r1 42, r2 54,
  shipped 58 of 74). Four rounds left it untouched on purpose.
- `_SHELL_NOTHING_HOLLOWED` = 1% and both skin factors: measured from both
  sides, populations overlap, do not re-tune.
- The fit box ignoring holes: the threshold-free alternative was built and
  picks the shipped box on all seven test faces.
- Closing Parameters when a tool opens: fixes one of three cases and takes
  away a panel the user opened.
- The frozen Parameters row while a cell is open: the deliberate trade that
  fixed the lost-typing bug.
- Everything else already carried in LAUNCH-PLAN section 10.

## What the next review should take

1. **The two rounds still in flight** when this was written - trace round five
   (`c30b2d9..46fc32d`: `imgtrace.settle`, the rewritten `_walks_through_itself`,
   and `_MEET_MM`, a refusal costing about 1 trace in 500) and shell round four
   (whose job one is rebuilding the user's 50 designs to prove none is newly
   refused). Read their reports first; neither had reported when this was written.
2. **The Sweep/Loft crash gap (P2, section 10).** `kernelguard` answers exactly
   two job kinds, `blend` and `shell`, so `BRepOffsetAPI_ThruSections` and
   `MakePipeShell` run in the LISTENER process, where an access violation takes
   the request, the tab and the process. Measured twice. `REVIEW-QUEUE.md`
   section 4 already records a loft doing exactly that (exit 139).
3. **A unit on every parameter in `author.op_catalog()`.** Two surfaces are
   blocked on it and both are recorded in section 10: the feature tree's
   editable rows and the Add Feature dialog both show raw millimetres, in an
   app whose status bar prints inches. The catalogue carries units on 48 of 122
   parameters, and the 74 without include real lengths sitting beside ones that
   have them. Fixing either surface in the browser without it would be an R1
   violation.
4. Otherwise the ranked remainder of section 10, which is now mostly Fusion
   parity features and polish.

## How the review starts

The user opens a fresh chat on Opus (`/model claude-opus-5[1m]`) and types only
`code review`. CLAUDE.md's "The review chat" section routes it.
