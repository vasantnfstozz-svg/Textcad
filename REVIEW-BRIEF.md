# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — review `b99a24d` (one commit, base `667ccc0`): the fix
> pass of Shell review ROUND TWO. A **P0 was fixed again**, so this is ROUND
> THREE. Sections 3, 4, 5 and 6 each went to a round two, and rounds two of 3
> and 4 both found the SAME P0 through a further door — which is exactly what
> round two found here.
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

## The range: `b99a24d` — round two's own fixes

Round two of the Shell review (`667ccc0`) found 3, fixed 3, rejected 0. Read
`LAUNCH-PLAN.md` §7 "Shell done 2026-09-10", the *Round two b99a24d*
paragraph, first — the measured numbers are there, so none of it has to be
re-derived. The diff is +184 −6 over 6 files, and TWO of the three fixes are
again in files EVERY tool inherits.

Files, in the order to read them:

- `sketch.py` — `assert_every_lump_hollowed` (new, +51, before `shell`) and
  the one call at the END of `shell`, after the `closed_shell` check.
- `static/js/tree.js` — `readable` (new, mutually recursive with `namedParts`)
  and the list branch of `buildBody`'s final `else`.
- `static/js/tool.js` — two lines in `startPreview`.
- `static/index.html` — `main.js?v=186`.
- Tests: `tests/test_shell_tool.py` (+2), `tests/test_shell_gauntlet.py` (+9,
  the new multi-lump corner of the corpus).
- Probes: `probes/shell_round2_*.py` (6).

## Where the risk is

1. **The pairing in `assert_every_lump_hollowed` is nearest bounding-box
   CENTRE.** Measured sound for boxes standing apart, and an inside shell keeps
   the box exactly. Is there a body where it pairs WRONG — two lumps that are
   concentric or nested (a ring around a post, a lid over a base), a lump whose
   centroid moves a long way, an OUTSIDE shell thick enough to merge two lumps
   into one (then two input lumps map to the same output lump and its volume is
   counted twice)? A wrong pairing either false-refuses a good shell (section
   5's rejected-fix shape) or, worse, lets a block through.
2. **It runs AFTER the kernel, unlike its sibling.** `assert_every_lump_open`
   is a gate BEFORE the kernel because of section 4's lesson. This one cannot
   be — only the kernel knows whether a wall fits. But it calls `.solids()`,
   `.volume` and `.bounding_box()` on the RESULT, outside the op's `try`: can
   any of those RAISE on a result the kernel called a success (section 4: a
   raising property is not swallowed by `getattr`)? And what does it cost on a
   real 400-face multi-lump body, where `.volume` is a GProps pass per lump?
3. **The `outside` direction is guarded only by "unchanged" and "vanished".**
   The `v >= v_in` clause is inside-only, because an outside shell's walls are
   legitimately smaller than the body. Round one's P0 WAS an outside case.
   Probe outside on bodies the round-two probes did not: nested lumps, a lump
   that is already hollow, an imported STEP, a pattern of a shelled boss.
4. **`readable` in `tree.js` is mutually recursive with `namedParts` and has no
   depth or size limit.** Params come from a FILE. A deeply nested or
   self-similar stored form would recurse; a big one writes a very long string
   into a tree row. A sketch's `entities` is caught by an earlier branch today —
   is there any other param that is large, and does a cycle reach here at all
   (JSON cannot carry one, but `/api/feature/params` is not the only door)?
   Check the rendered length on the largest live design's fillet row.
5. **Clearing `lastGood` / `lastGoodPlan` in `startPreview`.** It is reached by
   `begin()` (both already null) and `changeProfile()`. Confirm no THIRD caller
   appears through a spec hook, and that a tool with `spec.settle` (Extrude's
   milder values, Fillet's radius ladder) still behaves when there is nothing
   to revert to on a just-switched profile — it must leave the red row that
   says why, never a silent nothing.
6. **The new gauntlet corner asserts `abs(lump.volume - v) > 1e-6` against
   EVERY input lump's volume.** On a pattern all lumps are identical, so that
   is one number; on a mixed pair it is two. Could a correctly shelled lump
   land within 1e-6 of some OTHER lump's input volume and fail the test for the
   wrong reason? And does the sweep still go red with the fix removed (it did:
   5 of them)?

## Ground rules

- Reproduce by measurement or a red test before fixing; kernel probes go
  under `probes/`. The gauntlet (`tests/gauntlet.py`) is the corpus.
- Fix in the same chat, smallest change, covering tests, commit, push,
  restart the user's server (backend). Then set this file to NOTHING PENDING
  (or PENDING again if another P0 falls) and add the round-three line to the
  LAUNCH-PLAN §7 Shell note.
- Never `--fix`. One reviewer.

## Do not report (settled in rounds one and two, or by the spec)

- Everything on `specs/shell.md`'s own decided list: no ghost, no **Both**
  direction (§10), flat openings only, sharp cavity corners, `_pick_body`'s
  fall-through to the newest solid.
- Round one's five findings and round two's three, unless the FIX is wrong.
- **Cleared by measurement in round one, do not re-derive:** the volume oracle
  over the whole thickness ladder in both directions; the closed hollow as one
  solid with a void; an inner cavity face unable to toggle an outer one;
  `shell` of a sketch profile failing with a sentence and NOT segfaulting;
  names and picks de-duplicating by `_shape_key`; `open_face: null` surviving
  `_clean` and `check_params`; `bodyRow` unable to fire on a sketch row.
- **Cleared by measurement in ROUND TWO, do not re-derive:**
  `assert_every_lump_open` keying openings against the input body's own faces
  is exact through `linear_pattern`, `polar_pattern`, `mirror`, a severed plate
  AND an imported STEP — zero lump-face keys missing, zero cross-lump key
  collisions, zero false refusals (`probes/shell_round2_probe.py`).
  `solid.solids()` never raises and answers 1 / 1 / 3 / 0 / 0 for a Solid, a
  Part, a Compound of 3, an empty Compound and a 2D Face. The NO-OPENINGS
  difference route on mixed lumps is refused by the kernel already, and
  `closed_shell` needed no per-lump version (a lump cannot come back an open
  shell while the others are fine — probed at t = 6 and t = 9). The framework's
  `st.input.kind === 'edges'` gate changes behaviour for Shell ALONE: only
  Fillet and Chamfer have kind `edges`, and only `plan_fillet` and `plan_shell`
  return an `edges` key at all.
- **`TOP_RIM` and the e2e click point.** Settled: a pick is stored and resolved
  by the FACE'S OWN CENTRE, and `_face_of`'s docstring records the measurement
  over 20 cases in `probes/face_of_revolve_probe.py` §3 — including an annulus
  and a U-shape, whose centres are off their material. The journey passes for
  the right reason.
- **`n <= 8` in the revert journey.** The honest cost is 3–5 and the loop it
  guards was 50 in 6 s; the margin is deliberate.
- **`tests/e2e/test_tree_delete.py` is 5 red.** Measured red at `667ccc0`
  itself in a clean worktree, so it is not this range. It is the delete /
  strike-out workstream; LAUNCH-PLAN §10's browser-tier P1 row carries it, now
  with the root cause narrowed.
- CRLF warnings on the touched files: the checkout normalises on commit.
