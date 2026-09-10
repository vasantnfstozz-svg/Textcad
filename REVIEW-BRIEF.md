# REVIEW-BRIEF.md - what the next code review should look at

> **How this file works.** It is written fresh after every code commit and is
> always about ONE review. The previous contents are REPLACED, so the file
> stays short and the review chat pays for one small read. Ship-check step 6
> refreshes it. (The from-scratch reviews of the OLD modules live in
> `REVIEW-QUEUE.md`, one section each; this file is for NEW code.)
>
> **Status: PENDING** — review `667ccc0` (one commit, base `fb0b8c8`): the FIX
> PASS of the Shell review. A **P0 was fixed**, so this is ROUND TWO on the fix
> commit — the rule sections 3, 4, 5 and 6 all followed, each time finding more.
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

## The range: `667ccc0` — the Shell review's own fixes

Round one of the Shell review (`fb0b8c8`, specs/shell.md) found 5, fixed 5,
rejected 0. Read `LAUNCH-PLAN.md` §7 "Shell done 2026-09-10" first — the
done-note carries the measured numbers, so none of it has to be re-derived.
The diff is small (+157 −8 over 6 files) but TWO of the three fixes are in
files EVERY tool inherits.

Files, in the order to read them:

- `sketch.py` — `assert_every_lump_open` (new, +28, before `shell`) and the
  one call in `shell`; the `try/except TypeError` in `shell_refs`.
- `static/js/tool.js` — TWO framework changes: the "keeps at least one edge"
  guard in `replanNow` is now gated on `st.input.kind === 'edges'`, and
  `settle`'s revert path now does `st.plan = st.lastGoodPlan`.
- `static/js/tree.js` — `isNamedParts` / `namedParts` (new) and the final
  `else` of `buildBody`.
- `static/index.html` — `main.js?v=185`.
- Tests: `tests/test_shell_tool.py` (+4), `tests/e2e/test_shell_tool.py`
  (+2 journeys, +2 constants).

## Where the risk is

1. **`assert_every_lump_open` keys the openings against the input body's own
   faces** (`_shape_key` of a face reached through the lump vs through the
   compound — probed equal on a 3-lump pattern). Is there a body where a lump's
   `.faces()` does NOT contain the resolved opening face object even though the
   opening lies on it — a located copy, a mirror, an imported STEP? A false
   refusal would block a legitimate shell, which is the exact shape of section
   5's rejected fix (the cone guard that took away a real funnel). Probe it on
   `mirror`, `polar_pattern` and an imported body, not just `linear_pattern`.
2. **`solid.solids()` on every input kind.** `shell` may be handed a Solid, a
   Compound or a Part. Does `.solids()` answer 1 for a plain Solid on all of
   them, and can it RAISE (the section-4 lesson: a raising property is not
   swallowed by `getattr`)? It is called OUTSIDE the op's `try`.
3. **The framework guard's new gate.** `st.input.kind === 'edges'` is Fillet
   and Chamfer only today (`ops: { edges: o.op }`). Confirm no other tool can
   reach `replanNow` with an empty `plan.edges` and a built feature and now
   ADOPT a plan it used to refuse — Fillet's own e2e is green, but check the
   `feature_toggle` and `face_toggle` paths that release every edge at once.
4. **`st.plan = st.lastGoodPlan` in the revert.** Every tool reverts. The
   gizmos are NOT redrawn there (only a tool with `refresh` replans, which
   today is Shell alone), so for Mirror, Fillet, Hole, Extrude and Pattern the
   handles keep describing the FAILED plan while `st.plan` now describes the
   good one. Is there a tool where the next apply, or `describe`, or
   `lastGoodPlan` itself, reads a field that the two plans disagree about and
   writes the wrong thing? And can `st.lastGoodPlan` be a plan from a DIFFERENT
   input (a changed profile, a moved Hole point) by the time a revert runs?
5. **The Shell journeys' new click point.** `TOP_RIM = [28.5, 0, 6]` closes the
   top face by clicking its 3 mm wall band. That works because the pick sends
   the FACE's centre, not the click point. Confirm the same is true for a face
   whose centre is off its material on a NON-box body (an annulus, a U-shape),
   or the test is passing for the wrong reason.
6. **The rebuild-count assertion** (`n <= 8`) in
   `test_a_refused_face_set_reverts_ONCE_and_does_not_loop`. Is 8 above the
   honest cost on a slow machine, and does the test still go RED if the revert
   fix is removed? (It did: 50 pushes in 6 s, 28 more in the next 3.)

## Ground rules

- Reproduce by measurement or a red test before fixing; kernel probes go
  under `probes/`. The gauntlet (`tests/gauntlet.py`) is the corpus.
- Fix in the same chat, smallest change, covering tests, commit, push,
  restart the user's server (backend). Then set this file to NOTHING PENDING
  (or PENDING again if another P0 falls) and add the round-two line to the
  LAUNCH-PLAN §7 Shell note, the way sections 4 and 6 read.
- Never `--fix`. One reviewer.

## Do not report (settled in round one, or by the spec)

- Everything on `specs/shell.md`'s own decided list: no ghost, no **Both**
  direction (§10), flat openings only, sharp cavity corners, `_pick_body`'s
  fall-through to the newest solid.
- The five findings round one already fixed, unless the FIX is wrong.
- **Cleared by measurement in round one, do not re-derive:** the volume oracle
  over the whole thickness ladder in both directions (no garbage passes); the
  closed hollow as one solid with a void (`pieces 1`, `closed_shell` true,
  `health []`); an inner cavity face unable to toggle an outer one (the
  `dot >= 0.99` test separates them even at t = 0.02); `shell` of a sketch
  profile failing with a sentence and NOT segfaulting; names and picks
  de-duplicating by `_shape_key`; `open_face: null` surviving `_clean` and
  `check_params`; `bodyRow` unable to fire on a sketch row (`volume = None`).
- A Direction change costing ONE EXTRA rebuild of identical params inside a
  held viewport (`refresh` replans and the `onchange` applies): read, measured
  harmless, no wrong output. Not worth a finding unless it is visible on a
  heavy design.
- `thickness: "2mm"` in a LOADED FILE reaching `float()` — `check_params`
  guards every API door, files never come through it, and that is every op's
  behaviour, not Shell's.
- `resolve_face`'s nearest-centre match having no gap check inside the op: it
  is the house rule `sketch_on_face`, `extrude_face` and Hole all follow, so a
  stored pick rides an upstream change. Its shared-centre TIE belongs to
  REVIEW-QUEUE section 10 (viewport, picking and face provenance).
- CRLF warnings on the touched files: the checkout normalises on commit.
