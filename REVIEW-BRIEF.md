# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** `8e0ac42..fa99902` — the three LAUNCH-PLAN
> §10 P1 rows — was built AND reviewed on 2026-09-16, in one chat, because
> the user asked for the fixes and two review rounds in the same breath.
> That is a departure from the usual split (Fable builds, a fresh Opus chat
> reviews) and the next reviewer should know it: the same reader wrote and
> read this code, so a fresh pair of eyes over `blocks.resolve_face` and
> `document._shift_face_picks` is worth more here than usual. Both rounds
> are in the range (`8cf6cf9`, `fa99902`). Otherwise the next `code review`
> goes to `REVIEW-QUEUE.md` and takes the first status-board row marked
> TODO: **section 9, Trace image.**
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

## What the last review found (2026-09-16, range `8e0ac42..fa99902`)

Three commits: `1a8d28f` the three P1 fixes, `8cf6cf9` review round one,
`fa99902` review round two. Seven findings in all, every one inside code this
range itself had just written.

**The pass itself.** A stored face pick could slide onto another face of the
same kind when a PARAMETER changed — thicken a 10 mm plate under a boss to
14 mm and 22800.0 mm3 was built where 18810.62 was asked for, every row `ok`.
The move half had been closed by carrying the delta; this half has no move in
it, so no carry can reach it, and a body-frame pick — what the plan row asked
for — does not answer it either. The pick now remembers the face's SIZE, which
the click already knew (the server measures every face's area for the
viewport's pick panel, so nothing is derived in the browser). `resolve_face`
narrows the same-facing candidates to the ones still that size, then distance
decides between them; it FAILS OPEN, so every design saved before today
behaves exactly as it did.

**Round one, 2 of 5 fixed there (3 were fixed as they were found).**

1. *The carry knew one of the three shapes a pick is written in (P1, silent).*
   `_shift_face_picks` shifted `face_center` and missed a Shell opening
   (`faces: [{center, normal}]`) and a picked EDGE (`edges: [{mid, faces}]`).
   Measured: moving the body 8 mm reopened a shell where the wall does not fit
   (6597.628 → 13005.31 mm3, red row) and rounded a DIFFERENT edge with every
   row still `ok` (12994.824 → 13016.398).
2. *The size tolerance had no floor,* so on a face under 0.25 mm2 it was
   tighter than its own two-decimal rounding and such a face could fail to
   match itself.

**Round two, 1 of 1 fixed — in round one's own fix.** Round one narrowed the
guard from `list | tuple` to `list` so it could assign into the seat by index,
which silently skipped a pick list handed over as a TUPLE — and round ZERO
would at least have moved the dicts inside one. The list is rebuilt now
instead of assigned into.

## What was verified

Fast tier **1827 passed** (from 1800). Browser tier **202 passed, 0 failed** —
green for the first time since 2026-09-05, and the second of the three P1s.
Library tier **101 passed**, all 50 live designs rebuilt. Ruff zero, ESLint
zero. ui v203.

Measured, not assumed: the new area pass costs **71 ms once per body** on
esp32-remote's 1266-face logo body (against the 261 ms face pass that already
ran) and is cached beside the shape; no two features of that design share a
params object, so the carry cannot double-shift one; and every flat face of
all nine bodies in `tests/gauntlet.py`, asked for by its own size and centre,
comes back as itself.

## Do not re-report

- **The gate fails open by design.** No stored size, or no candidate within
  tolerance, hands the candidate list back untouched. That is the safety
  argument, not an oversight: it is what keeps the user's 50 designs at
  yesterday's answers.
- **Old picks have no size and cannot get one.** A backfill would freeze
  whatever the old rule answered, including a wrong answer. LAUNCH-PLAN §10
  carries it as a P3 with that reasoning.
- **A face that changes size AND has a same-size neighbour is still a coin
  toss.** Same row.
- **`rotate`, `mirror` and `polar_pattern` stop the carry** — that is
  `_hands_on_the_move`, settled by the previous review and measured.
- **`tests/e2e/test_recovery.py::test_a_crash_inside_a_tools_own_step_closes
  _the_panel`** failed once on a page error in one full run of code that was
  green in the next, and passes alone. Recorded as the tier's own flake in the
  plan; not a finding.
- **The five `test_tree_delete.py` tests changed gesture, not promise.** They
  drive strike-then-delete because that is what the ✕ has meant since the
  2026-08-31 mandate; the engine underneath was measured unchanged
  (`probes/tree_delete_e2e_probe.py`).
