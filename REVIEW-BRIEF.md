# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING** — Move and Rotate are CLOSED after two rounds
> (`2f1d776`). The next `code review` opens `REVIEW-QUEUE.md` and takes the
> first status-board row marked TODO: **section 7, Extrude**.
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

## What round two settled (2026-09-11, `2f1d776` on base `4ee5670`)

Four findings, four fixed, none rejected; no P0. All four sat in the ONE guard
round one added — `toolplan._place_input`'s "a body another feature is built
from is not a body to place".

- It counted a **face sketch** as a consumer, so 3 of the 50 saved designs had
  their only visible body refused (esp32-remote among them).
- It missed a consumer reading through a **struck row**, so the round-one P1 —
  a second copy of the body, the result flipping to it, every row green — was
  still live.
- It fired on the tool's **own session feature** after the first drag, so
  changing Rotate's Axis said "Rotate cannot start".
- Round one's rotate-default fix landed in `plan_rotate`'s `params`, which
  **move.js never reads**; the panel still opened a param-less rotate at 0°.

The guard now asks the question in `Document.consumed_ids`' words
(`_live_source` for the struck chain, `FACE_REFERENCE_OPS` skipped) and honours
`own_id`. Measured after: 0 visible bodies refused across the 50 designs.
Fast tier 1522, 7 of 7 Move/Rotate browser journeys, ui v189.

## Still open, on purpose (LAUNCH-PLAN §10, not review findings)

- A pick is stored in WORLD coordinates, so a rigid move can hand a STEPPED
  body the wrong same-facing face (§10 P1).
- `tool.js solids()` offers intermediate rows to Shell and the Target dropdown
  (§10 P3).
- The one-lump gauntlet corpus gap (§10 P2); Rotate's default pivot is the
  world origin (§10 P2, the user said not now).

## Ground rules (unchanged)

- Reproduce by measurement or a red test before fixing; kernel probes go under
  `probes/`. The gauntlet is the corpus.
- Fix in the same chat, smallest change, covering tests, commit, push, restart
  the user's server if the backend changed. Then the paperwork.
