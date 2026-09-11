# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING.** Review the range **`b78dc1f..HEAD`** (code commits
> `5dc7817` and the wording fix after `e9ebd0d`): **LAUNCH-PLAN P5 — the AI
> uses the tools.** Base for probes: `HEAD`. Files: `author.py`, `studio.py`, `static/js/chat.js`,
> `static/css/studio.css`, `static/index.html` (ui v194),
> `tests/test_author_steps.py` (new), `tests/test_tree.py`,
> `tests/test_tab_reuse.py`.
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

## What the commit does

The chat's design path no longer authors a whole tree in one JSON answer.
`author.author_steps(doc, request, model, on_step, guard)` lets the model
reply ONE step at a time — `{"add": {...}}`, `{"edit": {...}}`,
`{"remove": "id"}`, `{"done": true, "spec": {...}}` — and `_apply_step`
pushes each through `Document.add(strict=True)` + `lint_tree(final=False)` +
`rebuild`, then judges it: a refusal or a red feature (new OR previously ok)
restores the `to_data()` snapshot taken before the step (`_restore`) and the
model hears the sentence. `done` runs the final lint (the blob rule), sets the
spec through `_spec_of`, and is refused while `rebuild()` is not ok. The loop
gives up after 3 refusals in a row or 40 steps. `author_design` is now this
loop on a fresh document (MCP `design_part`); `_to_document` stays for MCP
`build_design`.

`studio.py`: intents `create` and `add` start a JOB (`_start_job` →
`_run_job` in a daemon thread; `JOB_THREADS=False` runs it inline for tests).
`create` opens a new tab WITHOUT activating it and builds there; `add` takes
ONE `_snapshot()` on the active tab and, when the job gives up, restores
`job["before"]` and `_unsnapshot(e)`s. Each kernel step runs inside
`_step_guard`: the new re-entrant `_KERNEL_LOCK` (also taken by
`_rebuild_and_mesh`) plus an `_INFLIGHT` marker, so a segfault in a step is
attributed and `_persist_session` never checkpoints a half-applied step.
`GET /api/chat/job/{id}` returns log/done/reply + `_doc_json()` read under the
lock. `chat.js` polls it every 0.7 s, prints each step (`.msg.step`), emits
`doc-updated` on every new step (tab strip), `loadMesh()` when the ACTIVE
document's signature changed, and holds the busy overlay for `add` jobs.

## Where the risk is (look here first)

- **Concurrency.** The job thread mutates a tab's `Document` while POSTs from
  the browser run in FastAPI's threadpool. The lock covers rebuilds and the
  job's steps, not every read (`_doc_json` in other routes, `/api/model`
  tessellation, `/api/tabs/*`). An `add` job holds the busy overlay, but
  nothing server-side stops a second POST on that tab (a second chat, an MCP
  edit, the 3-second poll's GET). Undo-stack interleaving on the `add` path if
  the user does edit meanwhile.
- **The restore road.** `_restore` swaps `doc.features`/`doc.spec` from
  `Document.from_data` but keeps `rollback`, `_geom_version`, caches on the
  old object; `_run_job`'s give-up path replaces `e["doc"]` wholesale instead.
  Are `hand_edits`, `dirty`, `clean_hash`, `pending` right after each?
- **What the model is told.** `_built` reads `doc._parts[f.id]` and
  `doc.warnings` filtered by `f.id in str(w)` (substring match on ids like
  `b`). `_first_problem` reports the first red feature, which after a
  suppressed/struck feature may not be the one the step broke.
- **The step that changes the doc name** (`name` honoured while
  `doc.features` is empty — including on an `add` job on an empty tab).
- **`_spec_of` accepts a spec at `done` and `doc.spec.setdefault("n_solids",
  1)`**; a design with `bodies > 1` and a model that never says done.
- **Cost bound.** 40 steps × a growing message list; no per-job token or
  wall-clock cap. The real model (OpenRouter, claude-sonnet-4.5) ran the
  protocol ONCE live: an 8-step mounting plate, no refused step — so the
  refusal/undo/give-up roads are proven only by the 19 scripted tests.
- `JOBS` pruning (`del_ids = list(JOBS)[:-20]`, only finished ones) and a
  job id that is never found by the browser after a server restart.

## Ground rules

- Probe with `Document.from_data`, never `/api/open` (it pushes a version).
- `tests/fixtures/` only; the user's `designs/` are `-m library`.
- Reproduce before fixing; smallest fix; a test per finding; the fast tier
  green; restart the user's server if `studio.py` changes (it is running
  `5dc7817` now); bump `main.js?v=` if `static/` changes (currently 194).

## Do not re-report

- R10 line delta: +899 / −151. Known — P5 is new capability, not a
  refactor; the plan note records it.
- The intent model reading "design a washer" as an EDIT while the active
  tab already holds a washer (it set a radius to the value it had). That is
  the intent prompt's judgement, pre-existing, and no code path of P5.
- `lint_tree(final=False)` skipping the blob rule per step is deliberate
  (tested: `test_the_blob_rule_judges_the_finished_design_not_the_second_step`).
- The pre-existing red `tests/e2e/test_tree_delete.py` (five, measured at
  667ccc0), and everything on LAUNCH-PLAN §10's open list.
