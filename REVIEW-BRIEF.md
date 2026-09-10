# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING** — the next `code review` takes `REVIEW-QUEUE.md`'s first TODO row.
>
> **How the review starts.** The user opens a fresh chat on Opus
> (`/model claude-opus-5`) and types only `code review`. CLAUDE.md's section
> "The review chat" tells that chat to read this status line: PENDING means
> review the range below; NOTHING PENDING means go to the queue. ONE
> reviewer, no `/code-review` command, no subagents; the fix pass follows in
> the same chat without being asked.
>
> That line never changes. Everything specific to this review is below.

---

## Just done: section 2, Document core and feature tree (6ea5546)

Five findings, **4 fixed, 1 rejected**, 7 new tests, fast tier 1271 green.
No P0, so no second round is owed. The full record — what was found, what
was fixed, what was checked and found sound, and the one rejection with its
evidence — is `REVIEW-QUEUE.md`'s done log, section 2.

**The rejection matters more than the fixes and must not be re-opened:** a
design file naming an op this build does not know is refused ON PURPOSE.
A version restore of one answers "cannot open it — it is still in the
history", and a restored session tab holding one is dropped while every
other tab lives. `op_params` returning `()` for an unknown op is about
walking the CATALOGUE without raising, not a promise that the file opens.
`test_an_unknown_op_is_refused_at_every_door` pins it.

---

## Review this

| | |
|---|---|
| **Range** | nothing pending. `6ea5546` is the last code commit and was itself the fix pass for section 2 |
| **Next** | `REVIEW-QUEUE.md` **section 3 — Version tree and session persistence** (`history.py`, `backfill.py`, `static/js/versions.js`, plus the tab/session and versions endpoints in `studio.py`), the first row still marked TODO. Data loss is the P0 class there and it has never been reviewed. A fresh Opus chat, `code review`, nothing else |
| **Then** | section 4, Booleans and transforms |
| **Frontend** | `ui v180`, `css v40` |

## Ground rules (unchanged, for whichever commit comes next)

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. The whole fast
  tier is 1271 (`python -m pytest tests -q --ignore=tests/e2e`).
- **A finding is a concrete input on which the code does the wrong thing**,
  with the exact click or data that triggers it. Order: P0 wrong geometry or
  data loss, P1 blocks the action, P2 daily annoyance, P3 polish.
- **The frontend must not re-derive backend facts** (rule R1).
- **Two banned failures:** a kernel exception reaching the user (OCP errors
  derive from `Exception`), and a "successful" invalid or empty solid.
- **Comments naming a date record a past bug**; do not report them as noise.
- **No fixes, no style remarks**; both linters run at zero.
- **ONE reviewer at medium.** On 2026-09-09 a fan-out ran ~46 Opus agents at
  xhigh and drained the five-hour limit; one reviewer at medium then found
  five real gaps. The agent count must be quoted to the user before any
  fan-out ever runs again.

## Output format

```
### F1 - P<0-3> - <one line>
- File: <path>:<line>
- Trigger: <the exact click or input>
- Expected / Actual: <one line each>
- Confidence: high | medium | low - <why>
- Evidence: <1-3 quoted lines>
```
then `### Checked and found OK` (up to 8) and `### Could not judge without
running the app` (up to 5). At most 15 findings; say so if fewer than 5 are
high or medium confidence.

## Already known — do NOT report

- **Everything in `REVIEW-QUEUE.md`'s done log** — section 1 (the sketcher,
  five rounds) and section 2 (document core). Report a fix that is WRONG or
  INCOMPLETE, never an original defect.
- **The sketcher's two-part ordering rule and `_overlaps` failing open.** An
  outer is composed before anything nested in it, AND material before a cut
  that OVERLAPS it without containing it. Never collapse it to one part;
  removing either half reintroduces a measured P0.
- **Refusing to open a file with an unknown op** — settled, see above.
- **A struck row's dimension rows stay editable** while its ✎ is withheld.
  Deliberate: ✎ reopens a live tool with a preview.
- **The tree's folded-boolean rule and `delta_features`' folding rule are two
  copies of one rule.** No arrangement was found where they disagree.
- **The first card in the sketch tree shows a fixed `add` badge**, stricter
  than the backend now needs. Deliberate.
- **A full circle offers no QUADRANT snaps.** Deliberate.
- **`blocks.resolve_face` picks by nearest centre**, so two coplanar faces
  sharing a centre resolve to the wrong twin. Queued, P1.
- **`sketch_trim.py` keeps its OWN copy of the composition rule** and refuses
  entity lists `_compose` now accepts. Queued, P1 — a build job, not a review.
- **Pattern's `_axis_face` guards with the bounding box `_face_of` dropped.**
  Queued.
- **A self-crossing polygon builds an invalid face and reports ok.** Queued, P2.
- **The arc-label doc guard is keyed by design NAME.** Queued, P3.
- **A suppressed final boolean promotes its TOOL to the result**
  (`_result_feature`). Queued, P1 — and `/api/feature/suppress` is not
  reachable from the UI at all, only from a script or the MCP.
- **`-m library` cannot collect** (duplicate basenames against `tests/e2e`).
  Tracked test-infrastructure item.
- Face MODE (`extrude_face`) opens on Join regardless of direction; Edit mode
  never rewires a combiner. Known.
- `feature_faces` answers nothing for a row whose whole body was MOVED after
  it. Pre-existing.
- The pre-existing red browser tests (`tests/e2e/test_tree_delete.py`, five)
  and the order-dependent revolve ring test.
- Lint-class output (unused names, two statements on a line, single-letter
  geometry variables).
