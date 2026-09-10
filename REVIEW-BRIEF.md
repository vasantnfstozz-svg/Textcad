# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: NOTHING PENDING** — `fafe983` fixed four findings and none was a
> P0, so there is no second round to run. The next `code review` goes to the
> queue.
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

## Just done: section 3's FIX PASS, re-reviewed (fafe983)

The section 3 fixes (`f63ba5a`) closed a P0, so the house rule sent a second
chat over the fix commit itself. It found **four more doors open, all four
fixed**, 8 new tests, fast tier 1288 green. Measured first in
`probes/version_review_probe.py`; the full record is `REVIEW-QUEUE.md`'s done
log, section 3, round two.

Two of them were the SAME P0 through another door — a save landing on another
design's version tree — which is why this round mattered:

- the identical-content escape hatch bound a **second tab** to a file another
  tab already owned, after which either tab's save silently overwrote the
  other's file and hung its version off the other's latest;
- a design file deleted in Explorer leaves `<slug>.history/` behind, and a new
  design of the same name **appended itself to that tree**;
- `can_repair()` said yes for an index from a **newer build**, and the new
  panel button then replaced it with a guessed linear chain;
- a cloud-sync conflict copy (`v3 (2).json.gz`) took `repair()` down with an
  **AttributeError** whose text reached the user.

No P0 was fixed this round, so no third pass is due.

## Review this

| | |
|---|---|
| **Status** | **NOTHING PENDING** |
| **Next** | `REVIEW-QUEUE.md` **section 4 — Booleans and transforms**, the first status-board row still marked TODO. Read the queue's header, its shared rules, section 4 and the output format |
| **Frontend** | `ui v181`, `css v40` — unchanged by `fafe983` (backend only) |

## Ground rules (unchanged, for whichever commit comes next)

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. The whole fast
  tier is 1288 (`python -m pytest tests -q --ignore=tests/e2e`).
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
  five rounds), section 2 (document core) and section 3 (version tree, two
  rounds). Report a fix that is WRONG or INCOMPLETE, never an original defect.
- **The sketcher's two-part ordering rule and `_overlaps` failing open.** An
  outer is composed before anything nested in it, AND material before a cut
  that OVERLAPS it without containing it. Never collapse it to one part;
  removing either half reintroduces a measured P0.
- **Refusing to open a file with an unknown op** — settled (section 2).
- **A struck row's dimension rows stay editable** while its ✎ is withheld.
  Deliberate: ✎ reopens a live tool with a preview.
- **The tree's folded-boolean rule and `delta_features`' folding rule are two
  copies of one rule.** No arrangement was found where they disagree.
- **The first card in the sketch tree shows a fixed `add` badge**, stricter
  than the backend now needs. Deliberate.
- **A full circle offers no QUADRANT snaps.** Deliberate.
- **`/api/save` refuses three things** (fafe983): a file a DIFFERENT tab owns,
  a different design's file whose content differs, and a slug whose
  `.history/` still holds versions after the file was deleted by hand. All
  three are deliberate, all three are tested, and the identical-content
  escape hatch that remains is guarded by the tab-owner check.
- **`repair()` refuses a FOREIGN index** (a schema this build does not
  understand) and only treats exact `v<N>.json.gz` names as snapshots.
  Deliberate; a conflict copy is left on disk untouched.
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
- **The versions routes answer refusals with HTTP 200 and an `error` key**
  rather than through `_refused`. Local convention across that whole group;
  `postJSON` surfaces it. Not a finding.
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
