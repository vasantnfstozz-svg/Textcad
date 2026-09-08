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

## Review this

| | |
|---|---|
| **Range** | `bea3144..e2c93fe` - ONE code commit, `e2c93fe` (Extrude: a FACE sketch follows the drag - Join out / Cut in; the session's combiner is removed with `mode: 'strict'`) |
| **Already reviewed** | everything up to `e5ffb8d` (Fillet faces + tree rows). Its fix pass may sit UNCOMMITTED in the working tree (`toolplan.py`, `provenance.py`, `viewport.js`, two test files) - that is another chat's work, not this review's |
| **Effort** | high - small diff (+32/-6 source), but it changes what a drag DOES (which body a boss lands in) and how a session deletes, for every tool built on `tool.js` |
| **Branch** | `master` (no pull request - do not try to comment on GitHub) |
| **Frontend** | `ui v173`, `css v40` |

## What the commit does

The user exported a design and the other program said "3 solid bodies" and
refused to edit it. The STEP was honest (753c24c exports every body): two
bosses had been drawn on pocket floors and pulled up with Extrude's Operation
box left at **New body** - `tool.js open()` set `'new'` for EVERY sketch
profile, a face sketch included. Fusion's default for a profile that lies on a
body: pulled away it JOINS, pushed in it CUTS; New body is for a free sketch.

- **`static/js/extrude.js beforeApply`** (l.188): when the profile is a face
  sketch (`plan.into_sign` is set), the session is not an edit, the user has
  not touched the Operation box (`st.opUser`), Through all is off and the
  direction is one-sided: the effective sign (`Math.sign(dist)` times Flip)
  equal to `into_sign` selects `cut`, otherwise `join`; `sync(st)` follows so
  the Through row appears. Runs on EVERY apply while untouched, so dragging
  through the face swaps Join and Cut (Fusion does the same) and a plan that
  lands after the first apply corrects the first choice.
- **`static/js/tool.js`**: `session()` gains `opUser`; the Operation box's
  `onchange` sets it. `applyOp` and `unbuild` remove the session's combiner
  (and, on Cancel, the feature) with **`mode: 'strict'`**. The default
  `auto` mode REPAIRS the tree: `Document._orphan_sweep` takes a cut's tool
  prism and that prism's SKETCH with it, so switching Cut to Join, or Cancel
  in a Cut session, deleted the user's sketch and the extrude. Pre-existing;
  found by the new journey's phase 3.
- Tests: `tests/e2e/test_extrude_face_sketch_joins.py` (boss joins, pocket
  cuts, hand-picked New body kept + sketch survives the switch; Cancel of a
  Cut session keeps the sketch). `test_user_workflow.py
  test_extrude_never_auto_selects_the_sketch` now expects the join (one body).

## Where the risk is (the author's own list - check it, do not trust it)

1. **`mode: 'strict'` refuses when anything depends on the node.** In a fresh
   session the combiner is the tail, so nothing does - but is there ANY path
   where `applyOp` or `unbuild` runs with a feature downstream of the
   session's own combiner or feature (a plan landing late, a document change
   from the chat while the panel is open, a Pattern/Mirror session whose
   `featureId` is not the tail)? A refusal there returns HTTP 400 with
   `error`; `post()` does not throw on it, so the removal would silently not
   happen and the session state (`st.opId = null`) would lie.
2. **`into_sign` and Flip.** `intoSign` is the plan's; the box value runs
   along the arrow, which `setAxis` turns around when Flip is ticked. The
   OLDER cut-flip block right below (l.207) ignores Flip. Are the two
   consistent for a face sketch on a BOTTOM face (`into_sign = +1`) with Flip
   ticked - does the auto rule pick Cut for a distance that really goes in?
3. **The `opUser` reset.** Set once per session; `changeProfile()` (another
   profile chosen in the panel) keeps it. Should a new profile re-arm the
   default? `unlock()` does not clear it either (it runs before `session()`
   is created, so a new session starts false - confirm).
4. **Revolve, Loft, Sweep on `tool.js`.** They inherit the `strict` removal;
   Revolve's face sketch path has no such default rule (out of scope), but
   does any of them create its combiner NOT at the tail?
5. **`sync(st)` inside `beforeApply`.** extrude.js's `sync` clears
   `st.cutFlipped` when leaving Cut and unticks Through when not Cut; called
   mid-apply, before `params(st)` is read. Any order dependency with the
   cut-flip block that follows?
6. **A join that fails.** A boss pulled off a face whose profile touches the
   face boundary makes a fuse the kernel may refuse (zero-thickness wall).
   The extrude then builds and the FUSE row is red; `settle()` only looks at
   the extrude's health. What does the user see, and does OK say "created"?

## Ground rules

- **Read-only.** Do not start the server (port 8123 is the user's; a second
  listener there is a known trap). Do not run `tests/e2e/`. Nothing in Python
  changed; `C:\Python314\python.exe -m pytest tests/test_delete_repair.py -q`
  documents the sweep semantics `strict` avoids.
- **A finding is a concrete input on which the code does the wrong thing**,
  with the exact click or data that triggers it. Order: P0 wrong geometry or
  data loss, P1 blocks the action, P2 daily annoyance, P3 polish.
- **The frontend must not re-derive backend facts** (rule R1): `into_sign`
  and `target_body` come from the plan, never from JS.
- **Two banned failures:** a kernel exception reaching the user (OCP errors
  derive from `Exception`), and a "successful" invalid solid.
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

- Face MODE (a picked face, `extrude_face`) still opens on Join regardless of
  direction (`tool.js open()`, l.341); pulling a face inward with Join is a
  no-op fuse. Known, not this commit's.
- Edit mode never rewires a combiner ("changing the operation of an existing
  extrude comes later"). Known.
- The uncommitted working-tree changes to `toolplan.py`, `provenance.py`,
  `viewport.js`, `tests/test_fillet_tool.py`, `tests/test_face_provenance.py`
  belong to the e5ffb8d fix pass in another chat.
- The pre-existing red browser tests (`tests/e2e/test_tree_delete.py`, five)
  and the order-dependent revolve ring test.
- Lint-class output (unused names, two statements on a line, single-letter
  geometry variables).
