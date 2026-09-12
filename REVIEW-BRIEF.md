# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review `7a811b6..c11fd74` — P5b, the machine plays the
> user (LAUNCH-PLAN.md §7 P5b, §6 tier 4). Base `7a811b6`. One code commit.
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

## The commit

- `c11fd74` P5b: `tests/journeys.py` (the random-journey runner, ~800 lines),
  `POST /api/bug` + `BugReq` + `_bug_report_lines` in `studio.py` (~90 lines,
  and `/api/bug` added to `_JOB_OPEN_POSTS`), `static/js/bugreport.js` (fetch
  ring, error ring, the button), `snapshotPNG` in `viewport.js`, the button in
  `index.html` (ui v197, css v43), `tests/__init__.py`, `tests/test_library.py`,
  `tests/test_journeys.py`, `tests/test_bugreport.py`,
  `tests/e2e/test_bug_button.py`, `.gitignore` (`!bugs/**`, `bugs/journeys.log`).

## Where the risk is

This commit is a TEST INSTRUMENT plus one read-only route. The product's
geometry did not change. What can be wrong is the instrument lying:

1. **False negatives in the oracles** (`Journey.call`, `check_bodies`, the
   pair moves). `unhandled()` decides "leaked exception" by a regex on the
   `error` sentence; a leak worded without a class name passes. `check_bodies`
   looks at LEAF solids only (cost), so an intermediate feature that is green
   and unsound is not caught unless it is on screen. The undo oracle runs only
   inside `move_edit` and `move_undo_add`; a route that snapshots differently
   is not judged. `signature()` masks numbers and cuts at 80 chars, so two
   distinct bugs with the same opening words file as one folder.
2. **False positives** — a clean journey must stay clean: does any route
   legitimately answer 400 AND change the document (the runner calls that a
   bug)? Does `strike` + `restore` legitimately change `to_data()` anywhere
   (struck ancestors)? Does `rollback` + release legitimately move a volume?
   12 journeys × 30 moves over `empty`, `pump-impeller`, `esp32-remote` were
   clean; the e2e and library tiers are the other evidence.
3. **The child-process protocol** (`spawn`): exit codes 0/2/3/4 versus a
   Windows access violation (3221225477); the step log written BEFORE each
   request; a "broken runner" (exit 2) must never file a folder. A crash
   folder has no `before.tcad.json` by construction.
4. **`/api/bug`**: writes under `ROOT/bugs` from `doc.name` (slugged); decodes
   a data-URL of any size; `_doc_json()` inside the report under no lock while
   a job may be writing that tab (the route is deliberately in
   `_JOB_OPEN_POSTS`). It must never snapshot, rebuild or mint a version.
5. **`bugreport.js` wraps `window.fetch` for the whole tab** from
   `initBugReport()` (first init in `main.js`). A body that is not a string
   (FormData) is recorded as null; `/api/bug` itself is not recorded. The
   `msg` bus listener keeps every bot line — is anything sensitive said there?
6. **`tests/__init__.py`** changes the fast tier's module names to
   `tests.test_x`; e2e files stay rootless (their `from conftest import`
   depends on that). Both tiers collect (1841 / 197).

## Ground rules for this review

Reproduce before reporting: a false-negative claim needs a staged failure the
oracle misses (as `test_journeys.py` stages one it catches); a false-positive
claim needs a seed that files a folder for correct behaviour. Fix in the same
chat, smallest fix, test proven red first. Restart the user's server if
`studio.py` changes. Never `--fix`.

## Do not report (already in LAUNCH-PLAN.md §10 or decided)

- Values drawn at random instead of from the plan's safe range; measure,
  params, export and save routes not exercised; one circle/rectangle per
  sketch (§10 P3 row).
- The screenshot is the viewport canvas only (§10 P3 row).
- `bugs/journeys.log` is ignored while `bugs/**` is tracked — on purpose.
- The runner never calls `/api/save` or `/api/open` — on purpose (writes into
  designs/ and the real `.history/`).
- `test_library.py` reporting a red feature in a live design is the tier
  doing its job, not a finding about the tier.
