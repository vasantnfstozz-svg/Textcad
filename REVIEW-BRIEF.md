# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** Section 7 (Extrude, with loft and sweep) is
> CLOSED: round one fixed 6 findings at `dfcb73f`, and round two re-read that
> fix commit and fixed 2 more at `a8e96d9` (the loft refusal quoted one profile
> count for several sections; OK said "Extrude created" over an empty viewport
> when the new auto-cut ate the whole body). The next `code review` therefore
> goes to `REVIEW-QUEUE.md` and takes the first TODO row of the status board:
> **section 8, Import STL and STEP** (which may share its chat with section 9,
> Trace image, as the queue note says).
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

## What the last review did (section 7, Extrude: `dfcb73f` + round two `a8e96d9`)

**6 findings, 6 fixed, 0 rejected, 0 deferred. Two P1s in ops nobody had ever
reviewed. No live design was affected; all 50 rebuild unchanged.**

- **A loft blends ONE profile per sketch** and never said so. build123d chains
  every section's faces into a single loft, so two sketches of two circles each
  came back as ONE snaking solid of 1570.8 mm3 (the honest tubes are 3141.6),
  reaching outside BOTH sketch planes, green and silent. Refused now, in the
  same place section 4's kind gate lives.
- **`sweep` fed a solid BODY sweeps it face by face.** A 24 000 mm3 plate
  became a 178 000 mm3 six-lump blob — status ok, no problems, no warnings —
  and the plate was consumed. The Add Feature dialog pre-ticks the newest
  feature, so it was one click from the Create ribbon. The sketch-consuming
  MODIFIERS (extrude, revolve, sweep) are gated now, on SOLIDS rather than on
  `is_sketch` so a sketch of disjoint islands still builds.
- **A picked face pushed INTO the body did nothing, quietly** (the default
  behaviour of the most-used tool changed here) (plate 24 000,
  prism 9 600, join 24 000 — three green rows and no word): the drag-direction
  Join/Cut rule was written for face SKETCHES only. It runs in face mode now,
  and a join that adds nothing is named the way a cut that removes nothing has
  been since section 4.
- Three smaller ones: Through all threw the taper away while the box and the
  ring still showed the angle; a typed negative "Distance 2" was dropped; and
  Through all's into-the-body seeding was missing from Two sides, so the 2 m
  side ran into the air.

## What round two changed (already reviewed - do not re-report)

- The loft refusal names each section's own profile count.
- `okSession` now looks at the COMBINER the session added as well as the tool's
  own feature, so OK can no longer claim success over an empty viewport. The
  sentence for the tool's own failure is untouched (`Mirror was NOT built`).
- 3 more browser journeys: the auto-cut's target on a two-body design, the
  taper box under Through all, and OK's honesty after a too-deep pull.

## Where the risk is - read these four first

The two new guards are REFUSALS, so the risk is a false one: a shape that used
to build and now does not. The first two lines below are the widest blast
radius in the commit.

- `_check_modifier_input` is called from `document._eval`, so it runs for EVERY
  modifier feature on EVERY rebuild. It tests `n_solids(part) > 0`, deliberately NOT
  `is_sketch`: a sketch of disjoint islands composes into a Compound that is
  not a Sketch instance. Covered by a test, and all 50 designs rebuild.
- the loft gate counts `len(p.faces())` per section; a section with ONE face and
  inner wires (a ring) is still fine, which is what build123d supports.
- `_check_idle_booleans` now warns about `fuse` as well as `cut`. Zero of the
  50 saved designs trip it, but a legitimate "sink a boss fully into the body"
  join would now be named. It is a warning, never an error.
- `sync()` zeroing the taper box under Through all writes a box the user typed
  in. It only fires while Through all is ticked, where the server built straight
  walls anyway.

## Do not re-report

- The symmetric branch (`both=True`) skipping `_taper_offset_problem`. It was
  read, it is real, and NO profile could be constructed that reaches it
  (`_apex_cap` caps every case tried). Recorded in the queue's done log as an
  asymmetry, not a bug.
- The taper direction chain: measured clean this pass (`_straighten_face` does
  not flip the rebuilt normal anywhere in the gauntlet corpus).
- Everything on LAUNCH-PLAN.md section 10's open list, and the pre-existing red
  `tests/e2e/test_tree_delete.py` (five, measured at 667ccc0).
