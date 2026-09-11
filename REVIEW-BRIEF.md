# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** The P5 step loop has been reviewed and fixed
> over seven rounds (`4041703`, `5975aad`, `bb0c4ab`, `231bf16`, `7d03e9c`,
> `5d2d431`; round seven found nothing). The next `code review` goes to
> `REVIEW-QUEUE.md` and takes the first TODO row of the status board —
> **section 8, Import STL and STEP** (section 9, Trace image, may share that
> chat).
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

## What the last review closed (P5 — the AI uses the tools)

Range reviewed: `b78dc1f..92bdeef`. Seven rounds, 20 findings, all fixed;
19 + 3 + 3 + 1 + 2 + 1 new tests (fast tier 1594 → 1623), ui v196. Every
finding was reproduced by measurement first (`probes/p5_*.py`) and every fix
is locked by a test proven RED on the commit it fixes (checked in a throwaway
worktree, not assumed).

The five that mattered most, all in the AI's "add to the design on screen"
road:

- `done` **wrote the model's spec over the user's own** (31 of the 50 live
  designs pin a size, 22 pin holes). A design that already exists now keeps
  its spec, and a spec its new geometry breaks is reported to the USER in the
  reply instead of being deleted to look green.
- **A correct step was undone and blamed** whenever some other feature was
  red: one red row locked the AI out of the design entirely. A step now
  answers for what it touched; `done` still judges the whole tree.
- The AI could **delete a feature the user built**, and the reply called it
  "one or more parameters". Removes are limited to its own steps; the reply
  is a diff.
- `{"add": ..., "done": true}` in one reply **finished the design with no
  final lint and no spec check** — two loose bodies reported as verified.
- A user edit landing mid-job **broke "one Undo takes it all back"**. A
  running job is the only writer on its tab now, and the job carries a clock
  so a slow model cannot hold that tab for ever.

## Known and deliberately left (not findings)

- `/api/tabs/switch` reads the document without the kernel lock, so switching
  TO a tab mid-step can flash one stale row for under a second before the
  next step corrects it. Taking the lock would block the switch for the
  length of a kernel step — and switching away is the user's escape hatch
  from a busy tab, so it must stay fast.
- `GET /api/model` still tessellates outside the kernel lock
  (LAUNCH-PLAN §10, "Two requests can be in the kernel at once").
- There is no Stop button for a chat job; the 300 s clock is what bounds it.
  §10 row.
