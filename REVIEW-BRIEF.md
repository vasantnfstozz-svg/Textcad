# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — review `fb0b8c8` (one commit, base `cd50642`): the
> Shell tool, P4's fifth tool on the framework. New code, never reviewed.
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

## The range: `fb0b8c8` — Shell (specs/shell.md)

Fusion's Shell as ONE op that eats its body: the picked flat faces removed,
walls of one thickness around the cavity, Direction Inside / Outside, sharp
corners. The selection is a SET of faces toggled by clicking; the server
decides add-or-remove (`face_toggle`). Read the spec first — it names the
decisions made without the user (no ghost, no Both, flat openings only) so
they are not re-reported.

Files, in the order to read them:

- `sketch.py` — `shell`, `shell_refs`, `opening_face`, `assert_flat_opening`,
  `shell_openings` (+116, after `hole`).
- `toolplan.py` — `plan_shell`, `_face_words` (+82) and the `_PLANNERS` entry.
- `static/js/shell.js` (93 lines, new) and `static/js/tool.js` (+12: the
  `bodyRow` branch in `open()`).
- `blocks.py` (`shell_out` is now a lazy wrapper over `sketch.shell`; the
  `_b3d_offset` import went), `document.py` (MODIFIERS entry), `author.py`
  (the note), `studio.py` (`ToolPlanReq.faces`, `.direction`),
  `static/index.html` (the panel, `main.js?v=184`), `main.js`, `ribbon.js`.
- Evidence: `probes/shell_probe.py`; tests `tests/test_shell_tool.py` (24),
  `tests/test_shell_gauntlet.py` (3), `tests/e2e/test_shell_tool.py` (4).

## Where the risk is

1. **The op's volume oracle.** `shell` refuses an UNCHANGED result (walls
   meeting in the middle — the kernel calls it a success) and an open shell.
   The check is `abs(v_out - v_in) <= _CUT_FLOOR_MM3` plus, for Inside only,
   `v_out >= v_in`. Is there a body where a real Inside shell leaves the volume
   within a millionth of the original? Is there an Outside case where the
   kernel returns garbage that is neither unchanged nor open? Probe, do not
   reason.
2. **The closed hollow is a boolean difference** (`solid - offset(solid, -t)`
   / `offset(+t) - solid`), because `offset()` without openings returns the
   offset SOLID. `inspector.closed_shell` passes a two-shell solid (probed);
   check that `Document`'s health / pieces logic does not call the inner void
   a second piece on any corpus body, and that `result_pieces` stays 1.
3. **The toggle keys faces on the INPUT body** (`_shape_key` of the resolved
   face). A click arrives from the PREVIEW body (the hollowed one) and goes
   through `_face_of(part, toggle, body_id)` — surface gap ≤ 0.02 mm and a
   normal within ~8°. On a thin wall (t = 0.5) the preview's inner faces sit
   0.5 mm from the outer ones: can a click on an INNER cavity face resolve to
   an OUTER face and toggle the wrong one? The e2e clicks a wall band on
   purpose; the review should try the inner face.
4. **Names and picks in one list.** A stored `"top"` and a pick of the same
   face de-duplicate by `_shape_key` at rebuild, but the PLAN's toggle compares
   keys too — a legacy row with `open_face: "top"` and a click on the top face
   should CLOSE it (`faces: []`), and the op then reads `faces=[]` over the
   stale `open_face` (a list beats it). shell.js sends `open_face: null` once
   the plan has spoken — confirm `Document.edit_many` accepts a `None` for a
   key the signature knows, and that the tree never shows `[object Object]`
   for the `faces` param (Mirror's lesson — an object param reads as its
   parts).
5. **`bodyRow` in `tool.js open()`.** A tree row of a SOLID opens a face-only
   tool with `center: null`. Every other face tool (Hole, Extrude's face mode)
   is untouched because the branch is gated on `spec.bodyRow`; confirm the
   gate holds when the selected row is the tool's OWN preview (`shell1` while
   its panel is open — the modal guard should refuse the second open anyway).
6. **`planExtra` sends `faces` from `st.plan`, the LAST settled plan.** The
   framework's `replan` chain serialises requests; a plan REFUSED mid-session
   (`ok: false`) leaves `st.plan` as it was, so the next click resends the
   old set — right. But `refresh` (Direction changed) calls `sh.replan()` and
   the framework then calls `apply()` too: two rebuilds for one change, or one
   coalesced? Measure, do not assume.
7. **Sentences on the AI path.** `author.py` still describes `faces` by name
   only; an AI that writes `open_face` keeps working. Check the lint that
   rejects unknown op params accepts both forms and that a `faces` entry of an
   unknown NAME fails the feature with `named_face`'s sentence, not a stack.

## Ground rules

- Reproduce by measurement or a red test before fixing; kernel probes go
  under `probes/`. The gauntlet (`tests/gauntlet.py`) is the corpus.
- Fix in the same chat, smallest change, covering tests, commit, push,
  restart the user's server (backend). Then set this file to NOTHING PENDING
  and write the §7 P4 done-note for Shell in LAUNCH-PLAN.md (stamp it) with
  the review's findings, the way Mirror's note reads.
- Never `--fix`. One reviewer.

## Do not report (decided, see the spec)

- No ghost for Shell (a cavity cannot be drawn by growing an outline; the
  box follows the drag, the kernel's hollow appears on release — Fillet's rule).
- Fusion's **Both** direction and its second thickness: deferred, §10.
- Curved faces cannot be openings: the kernel refuses (`probes/shell_probe.py`
  §8); the picker never offers one, the op says why for the AI path.
- Sharp cavity corners (`Kind.INTERSECTION`): Fusion's behaviour; a fillet
  afterwards rounds them. The user's "no sharp internal corners" rule is a
  shop rule for THEIR parts, never a software rule.
- A `body_id` naming nothing falls through to the newest solid: `_pick_body`'s
  rule for every face-mode plan, tested as such.
- CRLF warnings on the touched files: the checkout normalises on commit.
