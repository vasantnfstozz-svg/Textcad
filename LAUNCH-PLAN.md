# TextCAD launch plan — a robust, user-friendly CAD you can trust

> **Status: ACTIVE — approved by the user 2026-09-02 ("proceed with your
> plan").** P0 done 2026-09-02 (31cccf0), P1 done 2026-09-03 (1246e3c), the
> taper work the same day (Fusion sign + semantics, fc15233), P2 done
> 2026-09-03 (the tool framework, 7b62ff3; review fixes 6cc526a), P3 done
> 2026-09-03 (Revolve, the first tool born on the framework, a079c8c; its
> review fixes 127dbcf + the commit after), P4's first tool done 2026-09-04
> (Fillet/Chamfer on picked edges, 1412dc6; review fixes df68f60; checklist
> passed). ★P0 kernel-crash survival done 2026-09-05 (1aea14a: `python
> studio.py` is a supervisor + server child; a segfault costs one step, not the
> session — §10). The three ★P0 data items in §10 closed 2026-09-05 (36584e1:
> a tail-cut delete wiped the tree, clockwise polygons, refusals sent as 200).
> P3b done 2026-09-05 (4987a15: a picked FACE as a Revolve profile, the
> outline's own edges as the axis, Two sides / Symmetric; review fixes
> d82e9d0, ui v155 — §7 P3). **P4's second tool, Hole, done 2026-09-06**
> (5336c82: Fusion's Hole as ONE op that eats its body; all 25 findings of its
> code review fixed 0c49c42, ui v157 — §7 P4). **P4's third tool, Pattern,
> done 2026-09-06** (5b52dc1: Circular / Rectangular Pattern of a FEATURE's
> delta; all 7 review findings fixed ca5725a, ui v159; both checklists passed;
> Hole's drag ghost c6a2377, ui v160 — §7 P4). **P4's fourth tool, Mirror,
> done 2026-09-07** (023ca5d: a FEATURE's delta or a BODY mirrored across a
> face / an origin plane / a mid-plane; five review rounds 9644b6d, c4d5961,
> 85821be, 072aa95, 21429d8 + the deferred findings in the commit after the
> stamp, ui v164; user's checklist passed 2026-09-07 — §7 P4). **P4's fifth
> tool, Shell, DONE 2026-09-10** (fb0b8c8: the picked flat faces open, walls
> of one thickness Inside / Outside, every click a server-decided toggle;
> reviewed and fixed 667ccc0 — 5 of 5 findings, one of them a P0, ui v185;
> CLOSED after three review rounds, b5c6e70). **P4's sixth and seventh tools,
> Move and Rotate, BUILT 2026-09-11** (one file, `static/js/move.js`: three
> coloured arrows meeting at the body's centre, a ring about X / Y / Z through
> the body's centre — `rotate` grew a `pivot` and the legacy default stays the
> world origin, so no saved design moves; the ghost is the body itself; ui
> v187; review CLOSED after two rounds, 4ee5670 + 2f1d776, ui v189). **P4's
> last tool, Press Pull, BUILT 2026-09-11** (the plan's "Push/Pull naming":
> Fusion's router button in the Modify tab — a flat face or a sketch profile
> opens Extrude, an edge opens Fillet, a curved face gets a sentence; no new
> op, no backend change; review CLOSED in one round, 9584b39, ui v191).
> **P4 IS COMPLETE — all seven Tier-1 tools built and reviewed.** **P5, the
> AI uses the tools, BUILT 2026-09-11** (5dc7817: one verified feature per
> model reply through the same strict add + lint + rebuild as the toolbar;
> create builds in its own tab, add builds on the design on screen behind one
> Undo). **P5 IS DONE — reviewed and CLOSED 2026-09-11 after seven rounds**
> (`4041703`, `5975aad`, `bb0c4ab`, `231bf16`, `7d03e9c`, `5d2d431`; round
> seven found nothing): 20 findings, all fixed, 29 new tests (fast tier 1623),
> ui v196. The heaviest were on the "add to the design on screen" road — the
> model's spec written over the USER's, a correct step undone and blamed for
> another feature's redness, the AI able to delete a feature the user built,
> `add` + `done` in one reply finishing a design unchecked, and a user edit
> landing mid-job breaking "one Undo takes it all back" (§10). **P5b, the
> machine plays the user, BUILT 2026-09-12** (c11fd74: `tests/journeys.py`
> plays random user moves against the in-process app and files each
> finding as a replayable folder under `bugs/`; a status-bar bug button
> saves the design, the tab's last requests, the browser's warnings and a
> viewport PNG there in one click; `pytest -m library` collects again and
> rebuilds every live design; ui v197; 12 journeys of 30 moves over empty, pump-impeller and esp32-remote, seeds 100-111: 12 clean, 0 bugs, 0 crashes). Next: its
> `code review` (CLOSED 2026-09-12 after two rounds, 8f72d9e), then P6. **Its first catch fixed 2026-09-12 (ac5c11d):** a closed Shell of a box-clipped ball segfaulted the kernel; refused per lump before the kernel now, and the body joined the corpus, where it found a Mirror + Join segfault (a part-ball reflected through its own centre) that is refused the same way — §10 carries the one direction still open. Every other plan file points here; §7 carries the
> done-notes, §10 the ranked open items. **Added 2026-09-10 (user's decision):** P5b, the machine plays the
> user — a zero-token random-journey runner, a bug button, the library tier
> fixed — sits between P5 and P6 (§6 tier 4, §7 P5b).
>
> It replaces the reverted TOOL-FRAMEWORK-PLAN.md (2026-09-02, another model's
> session, deleted at the user's request). Its diagnosis was checked against
> the code and found correct; the parts worth keeping are credited in §11.

---

## 0. The goal, in the user's words

> "We are building a robust TextCAD software, where we can make complex
> designs using AI, and we can edit the design simply in the feature tree,
> instead of going back to the AI. So we need user-friendly tools, so that a
> user can easily modify the design or create it from basics. For that we need
> a robust feature tree for every design generation, the best AI chat box for
> complex designs, and user tools."

> "Whenever I am creating a new tool like extrude, we are getting really a lot
> of bugs and errors, sometimes not the intended function, and sometimes I am
> wasting really a lot of tokens. Even when we are running test cases, we are
> still getting a lot of bugs while using."

> "Extrude took many attempts to get this behaviour. Other tools should also
> behave like this: click and drag an arrow, instead of filling numbers in a
> box."

> "We need a robust design AI. If the user wants to do something, it should
> not hallucinate. That is our main motto as well." (2026-09-03)

Four things must be true at launch:

1. **Every tool works the Extrude way** — drag a handle on the model, the
   number box is the second option, the preview is the real verified solid.
2. **Every feature the AI or the user creates can be re-opened and changed
   with the same tool that made it**, straight from the feature tree.
3. **The design AI does not hallucinate.** It can only use the tools in the
   toolbar, every step it takes is built and verified before the next, a
   failed step is repaired or refused out loud, and it never redraws a design
   to make a small change — it points at the parameter. What the user asked
   for is what gets built, or the AI says plainly why it cannot. (The founding
   motto, restated for the AI chat: mistakes must never reach the user.)
4. **No silent wrong geometry, no data loss, no phantom bugs.** A launch for
   students and professionals alike; also the base for the user's own
   personal project (to be discussed).

---

## 1. Where the software stands (2026-09-02, HEAD 253c7bc)

Working and shipped: the feature-tree engine with verified rebuild, undo and
strike-out; in-viewport sketching with snapping, trim, arc radii and image
tracing; **Extrude** as the one fully direct-manipulation tool; Measure &
drive; per-design version tree with explicit push; STL/STEP import and
guarded STEP export; multi-tab session that survives restarts; AI authoring of
whole trees with lint + repair; MCP doorbell for external scripts.

Tools that exist only as **form dialogs** today (registered ops, no handle,
no select-then-command, no live gizmo): fillet, chamfer, shell, move, rotate,
scale, mirror, polar and linear pattern, fuse/cut/intersect, revolve, loft,
sweep, primitives. These are the tools the plan turns into real tools.

Sizes that matter (2026-09-03, after P3): `tool.js` 528 lines carries
`extrude.js` 267 (was 941 alone) and `revolve.js` 97; `sketcher.js` 2091,
`studio.py` 2572, `viewport.js` 2032. 50 test files + 28 browser test files
(127 journeys).

---

## 2. Why new tools bleed bugs — the diagnosis

Each cause is structural: the architecture *makes* the bug likely. Fixing
instances never ends; only removing the cause does.

**Cause 1 — the browser re-derives geometry the server already knows.**
`extrude.js` carries `PLANE_FRAME` (a hand copy of build123d's plane frames,
including the XZ sign that had to be probed) and `canonAxis()` (a JS
reimplementation of `sketch.face_sketch_plane()`). Two homes for one fact.
They agreed on most faces and disagreed on the rest — the 2026-09-01 "arrow
goes one way, ghost goes the other" bug. The fix ADDED a copy, so the class
regenerates itself.

**Cause 2 — there is no tool framework; every tool re-implements the rules.**
The fusion-parity skill lists the rules (modal guard, honest zero, gizmo
lifecycle, throttled verified preview, cancel/OK/Esc, warnIfFailed,
select-then-command from viewport AND tree, combine-target default). They are
applied from memory, per tool. `S.modalTool` appears in only four files. Most
of Extrude's 941 lines are this checklist, not extruding. The same bug —
"nothing refreshed the viewport, so it showed stale geometry beside a correct
number" — shipped in Trace Image, Measure and Extrude separately, because the
viewport does not follow the document; each tool must remember to poke it.

**Cause 3 — no single authority for selection and direction.** Viewport pick,
tree row, lingering pick, picked profile; flip, through, amount sign, face
normal, the one-shot cut flip, and a bottom face where flip means the
opposite. The three Extrude bugs of the last session (tree pick ignored,
phantom 1 mm default, body vanishing behind a struck cut) were all of this
kind.

**Cause 4 — the tests exercise the machinery, not the experience.** Most e2e
tests drive the app through internal bus events with hand-typed coordinates,
then check the DOM. Three sketch bugs were live while the suite was green
because the tests bypassed real face picking (2026-08-31). Measure shipped
with three UI bugs every backend test passed through. "A body drawn as a ghost
passes every DOM check." 638 unit tests passed while the extrude arrow pointed
the wrong way.

**Cause 5 — red does not mean red.** Code tests read the user's LIVE designs:
`tests/test_through_cut.py:27` loads `designs/esp32-remote.tcad.json`,
`tests/test_face_provenance.py:31` loads `designs/pump-impeller.tcad.json`,
`tests/test_history.py:600` reads the live esp32 history, and the e2e
examples-tab test depends on esp32 being in the gallery. A work-in-progress
edit in the app turns backend tests red with zero code change, and a habitually
red suite stops being a signal. Peer sessions "owned" red tests for days.
**Verified still true at HEAD:** `esp_pillar_trim_tool` in esp32-remote has
lost its `through: true` (params are now only `amount: 6.0`) — the test that
went red was right; the design regressed.

**Cause 6 — the AI and the buttons are held to different standards.**
`author.lint_tree()` rejects an absolute-offset sketch once a body exists
(the offset method). `studio.py` never calls it for UI-created features, so a
hand-built design can be *less* editable than an AI one — the opposite of the
product goal.

**Cause 7 — phantom bugs and scattered knowledge burn tokens.** Stale browser
tabs, several servers on one port, two Claude sessions committing into the
same checkout and racing the cache-buster, tests loading live designs. Each
cost a debugging round about a bug that did not exist. Knowledge lives in
five plan files, a BACKLOG whose header still says "paused", thirty memory
notes and eight skills; every session re-reads all of it.

---

## 3. The rules (the constitution — every phase and every tool obeys these)

| # | Rule | Kills |
|---|------|-------|
| R1 | **One geometry authority.** If the UI needs an axis, origin, frame, safe range, or target body, it is a field on a server response, never a calculation in JS. | Cause 1 |
| R2 | **One tool framework.** A tool declares only what makes it different (inputs, params, op, gizmo kind). Modal guard, honest zero, preview, cancel/OK/Esc, warnIfFailed, select-then-command, combine default are inherited, not re-typed. | Cause 2 |
| R3 | **The viewport follows the document.** A document change (rebuild stamp) refreshes the scene automatically. No tool calls the refresh by hand. | Cause 2 |
| R4 | **One selection, one direction.** A single selection resolver (viewport pick, tree row, explicit argument — one set, tree click replaces viewport pick) and the server's plan decides direction and sign. | Cause 3 |
| R5 | **Tests replay the user.** Per tool: real clicks on frozen sample designs, assert what appears on screen and the measured volume. Bus-event shortcuts are allowed only for setup, never for the step under test. | Cause 4 |
| R6 | **Frozen fixtures; red means red.** Code tests read `tests/fixtures/`, never `designs/`. Live-design health is a separate, opt-in check. `pytest tests -q` is green at every commit and stays green through a design edit. No test is left red because "another session owns it". | Cause 5 |
| R7 | **Same standard for AI and UI.** The lint runs on both paths: rejection for AI/MCP trees, a spoken chat warning naming the fix for UI-created features. | Cause 6 |
| R8 | **Spec before code.** Every tool starts as a one-page description the user approves: what you click, what you see, what can go wrong. No code until approved. | "not the intended function" |
| R9 | **The review is the gate, not a checklist.** Each shipped tool gets one code review in the review chat before its plan row is stamped, and the findings are fixed there. The per-tool five-step user checklist was retired 2026-09-10: the user tries tools when they choose to, and what they find becomes a §10 row. | tokens, Cause 4 |
| R10 | **Every phase deletes more than it adds**, or it is another layer, not a fix. Record the line delta in the commit. One exception, named here so it is never self-granted: the phase that CREATES the framework (P2) is judged together with the first tool built on it (P3) — their combined delta must be negative against the hand-wired tool they replace. | Cause 2 |
| R11 | **Token rules.** One Claude session per checkout. Check the `ui v` stamp and single server before debugging any browser report. Targeted tests while building, full suite only at ship. Probe scripts committed under `probes/` so no API is probed twice. No agent fan-outs on this project. Fable plans and builds, Opus reviews and fixes in the review chat, effort `high` (§9). | Cause 7 |

Standing design rules stay in force: the offset method (base first, then
sketch on a named face with an offset), no sharp internal corners in milled
parts, probe before build, never trust — measure.

**How this relates to the 13 fusion-parity rules** (`.claude/skills/
fusion-parity/SKILL.md`, each learned from a user correction): those rules say
how a tool must BEHAVE (inputs are profiles and faces and bodies;
select-then-command incl. tree rows; drag handles first; honest zero; live
verified preview; Join/Cut as separate features with the right default
target; failures speak; contextual ribbon; one command at a time; a mode is
never a separate screen; base first then sketch on the base; sketch-first
tree; the navigation mapping). They are not replaced. Today they are applied
from memory per tool; **R2 exists so that rules 2–7 and 9 are inherited by
every tool automatically**, and the rest are checked by the plan tests and the
review chat. Rule compliance becomes the default instead of an achievement.

---

## 4. The tool set

Every tool: select-then-command (viewport pick or tree row), a handle on the
model, live verified preview, the value box as the second option, Esc cancels.

**Tier 1 — must exist at launch**

| Tool | Handle you drag | Input | Backend today | Notes |
|------|-----------------|-------|---------------|-------|
| Sketch | draw tools, snap | plane or flat face | done | done |
| Extrude | arrow (distance), ring (taper) | profile or flat face | done | reference implementation; port onto the framework with zero behaviour change |
| Revolve | ring (angle), axis shown in gold | profile | `revolve` op exists; guards from the reverted session to be re-added | axis worked out from the profile, never asked for (a form step in disguise) |
| Fillet / Chamfer | ball on the edge (radius / distance) | one or more picked EDGES | ops exist for edge GROUPS only (`all/top/bottom/vertical/horizontal`) | needs edge picking + a per-edge op; user asked for this twice |
| Hole | arrow (depth) at a point on a face | flat face + point | none as one op | plain, countersink, counterbore (thread-case needed these); composed from existing cutters |
| Pattern (circular, linear) | drag count / spacing | a feature or body | `polar_pattern`, `linear_pattern` exist | bolt circles, gear teeth |
| Mirror | pick a plane or flat face | body | `mirror` exists (returns a copy) | |
| Shell | arrow (wall thickness) on the open face | body + face | `shell` exists (group selector) | |
| Press Pull (the plan's "Push/Pull") | Extrude's arrow / Fillet's ball | flat face, sketch profile or edge | `extrude_face` exists | built 2026-09-11 (`specs/press-pull.md`): Fusion's router — face or profile → Extrude, edge → Fillet; no op of its own |
| Move / Rotate body | three arrows / ring | body | done | built 2026-09-11 (`specs/move-rotate.md`); `rotate` has a pivot now, "center" from the tool |
| Combine (Join / Cut) | in the tool's dropdown | two bodies | exist | Intersect stays locked until a real use appears |

**Tier 2 — after launch:** Sweep, Loft (ops exist, need tools), Text in a
sketch (`text` entity — names and logos), Section view, **Named parameters**
(`wall = 3` once, everything follows; the biggest usability win after the
tree, needs an expression engine), Assemblies/joints (assembly.py exists).

---

## 5. The AI uses the same tools

Today the chat authors a whole tree in one JSON answer, checked afterwards.
The plan changes this in two steps.

**Step A (with P1–P3):** parity. Every op the AI may emit is a tool in the
toolbar, and the lint runs on both paths (R7). An AI-made feature is
re-openable with the tool that has the same name.

**Step B (P5):** **incremental tool-calling.** The AI builds a design by
calling the same server plan + feature-add endpoints the buttons use, one
feature at a time, each verified before the next. The tree grows on screen as
it works. A mistake is caught at the step that made it, not at the end. For
changes, the AI never regenerates: it points at the parameter ("sketch 3,
circle radius, 5") and the tree does the rest — the safest possible edit,
and exactly what the user asked for. The AI can only use what is in the
toolbar, so it can never build a shape the software cannot edit.

The model is configurable (OpenRouter today). Which model is a later decision
and never a hard-coded fact in the UI.

---

## 6. Testing — four tiers, each cheap where it can be

1. **Kernel gauntlet** (fast, no browser): every op that consumes a face,
   profile or body runs against the body corpus in `tests/gauntlet.py`. When
   a real bug is found, its geometry joins the corpus. *An operation is the
   feature times the geometry.*
2. **Plan contract tests** (fast, no browser — most cases live here):
   selection + params in, plan JSON out (`axis, origin, frame, limits,
   target_body, will_build`). Deterministic, so the cases that bit Extrude
   (bottom face, tilted face, struck consumer, tree pick vs viewport pick)
   become one-line table tests.
3. **User-journey e2e** (a few per tool, ship time only): real ribbon clicks,
   real pixel picks on `tests/fixtures/*.tcad.json`, assert the rendered body
   count and the measured volume. Waits use `controls.enabled`, never fixed
   sleeps.

Plus: `pytest -m library` (opt-in) reports the health of the user's live
designs — parses, rebuilds, piece count vs spec — in its own channel.

4. **Random journeys** (P5b, no browser, no AI, no tokens): a script plays
   the user against the real server for hours — random face, random value
   inside the plan's own safe range, edit, strike-out, undo, redo, pattern a
   random seed — through the same plan + feature endpoints the buttons use.
   The oracle is the founding rule: every step ends in a healthy verified
   solid or a clean refusal sentence; anything else (a kernel exception, an
   invalid or open solid, a crash, a "success" whose volume moved when
   nothing should have) is a bug, saved with its exact step sequence as the
   repro. Found bugs join the gauntlet. This tier covers what nobody
   imagined; the review covers what the code says; the user covers what only
   a human notices.

---

## 7. Phases, in order, with acceptance and what the user does

**P0 — Docs and hygiene (no behaviour change).**
Write a short `CLAUDE.md` (map, rules, how to run, pointer to this file),
`ARCHITECTURE.md` (modules, data flow, contracts), mark `README.md` as the
historical prototype. Reconcile stale headers (BACKLOG "paused", version
tree "nothing built", "/api/model has no mesh cache" — all superseded).
Freeze fixtures: copy the designs the tests need into `tests/fixtures/`,
point the live-design tests at them, add the `library` marker.
*Acceptance:* `pytest tests -q` green at HEAD, and still green after editing
any design in the app. *User does:* reads CLAUDE.md, confirms it says what
they mean.

*Done 2026-09-02:* `tests/fixtures/esp32-remote.tcad.json` = history v15 (the
user's chosen clean version, 79 features) plus `through: true` on the pillar
trim — measured: one solid, volume 107484.7823 mm³ with and without the flag,
so the fixture is the same part the tests were written against;
`tests/fixtures/pump-impeller.tcad.json` = plain copy (10 features, one
solid). `test_through_cut` and `test_face_provenance` read the fixtures;
`test_history::test_diff_runs_on_the_real_backfilled_library` is marked
`library`; the gallery test no longer pins the catalog's dead feature count;
`pytest.ini` excludes `library` by default. **Decision change:** the LIVE
`designs/esp32-remote.tcad.json` was NOT edited. It is the user's
work-in-progress v16 (81 features, verify failed: an unfused logo extrude, 35
pieces) and their Studio tab holds it — editing the file underneath an open
tab is the stale-tab trap. The missing `through` on the live design is a
design-health item for the user to fix in the app (§10).

**P1 — One geometry authority.**
`POST /api/tool/plan` → `{axis, origin, frame, limits:{min,max,safe_taper},
target_body, will_build}` for a tool and its input. Extrude draws what it is
told. Delete `PLANE_FRAME`, `PLANE_N` and `canonAxis` from `extrude.js`.
*Acceptance:* `grep -n "z_dir\|CANON\|PLANE_FRAME\|PLANE_N" static/js/`
returns only reads of server data; Extrude e2e stays green. *User does:*
five-step Extrude checklist on top, bottom, side and tilted faces.

*Done 2026-09-03:* `toolplan.py` (new, pure functions over a Document) +
`POST /api/tool/plan` (read-only: no snapshot, no rebuild, no version). The
plan carries `axis`, `origin`, `frame`, `loops`, `into_sign`, `limits`
(inradius / has_holes / outer_radius), `target_body`, `will_build`.
`extrude.js` lost `PLANE_N`, `PLANE_MAP`, `PLANE_FRAME`, `CANON_AXES`,
`canonAxis`, `baseAxis`, `arrowOrigin`, `entLoop`, `loopsForEntities`,
`loopsCentre`, `safeRadius`, `latestDescendant`, `defaultTarget`: 941 → 715
lines, and it now refuses to open with the server's sentence when a plan
cannot be made (rule 7). Tests: `tests/test_toolplan.py` (20 — every plan is
also checked against what the kernel builds), the 14 Extrude browser journeys
green unchanged. Two things the authority CORRECTED on the way: (1) the
"cut goes into the body" flip assumed negative = into; on a bottom / -x / +y
face the canonical frame points into the body, so there the pocket direction
is POSITIVE — `into_sign` now says which, and the kernel-verified table is in
the tests; (2) a face pick's ghost frame is now the face's OWN plane (z = the
build axis), so a tilted wall's ghost grows with its solid instead of along a
snapped principal plane. Sampled outlines no longer repeat the seam point
(a circle's centre was 0.2 mm off). **Acceptance partly met:** `extrude.js` is
clean; `sketcher.js` still owns `PLANE_FRAMES` (the frame a NEW plane sketch is
drawn in) — the last duplicate, listed in §10 for P2.

**P2 — The tool framework, extracted FROM Extrude.**
A `tool({...})` factory owning the inherited rules; viewport follows the
document (R3); one selection resolver (R4). Extrude is ported with zero
behaviour change. *Acceptance:* `extrude.js` under ~300 lines, all Extrude
tests green, no `loadMesh()` call left in any tool file. *User does:* the
same Extrude checklist — nothing should feel different.

*Done 2026-09-03:* `static/js/tool.js` (new, 497 lines, the contract in its
header) is the framework. `tool({...})` inherits: the modal lock (rule 9);
the ONE selection resolver `currentSelection()` — explicit argument > viewport
face > viewport profile > tree sketch row > curved-face refusal (R4);
select-then-command with the pick fallback; honest zero; the lazy verified
preview with serialized applies; the kernel-refused backstop (tool retreat →
last good → safe params); Join/Cut combiners with the plan's default target;
edit-in-isolation with Cancel-restores-verbatim; OK / Cancel / abandon; and
every failure sentence. `extrude.js` 768 → 261 lines: it declares its panel,
its two ops, boxes ↔ params, the arrow / ghost / ring and the cut-flip and
taper rules — nothing else. **R3:** `viewport.follow()` refreshes the scene on
every `doc-updated` whose `geom_version` differs from what is drawn;
`holdViewport(fn)` makes a multi-step change (a feature and its Cut) ONE
refresh; a `loadMesh()` for the version already being fetched joins that load
instead of transferring the model twice. No tool file calls `loadMesh()`, and
the ten redundant calls in `tree.js` / `placement.js` are gone;
`tests/test_launch_rules.py` holds R1 / R2 / R3 by grep. **R1 closed:**
`sketcher.js` lost `PLANE_FRAMES` — `/api/tool/plan {tool:"sketch", plane,
offset}` returns the frame from `sketch.sketch_plane()`, the same function
`make_sketch()` builds on (kernel-checked: the built face's centre and normal
equal the frame, tests/test_toolplan.py, 6 new). `cancelTool()`,
`editFeature()`, `canEdit()`, `activeToolFeature()` replace the
Extrude-specific exports in ribbon, dialogs, placement and tree, so the next
tool needs no edit there. Zero behaviour change: the 17 Extrude browser
journeys pass unchanged. **Line delta (source, excl. tests): +59** — JS +30
(tool.js +497, extrude.js −507, viewport +37, sketcher +13, tree −9,
placement −2, ribbon +1), Python +29 (the planner). This is the one phase
that is allowed to add: the framework is 497 lines written once so that
Revolve is not 700 lines written again — R10 is judged on P3, where a tool
must land in 100–250 lines. Honest corner: on the rare revert-to-last-good
path, a through-all cut with the untouched 0 distance now shows the sign it
sent (±1) in its disabled distance box instead of 0.

**P3 — Revolve, the first tool born on the framework.**
Axis derived from the profile, drawn in gold; drag a ring 0..360; backend
refuses (with a sentence) a profile that straddles the axis or an axis
perpendicular to the plane — both reached the user raw before (one as a raw
OCP exception, one as a "successful" solid of volume 0). *Acceptance:* the
tool lands in ~100–250 lines with no geometry maths; 40+ plan tests; 3–6
journey tests; volume cross-checked (Pappus). *Success metric for the whole
plan:* bugs the user finds in Revolve's first week, compared with Extrude's
history. *User does:* Revolve checklist.

*Spec approved 2026-09-03* (`specs/revolve.md`, 629ca66): the axis is
derived (one of the sketch's two in-plane axes through the sketch origin,
`u`/`v`, riding the geometry; Swap offered when both work); the angle box
starts at 0 with a Full button; a picked FACE as profile, a sketch-line axis
and Two-sides/Symmetric are P3b.

*Done 2026-09-03, in one session on the framework.* `static/js/revolve.js` is
**97 lines with no geometry maths**: panel `rv…`, op `revolve`, boxes ↔
params, and the three handles — gold axis line, angle ring, lathe ghost — each
placed from the plan. Backend: `sketch.revolve_sketch` takes axis `u` / `v`
(the sketch plane's own axes through the sketch origin; a sketch now remembers
its plane ON the object, `_tc_plane`, set by `make_sketch` / `sketch_on_face`)
or the legacy `X` / `Y` / `Z`; its guards turn three kernel behaviours into
sentences (probes/revolve_axis_probe.py): angle 0 quietly built a FULL turn
and 400 quietly built 40 → refused outside (−360, 360] \ {0}; an axis not in
the plane was a zero-volume "success" → refused; a straddling profile was a
raw `StdFail_NotDone` → refused, measured on the kernel's bounding box so a
circle's whole reach counts, not its seam vertex. `toolplan.plan_revolve`
derives the axis (lathe axis `v` first, `u` offered, legacy world names
mapped onto the local axis they coincide with, a swap to an axis that does
not work falls back), returns the ring frame with x toward the material and
y = z × x so a positive drag turns the way the kernel sweeps (probed
right-handed), and the outline as (radial, axial) pairs. Framework additions
under §8 step 5 ("extend the framework and Extrude gets it too"): `planExtra`,
a refused opening plan closes the session instead of leaving an empty panel,
a tool without a face op says so and keeps the pick alive; viewport:
`beginAxisLine`, the ring's `continuous` mode (0..±360), `beginRevolveGhost`
(a three.js lathe in the plan's frame). **Tests:** `tests/test_revolve_tool.py`
— 92 cases: 30 plane × axis × side combinations never raw, Pappus on
rectangles / a circle / an L-profile / a face sketch on all three planes,
sweep direction by centroid, the planner's pick / swap / mapping / refusal, the
ring frame orthonormal and pointing at the material, document integration,
the HTTP route read-only; `tests/e2e/test_revolve_tool.py` — 5 journeys: tree
row + ring drag (ghost and solid on the kernel's side, volume = Pappus), Full
+ OK, edit + Cancel restores, refusal with no panel, Cut into the body the
sketch sits on (default target). **Line delta (source, excl. tests/probes):
+479** — a new tool is new capability; the R10 judgement the P2 note deferred:
`revolve.js` + `tool.js` = 625 lines against the 768-line hand-wired Extrude
they replace as the pattern. **The success metric runs from today:** bugs the
user finds in Revolve's first week, against Extrude's history. *Review the
same day (§10):* 40 findings, 30 acted on; the worst — a world axis outside
the sketch plane building a wrong-shaped solid — never reached the user.

*P3b done 2026-09-05 (4987a15; review fixes d82e9d0; ui v155)* — the three
pieces the P3 spec deferred, built in one session at the user's word (R8 bent:
the spec page was written WITH the code; the checklist is the approval gate).
**A picked FACE as the profile:** op `revolve_face`, a face-reference op like
`extrude_face` (never consumes the body), resolved by geometry at every rebuild
and revolved in its TRUE plane — `sketch._face_frame(face, snap)` is now the
one framing rule behind `face_sketch_plane` (snap on) and `face_profile_plane`
(snap off); identical on a box's faces, and a wall tilted under 25° keeps its
own plane because the snapped one does not contain it (probe §7: edges 1.4 mm
off — a latent `sketch_on_face` issue, §10). **The outline's own straight
edges as the axis** (Fusion's "pick a line"): the plan lists `u`, `v` (greyed
with the reason when crossed) and the 12 longest edges, each with the `param`
the feature stores — a LINE in the sketch plane, `axis: [[u1,v1],[u2,v2]]`,
never an index — so a rectangle across the origin now turns about a side where
P3 refused it; a picked face lists its edges FIRST (its plane's u/v pass
through the world origin's foot, an axis far from any off-origin body). The
stored line rides plane moves like u/v; after a profile resize it snaps to the
edge it lies ALONG, else stands as a construction line ("the stored line",
fallback when crossed). **Two sides / Symmetric:** `angle2` the other way,
`both` = the angle to EACH side (Autodesk's reference; extrude's key), built
as one sweep of the total turned back — exact. **Three kernel truths the
gauntlet forced out** (`probes/revolve_face_probe.py` §9): an axis microns off
an edge sweeps a SLIVER face that OCCT calls valid (fixed: the stored line
snaps to the kernel's own vertices); a hair off is a raw `Standard_OutOfRange`
(fixed: a barrier + the rebuild's cheap health census inside the op — a failed
feature beats a corrupt body); and `inspector.health` was a FALSE NEGATIVE on
every cone apex and sphere pole (build123d's `is_manifold` counts degenerated
edges) — `inspector.closed_shell` is now THE verdict for health and measure,
excusing a degenerated edge only on ONE cone / sphere / revolution face; a
spline fillet pinched to a point stays a defect (the Fillet tool relies on it).
**Tests:** `tests/test_revolve_p3b.py` (35), `tests/test_health_degenerate_
edges.py` (4), the gauntlet revolving every corpus face about each of its
edges, 3 browser journeys — the face one with a REAL viewport click and the
ribbon button (R5). **Line delta (source):** +528/−131 shipping, +330/−229 in
review — a new capability, as P3's was; the R10 comparison: `revolve.js` is
200 lines for two ops, an axis list and three extent modes, still on the
701-line framework, against the 768-line hand-wired Extrude. *Review (§8 step 8, 8 angles):*
~20 distinct findings, all verified first; one refuted by measurement (edge
axes of near-flat spline faces are in-plane); the ones that mattered — an edit
typed before its plan arrived rewrote a stored edge axis to the select's
default, the face default fell on `v` for any off-origin body, the plan was
O(N²) in outline edges (1.8 s for a 40-gon, 20 s for 120; now 0.2 s / 0.5 s).
Deferred to §10: a handle for Angle 2 (typed only today, against parity rule
3), the `sketch_on_face` 25° snap.

**P4 — The rest of Tier 1, one tool per session.**
Order: Fillet/Chamfer on picked edges (needs edge picking + per-edge op) →
Hole → Pattern → Mirror → Shell → Move/Rotate → Push/Pull naming. Each: spec
(R8) → plan tests → tool → user checklist (R9) → ship-check → commit.

*Fillet/Chamfer done 2026-09-04* (spec 1f8d55d, tool 1412dc6, review fixes
df68f60, ui v151; user's checklist passed). `static/js/fillet.js` is **76 lines
with no geometry maths** and declares BOTH tools from one function. The new
input kind is **edges**: the framework grew a third selection kind, and every
click goes to the server as a toggle — only the kernel knows which tangent
chain an edge is in, so only the server can say whether a click adds or
removes. An edge is stored as **the two faces it separates** (resolved the way
a face pick is), never an index: it rides a height change, and when those faces
no longer meet it says the edge is gone instead of quietly rounding a different
one. Tangent chain is a picking aid, ON for fresh picks and OFF for edges
loaded from the tree — keyed on provenance, because the stored set is already
the answer. Backend: `fillet`/`chamfer` take a group name OR picked edges;
`toolplan.plan_fillet` returns the gold edges, the handle's frame and the
resolved edges. Framework additions under §8 step 5: the `edges` kind,
`planExtra`, `replan`, a one-way Cancel/OK, and **Esc cancels any tool panel**
(the §10 item that was waiting for the second tool). The extrude arrow is
reused as the fillet handle — no new gizmo. **Probes:**
`probes/fillet_edges_probe.py` (what the kernel throws, tangent chains, edge
identity across a change) and `probes/fillet_segfault_probe.py` (below).
**Tests:** `tests/test_fillet_tool.py` (42), `tests/test_fillet_gauntlet.py`
(40: every edge of every corpus body picked alone, for both ops),
`tests/e2e/test_fillet_tool.py` (6 journeys). **Line delta (source, excl.
tests/probes/spec): +577/-78 shipping, then +130/-62 in review.**

*The review is the story of this phase.* `/code-review high` found 7; all 7
were re-verified against the running kernel before anything changed, and two
verifications changed the decision. **The tool no longer searches for "the
largest value that would fit."** Finding that number means building at radii
the user never typed, and on esp32-remote's 80-edge top rim radius **2.0
segfaults OCCT** (exit 139) while 1.95, 2.05 and 4.0 all refuse politely. It
was not bad luck: a halving search from 0 to 4 guesses exactly 2.0 first, and
exact round values are where geometry degenerates. **Rule learned: never hand
the kernel a value the user did not ask for.** The other six: a fabricated
diagnosis ("a face beside them is too small" — nothing had measured a face),
two stored faces collapsing onto one bypassing the gone-edge refusal, a stale
edge pick looping Extrude's face path forever, the tangent chain growing a
stored selection on reopen (the founding rule), one click on an AI group adding
every tangent neighbour, and a held Escape removing the same feature twice.
Plus one the review could not see: 1412dc6 broke a Revolve journey by adding
keys to the `gizmos()` debug hook, which the token rule (only the shipped
tool's journeys) hid — **when a change touches `viewport.js` or `tool.js`, run
the other tools' journeys too.**

*Fillet picking fixed 2026-09-07* (4f15f66 + 9bed191, ui v167; built on
branch `worktree-fillet-picking` while the main checkout held other sessions'
uncommitted edits, rebased onto 0f387ab and fast-forwarded; user's checklist
pending). The third bug came from the user testing the fix: SELECT mode
(`pickAt`) had its own copy of the depth-only rule and still selected the
WALL at an inside upright edge — both pickers now share `visibleEdgeHit`. Two bugs from the user's isogrid panel. **No inside corner could be
picked**: the picker refused any edge with a face a hair nearer, and the two
walls meeting at an inside corner always are, from every viewing angle. The
model now names the faces each edge bounds (read off the ancestor map the edge
polylines already use — a separate pass cost 10% of the mesh) and a face may
not hide its own boundary: R1, the server states the topology and JS compares
ids. **A click sometimes did not select**: plan requests could overlap and the
later one was sent WITHOUT the earlier click; they queue now, and a click that
RELEASED edges (Chain on: one click releases a whole smooth rim) says so in the
chat. Also: a raw pick resolves by "lies on the edge" instead of nearest
midpoint, so the preview body's trimmed neighbours and its own new rims are
told apart — a rim click is refused with a sentence instead of silently
un-picking the edge it replaced. **Tests:** 4 fast (all red before), 1 journey
(a pocket's floor rim and an upright corner rounded: the volume GROWS).
**Line delta:** source +124/-17. **Lesson:** a picker's occlusion test needs
topology, not depth alone — "any nearer face hides it" is wrong for exactly
the concave half of a solid's edges.

*Fillet edge GROUPS 2026-09-07 — SUPERSEDED 2026-09-08 by face / tree-row
selection (record below); the chips and `blocks.edge_groups` are gone.* (ui
v168, css v39; same branch). The user's
esp32 wish: "select all the vertical or horizontal edges by clicking one
option". Six chips in the Fillet / Chamfer panel — **inside corners** and
**outside edges**, each × vertical / horizontal / all — add a whole group in
one click, or take it out; the chat says how many; each chip is lit / dashed /
dim from the plan. **Inside vs outside is measured** (`blocks.edge_side`): a
concave edge's in-face direction points the way the other face's normal does;
a smooth seam (a round meeting a flat) is neither. `blocks.edge_groups` is
classified once per body (0.7 s on esp32's 609 edges) and cached on the Part;
a plan per click is set arithmetic. **Horizontal means LIES FLAT**, so a
pocket's rounded floor rim counts — the person machining it does not care that
it is an arc. `toolplan` grew `group_toggle`; `_toggle_set` adds a group's
missing edges or removes a fully-picked one. **Deferred:** face-click-adds-all-
edges (Fusion has it) — a >5 px near-miss would grab a face's edges with no
hover to warn, and it broke the chamfer rides-along journey; the chips cover
the real need. **Tests:** 3 fast, 1 journey. **Probe:** `edge_side_probe.py`
(the distance rule beats the orientation shortcut, which was wrong on half the
edges of a plain pocketed box).

*The 6 findings of the combined review of 16ade36..HEAD, 2026-09-07* (ui
v169). One review covered the STEP export (A), the fillet picking pair (B) and
the edge-group chips (C). Every finding was reproduced first, then a test that
was RED before the fix.

1. **A queued click landed on a session opened after it** (`tool.js replan`).
   The plan queue that 4f15f66 added bound its session when the queue got to
   the click, not when the click was made — and Cancel / OK do not drain the
   queue (`settled()` waits for rebuilds, not plans). So a chip click still
   waiting its turn ran against whatever session was open by then: gold edges
   nobody picked in a fresh session, and in an EDIT session **that feature's
   stored edges rewritten with a group the user never chose**. The session is
   bound at click time now. 1 journey (measured: 4 gold edges in a session
   that picked nothing).
2. **The export's body count described the parked build state** (`studio.py`,
   `document.to_step`). `bodies` was counted after `to_step` returned — and
   `to_step` RE-PARKS the rollback bar on its way out, so with an editor open
   the file held every body and the response said "1": the "this design has N
   separate bodies" sentence that the whole multi-body export was written for
   never appeared. Counted inside `to_step` now, while the bar is released
   (`Document.exported_bodies`). 1 test through the HTTP API.
3. **A lit chip added instead of removing** (`toolplan._toggle_set`). The chip
   is lit from the picks GROWN into their tangent chains; the click compared
   the RAW picks. On a machinable pocket (rounded corners) one chained click
   lights inside/horizontal 8 of 8 and the tooltip says "click to take them
   out" — the click then added the other 7. Both ends read the same set now,
   and the count reported is edges, not picks. 2 tests.
4. **One odd edge could take the whole panel down** (`blocks.edge_side`,
   `edge_direction`, `edge_groups`). The chips made the classifier measure
   EVERY edge on EVERY plan, and only the normals were guarded — so an edge
   the kernel will not answer for would abort `plan_fillet` and the panel
   would not open at all (rule 5). Guarded per edge; a refusal costs that edge
   and nothing else. 1 test + the corpus (`gauntlet.BODIES`, 8 bodies).
5. **The picker could select an edge through 10 mm of material**
   (`viewport.ownFaceHit`). An edge may be picked though its own face is in
   front of it — an inside corner's line sits a hair behind its two faces —
   bounded by 4× the click reach, a world length that GROWS with the zoom: at
   a 400 mm view that is 11.5 mm. Measured on the real body
   (`probes/own_face_reach_probe.py`, 853 samples over 3 zooms × 3 directions
   × 6 click offsets): a legitimate click's face hit lands within 1.1× the
   reach (p90), and the shipped bound accepted a face hit 10.0 mm from the
   line — on a dead-centre click. Bound is 2× now. **The review's proposed fix
   — compare in pixels — was measured and rejected**: every own-face hit is
   inside the 5 px pick threshold by construction (max 4.02 px of 853), so a
   pixel bound accepts them all and guards nothing. 1 journey, driven through
   the rule itself (`__vp.edgeHitReport`).
6. **The deep validity check saw only the tail** (`document.rebuild`). OCCT's
   validity analysis is skipped per feature for speed (~270 ms) and paid on
   "the result" — which was `_result_feature()`, the tree's tail. A design
   legitimately has SEVERAL bodies, so an invalid body that was not the tail
   was never validated: green row, and `_export_blockers` (which trusts
   `status`) would hand it to the file. Same class as the export bug it was
   written beside. Every body is validated now, with the verdict cached on its
   content signature — so N bodies do not cost N × 270 ms per rebuild, and an
   unchanged design pays nothing where the tail used to pay every time.
   2 tests. **Swept the whole live library: 51 designs, 0 with a body OCCT
   calls invalid, second rebuild ~0.0 s everywhere.** (`esp32-remote` reports
   a spec mismatch — 36 solids vs `n_solids: 1` — which is 753c24c's doing and
   an improvement: against the tail it reported 4 problems, including the size
   being 11×57×1 mm. The design really is a body plus 35 lettering solids; the
   spec is the user's to update.)

Two comments that had gone false with A were corrected (`studio.py`'s export
docstring and the per-feature health note in `document.rebuild`). Line delta:
source +197/−58, tests +337/−2, one new probe (247). Fast tier 1181 green;
browser: fillet 11, pattern/mirror/hole 23, measure/face/extrude/revolve 20
(the known order-dependent revolve ring test passes on its own — §10 P1).

*Fillet picks FACES and TREE ROWS 2026-09-08* (ui v171, css v40; branch
`worktree-fillet-select`, on top of the lint pass f1bca51). The user, on
testing the chips: "instead of dividing all edges into vertical and horizontal
and inside and outside, I can select a body, like from the feature tree — if I
am selecting an extrude and pressing Fillet, those selected face or body edges
should be selected … I can add a body by clicking a face or body; another
click on the selected body should deselect." That is Fusion's Fillet exactly
(its selection filter reads Edges / Faces / Features), so the six chips are
GONE — with `blocks.edge_side / edge_direction / edge_groups` and
`group_toggle` — and the tool has **three selection kinds, every one a toggle
the server decides**: an **edge** (as before), a **face** (every edge two faces
meet at on it, as one set: the missing ones come in, a fully picked set goes
out), a **tree row** (the edges of the faces that feature MADE, as they exist
now). The row rule is provenance's, run forward for one feature
(`provenance.feature_faces`): a face of the body is the feature's when it is a
trimmed survivor of a face the feature's OUTPUT has and its INPUT did not,
`delta_features` deciding what those are (the tree's folding rule). Measured
on a pocketed box (`probes/feature_edges_probe.py`): the cut's row = its 12
pocket edges; the base plate's row = its outer 12 PLUS the pocket's opening
(the top face is the plate's, as it is now — Fusion agrees); a fillet's row =
its bands' 16 edges; the tool prism's row = the pocket too. Seams are never
offered. A face click resolves by nearest centre and is REFUSED when the
centre lies outside the resolved face's bbox — the picker hands the tool clicks
on its own PREVIEW body, and a new round's band would otherwise name the wall
beside it and round ITS edges (the same guard as Pattern's `_axis_face`).
Select-then-command works for all three; a row picked before the tool also
names the body. The face under the pointer glows while the picker is armed
(the missing hover that had deferred face picks). **The cost that was hiding:**
the first row click on esp32-remote's 48-edge ring took **55 s**. cProfile put
31.5 of 33.7 s in `toolplan._expand` — not in feature_faces (1.5 s cold, then
cached) but in RESOLVING the picks: `resolve_face` measured all 254 face
centres for both stored faces of every edge (96 calls, 15 s) and
`tangent_chain` rebuilt its vertex table from `part.edges()` per edge
(12.7 s) — a cost every multi-edge plan had paid since the tool shipped, that
a one-edge click never showed. Both are enumerated once per built Part
(`blocks._face_rows`, `blocks._edge_topo` with the end tangents): 5.8 s cold,
**0.37 s** warm. **The memo's key was a P0 for an hour:** stored as attributes
on the Part (as yesterday's `edge_groups` was), they rode along in build123d's
`__deepcopy__` — `moved()` and `Pos * part` copy first and move second — so a
moved plate resolved a face by its parent's centres at the OLD position. The
full fast tier caught it (`test_revolve_p3b`'s moved plate, green alone, red
after any test that had touched the cached plate — Parts are shared across
Documents by the rebuild cache) and `probes/shape_cache_probe.py` measured it
(cached centre −20, real 80). The memo lives beside the shape now
(`blocks._cached`: a WeakKeyDictionary on the Python object, each entry checked
against the TopoDS shape with IsEqual, so a copy, a re-used id and an in-place
move all miss). **Tests:** fast `test_fillet_tool.py` 53 (8 new for the 6 chip
tests removed, incl. the moved-copy memo), 11 journeys (2 rewritten: the cut's row → open
with 12 gold, row again → 0, floor face → 4, row → 12, face → 8, radius 1.5
builds on the 8; the queued-click journey now queues two face clicks).
**Line delta:** source +401/−280 — R10 NOT met: the chips' 154 lines left,
but the memo (+~110 with its key) and the hover face (+~30) came in; tests
+219/−211; two new probes. **Debt found:** two requests in the kernel at once (§10
P2 below). **Lesson:** a selection that grows to dozens of edges pays every
per-edge cost dozens of times — profile the real design before shipping any
multi-select; the chips would have shown the same 55 s on their first big
group.

*Hole done 2026-09-06* (spec `specs/hole.md`, tool 5336c82, review fixes
0c49c42, ui v157; user's checklist passed 2026-09-06; drag ghost c6a2377, ui
v160, re-checked by the user the same day). `static/js/hole.js`
is **193 lines with no geometry maths**. Two firsts, and both cost the
framework a new idea. **The op EATS its body**: `sketch.hole` takes the solid
and returns the solid WITH the hole — no cutter prism, no Cut row, one `hole1`
in the tree — so the framework grew `eats` (Operation stays "new", no Target).
**The input is a POINT on a face**, not a profile: the viewport pick now
carries WHERE it was clicked, a tool may declare itself face-only (the picker
refuses sketches in that tool's own words), and a `repick` pick lives as long
as the SESSION — click another spot and the hole moves there. `at` is stored
in the face's own frame, so the hole rides an upstream change like everything
else. Backend: `sketch.hole` / `hole_frame` / `hole_cutter` /
`material_depth` / `through_reach`, `toolplan.plan_hole`;
`sketch_on_face`'s face branch and `toolplan._pick_face` collapsed onto one
`sketch.pick_face`. **Probes:** `probes/hole_probe.py` (build123d's own `Hole`
objects are double-length builder-mode tools — not used; a hole centred in an
existing hole removes nothing and "succeeds"; a hole tangent to the face's edge
comes back an OPEN SHELL the kernel calls valid) and
`probes/hole_review_probe.py`. **Tests:** `tests/test_hole_tool.py` (42),
`tests/test_hole_gauntlet.py` (8 bodies × every flat face × 3 kinds × through /
blind × centre / near-vertex), `tests/e2e/test_hole_tool.py` (6 journeys).
**Line delta (source, excl. tests/probes/spec): +557/−49 shipping, then
+369/−123 in review.**

*Its review found the same class twice: a tool that lies while it is open.*
25 findings, all acted on (§10 carries the full note). Four could reach the
user — a click while EDITING was ignored, a hole authored without an `at`
opened where it does not cut, a stored face NAME outlived every moved pick,
and a real ⌀1 hole in a big block was refused as "nothing was cut". Two more
UNDID the user's own choice: the seat kinds and Through all applied
zero-valued boxes, the op refused, and the framework's revert put the choice
back. The lesson is the framework's: **a change field that puts the form into
a state the op will certainly refuse must not be applied at all** — applying
and reverting is worse than waiting, because the revert overwrites what the
user just chose. `spec.hold` is that wait, and OK reports it instead of
claiming a change that never landed. Then the FIXES were reviewed the same way
(4 angles) and 7 defects in them were found and fixed — two of them mine and
new (`at=None` drilling at the face centre, a 2 m ceiling on through holes),
one a shared-resource mistake three.js invites (`ArrowHelper` hands the same
two geometries to every arrow; only the materials are the caller's). **Rule
learned: a fix commit earns a review of its own.**

*Pattern done 2026-09-06* (spec `specs/pattern.md` 925ab67, tool 5b52dc1,
review fixes ca5725a — all 7 findings, ui v159; user's checklist passed
2026-09-06). `static/js/pattern.js` is **154 lines with no geometry maths**.
The two ops that existed, `polar_pattern` / `linear_pattern`, now take a
`seed` and repeat a FEATURE: the document hands the op the seed's before /
after bodies and the pattern repeats the DELTA (before − after cut again,
after − before fused again) about an axis or along a direction on the body's
CURRENT state — a hole, a pocket, a boss, a fillet all pattern the same way;
no seed = the legacy body pattern, signature-compatible. `document.
delta_features` is the ONE seed resolver (a modifier is its own before /
after, a pulled tool with a folded boolean is the boolean's, anything else a
body seed). The axis lives in ONE stored form (null = world Z, a world name, a
face pick / name, or `{origin, dir}`). Every copy is measured: one that
removes exactly nothing is refused by number, an open shell is refused, a
kernel error is a sentence. Framework grew a fourth selection kind `feature`
(a tree row feeds a waiting tool), `anyFace` picks and `onRepick` (a session
click re-aims the AXIS); the viewport a second arrow. Circular = ring (total
angle) + typed count, opens at 1; Rectangular = two arrows (Distance 1 / 2),
Spacing / Extent, opens at count 2 / distance 0. **Probes:**
`probes/pattern_probe.py` (11 findings). **Tests:** `tests/test_pattern_tool.py`
(38), `tests/test_pattern_gauntlet.py` (16: 8 bodies × every flat face ×
circular 3 / 5 + rectangular), `tests/e2e/test_pattern_tool.py` (5 journeys).
**Line delta (source, excl. tests/probes/spec): +500/−112 in existing files,
+527 in two new files (pattern.py 373, pattern.js 154).** *Its review (7
findings, §10):* a pattern's `seed` is the tree's only REFERENCE that is not
an input, so `document.REF_PARAMS` was born; a body pattern is never refused
for producing the same volume (a symmetric body patterns onto itself — 14
live designs would have failed at rebuild), only zero motion is.

*Mirror done 2026-09-07* (spec `specs/mirror.md` 6156cf6, tool 023ca5d,
review fixes 9644b6d / c4d5961 / 85821be / 072aa95 / 21429d8 + the deferred
findings in the commit after this stamp, ui v164; user's checklist passed
2026-09-07). `static/js/mirror.js` is **89 lines with no geometry maths**. The
op that existed, `mirror`, now takes a `seed` like the patterns: the document
hands it the seed's before / after bodies and the DELTA is reflected across a
plane on the body's CURRENT state (removed cut again, added fused again — a
hole, a pocket, a boss, a fillet all mirror the same way); no seed + `join` =
the body fused with its reflection (Fusion's Join, one symmetric solid); the
legacy copy-only call still builds every saved design. The plane lives in ONE
stored form (an origin-plane name, a face pick / name, the body's mid-plane
`{mid: "X"}`, or `{origin, normal}`) and is CLICKED — a flat face or one of
the three origin quads, which follow the body — or chosen in the panel; no
drag, no ghost, a gold quad marks it. Every image is measured: one that
changes exactly nothing is refused by number and told apart from one that IS
the seed (image ∩ seed, for a cut and for a fuse), an open shell is refused,
a kernel error is a sentence. The framework grew the origin-quad pick
(`planePick`), `spec.verb` / `sketchNote`, `lastGoodPlan` (the revert
sentence in the PLAN's words, R1) and an honest OK over a red first build.
**Probes:** `probes/mirror_probe.py` (10 findings), `mirror_p0_probe.py` (4),
`pattern_barrier_probe.py` (3), `mirror_seed_collapse_probe.py` (2),
`mirror_boss_seed_probe.py` (3). **Tests:** `tests/test_mirror_tool.py` (45),
`tests/test_mirror_gauntlet.py` (16: every corpus body × every flat face and
mid-plane), `tests/e2e/test_mirror_tool.py` (8 journeys). **Line delta
(source, excl. tests/probes/spec): tool 023ca5d +326/−67 in existing files
+82 new; the six fix commits +≈190/−≈60.** *Its reviews (five rounds, §10):*
every P0 lived in the gap between what the tree STORED and what the plan
DERIVED — a PLACEMENT row folds to a body seed, `join` is a body mirror's
business, a stored seed that stops resolving must never come back as the
legacy copy, a body union gets the health gate; and twice a test had locked
the bug in and was part of the fix.

*After both checklists (2026-09-06) the user found ONE thing: no ghost while
dragging.* Hole got it the same day (c6a2377, ui v160: hole.js feeds Extrude's
ghost the hole's circle in the plan's frame, +42 net lines, no viewport
change, +1 journey; the user re-checked it). Pattern's ghost is deferred by
the user's decision (§10) — its copies need the seed's delta mesh from the
server. The review of c6a2377 rides with the next tool's (user's call).

*Shell done 2026-09-10* (spec `specs/shell.md`, tool fb0b8c8, review
667ccc0). Fusion's Shell as ONE op that eats its body: click the
faces that should be open, drag the arrow for the wall, Inside / Outside; a
body's tree row opens it with no face open (a closed hollow — the framework's
new `bodyRow`); every click on the body while the panel is open is a toggle
the SERVER decides (`face_toggle`, Fillet's face rule). `probes/shell_probe.py`
found three kernel lies the op now refuses with a sentence: `offset()` with no
opening returns the offset SOLID (a shrunk box), walls that meet in the middle
return the body UNCHANGED, walls past the far side return an OPEN SHELL — and
two exception classes with kernel wording, translated. 24 + 3 gauntlet + 4
browser tests, fast tier 1435. Decided: no ghost (a cavity inside an opaque
body cannot be drawn by growing an outline), flat openings only (the kernel
refuses a curved one), Fusion's Both direction deferred (§10).

*Reviewed and fixed 667ccc0* — 5 findings, all 5 fixed, 0 rejected, 4 + 2
browser tests, fast tier 1439, ui v185. The **P0** was silent wrong geometry
on a body in SEVERAL LUMPS, which the new `bodyRow` makes a one-click target
(a `linear_pattern` of a boss — a form 13 of the 50 saved designs carry — or
a cut that severed a plate): `offset(openings=[…])` shells only the lumps a
listed face belongs to and hands back the RAW OFFSET SOLID for the rest.
Measured on three 20 × 20 × 10 boxes at t = 2 with one top open,
[1952, **1536**, **1536**] where a correct closed shell is 2464, and Outside
[2912, **8064**, **8064**] — blocks GROWN by 2 mm — with one solid per lump,
watertight, `health []`, `pieces 3` and a green row. So two of three patterned
bosses silently became smaller blocks. Section 4's lesson again: the gate goes
BEFORE the kernel (`sketch.assert_every_lump_open`), and it refuses only that
case — an opening on every lump is exact (1952 each) and no opening at all is
exact through the difference route in both directions (2464 / 4064 each).
Two **P1**s in the framework, the second hiding behind the first: the LAST open
face could not be closed, because `tool.js`'s "keeps at least one edge" guard
read the plan's `edges` — the picks for an EDGE tool, but the OPEN FACES'
outlines for Shell, whose empty set is exactly the closed hollow body the spec
promises (gated on the input KIND now; Fillet and Chamfer unchanged); and a
REVERT re-pushed the values it had just undone, because `show()` restores the
BOXES while a param with no box lives in the plan (Shell's face set, Mirror's
plane) — on the 12 mm plate at 6 mm walls the top-open shell builds and a
closed hollow cannot, so closing that face looped revert → replan → refuse at a
MEASURED 50 rebuilds in 6 s and 28 more in the next 3, for ever (the revert now
restores `st.plan` to the plan the good values came from, which closes the same
latent hole for Mirror). Two **P3**s: a `faces` value that is not a list put
`TypeError: 'int' object is not iterable` in the feature row (section 5's
class), and the tree dumped the picked faces as raw JSON — Mirror's "reads as
its parts" handler covered a single object, not a list. CLEARED by measurement:
the whole thickness ladder in both directions (nothing garbage passes the
volume oracle), the closed hollow as one solid with a void (`pieces 1`), an
inner cavity face unable to toggle an outer one (the normal test separates them
even at t = 0.02), and `shell` of a sketch profile failing with a sentence
rather than segfaulting.

*Round two b99a24d* — 3 findings, all 3 fixed, 0 rejected, 11 tests, fast tier
1450, ui v186. The **P0** is round one's P0 THROUGH ANOTHER DOOR, the pattern
of sections 3 and 4 again: `assert_every_lump_open` asks that every lump have
an OPENING, not that every lump actually HOLLOWS. With a top open on each — so
that guard is satisfied — a lump the wall does not fit comes back UNTOUCHED:
20 × 20 × 10 beside 3 × 20 × 10 at t = 2 measured [1952, **600**], where 600 is
the raw block with 6 faces; beside 20 × 20 × 4 at t = 5, [3500, **1600**];
three patterned bosses with the middle one narrow left that one solid. Every
check passed — watertight, `health []`, the total volume down, the row green.
ALONE each small lump is correctly refused ("nothing was hollowed"): it is the
WHOLE-BODY volume check that a second, bigger lump defeats, because the big
lump's hollow pays for the small one's block. `sketch.assert_every_lump_hollowed`
is that same rule applied PER LUMP (result lumps paired to input lumps by
nearest bounding-box centre), AFTER the kernel, because only the kernel knows
whether a wall fits. Outside measured clean over the hostile corpus, the
no-openings difference route the kernel already refuses, and a one-lump body
skips the check — so nothing in the library changes. The multi-lump corner is
now IN the gauntlet: the shared corpus is all ONE-lump bodies, which is how
this got through twice. A **P2** REGRESSION in the user's live designs: round
one's "a list reads as its parts" branch also catches fillet's and chamfer's
stored `edges`, which carry `faces: [{center, normal}, …]` — a list of forms,
joined, writing `faces [object Object], [object Object]` into the feature tree
on `my-part-8` and 4 more features. The P4 review's own rule, put back by the
fix that cites it; a part that is itself a form now reads as its parts at any
depth, and the MIXED list `["top", {center, normal}]` — the ordinary result of
clicking a second face on an AI-authored or legacy shell — reads as words
instead of falling back to raw JSON. A **P2** from the revert fix: `st.plan =
st.lastGoodPlan` made a pre-existing wart visible, because `changeProfile()`
reaches `startPreview()` with the session still under way and cleared neither
`lastGood` nor `lastGoodPlan` — so after switching Extrude or Revolve to
another sketch, a refusal reverted to the FIRST sketch's values and now also
restored its PLAN, putting the arrow, the safe range and the through-all sign
on the other sketch. Both are cleared now; edit mode never passes there.

*Round three b5c6e70 — Shell is CLOSED* — 2 findings, 1 fixed, 1 REJECTED, 4
tests, fast tier 1454. Round two's own guard **refused correct geometry**: it
paired each result lump to the input lump with the nearest bounding-box
CENTRE, on its own written assumption that "separate lumps stand apart by far
more than one wall, so it never ties". Two CONCENTRIC lumps break that outright
— a post inside a ring, a spigot in a bore, whose centres are the SAME point —
so the tie sent both results to one seat, left the other empty, read that as
"vanished" and refused. Measured: the kernel had shelled both lumps perfectly,
ring 3628.54 and post 458.28, each to its own oracle's decimal, watertight and
`health []`. Section 5's rejected-fix shape, built by the round guarding
against it. The pairing was never needed: a result lump is the block when it is
IDENTICAL to one that went in — same bounding box, same volume — which needs no
pairing, no distances and no ties, and the whole BOX tells the ring and the
post apart where the centre cannot (40 × 40 × 10 against 10 × 10 × 10).
Identity is exact rather than a judgement call: over 99 result lumps across
five second-lumps and ten thicknesses in both directions, an untouched lump
matched at d(volume) 0.0 and d(box) 0.0 (1.1e-13 at worst) while the closest a
lump that really hollowed ever came was 0.992 of its input — an honest 4 × 4 ×
2 cavity at t = 8. The rule is direction-agnostic now, which round two's was
not. **REJECTED, measured:** `tree.js`'s new `readable` recursion overflows the
stack at depth ~5000, but `JSON.stringify` — the branch it replaced — throws
`RangeError` at exactly the same depth and threw on a cycle where `readable`
throws; nothing was added, and the longest real row got SHORTER (567 chars
against 607). CLEARED so no round four re-derives them: no lump ever vanished
over six extreme thicknesses; an outside shell never merged two lumps even at a
2 mm gap and t = 6; `inspector.closed_shell` is effectively per-lump; the
result's `.solids()` / `.volume` / `.bounding_box()` never raise and cost 5 ms
against the kernel's own 239 ms; `startPreview` has exactly two callers and is
a closure local.

*Move and Rotate built 2026-09-11* (spec `specs/move-rotate.md`, tool in the
commit the review brief names; review pending). Fusion's Move/Copy split along
the ribbon's two buttons and declared from ONE file (`static/js/move.js`, 139
lines for both, Fillet/Chamfer's shape): **Move** — three arrows in Fusion's
colours (red X, green Y, blue Z) meeting at the body's centre plus the current
offset, so the triad rides the body; **Rotate** — one ring about X / Y / Z
through the body's own centre, the gold axis line, 45° snapping inherited.
Both ops EAT their body (no Join / Cut row); any face of the body names it — a
CURVED one too (the framework's `anyFace` + `bodyRow` now means "the body is
the input"), or its tree row. `rotate` grew a **`pivot`**: `"center"` (the
tool's choice — the ring's centre and the op's pivot come from ONE function,
`blocks.body_centre`), `[x, y, z]`, or absent / `"origin"` = the world origin,
the legacy default kept on purpose so planetary-assembly (the one saved design
with a rotate) does not move — §10's "rotate needs a migration" row is met
without one. The **ghost is the body itself**: its mesh, cloned when a drag
STARTS (afterApply runs before the viewport follows the document, so the scene
is stale there), offset or turned by the change since the last build, gone on
release. `probes/move_rotate_probe.py` records the right-hand rule on all
three axes (the ring frames are (X,Y) / (Y,Z) / (Z,X)), the pivoted turn's
health and the Python wording `move` now translates. 44 backend + 3 browser
tests. Decided without the user: world axes only (Fusion's edge / face-normal
axes and Point-to-Point later, §10), no Copy box (Pattern's job), relative
offsets. Gotcha for the next gauntlet: a turned L-bracket's bounding-box
centre MOVES even though the pivot does not — the invariant is the way back.

*Press Pull built 2026-09-11* (spec `specs/press-pull.md`, tool in the commit
the review brief names; review pending). The plan's "Push/Pull naming" row and
the last of P4's seven: no new op, no panel, no backend change, no kernel
call, so no probe. Fusion's Press Pull is a ROUTER and so is ours —
`extrude.js openPressPull()` reads the selection's kind once (`tool.js
selectionKind`, the same answer `open()` reads a moment later) and starts the
command that fits: a flat face or a sketch profile is Extrude (face mode pulls
the face), an edge is Fillet, a curved face gets one sentence (Fusion's Offset
Face does not exist here) and no panel. The panel header and the tree row are
Extrude's or Fillet's, as Fusion's timeline shows an Extrude and never a
"Press Pull"; `press_pull` is a ribbon key in `icons.js` marked as not an op,
first in Modify → Features where Fusion keeps it. 4 browser journeys with real
clicks (a typed 5 mm pull grows the plate by exactly 60 × 40 × 5 mm³ as a
Join, one body left; a sketch row; an edge; a curved face). Line delta:
+40 / −4 in `static/js`, the smallest of P4's seven. Decided without the user:
Fusion's name "Press Pull" over the plan's "Push/Pull"; the profile and edge
routes beyond the row's "flat face of a body".

*Press Pull review CLOSED 2026-09-11 in ONE round* (`9584b39`, ui v191): 1
finding, 1 fixed, none live. The curved-face branch was **the only command
press in the app that returns without ending what was pending** — press Create
Sketch (a plane pick, no panel, so no modal lock and the ribbon lets the next
button through), then Press Pull on a cylinder's side: the sentence says "click
a FLAT face to pull it" while the plane pick is still armed underneath, so that
very click lands in the SKETCH EDITOR. It stranded an Extrude / Revolve / Hole
profile pick the same way, and the row waiter `ca5725a` had closed for every
other tool. The generalizable rule, now enforced in one place: **a command
press ends what was pending even when it opens no panel** — `open()`'s own
preamble became `tool.js endPending()` and the router calls it after reading
the selection, before routing, so no later branch can reopen the hole. With
that, P4's seven tools are all built AND reviewed.

**P5 — The AI uses the tools (§5 step B).** Incremental authoring through
the plan endpoint; chat edits point at parameters; the FEATURE-TREE-PLAN
"step 4" everyone deferred.
**BUILT 2026-09-11, 5dc7817 (review pending).** The model replies ONE step
at a time — `add` a feature, `edit` one parameter, `remove` its own last
step, `done` with a spec — and `author.author_steps` pushes each through
exactly what the toolbar's Add Feature goes through (`Document.add` strict,
`lint_tree`, rebuild). A refused or broken step is undone before the model
hears its sentence; a good step answers with measured facts (volume, size,
pieces, the bodies now in the tree). The whole-design blob lint judges the
finished design at `done`; offset-method and entity-count lints run per
step. In Studio, `create` and `add` are jobs: a thread under a new kernel
lock (which every rebuild takes), an in-flight marker per step, `GET
/api/chat/job/<id>` for the browser, which prints each step as it lands (ui
v194). `create` builds in its own tab without stealing the user's; `add`
builds on the design on screen behind ONE snapshot (one Undo takes it all
back) and a job that gives up restores the design and says so. The intent
prompt gained `add`. 19 new tests, fast tier 1594. **Line delta +899/−151:**
P5 is new capability, not a refactor, and the old whole-tree repair loop
(~40 lines) is the only deletion. **Proven live the same evening:** after the
user renewed the expired OpenRouter key, the real model built an 8-feature
mounting plate through the protocol with no refused step (§10 done row). What the user does:
nothing — the key was renewed the same evening and the real model built an
8-feature mounting plate through the protocol first time (§10 done row).
**REVIEWED AND CLOSED 2026-09-11, seven rounds** (`4041703`, `5975aad`,
`bb0c4ab`, `231bf16`, `7d03e9c`, `5d2d431`; round seven found nothing): 20
findings, all fixed, 29 more tests (fast tier 1623), ui v196. What the review
changed about the DESIGN, not just the code: the spec is the user's, so an
`add` job keeps the design's own and reports a spec its new geometry breaks
instead of rewriting it; a step is judged on what it TOUCHED, while `done`
still judges the whole tree; the model may edit a feature the user built but
never remove one; one action per reply, so `done` can never ride in on an
`add` and skip the final lint; and a running job is the ONLY writer on its
tab (`_one_writer_per_tab`), which is what makes "one Undo takes it all back"
true — with a 300 s clock so a slow model cannot hold that tab (§10). The
give-up road restores the document IN PLACE, keeping the object, the rollback
bar and the build cache. A parked rollback bar refuses the job up front:
nothing below the bar is built, so nothing could be verified.

**P5b — The machine plays the user (§6 tier 4).** Decided with the user
2026-09-10: code review finds what the code says, tests find what we
imagined, and the user must not be the test department — bugs surface while
they are on a real design task, and that is the wrong moment. Three layers,
in this order. (1) `tests/journeys.py`: the random-journey runner over
`tests/fixtures/` and, opt-in, the live `designs/`; reuses P5's drive-the-tools
path, which is why it comes after P5; runs overnight at zero token cost — a
plain script against the local server, tokens are spent only when a chat
reads the bug files it saved, so the cost scales with bugs found, not hours
run. Each finding = a saved step file under `bugs/` + a §10 row + a gauntlet
case. (2) A **bug button** in Studio: one click saves the open document, the
last requests and a screenshot under `bugs/`, and the user keeps designing;
a later chat reads the folder and has the repro without a description. (3)
The **library tier fixed and run before every ship**: `pytest -m library`
cannot collect today (duplicate test basenames against `tests/e2e/`), so the
only check that protects the user's real parts never runs — fix first, it is
small. Acceptance: one overnight run over every fixture with zero unhandled
failures, at least one real bug found and fixed by it (or the run's log
proving none), the bug button round-trips to a chat, `-m library` green on
every committed design. What the user does: nothing until it exists; then
starts the run before leaving and presses the button when something feels
wrong.

**BUILT 2026-09-12, c11fd74 (review pending).** Layer 3 first, as the plan
said: `tests/__init__.py` makes tests/ a package so the seven tool tests
that share a basename with `tests/e2e/` collect (pytest 9 refuses two
rootless modules of one name), and `tests/test_library.py` rebuilds every
live design ONCE per run and asks four things of it: the file round-trips,
every green body on screen passes `inspector.health`, a red feature
carries a sentence, and every live feature is green (50 designs, 101 passed in 8 min 50 s on 2026-09-12). Layer 1:
`tests/journeys.py` opens a design the way the app does (FastAPI in-process,
the routes the toolbar calls, a throwaway history root, never `/api/save`)
and plays weighted random moves — creators, a face sketch + extrude in or
out, every modifier, fuse/cut/intersect, edits to half, double, zero and
negative, undo/redo, strike + restore, rollback + release, remove with each
mode, every tool plan on random targets, a scratch tab. After EVERY request
it asks the reviewer's questions: an `error` naming an exception class or
a status outside 200/400; a 400 that changed the document; a green body
that is unsound; undo that does not give back the document before the
step; strike+restore or rollback+release that leave a different document or
a different body volume; a `to_data` that does not round-trip. Each journey
is a CHILD process, so an OpenCASCADE segfault (0xC0000005) is a finding and
the step log written before each request is its recipe. A finding is one
folder under `bugs/` — `before.tcad.json`, the one request, `after`,
`report.md` — filed once per signature (kind + op + wording with numbers
masked) and replayed with `--replay bugs/<folder>`. Layer 2: the status
bar's **Report a bug** asks one line, then `POST /api/bug` writes
`doc.tcad.json`, `state.json` (the tree with every status and sentence,
the tab's last 40 requests from a fetch ring that runs from boot, the
window errors and chat warnings, the `ui vN` stamp) and `screenshot.png`
(rendered first, then read — an unrendered canvas reads back black); it
reads the document only and is open while an AI job runs. `bugs/` is
tracked except the run log; the chat that fixes a folder deletes it.
**First runs:** 12 journeys of 30 moves over empty, pump-impeller and esp32-remote, seeds 100-111: 12 clean, 0 bugs, 0 crashes. Tests: 9 runner, 6 button, 1 browser, 2 per live
design in the library tier; fast tier 1657. **Line delta +1330/−3:**
P5b is a new tier and a new button, not a refactor. What the user does:
`python tests/journeys.py --hours 8` before leaving (add `--library` to
include the real designs, read-only), and press the button when something
feels wrong; the next chat reads `bugs/`.

**P6 — Launch preparation.** Vendor three.js locally (offline today = broken),
LICENSE + third-party notices, units label, a one-click run script, examples
gallery review, CI running the fast tiers, a fresh-machine install test.

**Later:** named parameters, Sweep/Loft tools, Text entity, section view,
assemblies, the user's personal project.

---

## 8. The per-tool ritual (P3 onward)

1. **Spec** — one page in `specs/<tool>.md`: the three sentences of what you
   click and see, the handle, the value box, failure messages. User
   approves.
2. **Probe** — any kernel behaviour the tool relies on gets a probe script
   under `probes/<tool>_*.py`, committed.
3. **Plan tests** — table of (input geometry × selection × params → plan).
4. **Backend op guards** — every way the kernel can fail becomes a sentence
   naming what to change; no raw exception, no zero-volume "success".
5. **Tool declaration** — the `tool({...})` object; if it needs more than the
   framework offers, extend the framework (and Extrude gets it too).
6. **Journey tests** — real clicks on a frozen fixture, rendered + measured.
7. **Ship** — targeted tests during the work; at ship: the fast tiers +
   this tool's journeys, `ui v` bump, restart, commit with capability +
   proof + line delta, push.
8. **Review, in the review chat** — right after the CODE commit Claude
   rewrites `REVIEW-BRIEF.md` (`Status: PENDING`, range, base, risk, rules,
   known list) and says: "Open a new chat, type `/model claude-opus-5[1m]`, then
   type `code review`." That chat (CLAUDE.md, "The review chat") reviews the
   range as ONE reviewer, fixes every confirmed finding in the same chat
   without being asked, commits, and sets the brief back to NOTHING PENDING.
   The plan row is stamped after that. Docs / plan / memory commits get no
   review. There is no user checklist after the review (retired 2026-09-10;
   the user tries tools when they choose to). The modules that predate this
   ritual (sketcher, document core and tree, versions, booleans, primitives,
   measure, extrude as a whole, import, trace, viewport, framework, server,
   author) get the same review FROM SCRATCH, one module per review chat, in
   the order of `REVIEW-QUEUE.md` (started 2026-09-08): when the brief says
   NOTHING PENDING, `code review` takes the queue's next TODO row. Two
   workstreams, one chat type.

---

## 9. Token and session rules (R11, spelled out)

- **One Claude session at a time on this checkout.** A second one gets its
  own git worktree, or waits.
- **Before debugging any "the UI does X" report:** what does the status bar's
  `ui v` say, and is exactly one `studio.py` listening on 8123? If either is
  off, there is nothing to debug yet.
- **Reading:** CLAUDE.md first, then only the files the task touches. The
  plan files are history; this file is the present.
- **Tests:** the one file that covers the change while working; fast tiers
  at ship; the browser tier only for the tool being shipped. Never the full
  suite to "see what happens".
- **No agent fan-outs, no exploratory sweeps, no screenshot loops** unless
  the user asks.
- **The user's server:** launch detached with `studio.py`, never `dev.py`;
  restart after backend changes and let it open the browser.
- **Model by task** (decided 2026-09-04 after both 5-hour windows died on
  2026-09-03 at roughly 7-8M weighted tokens each; revised by the user
  2026-09-10). **Fable 5.1 plans AND builds:** specs, kernel and geometry
  decisions, guards, probes, the tool framework, root causes, and the tool's
  code — one fresh Fable chat per tool. **Opus 5 reviews and fixes:** one
  fresh Opus chat per review (`/model claude-opus-5[1m]`, then `code review`),
  which also does the fix pass, e2e wiring, docs, plan and memory updates
  for that review. Subagents run on Opus (`CLAUDE_CODE_SUBAGENT_MODEL` in
  the user settings). Per token Opus is half of Fable, Sonnet 5 a fifth.
- **Effort `high` by default** (`/effort`); `xhigh` for a hard piece of a
  tool or the day's hard kernel question, then back to `high`. Output tokens
  are the most expensive class, and effort decides how many there are.
- **A fresh chat per tool, and after any pause over an hour.** Resuming
  rewrites the whole context to cache at 1.25x; a fresh chat costs CLAUDE.md
  plus the memory. The 1M window (`[1m]`) is off, so a chat that runs long
  compacts near 200k instead of growing to 650k per call (it had drifted
  back on by 2026-09-10 and was switched off again).
- **One review per shipped tool, ONE reviewer** — the review chat itself,
  no `/code-review` command, no subagents (the 2026-09-09 fan-out ran 46
  agents and drained the window; one reviewer at medium then found five real
  gaps). Never twice on one commit; never re-launch one the limit killed
  until the window resets. `/usage` before starting it.

---

## 10. Open items carried over (deduplicated; launch-blocking marked ★)

| Pri | Item | Source |
|-----|------|--------|
| done | **Code review of the kernel worker and the two commits before it (`53f5653..0eaf9a2`, one round 2026-09-13, fixed in `edd60a9`).** ONE finding, fixed, 15 new tests (fast tier 1734 -> 1749), `-m library` 101, ui v200. **P1: the blend guard of `77bc7fa` refused CORRECT geometry on any corner sharper than about 26 degrees** — its volume half was flat in `value^2 x edge length`, and a round of 0.2 mm on designs/spiderman-logo's 160.5-degree crease moves 0.0628 mm3 of a 26707 mm3 body (0.0002 per cent, bounding box untouched, valid, health empty) and was told the kernel had returned "not a blend of this body", blaming sliver faces on a sound part; designs/rocky-balboa carries two such edges. Each picked edge is counted by its corner now — a round moves `r^2 x (tan(a/2) - a/2)` per mm, derived then measured to the fourth decimal on 90/30/10-degree wedges — floored at 1.0 so nothing is tighter than before and capped at 100. Safe because the two halves are ANDed and the BOX half is decisive on the body the guard exists for: across rims 0/2/4 at every radius from 0.05 to 0.79 the crash-class results retreat 49.6-50.0 mm against a 1.2-9.5 mm limit, and all eight rims are still refused at every radius. The process boundary itself came through clean, by measurement: a `.brep` round trip of a TESSELLATED body is exact to the last decimal in volume and in every face and edge fingerprint; OCCT's shape hash is orientation-insensitive, so the same edge from `part.edges()` and from `face.edges()` hashes equal (FORWARD against REVERSED) — `kernelguard.indices`' hash path is sound and its linear fallback is belt-and-braces, not load-bearing; `_cap_memory` really caps (a child under a 0.5 GB ceiling gets MemoryError); and the two locks cannot deadlock because no thread that holds `kernelguard._LOCK` ever asks for `studio._KERNEL_LOCK`. Also fixed: the busy overlay told someone waiting on a boolean that "this step stops itself if it runs too long" — only a round, a bevel and a hollow have that budget. | review 2026-09-13 |
| done | **Code review of P5, the AI step loop (`b78dc1f..92bdeef`, seven rounds 2026-09-11, `4041703` -> `5d2d431`; round seven found nothing).** 20 findings, all fixed, 29 new tests (fast tier 1594 -> 1623), ui v196. Every one reproduced by measurement first (`probes/p5_*.py`) and locked by a test proven RED on the commit it fixes, in a throwaway worktree. The five that mattered, all on the AI's "add to the design on screen" road: `done` WROTE THE MODEL'S SPEC OVER THE USER'S OWN (31 of the 50 live designs pin a size, 22 pin holes — and a refused `done` left its spec behind too); a CORRECT step was undone and blamed whenever some OTHER feature was red, which locked the AI out of the design entirely after three tries; the AI could DELETE a feature the user built while the reply said "Added one or more parameters"; `{"add": ..., "done": true}` in one reply FINISHED the design with no final lint and no spec check (two loose bodies reported as verified); and a user edit landing mid-job broke "one Undo takes it all back" — the busy overlay covers the viewport only, so the ribbon, tree and tab strip stayed live. Also: a dead job thread left the browser polling for ever behind the overlay; a parked rollback bar made every step "UNDONE (after rollback bar)" and the give-up restore then dropped the bar; the create door walked past MAX_TABS and left empty "designing..." tabs behind; `/api/tool/plan` ran inside the kernel between two AI steps. Rounds two to six were all findings in the previous round's OWN new guards. | 2026-09-11 |
| P2 | **A SIXTH pre-existing red browser test, not previously recorded: `tests/e2e/test_tree_history.py::test_sketch_nests_with_its_consumer`.** It asks the tree for the `class` of the node whose `.nname` reads `sk1` and expects `child` (a consumed sketch nests under its extrude); the locator resolves but the class does not contain it. Measured 2026-09-12 at `c11fd74` in a worktree, BEFORE the P5b review's fix commit, so it is not that commit's and not the review's — the known-red list in REVIEW-QUEUE.md named `test_tree_delete.py` (five) and the order-dependent revolve ring test, and this one was missing from it. Same class as those: it belongs with the delete / strike-out tree work. The other 18 browser tests in `test_bug_button.py`, `test_tree_history.py` and `test_tree_shape_edit.py` pass. | P5b review 2026-09-12 |
| P1 | **`shell` SEGFAULTS OpenCASCADE on a scaled body, reproducibly, in one click** — the journey runner's first real catch, and the repro is in the inbox: `bugs/20260912-175819-isogrid-panel-s9016-crash/`. `shell {thickness: 1.8, open_face: "none"}` on `j13_scale` (a `scale` of an `intersect` of an extrude and a rotated ball, built on designs/isogrid-panel) kills the process with 0xC0000005. Deterministic: `python tests/journeys.py --library --designs isogrid-panel --seed 9016 --steps 26 --journeys 1` files the same folder every time, on an idle machine, and `journey.json` holds all 26 steps in order. The product survives it as designed — the supervisor relaunches the child with the tabs as of the last completed request and the UI says so — so it is a crash, not silent wrong geometry. Deliberately NOT guessed at in the review chat: section 4's `loft(sketch, solid)` was the same class and the answer was a KIND gate before the kernel, but Shell's own review spent three rounds on guards that refused CORRECT geometry (nearest-bbox-centre pairing, whole-body "nothing was hollowed"), so this needs a build session that narrows the shape class first (is it the scale, the ball-intersect lump, or the thickness against the wall?) and probes `BRepOffsetAPI_MakeThickSolid` before writing a refusal. **DONE 2026-09-12, `ac5c11d`.** Not the scale: the shape class is a ball clipped by a box, and a thickness sweep put the edge at HALF the body's smallest extent (1.27 mm refuses, 1.29 mm crashes; the same shape unscaled and ten times bigger crash the same way). A closed inward wall of half a lump's smallest extent or more leaves nothing hollow, so `sketch.assert_wall_fits_every_lump` refuses it per lump BEFORE the kernel; the same bound refuses a silent wrong result (a ball of radius 3.2 at t = 5 came back "hollowed" through an inverted offset sphere). The journey replays clean. The body joined the gauntlet corpus as `clipped_ball` and found the Mirror crash below at once. | P5b review 2026-09-12; fixed ac5c11d |
| done | **`shell` OUTSIDE on the clipped ball still SEGFAULTS from 1.2 mm up** — the sibling of the row above through the other direction, found by its thickness sweep (`probes/shell_thick_wall_sweep.py`). No geometric bound applies to GROWING a body (the box at t = 15 outside is exact), and every flag combination of `MakeThickSolidByJoin` / `MakeOffsetShape` with the intersection join crashes on that body in both directions (`probes/shell_offset_flags_probe.py`); only the rounded join survives, which is not the sharp-cornered geometry the tool promises. The kernel refuses every thinner wall on this body cleanly, so the crash needs a wall thicker than the sliver where the sphere meets a clipping plane. Candidates: a per-vertex test that the offset surfaces still meet (the three surfaces at the cap's corner stop meeting at t of about 1.07 on the 2.56 mm body), or running the offset in a child the way the app's supervisor already survives it. The supervisor recovers the tab either way. **DONE 2026-09-13, the kernel worker (`kernelguard.py`).** Not another bound — the plan's own conclusion below. The offset runs in a warm child now, so its death is the sentence "shell: walls of N mm crashed the geometry kernel — nothing was changed and the app is unharmed" and a red row. Measured 2026-09-13 on the gauntlet's `clipped_ball` (the 10x body): OUTSIDE at 1.5, 4, 8 and 12 mm all refuse CLEANLY there, so the crash this row names belongs to the 2.56 mm original; either way it can no longer reach the user. | build 2026-09-12; kernelguard 2026-09-13 |
| done | **`fillet` SEGFAULTS OpenCASCADE on a sliver body when SEVERAL edges are picked at once** — the other half of the overnight run's first finding (`bugs/20260912-232440-my-part-8-s46791-crash/`, my-part-8 seed 46791 step 14). The silent WRONG result the same body gave on ONE edge is fixed (`77bc7fa`, the blend guard measures what the kernel returns); the crash is not, and no post-kernel measurement can help. Measured (`probes/fillet_crash_sweep.py`, `probes/fillet_crash_bisect.py`, one radius per child): all eight "horizontal" rims at once die with 0xC0000005 at every radius from 0.05 to 0.5 and refuse cleanly at 0.8 and up; any ONE of them alone never crashes; all 53 edges at once never crash either; `chamfer` on the same eight never crashes. The body is committed as `tests/fixtures/sliver_intersect_plate.brep` (181.499 mm3, 19 faces, a ZERO-area cylindrical face, edges 0.00014 mm long, valid by `BRepCheck_Analyzer`, unchanged by `.clean()`). A pre-kernel guard on the slivers themselves was MEASURED AND REJECTED: `probes/sliver_body_corpus.py` shows real bodies carry faces of 0.00028 mm2 and edges of 0.000035 mm (my-part-9, planetary-assembly, planetary-ring, autonomiq-sat-panel) and fillet correctly, so refusing them would block real work. Candidates: filleting the picked edges ONE AT A TIME and fusing the results (changes the geometry at shared vertices), or running the blend in a child the way the supervisor already survives. **DONE 2026-09-13, the kernel worker (`kernelguard.py`).** Both candidates this row listed (fillet the edges one at a time; run the blend in a child) were weighed and the second won: filleting one at a time CHANGES the geometry at shared vertices. `blocks.blend_after_guards` — the kernel call and the two measurements that judge it — now runs in the worker, and `tests/fixtures/sliver_intersect_plate.brep` at radius 0.4 on all eight rims is a test (`tests/test_kernel_guard.py`) that asserts the process LIVES. | overnight run 2026-09-13; fixed by kernelguard |
| done | **`shell` SEGFAULTS OpenCASCADE on real design bodies across a WIDE band of thicknesses, and no bounding-box bound fences it.** Two of the overnight run's eight findings, both in `offset()`, both beyond `ac5c11d`'s reach. (a) `bugs/20260912-232600-oneplus-7-pro-case-s46794-crash/`: `shell {thickness: 1.1, open_face: "bottom"}` on designs/oneplus_7_pro_case's `final_case` (78.9 x 165.6 x 12 mm, 60 faces, ONE lump). `assert_wall_fits_every_lump` guards the CLOSED inward hollow only (`d == "inside" and not openings`) and half the smallest extent here is 6 mm anyway. Measured (`probes/shell_open_face_crash.py`, one thickness per child, body committed as `tests/fixtures/oneplus_case_shell_body.brep`): open BOTTOM builds at 0.2, DIES at 0.5, 0.8, 1.0, 1.1 and 1.5, refuses cleanly at 2 and up; open TOP builds at 0.2, refuses at 0.5, DIES at 0.8 and 1.0, refuses from 1.1; CLOSED never crashes on that body. The window is NOT monotonic in thickness. (b) `bugs/20260913-045247-pump-impeller-s47244-crash/`: editing `hub_seat.z` from 8.75 to 17.5 rebuilds `j22_shell` — a CLOSED shell, thickness 1.9, on a 3-lump body — and dies. The SAME shell built at the previous z; the edit moved one lump's volume by 14 mm3 and left every bounding box identical, so nothing a bound can read changed. The lumps are 11.8 x 14.0 x 11.8, 11.8 x 5.86 x 5.9 and 11.8 x 5.86 x 11.8, so 2t = 3.8 is far under the 5.86 the per-lump bound needs. Measured (`probes/shell_third_crash.py`, body committed as `tests/fixtures/impeller_cut_shell_body.brep`): 0.2 and 0.5 refuse cleanly, **every thickness from 0.8 to 2.9 DIES**. Together with the clipped-ball rows above that is four bodies and three shapes of crash, so the answer is structural, not another bound: run `offset()` in a CHILD the way the app's supervisor already survives one, and turn its death into a sentence. The supervisor recovers the tab meanwhile. **DONE 2026-09-13, the kernel worker (`kernelguard.py`).** This row's own conclusion — "the answer is structural, not another bound: run `offset()` in a CHILD the way the app's supervisor already survives one, and turn its death into a sentence" — is what was built, for `shell`, `fillet` and `chamfer` together. Both bodies are tests now: `oneplus_case_shell_body.brep` at 1.1 open-bottom and `impeller_cut_shell_body.brep` closed at 1.9, each asserted to refuse in a process that lives. | overnight run 2026-09-13; fixed by kernelguard |
| done | **A closed `shell` could hand the BODY BACK as a hollow — valid, watertight, health empty, green in the tree and saved.** The P0 of `bugs/fixed/20260913-193839-my-part-5-s18800-step25/`, found BESIDE the segfault the folder was filed for, the way my-part-8's silent fillet hid behind its crash. On my-part-5's `j2_mirror` (413262.875 mm3, 25 faces, one lump, 35 x 313.383 x 116.214 mm) a CLOSED 3 mm shell returned **413260.165 mm3 — 2.709 mm3 removed, 0.00066 per cent** — and every check that existed passed, because all of them ask about IDENTITY: "nothing was hollowed" is `abs(v_out - v_in) <= 1e-6`, and 2.709 clears 1e-6 by seven orders of magnitude. The same body at 1.5 mm came back with `closed_shell` True and **`is_valid` False** — `closed_shell` is an edge census, not `BRepCheck_Analyzer`, and `Document.rebuild` runs health with `check_valid=False` on INTERMEDIATE features, so an op that eats its body could pass an invalid one on. **FIXED 2026-09-14.** Two checks in `shell_after_guards`: OCCT's own verdict (via `inspector._try`, because `is_valid` is a RAISING property), and `sketch.assert_walls_could_be_a_skin` — an inward shell's walls lie within `t` of the surface they came from, so their volume is about `area * t` and never a multiple of it. A volume FRACTION cannot do this job and was measured out: a 12 mm plate at 5.9 mm walls is 98.91 per cent of its body and CORRECT, while reading 0.72 of its skin where the wrong result reads 2.72. The ceiling is 2.0 against a measured 1.056, calibrated over the gauntlet corpus and the three committed crash bodies at nine thicknesses from 0.2 to 8 mm, closed and open (`probes/shell_wall_bound_corpus.py`): sound closed 0.61-1.056, sound open 0.61-0.955. Fast tier 1749 -> 1762, `-m library` 101 — no live design loses a feature. | overnight run 2026-09-14; fixed 2026-09-14 |
| done | **The `autonomiq-panel` s18884 "hang" was the runner's ceiling, not the kernel** — the last of the overnight findings to be cleared, and the fifth of the same class as the four retired in `371c8e2`. The runner killed the child at 600 s while the guard's own 900 s budget was still running, so what the kernel was doing was never learned. Measured 2026-09-14 (`probes/shell_slow_panel.py`): the body is designs/autonomiq-panel scaled 1.5x — ONE lump, 675 faces, 312 x 162 x 15 mm — and a closed 2.7 mm shell is REFUSED by the kernel ("walls of 2.7 mm do not fit this body") after **879 s standalone, 692 s through the API**. 2 x 2.7 fits the 15 mm thinnest extent comfortably, so nothing before the kernel could have known. The replayed journey now files no finding at all. **The margin is the thing to keep: 879 s sits about 21 s under the shipped 900 s budget**, so a slower box turns this correct refusal into "was stopped after 15 minutes"; `test_the_shipped_budget_is_above_every_correct_answer_ever_measured` carries 879 as its floor now (it was 630). | overnight run 2026-09-13; cleared 2026-09-14 |
| done | **A bug folder whose child was KILLED could not be replayed at all** — and those are the folders most worth re-running. A segfault or a stall dies before `before.tcad.json` is written, so the documented `--replay` line answered "holds no before/doc/after.tcad.json" and the only way back to the finding was a seeded overnight-length run; `process-died` was even declared `_REPLAY_BLIND` for that reason. Hit head-on on 2026-09-14 trying to verify s18884. **FIXED**: `journey.json` already keeps the design the journey opened and every step in order (the in-flight one included, with a null status), so `replay` opens that design and re-sends them, says out loud that the design is the live one as it stands today, and the crash report now prints the `--replay` line itself. | 2026-09-14 |
| P2 | **The shell depth guard still reads BELOW the real deepest material on a body whose thick region is a PLATEAU, so its refusal quotes a wall limit that is too low.** Found by the code review of `cc78019..3bbfcca` and only HALF fixed there. Two causes were separated by measurement. The first is COVERAGE and is fixed: a flat face tessellates into one to six triangles however big it is, so one ray per centroid spent 33 of a 108-point sample budget and put no ray near a taper's thick end (`sketch._barycentres`, the review's fix). The second is SEED RANKING and is not: `_climb_to_the_deepest` climbs the three DEEPEST samples, and a uniform region measures exactly what its chord allows, so it outranks every station on a taper whose real maximum is HIGHER. The repro is `probes/shell_depth_plateau_probe.py` -- a 2 mm-to-30 mm draft wedge fused into an 80 x 80 x 24 slab, ONE solid, 155,657.143 mm3: the guard reads 12.0000 (the slab's own half-thickness) where an independent grid reads 12.4300, and `shell` refuses 12.05, 12.2 and 12.4 mm while the kernel builds all three valid and watertight (cavities 21.185, 8.139, 0.326 mm3). Raising `_DEPTH_CLIMB_SEEDS` to 24 does NOT fix it -- the slab holds dozens of samples at exactly 12.0, all more than 12 mm apart, so they take every seed -- and neither does `_DEPTH_CLIMB_STEPS` 400: a plateau has no gradient to climb. WHAT IT COSTS THE USER, measured and not guessed: after the coverage fix, 7 of the library's measured bodies still read low (bit-tray 8.0039 vs 8.7300, my-part 2.5000 vs 2.9067, fan-disk 2.5001 vs 2.5923, my-part-2 41.4708 vs 42.3480, hole-box top-open 4.5054 vs 5.0045, my-part-8 18.5436 vs 19.0708, pump-housing 8.2918 vs 8.4848). On 6 of the 8 bands put to the kernel the KERNEL REFUSES TOO, so only the number in the sentence is wrong; on 2 it builds sound and the cavity is a sliver (fan-disk t = 2.55 removes 301.190 mm3 of 34,649; my-part-2 t = 41.8 removes 6.014 of 1,297,968). That is why this is P2 and not P1: nothing basic is blocked, the guard's verdict is right, its quoted limit is up to 0.87 mm low. THE CANDIDATE, not built: seed the climb from the deepest station of each cell of a coarse spatial grid rather than from the deepest three overall, with a cheap first pass (few steps) to rank the cells and a full climb only for the winner -- spatial coverage is what a plateau defeats, and depth ranking is what it exploits. It needs its own cost measurement on the 675-face panel first, where the refusal path is 7.2 s today and 13.0 s at 30 seeds. Coverage of the review's own sweep, said out loud: 11 bodies over 400 faces were skipped (the grid oracle is too slow on them) and the sweep was stopped on rocky-keychain's second mode, so 58 body/modes were measured, not the whole library. | code review 2026-09-16 |
| P2 | **The skin ceiling is set 89 per cent above the sound results and 2.6 per cent below the wrong one** — measured over the user's OWN library for the first time by the code review of 2026-09-16 (`probes/shell_skin_library_probe.py`, 50 designs, the finished body of each, t = 1/2/3, the skin check itself patched off so a result it would refuse is still measured). Of 37 results that pass every OTHER check, **35 read 0.4449 to 1.0377** and **two read 2.0524 and 2.7189** — and both of those are genuinely WRONG bodies, not false alarms: on designs/cam-cover-lower at t = 1 the kernel removed 971.569 mm3 where the real cavity is **39,921.8 +/- 280.9 mm3** by Monte Carlo over the interior (`probes/shell_skin_camcover_probe.py`; the same sampler reads the body's own volume 73,615 against 73,434), and at t = 0.5 it removed 452.798 of 56,472.7. So `assert_walls_could_be_a_skin` is EARNING ITS KEEP on the user's real parts, and the worry the brief raised — that a concave-heavy body would cross 2.0 while correct — did not happen. THE CAUTION IS THE OTHER WAY: 2.0524 clears the ceiling by 2.6 per cent, so a body a shade less detailed hands back a wrong hollow that passes. A ceiling of 1.5 would sit 42 per cent above every sound result either corpus has ever shown (1.056 is the gauntlet's worst, 1.0377 the library's) and 27 per cent under the nearest wrong one. NOT changed in the review's fix pass on purpose: tightening a ceiling is how this guard has twice come to refuse correct geometry, and it wants its own thickness sweep on concave-heavy bodies first (the ratio of a concave feature is `1 + t/2r`, so it rises with t and falls with detail size). Coverage of that sweep, said out loud: 4 designs timed out at the 40 s budget (autonomiq-panel, bottle_cap_28mm, cam-cover-plaque, rocky-balboa) and 2 segfaulted in-process where the product would have the worker (gear-case, isogrid-panel). | code review 2026-09-16 |
| P3 | **The skin ceiling judges INSIDE shells only.** An OUTSIDE shell's walls sit outside the old surface and were never measured, so `assert_walls_could_be_a_skin` returns early for them — they keep every other check (nothing hollowed, watertight, OCCT-valid, every lump hollowed) but not this one. Same ladder on the corpus in the outside direction would settle it; no wrong outside result has been seen. | shell skin bound 2026-09-14 |
| P2 | **One `/api/edit` on designs/planetary-ring NEVER comes back.** `bugs/20260913-081533-planetary-ring-s47276-crash/` was filed as `exit code 4294967295` because the runner could only read the corpse; the request is `POST /api/edit {feature_id: space_sketch, param: offset, value: 0}` at step 33, and in the overnight run it ran from 05:09:13 to 08:15:33 — **three hours and six minutes** — before something outside the runner ended it. Reproduced 2026-09-13: 14+ CPU-minutes with the working set FLAT at 460 MB, so it is a spin, not a memory runaway, and the two earlier edits in the same journey (steps 12 and 23) each took about 21 s. Repro: `python tests/journeys.py --library --designs planetary-ring --seed 47276 --steps 33 --journeys 1`; the runner now kills it at `--stall-secs` and files a `hang` folder naming that request. Not yet narrowed to a feature: the edit rebuilds a tree that by then holds `ring_gear` (168 faces) plus a cone, a polygon_plate, a tube, a sketch_on_face and two extrudes. **BOUNDED 2026-09-13 by the kernel worker**, not yet narrowed. The spin is INSIDE a guarded call: replayed at `TEXTCAD_KERNEL_SECONDS=120` that edit answers 200 in **169 s**, and at 30 s in **60 s** — the budget is the whole of the difference, so one guarded kernel call is the long pole and the worker's clock ends it. At the shipped 900 s the user waits up to 15 minutes and then gets a sentence, where before nothing ever came back. WHAT STILL NEEDS DOING (P2): name the op. The tree by then holds a shell, a chamfer, `ring_gear` (168 faces), a cone, a polygon_plate, a tube, a sketch_on_face and two extrudes; `bugs/kernel-crashes.log` now records every stopped call with its kind and params, so one replay names it. | overnight run 2026-09-13; bounded by kernelguard |
| P2 | **The kernel worker's budget counts the time the LAPTOP slept, so shutting the lid mid-fillet refuses correct geometry.** `kernelguard._Worker.answer` measures `DEFAULT_BUDGET` on `time.monotonic()`, and on Windows that clock IS the uptime clock — it reads `GetTickCount64` to the millisecond, and this box showed 33.08 h of uptime against 29.48 h awake on 2026-09-14. Suspend the machine during a guarded fillet, chamfer or shell and on resume the budget has "expired": the warm worker is killed and the user's sound feature goes red with "was stopped after 15 minutes" for work that took three seconds. Same defect as the journey runner's clock, fixed there in this commit (`tests/journeys.py awake_s`, QueryUnbiasedInterruptTime); NOT fixed here, because the product needs its own pass — the `queue.get(timeout=left)` inside `answer` expires on the OS's biased timer too, so a clock swap alone is not enough: `queue.Empty` has to go back round the loop while the awake clock still has budget. Not silent wrong geometry (the refusal is loud and nothing is changed), so P2. | journey-clock fix, 2026-09-14 |
| P2 | **Rounding or bevelling ALL the edges of a traced outline takes minutes and the app says nothing.** Three of the overnight run's eight findings are one class: `rocky-keychain-2` `chamfer {length: 2.5, edges: "all"}` took **630 s**, `rocky-keychain-2` `fillet {radius: 2.2, edges: "all"}` 156 s, `rocky-keychain-3` editing a fillet radius from 2.5 to 2.75 124 s (its previous step, editing a sketch offset, took 110 s and was only noted). All three bodies are traced PNG keychains of 600-670 faces, and "all" hands the kernel every one of their hundreds of edges. Nothing is wrong with the answers; the wait is indistinguishable from a freeze, and a rebuild pays it again. Candidates: say the edge count in the plan's `limits` so the panel can warn before the click; or bound the work the way the symmetry gate now is. Do NOT refuse on edge count alone — bit-tray and hole-box fillet 12-13 edges in milliseconds and the user's real parts live in that band. **HALF DONE 2026-09-13.** The wait is no longer silent and no longer unbounded: the busy overlay speaks at 20 s ("still working — a big body can take minutes; rounding, bevelling and hollowing are the slow ones") and again at 90 s ("still working — nothing you have made will be lost, whether this finishes or is refused"), ui v200 — the 90 s line first said "this step stops itself if it runs too long", which is true of a round, a bevel and a hollow and of nothing else the overlay is shown for (review of 2026-09-13); and the worker's 900 s ceiling ends anything past it. WHAT STILL NEEDS DOING (P2): this row's own suggestion — say it in the tool's panel BEFORE the click. It was not built because the threshold could not be measured honestly in one session: on the 968-face / 2862-edge keychain body (`probes/blend_cost_sweep.py`) a fillet costs about 4 s at THREE picked edges and 8.7 s at 128, so the cost tracks the BODY, not the pick count, in the band where a panel warning would fire — and the sweep's own `edge_ref` resolution is tangled into those numbers. A warning wants the kernel time separated from the pick-resolution time first. | overnight run 2026-09-13; half fixed |
| P3 | **The eighth of the overnight run's findings had no row until today: `bugs/20260913-011500-autonomiq-panel-s46927-step16/`, `add shell {thickness 2.2, open_face "top"}` on a `linear_pattern`, which took 1195 s — twenty minutes — and answered 200.** It is the slowest CORRECT kernel call the run recorded, and the reason the worker's budget is 900 s rather than tighter: 630 s and 156 s (the row above) are correct answers the user's own parts depend on, and a ceiling under those would refuse real work to catch a spin. THE COST OF THAT CHOICE, stated plainly: this particular shell is now STOPPED at 15 minutes instead of answering at 20, so whether the body it returned was sound — which `REVIEW-BRIEF.md` listed as unmeasured — will not be learned from the app. `TEXTCAD_KERNEL_SECONDS` raises the ceiling for anyone who wants to wait. | overnight run 2026-09-13 |
| done | **A shell of a body that is thin EVERYWHERE — a second shell on an already-shelled body — asked the kernel for nothing and crashed it.** The overnight run of 2026-09-15 (563 journeys, 556 clean, 2 findings + 5 repeats, all Shell) filed `bugs/20260915-210615-my-part-s95959-step18/`: `shell {thickness 1.1, open_face "top"}` on a 23.4 x 17.1 x 12.7 box already shelled at 1.3 mm, bottom open — 0xC0000005 inside `offset()`, caught by the kernel worker as designed. Measured 2026-09-16 (`probes/shell_thin_wall_probe.py`): the crash boundary is EXACTLY half the wall — 0.64 builds, 0.66 crashes — and `assert_wall_fits_every_lump` cannot see it (the body's smallest box extent is 12.7 mm and the hollow is open anyway). **FIXED 2026-09-16: `sketch.assert_something_would_be_hollowed`**, before the kernel, INSIDE direction, open or closed. An inward shell keeps the material within `t` of the faces that stay and removes the rest, so it hollows something exactly when some interior point is `t` or more from all of them (the openings' material is what the cavity replaces). `deepest_material` finds interior points by rays from face samples along the inward normal, stations along each chord, the opening faces' own points, and measures each station's distance to the staying faces exactly (`BRepExtrema`, under a millisecond each), stopping at the first deep one. **The first draft asked the OPPOSITE question — is there a wall the offset does not fit? — and refused 11 shells the kernel builds SOUND** (a 4 mm rib, a 4 mm pin, a 4 mm web between pockets, each left solid inside a hollowed plate; `probes/shell_thin_wall_corpus.py`): a thin PART is the kernel's to fill, a body thin EVERYWHERE is the one that dies. The shipped rule over the gauntlet corpus + the four committed crash bodies + both finding bodies, seven thicknesses, closed and open: 238 cases, **zero refusals of a sound shell**, 24 kernel round trips that ended in a crash or a refusal now end in a sentence naming the depth ("no point of it is more than 0.65 mm from the faces that stay"). Cost: 0.02-0.6 s per body up to 60 faces. THE HONEST LIMIT: the filed step itself (1.1 mm, top open) is a legitimate 0.2 mm recess in the lid — the lid's material is 1.3 mm from the cavity ceiling — and the kernel crashes on legitimate geometry there; that stays the worker's (`test_kernel_guard.py` KILLERS `shell_twice`, a sentence in a process that lives). The rays draw the line at 1.3 for the open lid and 0.65 closed. Fast tier +6 tests, the old lone-rib refusal moved from after the kernel to before it. **AMENDED by the code review of 2026-09-16:** "zero refusals of a sound shell" held over the corpus, and the corpus is prismatic. A station is where a ray happened to land, and the deepest material sits on one only when symmetry puts it there — on a plain draft wedge the stations read 10.62 mm against a real 12.42 (an independent grid, `probes/shell_depth_oracle_probe.py`), so closed shells at 11, 11.5 and 12 mm were refused before the kernel, in a sentence naming a limit that was 1.8 mm too low, while the kernel builds all three sound. `sketch._climb_to_the_deepest` walks the deepest measured points uphill before a refusal may stand; it can only RAISE the answer, so the corpus verdict is unchanged (238 cases, 24 correct refusals, 0 false). | overnight run 2026-09-15; fixed 2026-09-16, amended by review 2026-09-16 |
| P2 | **`shell` STALLS for the whole 900 s budget on a 55-face pocketed hexagon across a wide band of thicknesses, and it is not the wall.** The second finding of the 2026-09-15 run, `bugs/20260916-011919-my-part-9-s96223-step19/` (plus a repeat on isogrid-panel): `shell {thickness 2.5, open_face "top"}` on designs/my-part-9's body after a 0.6 mm bottom chamfer (hex prism 39 mm tall with two side extensions, a revolve, two chamfers, two fillets, four pockets, a pin and a boss). Measured 2026-09-16 (`probes/shell_thin_wall_probe.py`, 90 s budget): **1.5 and 1.7 come back REFUSED as invalid in 12-30 s; 1.6, 1.8, 1.85, 1.9, 2.0, 2.1, 2.5 and 5 all STALL**; 3.0 is refused after 45 s. Not a thickness rule: the body's thinnest web is 3.856 mm (between the round pocket and the hexagon's side) and its deepest material 15.6 mm, so 1.6 stalls with nothing thin in reach, and the stall band is not even monotonic. The pre-kernel guard above correctly ALLOWS every one of these — a cavity exists — and the kernel worker bounds each at 900 s and answers with a sentence, so the user waits 15 minutes for "was stopped" on this body. Candidates, none proven: the 0.6 mm chamfer strip whose offset vanishes at every t above 0.42 (a face that disappears is the classic MakeThickSolid pathology), or the r 2.2 fillet. The body is exported at `probes/_thin_mypart9.brep` by the probe; the folder stays in `bugs/` as the repro. | overnight run 2026-09-16 |
| done | **The spec check's symmetry proof was UNBOUNDED work and it killed the laptop (P0 class: the machine is part of the product).** 2026-09-12 21:10, the overnight journey run (`--library`, seed 39331, bottle_cap_28mm, step 5): a random 67.9 x 16.9 plate added beside the 24-rib cap made `inspector.is_rotationally_symmetric(result_shape, 24)` run `Compound(3 overlapping bodies) - rotated` for 22 minutes at 34 -> 44 GB (ShapeUpgrade_UnifySameDomain on the leftovers), Windows logged four Resource-Exhaustion events, the 16 GB box died at 22:00 and rebooted; the runner had logged `200 1351644 ms` and written "clean". **FIXED `53f5653`**: two necessary gates before the boolean (the rotation keeps the bounding box; every sampled vertex lands on or inside the shape), the proof under `SkipClean` via `cut()` (`Compound.__sub__` read 6967 mm3 of residue on an exactly symmetric overlapping compound); 11 ms for the plate case, 203 ms for the whole step, all ten live designs with a symmetry spec keep their verdict (`probes/symmetry_gate_corpus.py`). The runner: `HANG_MS` 120 s and `MEMORY_BUG_MB` 2 GB are findings even at 200, every child runs in a Windows Job object with a 6 GB ceiling (`--mem-gb`), a child dying AT its ceiling is a `memory` finding, `probes/memcap.py` runs any command under a ceiling. Evidence: `bugs/fixed/20260912-220013-bottle-cap-28mm-s39331-memory/`. | overnight run 2026-09-12; fixed 53f5653 |
| P2 | **OpenCASCADE under a REFUSED allocation answers as if it succeeded.** Under the 6 GB ceiling the same plate request completed in 55 s with build123d's `UserWarning: Boolean operation unable to clean` and a plausible verdict, HTTP 200. The kernel's `Build()` had finished and only the clean pass hit the wall, so the answer happened to be right; whether a boolean whose allocation is refused MID-BUILD can come back as a "successful" wrong or invalid solid is not measured. The deep health pass would catch an invalid solid; a valid wrong one it would not. Candidates: treat a `MemoryError` / `bad_alloc` anywhere inside a rebuild as a failed feature with a sentence, and let the runner read the child's stderr for that warning as a finding. Also known: the runner's memory oracle reads a PEAK (a request under the child's earlier high point reads 0 growth), and the ceiling is Windows-only. | 53f5653 2026-09-12 |
| P2 | **What a ✕ took away is remembered in memory only, so a restore after a reopen still falls back to the delete plan.** The P5b review found that restoring a feature turned another one the user had switched off back ON (THREE doors, all fixed: the upstream walk and the plan containing an already-struck row in round one, `/api/feature/suppress` setting the flag behind strike's back in round two). The fix records what each strike actually suppressed — `Document._struck_by` — and that record does not survive a save and reopen, nor an undo (which replaces the document object). After a reopen, striking a row whose delete plan sweeps up a row the user struck earlier, then restoring it, turns that earlier row back on again. What a FILE carries is one boolean per feature; telling "struck by this ✕" from "struck on purpose" needs a second piece of state in `to_data`, which changes the format for all 50 saved designs. Measured 2026-09-12: no saved design is in that shape today (only esp32-remote, my-part-5 and my-part-8 carry struck rows at all, and none of them has a struck row inside another row's delete plan). | P5b review 2026-09-12 |
| P3 | **`/api/bug` reads the document without the kernel lock.** It is in `_JOB_OPEN_POSTS` on purpose — "the AI is stuck" is exactly when the button gets pressed. Measured 2026-09-12: unlike `/api/tool/plan` (removed from that set on 2026-09-11) it touches NO OpenCASCADE at all — `to_data`, `_doc_json`, `leaf_solid_ids` and `is_sketch` are pure Python — so it cannot crash the kernel beside a job's own call. What is left is a torn read: `dataclasses.asdict` walking a params dict while a job step writes it raises "dictionary changed size during iteration", `_never_die` turns that into an error sentence and the report is not filed. Not reproducible on demand; the answer if it ever shows up is to take the lock for the two reads only. | P5b review 2026-09-12 |
| P3 | **The journey runner picks values at random, not from the plan's own safe range** (§6 tier 4 wording). A fillet radius is drawn from 0.3–3 mm whatever the wall, so most moves on a thin part are clean refusals and the interesting band just inside the limit is rarely hit. Read `/api/tool/plan` first and draw inside (and just outside) its limits. Also not exercised yet: `/api/measure*`, `/api/feature/params`, sketch entities other than one circle or rectangle, `/api/export`, `/api/save` round-trip (kept off on purpose: it writes designs/), and **`loft` / `sweep`** — the two ops section 7 found silent P1s in, reachable from the ribbon but not from `move_combiner`. Two moves it DOES play are judged by nothing: `move_misc` renames a feature and back, and suppresses and un-suppresses, with no comparison across either (measured 2026-09-12 on pump-impeller: 10 features, both round-trips, document and volumes identical, so there is no bug behind it today). And `check_bodies` re-asks the product's OWN `inspector.health` over the product's own leaf set, which makes it a cache-coherence check rather than an independent witness — the class section 6 covered with an inline oracle. | P5b c11fd74 |
| P3 | **The bug button's screenshot is the viewport only.** The feature tree and the open panel are in `state.json` as data, not as pixels; a whole-window capture needs a browser API the page does not have. | P5b c11fd74 |
| P3 | **A chat job has no Stop button.** An "add" job makes its tab read-only while it runs (`_one_writer_per_tab`), and the only way out is the 300 s clock (`author.MAX_SECONDS`, checked between steps) or switching to another tab. Fusion lets you cancel. Fix when the AI panel gets its own UI: `POST /api/chat/job/<id>/stop` setting a flag the step loop reads, and a Stop button beside the step log. | P5 review 2026-09-11 |
| P3 | **`/api/tabs/switch` reads the document without the kernel lock.** It is the one POST left open while a chat job builds — deliberately, because switching away is the user's escape hatch from a busy tab — so switching TO a tab mid-step can flash one stale row for under a second before the next step's `doc-updated` corrects it. Measured and left: taking the lock there would block the switch for the length of a kernel step, which is the opposite of what the escape hatch is for. Closes properly with the `/api/model` row above (one lock over every kernel-touching request). | P5 review 2026-09-11 |
| done | **P5's step protocol met the real model 2026-09-11** (after the user renewed the expired OpenRouter key): "a 60x40x5 plate, a 16 mm boss on top, four 5 mm corner holes" came out as 8 steps — base sketch, extrude, sketch_on_face, extrude, fuse, one 4-circle sketch, through extrude, cut — every step ok first time, volumes add up (12000 + 4021.2 − 4 × 98.2 = 15628.5), spec met. The only flaw was ours: the 4-cylinder cutting tool was told to "fix" being in 4 pieces (softened in the commit after 5dc7817). | P5 ship check |
| P2 | **Trim is slow on a big sketch, before any of this pass's work.** Hovering `rocky-balboa/field_sketch` (23 entities) costs 6.1 s in `trim_pieces` and a click 15.4 s; `esp32-remote/sketch28` (45 entities) costs 3.0 s to hover. The cost is `_pieces_raw` — every outline sampled to up to 384 points and every PAIR of outlines intersected — plus one full compose of the cluster per click. Measured 2026-09-11 in the review of `3b230b7` and NOT caused by it (the fix's own guard was taken off the rebuild branch, which gave 28 s back). Fix: cache the outlines between hover and click, and skip the pair loop with the bounding boxes it already computes. | review of 3b230b7 2026-09-11 |
| P1 | **A stored face pick is remembered in WORLD coordinates, so a body that MOVES can still take the pick to a different face of the same kind.** Round one of the Move review fixed the half that was silent and destructive — `resolve_face` scored the picked normal as a 25 mm² NUDGE, so past about one plate thickness of travel the nearest face was the one pointing the OTHER way, and a Ø12 boss jumped from the top face to the bottom, was built up INTO the material and swallowed whole (565 mm³ gone, every row green). The direction is a GATE now, and on a body with ONE face per direction the pick follows the move exactly as the spec promises. What is left: on a STEPPED body, two faces point the same way, and a rigid move of more than half the step can still hand the pick the wrong one — quietly, because both answers are legal. The real fix is to store the pick in the BODY's own frame (the offsets from its bounding box, say) instead of the world's, which touches `sketch_on_face`, `extrude_face`, `hole` and every saved design that holds a `face_center`. Measured: 50 designs rebuild with zero drift under today's fix, so nothing is broken while this waits. | Move review round one 2026-09-11 |
| P3 | **`solids()` in `tool.js` offers EVERY solid row, not the bodies you can see.** A `bodyRow` tool opened on a step half way up a branch appends its feature at the END of the tree, so the step feeds two features and the design grows a second copy of it. Move and Rotate refuse that in the PLAN now (a sentence naming the feature already built from it), but Shell — the other `bodyRow` tool — still accepts it, and the Target dropdown still lists intermediate solids as combine targets. The clean version is for the document to say which rows are bodies and for the tree to offer only those. | Move review round one 2026-09-11 |
| P3 | **A `linear_pattern` / `polar_pattern` fed a SKETCH answers with a diagnosis about a shape the user never asked for**: "the pattern leaves a broken solid (non-positive volume (0) - empty solid) - a copy touches the body along an edge only; a smaller count, a shorter distance, or another direction" (measured 2026-09-11: `linear_pattern` count 3, dx 20, on a plain circle sketch). The combiners have refused a wrong-KIND input by name since section 4 (`_check_combiner_inputs`), and the sketch-consuming modifiers do since section 7 (`_check_modifier_input`); the patterns, which need a SOLID, are the same family in the opposite direction and still have no gate. Out of scope for the Extrude diff, so recorded rather than fixed. | Extrude review round two 2026-09-11 |
| P2 | **The shared gauntlet corpus is all ONE-LUMP bodies** (`tests/gauntlet.py BODIES`), and that is how one P0 survived two review rounds of Shell: a lump that did not hollow is invisible to a WHOLE-BODY volume check the moment a second, bigger lump pays for it. Shell's own gauntlet now carries the corner (four mixed pairs plus a concentric ring-and-post, both directions, the whole ladder). Every other op that eats a whole body reaches multi-lump bodies the same way - a `linear_pattern` of a boss, a cut that severed a plate - and none of them has that corner: fillet, chamfer, hole, mirror, pattern, extrude_face, revolve_face. Adding a multi-lump body to the SHARED corpus would touch every op's gauntlet at once, so the cheap version is one corner per op, in its own gauntlet file. | Shell review rounds two and three 2026-09-11 |
| P3 | **Shell's second half of Fusion's dialog**: Direction **Both** with an outside thickness (two offsets, one result), a CURVED face as an opening (the kernel refuses `offset(openings=wall)` today — probes/shell_probe.py §8; a cut-then-shell route may exist), a measured maximum thickness in the plan's `limits` so the arrow can say where the walls would meet (today the op's sentence does, after the fact). | Shell 2026-09-10 |
| done | **Two panel fixes the user hit on 2026-09-07 — in the framework and the shared ring, so every tool inherits them.** (1) A DRAGGED angle lands on round numbers ("revolve goes to 90.5 — it should recognise 0, 45, 90, 180"): the ring — Extrude taper, Revolve, Circular Pattern — snaps to whole degrees and, within 3° of a multiple of 45°, to that multiple, where the handle sticks until the pointer leaves the band; the raw turn accumulates underneath so the handle never lags; typed values stay exact (`viewport.js snapAngle`). (2) A value CLEARED back to 0 with a preview up ("I change 12 to 0 and it reloads 12") was PUSHED: the kernel refused the zero-thickness solid (`Standard_ConstructionError` for extrude, the op's own sentence for revolve — probed) and the framework's revert wrote the OLD value into the box the user had just emptied. Honest zero now (parity rule 4): in create mode the preview goes and the box keeps its 0 (`tool.js unbuild`, the same code Cancel uses); an edit keeps its feature and says so once (the `hold` path). Fillet's radius, Hole's ⌀ and Pattern's count inherit both. Tests: 2 browser journeys in `test_edit_extrude.py` (create: 12 → 0 → preview gone, box 0, 8 → built, OK; edit: 0 keeps 12 with the sentence, Cancel) and the revolve ring drag now asserts 37.3 → 37 and 92 → 90. | user 2026-09-07 |
| P2 | **A polygon whose outline crosses itself builds a sketch that reports `ok` with an INVALID face**; the extrude two nodes later takes the blame ('OpenCASCADE reports the solid is invalid'). The shoelace guard in `_entity` catches a ring of zero area, not one that crosses. Pre-existing, confirmed by measurement 2026-09-09. Fix: a self-intersection test on polygon points, said as a sentence where the mistake is - the same shape as `_validate_path`'s crossing check, which paths already have. | 4th sketch review 2026-09-09 |
| P3 | **`tree.js`'s arc-label doc guard compares design NAMES**, and `freeDesignName` (dialogs.js:45-52) tests the saved design FILES, so two unsaved tabs can hold one name and an arc label can still cross between them. The guard needs the tab's identity, not the document's name. | 4th sketch review 2026-09-09 |
| P3 | **Five tools hand-type "a value typed before the plan arrived waits for it"** (revolve, hole, fillet, mirror, pattern × 2: an `if (!st.featureId && …) ctl.apply()` in `gizmos.begin`, and `!st.plan ||` folded into `isEmpty` in four of them). R2 says the framework inherits it: `applyOnce` waits for `st.plan`, `setupTool` re-applies once it lands, and OK awaits the plan. Surfaced by the honest-zero fix, which needs a `st.plan` guard only because of it. Roughly an hour, plus the browser files of the five tools. | 2026-09-07 |
| P3 | **Pattern has no drag ghost (improvement, deferred by the user 2026-09-06: "we will do that later").** Hole (c6a2377), Extrude and Revolve show a translucent ghost while the handle moves; Pattern's ring and arrows move only the number until release, and a pattern rebuild costs the kernel 250–500 ms. Plan: the pattern plan returns a tessellated mesh of the seed's DELTA (before − after / after − before — `document.delta_features` computes it already); the browser instances N−1 translucent copies about the plan's axis / along its directions, following the drag AND the typed count at once (type 6, see five ghosts before the kernel confirms); a browser test compares the ghost copies' positions with the real copies after release, because Full / partial angle and Spacing / Extent would then exist twice — the 2026-09-01 "ghost goes the other way" class. Marks only (dots on the ring, ticks on the arrow) was considered and rejected: honest but far less useful. Roughly half a day. | user checklist 2026-09-06 |
| P3 | **Pattern's count is typed, not dragged.** Fusion has a quantity handle beside the ring / arrow (parity rule 3). | specs/pattern.md |
| P3 | **Pattern lacks Fusion's Symmetric distribution and per-copy Suppress.** | specs/pattern.md |
| done | **Code review of Mirror (023ca5d → 21429d8, five rounds 2026-09-06/07: 4 P0 silent-wrong-geometry + the P0 the P0 pass itself opened, ~12 more real findings, all fixed; the ~9 deferred ones closed in the commit after this stamp).** The P0s, each reproduced by measurement first (`probes/mirror_p0_probe.py`): a `rotate` / `scale` / copy-only `mirror` row named as a seed has no delta and folded to a body-sized one (it gouged 2475 + 2475 mm³ of the plate) → `document.PLACEMENT` folds to a BODY seed; `join: True` stamped on a FEATURE seed became a whole-body Join at twice the size the moment the seed came back empty → `join` is planned only for a body seed; an image tangent to an edge is an open shell that `is_valid` passes → `_body_pattern` ends in `inspector.health` (which PASSES separate closed solids, so the legacy pieces still build); a body across its own mid-plane "created" nothing → mid-planes are offered for FEATURE seeds only. And the one the fix opened: a stored seed that stopped resolving came back from an EDIT as the legacy COPY and relocated an 80 mm plate with zero overlap → the stored `join` counts only while the stored params and the plan AGREE there is a seed (`probes/mirror_seed_collapse_probe.py`). **The deferred set (the commit after this stamp):** an unknown plane NAME sent to the plan was ignored in silence (refused with the names that exist; the current plane's own name, `face` / `stored`, keeps it); a boss ON the mirror plane was told it "lies inside the body" (image ∩ seed tells the two apart for a fuse as for a cut, `probes/mirror_boss_seed_probe.py`); the origin quads were built once at arm time and sat over HALF the doubled plate (they follow the fit in `loadModel`); the tree showed a stored plane as `[object Object]` (an object param reads as its parts); the revert sentence made its plane words in JS (R1 → `st.lastGoodPlan`, the PLAN's `plane_words`); OK on a NEW feature whose FIRST values the kernel refused said "created" over a red row (the framework now says NOT built and why — every tool's); `blocks.EXPORTS["mirror"]` still had the copy-only grammar while the tree had the new one (one grammar: every plane form + `join`; `blocks._PLANES` and its b3d import went with it). **Closed by decision, not code:** a body face wins a click over an origin quad behind it — the quads are glass THROUGH the model and sized past its silhouette, and "nearest hit wins" made faces unpickable from whole view angles (the bug that rule fixed; specs/mirror.md decision 6); the plan resolves a picked face through `plane_of` on purpose (the stored form must round-trip to what the op will build at rebuild) and `delta()` runs once per plan and once per rebuild (a cache on the document is not worth its risk for one boolean); `snapshot`'s `?? null`, the shared `originPlanes` teardown (one owner at a time — a tool cancels the sketch pick on open) and `planeQuadInfo` echoing the handed frame are nits. The retroactive body-pattern health gate stays an accepted risk (BACKLOG.md). | P4 2026-09-06/07 |
| done | **Code review of Pattern (5b52dc1; 7 findings, all fixed ca5725a, 2026-09-06).** A pattern's `seed` is the tree's only REFERENCE that is not an input — `document.REF_PARAMS` / `Document.param_refs`: rename rewrites it, delete / strike-out takes patterns of a deleted seed along, the orphan sweep leaves a live seed alone (any future param naming a feature joins REF_PARAMS). A body pattern must NOT be refused for producing the same volume (a symmetric body patterns onto itself; 14 live designs, 21 pattern features, all rebuild) — only zero motion is. `own_id` on a plan request = the feature THIS session built, so a replan never walks into the tool's own output. Frontend: a pick's bus subscription dies WITH the pick; every viewport pick outranks a tree row (fusion-parity skill). | P4 2026-09-06 |
| done | **`inspector.health` called every cone apex and sphere pole an open shell** — build123d's `is_manifold` counts the faces on DEGENERATED edges (one by construction), so a revolve about the profile's own edge, a plain cone, and anything sphere-bearing tripped it (spheres alone had an exemption), while a sweep about an axis a few microns OFF the edge — a SLIVER face, no apex — passed. `inspector.closed_shell` (one topology map) is the verdict for health AND measure (MCP `verify_step` read the raw flag and disagreed with the tree); a degenerated edge is excused only on ONE cone / sphere / revolution face — a spline fillet pinched to a point stays a defect (`tests/test_fillet_tool.py` radius 6 relies on it). | P3b 2026-09-05 (4987a15, d82e9d0) |
| P3 | **Revolve's second side has no handle.** Two sides gives Angle 2 a number box only; the ring drags side one. Fusion gives each side its own end to grab (parity rule 3: direct manipulation first). A second ring handle on the far end of the sweep, sharing the one-turn budget the way the boxes do. | P3b review 2026-09-05 |
| done | **Code review of Hole (P4, e4a9d05..5336c82; 8 angles, 25 verified findings, all acted on 2026-09-06).** The four that could reach the user: a click while EDITING a hole was ignored (the plan overwrote the request with the stored point, so the re-pick the tool itself arms did nothing and said nothing) → the request is the answer, the stored values the fallback; a hole authored without an `at` opened at the FACE CENTRE while the op cuts at (0, 0), so pressing OK on it moved the cut (one default now, `sketch.HOLE_AT`, measured against the kernel's own cut centroid); a `face` NAME outlived every moved `face_center` because the op prefers the name, so an AI-authored hole could never be moved (the plan hands back ONE stored form and a click clears the other); and "nothing was cut" was a millionth of the WHOLE part, so a real ⌀1 hole in a 200 × 100 × 50 block was refused as finding no material (absolute floor — a cutter that misses measures exactly 0.0). Panel traps: choosing Counterbore / Countersink on a built hole applied a ⌀0 seat, the op refused and the revert put the Type box back to Simple (the seat kinds were unreachable), and unticking Through all applied the still-disabled depth 0 and re-ticked itself — a seat kind now seeds sizes that fit, and the framework holds a half-made state instead of applying-and-reverting it (`spec.hold`). Also: measure can drive a hole's ⌀ (the bore has no sketch circle, and the read-only sentence was untrue); the marker frame was LEFT-handed on 3 of a box's 6 faces; a through hole may have a seat and reaches `THROUGH_MM`; the cutter is built inside the try; one `_csink_height`; the plan lost 4 dead fields and a bounding box and measures the material only when asked (250-510 ms per plan on a real body); undo/redo are refused while a tool panel is open (rule 9) and a sticky pick is cancelled by a document change that is NOT this session's; two ribbon buttons were called "Hole" (the legacy one is "Centre bore"). Evidence: `probes/hole_review_probe.py`. **14 new tests** (11 in `tests/test_hole_tool.py` — the plan's edit/move/one-face-form/no-`at` cases, the absolute cut floor, a seat in a through hole, a body deeper than THROUGH_MM, the seat checked before the face, a cutter error as a sentence, and a right-handed sweep over every face of a box; 1 measure-drive; 2 browser journeys). | review 2026-09-06 |
| P3 | **Hole has no diameter handle.** Fusion drags the ⌀ on the marker circle; ours is typed only (parity rule 3: numbers come from dragging handles). The plan already hands the browser the circle's frame — a radial handle on it is the missing half. | specs/hole.md, P4 2026-09-06 |
| P3 | **A blind hole's bottom is flat.** Fusion's default drill point is a 118° tip (a real twist drill), switchable to flat. Ours is always flat, so a blind hole's depth means "to the flat bottom" where a machinist would read "to the shoulder". | specs/hole.md, P4 2026-09-06 |
| P3 | **Hole extents are Distance and All only.** Fusion also has "To" (drill until a chosen face / object), which is what makes a hole survive a thickness change without a number. | specs/hole.md, P4 2026-09-06 |
| P2 | **`sketch_on_face` snaps a face tilted under 25° to the principal plane — a plane that does not contain the face.** `face_sketch_plane` positions the sketch by the face but orients it by the nearest principal frame (|n·k| > 0.9); on a tapered wall the face's edges sat 1.4 mm off that plane (`probes/revolve_face_probe.py` §7), so a sketch drawn "on" it floats above one edge and cuts into the other. Revolve's face profile uses the true plane (`_face_frame(face, snap=False)`) — the same switch is available to the sketcher, but the offset-method sign rules and every stored face sketch were written for the snapped frame, so it is a decision, not a one-liner. | P3b 2026-09-05 |
| done | **A kernel call can SEGFAULT and take the server (and every unsaved tab) with it** — `fillet` at radius 2.0 on esp32-remote's 80-edge top rim = 0xC0000005, reproduced (`probes/fillet_segfault_probe.py`); no try/except can catch it. **Fixed 2026-09-05 (1aea14a):** `python studio.py` runs `supervise.py`, a light supervisor that starts the server as a child and relaunches it after a crash the OS reported (NTSTATUS `0xC…`; never after Ctrl+C / Stop-Process / exit 0, so the restart routine still works — exit codes probed). The session file, written after every COMPLETED POST, is the checkpoint: the fatal request never reaches it and the child comes back one step behind. An in-flight marker names the request the dead process was in; the UI waits for the server, reloads the document and speaks the note once. A saved design whose rebuild segfaults comes back UNBUILT (safe restore) instead of killing every restart. Not out-of-process kernel calls (the rebuild cache and meshes live with the Document); a checkpoint-and-relaunch, which also covers crashes no one has met yet. **12 tests** (10 in `tests/test_supervisor.py`, 2 browser journeys) after the review below — the commit message's "14 new tests" was wrong, a miscount of a pytest line that included `test_session_restore.py`. | P4 review 2026-09-04 → fixed 2026-09-05 |
| done | **Code review of the crash supervisor (1aea14a, 2026-09-05): 6 findings, 4 real and fixed, 2 refuted by measurement; the verification pass found 3 the review had not.** The one that mattered was not in the review at all: POSTs overlap in FastAPI's threadpool, and `edit_params` writes the new value into the feature BEFORE the kernel is asked — so a tree click finishing during the fatal 8-second fillet wrote a checkpoint CONTAINING the radius that was about to crash, and the relaunched server rebuilt straight back into it. The checkpoint is now taken only when no POST is still running, and the in-flight marker is a SET whose file names the oldest (a later request can no longer steal it). Also fixed: an answer landing in a tool session the crash had already closed dereferenced null (one `GONE` throw, caught once in `apply()`, replacing three unguarded sites); the 3 s watcher saw the crash but never told the panel — and its typing guard, tested first, meant a panel with a focused number box NEVER heard (the emit now lives inside `noteRecovery`, so no caller can forget it); and the relaunch had no ceiling, so a crash nobody asked for (tessellation in GET `/api/model`, which the recovered page refetches) would have relaunched for ever — now the second comes back unbuilt and the third stops, while a fatal step the user RETRIES still costs exactly one step, told apart by the in-flight marker. REFUTED with measurements, so nobody redoes them: the 120 s wait for the server (worst real design measured 26.2 s, and two listeners on 8123 proved impossible on this machine — the wait was raised to 5 min anyway and the "start it again" advice dropped, since that sentence is how a second listener would be born), and a spurious `server-recovered` on a transient network failure (no AbortController exists, fetch resolves on every HTTP status, and the browser replays a POST on a dead keep-alive socket rather than rejecting). Probed and acted on: fastapi's TestClient gives each calling thread its OWN event loop, so the in-flight set is locked rather than trusted to a single writer. | review 2026-09-05 |
| P2 | The browser REPLAYS a POST when a reused keep-alive socket dies mute (probed 2026-09-05: the server saw the identical body twice on two connections). So an `/api/feature/add` or `/api/undo` can in principle apply twice with no crash involved. Not seen in use; the fix is an idempotency key on mutating requests. | review 2026-09-05 |
| P1 | **The BROWSER tier is not green: 8 of 137 fail, all pre-existing** (measured 2026-09-05 against a clean worktree at 083855d — identical failures, so today's review fixes cause none of them). Seven belong to the delete / strike-out work of an earlier concurrent session: `test_tree_delete.py` (5), `test_tree_history.py::test_sketch_nests_with_its_consumer`, `test_small_face_and_fold.py::test_deleting_the_folded_row_removes_the_boolean_too` — a consumed sketch no longer nests under its consumer, so the delete button the tests reach for is not there. The eighth, `test_revolve_tool.py::test_open_from_the_tree_row_and_drag_the_ring`, is ORDER-DEPENDENT: green alone and green after the recovery journeys, red when it follows the measure / taper / snap / origin-plane files (the revolve ghost never appears). **Re-measured 2026-09-06 (the Hole review fixes):** it is red after `test_hole_tool test_extrude_direction test_fillet_tool` too — so the trigger is not those four files, it is length or a leaked gizmo/pick from ANY earlier tool journey. **Re-measured 2026-09-07:** red straight after `test_edit_extrude.py` alone (7 tests) — the angle box never leaves 0 during the drag, so the ring GRAB itself does not take (the pointerdown lands somewhere else); green alone in 37 s. Attributed to the baseline: the identical sequence on a stashed-clean tree fails identically (`ghost visible: False`), so today's fixes do not cause it. R6 says red means red — this is the debt to clear before launch, and the order-dependent one first, because it hides a real bug or a real test flaw and no one can tell which while it only fails in company. **Re-measured 2026-09-11** (Shell review round two) in a clean worktree at `667ccc0`: the same 5 `test_tree_delete.py` still red, so nothing since has touched them. ROOT CAUSE narrowed: `tree.js deleteFeature` opens the confirm only when `plan.deleted.length > 1`, and the dialog never appears — so the remove PLAN now takes ONE feature where it used to take the group. Either the orphan sweep's grouping regressed (the user's original "delete is not working" complaint, partly back) or it was changed on purpose and the 5 tests encode the old shape; one `/api/feature/remove` dry run on the fixture answers which. | measured 2026-09-05, re-measured 2026-09-11 |
| P2 | **Two requests can be in the kernel at once.** FastAPI runs the sync endpoints in a threadpool, and OCCT is not thread-safe: a tree row click starts the tree's own highlight (GET `/api/feature-mesh/<fid>.stl`, a tessellation) and a tool click that lands while it runs plans on the same kernel concurrently. Seen once in four runs of the Fillet row→face journey (2026-09-08): the face click's plan was lost — gold stayed put, no toggle — and with 300 ms between the clicks it never happened. Fillet's face and row selection makes "click a row, then a face" an everyday sequence. Fix: one lock around every kernel-touching request (a plan, a rebuild, a mesh, an export), or the tree overlay served from the mesh the viewport already holds. The journey waits 400 ms after a row click meanwhile. | 2026-09-08 |
| done | **Clockwise `polygon` sketch entities silently refused to fuse.** OCCT takes the point order as the face's orientation: a clockwise polygon is a face whose normal points −Z, and adding it to a normal face raised nothing — it gave TWO overlapping faces (probed: 2 faces of total area 700 where the same points reversed gave 1), which extrude into a self-intersecting solid. `sketch._entity` builds every polygon counter-clockwise (shoelace sign); the stored points stay as drawn. Paths are unaffected, `make_face` orients them (probed). `tests/test_polygon_winding.py` (5, incl. a kernel-measured healthy solid of volume 3500). | fixed 2026-09-05 (36584e1) |
| done | **A refused edit was reported as success.** The server had refused an unknown parameter with a sentence since July, but the reply was HTTP 200 with `ok: true` beside `error` (`ok` is the BUILD's health, read by the tree badge), so a script or the MCP reading the status saw success — and `/api/feature/params` stored ANY key unchecked, failing the build. Now all 12 refusal sites return HTTP 400 through `_refused()` with the same body (the browser's `postJSON` never read the status; nothing changes there), `Document.edit_many` checks every key before writing any, and a parameter the op's signature knows is accepted even when the feature has not stored it yet: `through` on an extrude saved as `{amount}` — the original report — works. 3 tests in `tests/test_api.py`. | fixed 2026-09-05 (36584e1) |
| done | **`/api/feature/remove` wiped a 14-feature tree from its last cut** (gear-case, `clamp_pedestal_cut`, 2026-08-31). Diagnosed with a dry-run plan on the design itself: the orphan sweep starts at the cut's tool prism and follows every input of what it sweeps; the pedestal sketch was drawn ON the body (`sketch_on_face`, inputs = the body), the body's only consumer was the deleted cut, so it counted as leftover tool geometry and the walk climbed to the base sketch — "14 features removed, 0 left". The walk stops at a face reference now (`sk.FACE_REFERENCE_OPS`, the set that already keeps a sketched-on body visible); the same dry run says 3 removed, 11 left. Strict and cascade modes were never affected. 1 test in `tests/test_delete_repair.py` (the gear-case shape). | fixed 2026-09-05 (36584e1) |
| P1 | LIVE esp32-remote: `esp_pillar_trim_tool` lacks `through: true` (safe only via the healer), and the current v16 is a broken WIP (unfused logo extrude → 35 pieces). Fix WITH the user in the app, not by editing the file under their open tab. | verified 2026-09-02 |
| done | Code tests read live `designs/` — frozen in P0 (fixtures + `library` marker). The e2e examples-tab test still opens `pump-impeller` from the library: allowed, it is a stable committed design (e2e rule). | 2026-09-02 |
| done | `sketcher.js` `PLANE_FRAMES` was the last hand copy of build123d's plane frames in the browser. P2: `/api/tool/plan {tool:"sketch", plane, offset}` returns the frame from `sketch.sketch_plane()` (the function `make_sketch` builds on); the sketcher draws what it is told, and `test_launch_rules.py` fails if a frame vector is ever written by hand in `static/js/` again. | P2 2026-09-03 |
| P3 | `sketcher.js` (5) and `measure.js` (1, awaited) still call `loadMesh()` after their own document changes — redundant since R3, left in place because the sketch-mode scene was not audited for a refetch it may rely on when the version is unchanged. Remove with the sketch browser tests running. | P2 2026-09-03 |
| done | Esc cancels any tool panel — inherited once in `tool.js`, with a one-way Cancel/OK guard so a held key cannot remove the same feature twice. | P4 2026-09-04 |
| done | `viewport.beginProfilePick` speaks for the tool (name, and whether a face may do) — P3 review. | 2026-09-03 |
| done | **Code review of P3 (2026-09-03, 8 angles, 40 findings, 30 acted on).** Real, all kernel-checked: a world axis parallel to the sketch plane but OUTSIDE it built a valid solid of the WRONG shape (the guard tested only the direction) → the axis line must lie in the plane; the straddle test used the union of faces (a mirrored pair was refused) → per face; a sketch through mirror / scale got a GUESSED plane → refused with a sentence, a moved sketch carries its plane; a legacy world axis mapped by direction only was rewritten on edit → coincident lines only, others kept by name, an unusable stored axis is announced (`fallback`); a missing angle defaulted to 0 on Cancel → the op's defaults; the stale axis select before the plan; the endless pick loop for a profile-only tool; a refused plan mid-session closed the tool. Framework: `feature_id` on edit plans, swap via `alternatives` (no request), `setBox`, shared ghost parts, one ring mode, `_edit_input`/`_sketch_part`. Evidence added: `probes/lathe_orientation_probe.py`, `tests/test_revolve_gauntlet.py` (8 corpus bodies). Deferred with reasons: registry-driven ribbon/tree wiring (P4, when the third tool lands), one bbox for both axes, e2e helper de-duplication, measure panel on `.toolpanel`. | 2026-09-03 |
| P3 | Opening a sketch is async (the frame — and for a face sketch the outline — comes from the server), and nothing locks the UI between the plane click and sketch mode: a second plane click or a tool started in that window races `enterMode()`. Same shape as the face-sketch path before P2. Fix once: a "starting…" lock for the gap, in the sketcher. | review 2026-09-03 |
| done | **Code review of P2 (2026-09-03, 8 angles, 40 findings, 28 acted on).** Real: a rename never moved `geom_version` (viewport body ids stale; server fix `Document._stamp_geometry` + test), `\|\| [0,0,1]` default normals invented an axis in JS (null now; the plan resolves by centre; grep test), OK during a running rebuild or inside the debounce window dropped the value / skipped the Cut (`apply()` returns the burst's promise, OK waits), the modal lock was released before the closing rebuild landed (a tool opened in the gap was torn down; the lock now releases last, `modalGuard` says "still finishing"), a forced reload joined an in-flight load and was dropped (`force` always fetches). Aborting superseded downloads was tried and dropped: uvicorn logs a protocol-error traceback for every response a client abandons. Simplifications: one `planRequest`, one `uid`, one `pickedBody`, one `close` path, no `reset`/`fallback` hooks, `split(n)` sentence is Extrude's, the R1 grep found tools by discovery. Deferred with reasons: the taper tip arithmetic stays in JS (it is the definition of a taper on the server's kernel-measured radius; the ghost cannot round-trip per mouse move), Flip negation stays client-side (a UI toggle, kernel-checked by test_extrude_direction), the sketcher's `loadMesh(true)` fit calls stay (a fit is a camera wish, not staleness). | 2026-09-03 |
| done | **Code review of the taper work (2026-09-03, 14 findings, all fixed the same day).** The four that mattered: (1) P0 — the hole-to-wall distance was point-sampled and 5% off on a 200 mm plate, so a hole could break through the wall with status ok → the kernel's exact wire distance; (2) measuring the meeting depth ran on every plan for every face (27 s on a 33-hole plate) → measured only on request (`measure_collapse`), the tool asks the first time a taper needs it, exact distances make it ~50 ms; (3) a multi-face sketch was capped to its smallest face → each face ends at its own tip; (4) the cap was silent for AI / MCP / API → the op leaves a note, `Feature.notes` + `Document.warnings` carry it (R7). Also: an unmeasurable profile is not capped; ≥90° is refused on every path with one sentence; messages quote the distance the user asked; the UI takes `max_taper` and `apex_fraction` from the plan (R1); dead estimate and duplicate clamps removed; `probes/taper_apex_probe.py` committed (rule 1); e2e scaffolding shared; docstrings fixed. **Lesson for R6/R5:** the review's kernel probes found what the tests had not — every geometric claim needs a kernel-measured assertion on a LARGE part too. | 2026-09-03 |
| done | **Taper semantics are Fusion's** (user tested Fusion 2026-09-03: "all shapes go until -90, until flat as the sketch — there is no limit"; approved "proceed"). The DISTANCE is a maximum: when a narrowing taper's walls meet before it, the solid ends where they meet — a full cone / pyramid / ridge, lower as the angle steepens, flat at 90°. `sketch.collapse_offset(face)` measures the meeting depth on the kernel's own 2D offset by bisection (exact for L-shapes and holes), `_apex_cap` shortens the build to 99.9% of it (the exact tip is a broken solid for OCCT), and the tool plan reports the same number as `limits.inradius`. The ring and box accept ±89°; the ghost ends where the solid will; the chat says once that the tip comes before the distance. Tests: `tests/test_taper_apex.py` (kernel-measured heights for circle, rectangle, ring, face pick, symmetric, flip) + an e2e that drags the ring to -85. | 2026-09-03 |
| done | **Taper sign is Fusion's now** (user decision 2026-09-03: "flip the sign"): NEGATIVE narrows, POSITIVE flares. One turning point, `sketch._fusion_taper()`, at the public entry of extrude / extrude_face; the ghost morph, the barrier, the tests and the 6 stored taper values in my-part-2/3/5 (+ the live session file) were flipped with the server stopped. History snapshots of those three scratch designs keep the OLD sign — restoring one flares where it narrowed; noted here, not rewritten. Also: the barrier is 99.9% of the collapse angle for EVERY profile (probed: washer face, rect+hole, circle, rect, slot, plate face all build at 0.999; only the exact angle fails) — the old 0.92 margin for profiles with holes was why "narrowing does not go until flat". | 2026-09-03 |
| done | **Tapered face extrude on the wrong side** (user 2026-09-03, screenshot: "I tried a taper on the triangle face and it goes to the opposite direction"). build123d hands an upward, narrowing, hole-less face to OCCT's DPrism, which follows the face's INTERNAL orientation; faces made by an earlier taper are stored REVERSED, and `_straighten_face` can rebuild a face with a flipped normal too. The stub landed inside the body — and on the fused-body repro it was also INVALID, which ShapeFix then "healed", so the 2026-08-05 test passed while asserting five geometrically impossible tapers as ok. Fix: `sketch._tapered_extrude` measures the side against the ORIGINAL outward normal and, if wrong, builds `_taper_loft` along that explicit direction; impossible offsets are refused with a sentence. Tests: `tests/test_taper_direction.py` (7, kernel-measured sides) + the old test rewritten to "right side or refused". **Lesson for R6:** a status-only assertion is not a test of geometry — assert the measured side/volume. | 2026-09-03 |
| P3 | The taper ring (1.35 x the profile) can start OFF the visible canvas in a narrow window, so its handle cannot be grabbed until the user zooms out. Clamp the ring radius to the viewport, or place the handle at the visible edge. Found writing the ring test. | 2026-09-03 |
| done | **MCP doorbell re-fires on every page load** — FIXED 6b4c494. "Something arrived from outside" was JavaScript arithmetic (this poll's `active_tab` vs the last one), which is R1's exact failure: every page load replayed the banner and reset the view, sometimes from under an open dialog. The server owns it now — `mcp_server` posts `/api/open/<slug>?external=1`, `/api/doc` carries `arrival`, `POST /api/arrival/ack` consumes it once, a marker nobody came for goes stale after ten minutes, and the user's own Open dialog never rings it. 8 tests (`tests/test_mcp_arrival.py`) incl. the reload, the un-acked page, and a stale ack that must not swallow a newer arrival. | 2026-09-16 |
| P2 | **The tool panels ignore the display unit.** Settings ▸ Length unit says it changes how lengths are shown, and the status bar, the tree and the sketcher honour it — but every tool panel (Extrude, Hole, Fillet, Shell, Move, Pattern, Measure) has "(mm)" hard-wired in `static/index.html` and reads its box with no `toMm()`. Choose inches and the readouts convert while the boxes you type into do not. Surfaced by the units label (6b4c494), which made the inconsistency visible instead of merely present. The fix is one pass over the panels: label from `unitLabel()`, value through `toMm()` / `fmtLen()`, plus a test per tool that a typed value in a non-mm unit reaches the server as mm. | units label 2026-09-16 |
| P1 | A suppressed final boolean promotes its TOOL to the result (viewport shows the cutter). | BACKLOG |
| P2 | **Rotate and Scale do not share a pivot.** Measured (section 4 review, `probes/boolean_review_probe.py` §1): `rotate` turns about the WORLD ORIGIN, so a body that does not sit on the origin MOVES as it turns; `scale` is about the body's own shape centre, so it stays put. Fusion rotates in place about a pivot you pick. Both docstrings and `OP_NOTES` now state the measured pivot, but the behaviour was left alone on purpose: giving `rotate` a pivot would move geometry in every saved design that uses it (`designs/planetary-assembly` does), so it needs the user's call plus a migration, not a review fix. | section 4 review 2026-09-10 |
| P2 | **`polygon_plate` and `hex_plate` stand on Z=0; the other five primitives are centred.** Measured (section 5 review, `probes/primitives_review_probe.py`): at thickness 8 plate/disc/ball/cone/tube span −4…+4, these two span 0…8. The AI was being told all five were centred, which put every hex body it placed half a thickness out; **that sentence is fixed** (`author.AUTHOR_PROMPT`, the `blocks.py` module docstring and both function docstrings now state the real span, with a test measuring both sides). The GEOMETRY was left alone on purpose: `designs/hex-nut-M16` and `designs/planetary-assembly` hold five of these features, and re-centring would move a nut the user may already have cut — so it needs their call plus a migration, not a review fix. Carries a second question: click-to-place drops the five centred primitives half below the ground grid and sets these two on top of it, so a user placing a disc and a hex nut sees two different behaviours. **SETTLED 2026-09-10: the user said the hex nut is not even needed ("just delete it or leave it"), so the geometry STAYS as it is and this is not scheduled.** Re-open only if a design actually needs a centred hex; the wrong-placement half is already fixed where it did the damage. | section 5 review 2026-09-10 |
| P2 | `/api/open/{file}` and `/api/export` use unsanitised names for file paths. | reader 2026-09-02 |
| P2 | `imports/` holds 48 leftover STEP files written by tests (`my-box-N`, `roundtrip-N`, 9 MB) and no design references any import today. Route test uploads to a temp dir first, THEN re-include `imports/*.step` in `.gitignore` (tried in P0, reverted: it would have tracked the junk). | verified 2026-09-02 |
| P2 | `blocks.py:369` calls `is_valid()` as a method (property in build123d 0.11) inside a bare except — the as-is Solid fast path is likely dead. | reader 2026-09-02 |
| P2 | Right-edge tool panels cover the chat column where failures are reported. Dock tool panels in the viewport pane. | BACKLOG |
| P2 | Compressor sample rebuild ~1–2 min. | BACKLOG |
| P3 | **Measure cannot measure an imported MESH body at all.** An STL is tagged with one mesh pseudo-face (id -1) because 21552 triangles are not 21552 pickable faces, and mesh mode emits no outlines for it either, so there is nothing to click. Since 3ce97a3 the tool says so honestly instead of "face -1 is not on this body any more — click it again"; what it still cannot do is answer the question someone importing an STL actually has, which is how big the thing is. Smallest useful version: measuring a mesh BODY reports its bounding box, surface area and volume, with two mesh picks refused as before. | section 6 review 2026-09-10 |
| P3 | `text` sketch entity; Measure P3 pinned dimensions / P4 named parameters; Fusion nav preset; nav legend on the design tab; axes triad; Fit = zoom-to-fit; Extrude v2 (Start offset, To object); CI. (vendor three.js, third-party notices and the units label all shipped in 6b4c494; **TextCAD's own LICENCE is still unchosen — the user's decision**.) | MANUAL-DESIGN, MEASURE-PLAN, BACKLOG |
| doc | README documents the 2026-07 prototype and a long-fixed API blocker; `sketch_on_face` docstring still states the pre-v2 sign rule; MEASURE-PLAN header stops at round 1; measure.js header says P1 is future. | readers 2026-09-02 |

---

## 11. Decisions log

- **2026-09-02 — plan agreed in conversation.** Direction approved by the
  user ("I really love your idea"). Tool list, AI-uses-tools design and
  testing tiers delegated to Claude's recommendation.
- **2026-09-02 — GitHub backup.** The user delegated the decision. The safety
  branch `backup/session-2026-09-02` (the reverted work) is pushed. Replacing
  the remote `master` with the local one needs a force push, which the
  automation is not allowed to run; the user runs it (command in chat).
- **2026-09-02 — salvaged from the reverted session, with credit:** the
  four-cause diagnosis (confirmed against the code), the finding that 16 red
  tests were true reports through the wrong channel (live esp32 fixture, lost
  `through`, examples.json pinning a derived count), the `/api/tool/plan`
  response shape, the Revolve axis rules and its two kernel guards. NOT kept:
  building Revolve before the framework — the reverted Revolve hand-wired the
  rules again (its own sheet said so), which is the pattern this plan exists
  to stop. Revolve is rebuilt on the framework in P3; its backend guards and
  unit tests may be re-used from the backup branch where they fit.
- **Earlier decisions that stay:** offset method (2026-08-27); machinable
  corners (2026-08-25); one command at a time (2026-08-05); versions minted
  only on explicit push (2026-09-01); tree selection feeds tools (2026-09-01);
  honest zero (2026-09-01); right-drag pans, middle-drag orbits (2026-08-31).
- **2026-09-11 — the sketch composition order is settled in one place.**
  `sketch.compose` and `sketch.compose_order` are public and are the ONLY copy
  of the rule; `sketch_trim` kept a second one and the two disagreed (section
  10's P1, closed at `3b230b7`). The same commit finished the fourth review's
  two-part rule: material is composed before a cut that overlaps it for EVERY
  cut, not only one that leads, because one unrelated shape drawn first used
  to switch the rule off and rebuild `[far, boss, bar, pocket]` as 157.0796
  instead of 100.9046 — a cut lost, green and silent. Measured: 50 live
  designs, zero volume drift, rebuilds 4% faster. Anything that needs to know
  what an entity list MEANS calls `sketch.py`; a second implementation of this
  rule is a bug by definition.
