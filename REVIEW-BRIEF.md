# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **In a fresh chat on Opus (`/model claude-opus-5`), type exactly this:**
>
> ```
> /code-review high - read REVIEW-BRIEF.md first: it names the commit range, the base, and what not to re-report
> ```
>
> That line never changes. Everything specific to this review is below.

---

## The sketcher is CLOSED. Read this before reviewing it again.

Five rounds ran on `sketch.py`'s composition, 2026-09-09: 556a611, 6e2cae9,
5f65a7a, 13da90c, c489839. Rounds one to four each found a P0 **in the
previous round's fix**. Round five - one reviewer at medium - **cleared the
ordering rule itself** and found only gaps in the fix pass around it.

**The rule, in two parts. A sixth reader must not collapse it back to one:**

1. an outer is composed before anything nested inside it (a hole needs its
   material; an island survives its hole);
2. **material is composed before a cut that OVERLAPS it without containing
   it.**

A cut that still leads after both genuinely meets nothing, and only that one
is dropped - with a note saying so. Removing either half reintroduces a
measured P0 (2827.43 vs 2513.27; 1570.80 vs 1884.96; 4.3671 vs 7.6656;
78.5398 vs 22.3648 - all four are in `REVIEW-QUEUE.md`'s done log).

**What decides correctness, settled by reading the renderer:** the sketch
editor paints every entity ON ITS OWN - `add` fills GREEN, `subtract` fills
RED (`sketcher.js` draw3D). There is NO even-odd canvas fill; `assignModes()`
only assigns the modes, and only when the user edits. A green region the
kernel builds away is a P0.

**`_overlaps` fails OPEN (returns True when the boolean will not run).** That
is deliberate and the opposite of the safe direction elsewhere in the file: a
False answer leaves the cut leading, where it is dropped. Do not "fix" it.

---

## Review this

| | |
|---|---|
| **Range** | nothing pending. `c489839` is the last code commit and was itself the fix pass for round five |
| **Next real work** | **`sketch_trim.py`** - LAUNCH-PLAN section 10, P1. It keeps its OWN copy of the composition rule (`_compose_faces` l.223-229 composes in DRAWING order) and its own leading-cut refusal (l.372, l.424), so Trim computes a different profile from the builder and refuses entity lists `_compose` now accepts. Measured 2026-09-09: a Trim click deletes a green add the builder keeps, and Trim tells the user to delete their hole. The fix is for Trim to ASK `sketch.py` for the order instead of keeping its own - after which this file gets rewritten for that commit |
| **Then** | `REVIEW-QUEUE.md` **section 2 - Document core and feature tree** (`document.py` + `static/js/tree.js`), in a fresh Opus chat with the section's own paste line |
| **Frontend** | `ui v179`, `css v40` |

## The cost rule, learned the hard way on 2026-09-09

Round four was run as ten parallel lenses with a three-judge panel per
finding: about 46 Opus agents at xhigh before the user stopped it, 40-100x a
single review, against this repo's own token rules ("no agent fan-outs",
LAUNCH-PLAN section 9). It did find a P0 three cheaper rounds had missed, so
the shape is not banned - but it is only for a P0 in code that has already
failed repeatedly, **and the agent count must be quoted to the user before it
runs.** Round five found five real gaps with ONE reviewer at medium. Start
there every time.

## Ground rules (unchanged, for whichever commit comes next)

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. The whole fast
  tier is 1264 (`python -m pytest tests -q --ignore=tests/e2e`).
- **A finding is a concrete input on which the code does the wrong thing**,
  with the exact click or data that triggers it. Order: P0 wrong geometry or
  data loss, P1 blocks the action, P2 daily annoyance, P3 polish.
- **The frontend must not re-derive backend facts** (rule R1).
- **Two banned failures:** a kernel exception reaching the user (OCP errors
  derive from `Exception`), and a "successful" invalid or empty solid.
- **Comments naming a date record a past bug**; do not report them as noise.
- **No fixes, no style remarks**; both linters run at zero.

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

## Already known - do NOT report

- **Everything in `REVIEW-QUEUE.md`'s done log, Section 1, rounds one to
  five** - 38 findings fixed, 3 rejected, with their measured numbers. Report
  a fix that is WRONG or INCOMPLETE, never an original defect.
- **The two-part ordering rule and `_overlaps` failing open**, both explained
  above.
- **"The note is never rendered, so a dropped cut is silent" is REFUTED and
  measured.** Only `extrude.js` reads `f.notes`, but `Document.warnings`
  republishes every note (document.py:1211) and `tree.js renderWarnings`
  shows them in its info box.
- **The three findings deferred on purpose**, now rows in LAUNCH-PLAN section
  10: `sketch_trim.py`'s own copy of the composition rule (P1, the next job);
  a self-crossing polygon building an invalid face that reports ok (P2); the
  arc-label doc guard keyed by design NAME (P3).
- **The first card in the sketch tree shows a fixed `add` badge.** A leading
  cut is composable now, so the badge is stricter than the backend needs.
- **A full circle still offers no QUADRANT snaps.** Deliberate.
- **`blocks.resolve_face` picks by nearest centre**, so two coplanar faces
  sharing a centre resolve to the wrong twin. Queued, P1.
- **Pattern's `_axis_face` guards with the bounding box `_face_of` dropped.**
  Queued.
- **`-m library` cannot collect** (duplicate basenames against `tests/e2e`).
  A tracked test-infrastructure item, and the reason three of these P0s
  reached a live design uncaught.
- Face MODE (`extrude_face`) still opens on Join regardless of direction, and
  Edit mode never rewires a combiner. Known.
- `feature_faces` answers nothing for a row whose whole body was MOVED after
  it. Pre-existing.
- The pre-existing red browser tests (`tests/e2e/test_tree_delete.py`, five)
  and the order-dependent revolve ring test.
- Lint-class output (unused names, two statements on a line, single-letter
  geometry variables).
