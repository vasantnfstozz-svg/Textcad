# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING** — `2d2e8a9` re-read section 5's fix pass and
> found two findings, neither a P0 (a guard that had taken a legitimate shape
> away, and a flag that defaulted to the optimistic answer), so there is no
> third round to run. The next `code review` goes to the queue.
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

## Just done: section 5's FIX PASS, re-reviewed (2d2e8a9)

`e35450d` closed a P0-class finding — the AI's positioning rule called
`polygon_plate` and `hex_plate` centred when they stand on Z=0, so every
`move` it computed for a hex body was half a thickness out — so the house rule
sent a second chat over the fix commit. It found **two findings, both fixed**,
4 new tests, fast tier 1377 green.

Both were in the fix pass's own new code, which is where the queue said the
risk would be:

- **P1: the new `cone` guard refused a funnel standing point-down.** The fix
  pass required a positive `bottom_radius`; OCCT builds `cone(0, 10, 20)` at
  2094.40 mm³, exactly the volume of the flipped cone that was still allowed.
  Both radii now only have to be ≥ 0.
- **P3: `spec_checked` defaulted to `True`**, so a document that had never
  been rebuilt reported a green "spec PASS" for geometry nothing had verified.

The brief's four other named risks were cleared BY MEASUREMENT — `_drilled`'s
volume floor (six orders of magnitude of headroom), `numeric_params`'
coverage, `plain_cause`'s collapse, and the `sides=6.0` widening. The full
record is in `REVIEW-QUEUE.md`'s done log, section 5, round two.

**Next up, when the user types `code review`:** the queue's first TODO row,
**section 6 — Measure and drive** (`measure.py`, `static/js/measure.js`, the
drive-a-dimension path), high effort.
