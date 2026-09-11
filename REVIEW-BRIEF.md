# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING.** Press Pull (`af46160`) was reviewed and closed
> in one round at `9584b39`. The next `code review` therefore goes to
> `REVIEW-QUEUE.md` and takes the first TODO row of the status board:
> **section 7, Extrude as a whole module (with loft and sweep)** - which is
> the natural next read anyway, since Press Pull lives in `extrude.js`.
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

## What the last review did (round one of `af46160`, closed at `9584b39`)

**1 finding, 1 fixed, 0 rejected, 0 deferred. P2. No live design affected.**

The router's **curved-face branch was the only command press in the app that
returns without ending what was pending**, so the previous button's pick
stayed armed behind the sentence and swallowed the next click.

Repro, red before the fix: click a cylinder's side, press **Create Sketch**
(it arms a plane pick and opens no panel, so there is no modal lock and the
ribbon lets the next button through), then press **Press Pull**. The chat says
"a curved face would offset it ... Click a FLAT face to pull it" - and the
plane pick is still armed underneath, hint bar and glass origin planes and
all, so the very click that sentence asks for drops the user into the SKETCH
EDITOR. The same hole stranded an Extrude / Revolve / Hole profile pick and
the row waiter `ca5725a` had closed for every other tool.

Fixed where it cannot drift: `tool.js` `open()`'s own two-line preamble became
`endPending()` (`cancelPlanePick` + `cancelTool`, idempotent), and
`openPressPull()` calls it once - after reading the selection, before routing.
The branches that route reach it through `open()`; the branch that only speaks
reaches it directly; a fourth branch added later cannot reopen the hole.
+1 browser journey (5 in `tests/e2e/test_press_pull.py`), verified red with
the fix reverted. ui v191.

**Cleared without a change** - all four risks the round-one brief named:
the two selection reads cannot disagree (nothing in `open()`'s preamble clears
a pick or the tree row, and `releaseIso` is async and only live under a lock
the ribbon blocks); no import cycle (nothing below `extrude.js` imports it);
`OP_ICONS` / `TOOL_NAMES` are read by key in exactly three places and
enumerated nowhere, and `press_pull` is not a backend op; the e2e curved-face
pick was stable over three runs.

## For whoever picks up REVIEW-QUEUE section 7 (Extrude)

- `endPending()` is new in `tool.js` and shared by every tool. It is the whole
  teardown a command press owes: a pending plane pick, a prior session's
  gizmos, its profile pick and its row waiter. Any OTHER code path that starts
  or refuses a command without going through `open()` owes the same call -
  worth a grep while section 7 is open.
- Do not re-report: the name "Press Pull" over the plan's "Push/Pull"; the
  profile and edge routes beyond "flat face of a body"; an edge clicked AT
  Extrude's command-then-select prompt not routing to Fillet; no Offset Face
  for curved faces. All four are settled in `specs/press-pull.md`.
- Also settled, and NOT a Press Pull finding: `currentSelection` ranks a
  SKETCH tree row above a curved-face pick, so a row selected earlier hides a
  curved face clicked later. That order is deliberate and documented
  (`ca5725a` moved only the non-sketch `feature` row below the picks); Extrude
  behaves identically from its own button.
- Everything in LAUNCH-PLAN section 10 stands unchanged (world-coordinate face
  picks on a stepped body, `solids()` offering intermediate rows, the one-lump
  gauntlet corpus, Rotate's legacy pivot).

## Ground rules (unchanged)

- Reproduce by measurement or a red test before fixing; kernel probes go under
  `probes/`. The gauntlet is the corpus.
- Fix in the same chat, smallest change, covering tests, commit, push, restart
  the user's server if the backend changed. Then the paperwork: this file ->
  NOTHING PENDING (or the queue row -> done), the plan stamp, memory.
