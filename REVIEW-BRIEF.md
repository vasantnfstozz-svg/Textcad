# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — review commit `af46160` (Press Pull, P4's last tool)
> on base `274041e`. Round one. When it closes, the brief goes back to
> NOTHING PENDING and the next `code review` takes `REVIEW-QUEUE.md`
> section 7, Extrude — which is the natural next read anyway, since this
> commit lives in `extrude.js`.
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

## The range: `274041e..af46160` (one commit, 2026-09-11)

`af46160` — Press Pull, the plan's "Push/Pull naming" row and the seventh
and last tool of LAUNCH-PLAN P4. Spec `specs/press-pull.md`. **No new op, no
backend change, no kernel call** — the diff is +41 / −5 lines in `static/js`,
plus the spec and `tests/e2e/test_press_pull.py` (4 browser journeys, all
green; fast tier 1522 untouched; ESLint and Ruff at zero; ui v190).

What it does: Fusion's Press Pull is a ROUTER, not a tool with a dialog, and
so is ours. `extrude.js openPressPull()` reads the selection's kind once
(`tool.js selectionKind`, a new one-line export over `currentSelection`) and
starts the command that fits — a flat face or a sketch profile is Extrude
(`ex.open()`, face mode pulls the face), an edge is Fillet (`openFillet()`),
a curved face gets one chat sentence (Fusion's Offset Face does not exist
here) and no panel. Nothing selected falls through to Extrude's own
command-then-select prompt. `press_pull` is a ribbon key in `icons.js`
(marked "not an op") and first in Modify → Features (`ribbon.js`).

## Where the risk is

- **The route reads the selection once and `open()` reads it again.** Both
  go through `currentSelection(null)` with no explicit argument, so they
  should agree; check there is no path where the kind changes between the
  two reads (a `doc-updated` in flight, a pick cancelled by `cancelTool()`
  inside `open()` before `currentSelection` runs — note `open()` calls
  `cancelPlanePick()` and `cancelTool()` FIRST, and `cancelTool` may clear
  picks).
- **Circular import.** `extrude.js` now imports `fillet.js`; `fillet.js`
  imports `tool.js` and `viewport.js` only. Confirm nothing imports
  `extrude.js` from below it.
- **A ribbon key that is not an op.** `icons.js` OP_ICONS / TOOL_NAMES now
  hold `press_pull`. Check nothing enumerates those tables as the op list
  (grep found no `Object.keys(OP_ICONS|TOOL_NAMES)` in `static/js`; the
  tree, the author and the MCP were not touched).
- **One-command-at-a-time.** The ribbon wraps every button in `modalGuard`,
  so Press Pull refuses while a panel is open; the router itself calls no
  guard because it never opens a panel of its own — but it does `say()` a
  sentence in the edge and curved branches before / instead of a tool
  opening. Check the curved branch leaves no state behind (no lock, no
  pending pick).
- **The e2e curved-face pick** clicks the cylinder side at world (0, −20, 0)
  from the `front` view; if it is flaky on another machine, the test is at
  fault, not the tool.

## Do not re-report (known, in LAUNCH-PLAN §10 or decided)

- The name "Press Pull" over the plan's "Push/Pull" and the profile / edge
  routes beyond "flat face of a body" — decided in the spec, flagged to the
  user.
- An edge clicked AT Extrude's command-then-select prompt is not routed to
  Fillet (the prompt is Extrude's) — spec, "Nothing selected".
- No Offset Face for curved faces — said in the chat sentence; a later tool.
- Everything in §10 from the Move/Rotate reviews (world-coordinate face picks
  on a STEPPED body; `solids()` offering intermediate rows; the one-lump
  gauntlet corpus; Rotate's legacy pivot).

## Ground rules (unchanged)

- Reproduce by measurement or a red test before fixing; kernel probes go under
  `probes/`. The gauntlet is the corpus.
- Fix in the same chat, smallest change, covering tests, commit, push, restart
  the user's server if the backend changed. Then the paperwork: this file →
  NOTHING PENDING, the plan's P4 stamp, memory.
