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
> Hole's drag ghost c6a2377, ui v160 — §7 P4). Next: Mirror, in a fresh chat.
> One tool per session. Every
> other plan file points here; §7 carries the done-notes, §10 the ranked open
> items.
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
| R9 | **The user tests, with a checklist.** Each tool ships with a five-step checklist the user runs in the real app. Browser robots are for what machines are good at; the user's eyes catch usability. | tokens, Cause 4 |
| R10 | **Every phase deletes more than it adds**, or it is another layer, not a fix. Record the line delta in the commit. One exception, named here so it is never self-granted: the phase that CREATES the framework (P2) is judged together with the first tool built on it (P3) — their combined delta must be negative against the hand-wired tool they replace. | Cause 2 |
| R11 | **Token rules.** One Claude session per checkout. Check the `ui v` stamp and single server before debugging any browser report. Targeted tests while building, full suite only at ship. Probe scripts committed under `probes/` so no API is probed twice. No agent fan-outs on this project. Fable thinks, Opus reviews and fixes, effort `high` (§9). | Cause 7 |

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
user checklist. Rule compliance becomes the default instead of an achievement.

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
| Push/Pull face | arrow | flat face of a body | `extrude_face` exists | Extrude in face mode already does this; expose the name |
| Move / Rotate body | arrows / ring | body | `move`, `rotate` exist | |
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

## 6. Testing — three tiers, each cheap where it can be

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

*After both checklists (2026-09-06) the user found ONE thing: no ghost while
dragging.* Hole got it the same day (c6a2377, ui v160: hole.js feeds Extrude's
ghost the hole's circle in the plan's frame, +42 net lines, no viewport
change, +1 journey; the user re-checked it). Pattern's ghost is deferred by
the user's decision (§10) — its copies need the seed's delta mesh from the
server. The review of c6a2377 rides with the next tool's (user's call).

**P5 — The AI uses the tools (§5 step B).** Incremental authoring through
the plan endpoint; chat edits point at parameters; the FEATURE-TREE-PLAN
"step 4" everyone deferred.

**P6 — Launch preparation.** Vendor three.js locally (offline today = broken),
LICENSE + third-party notices, units label, a one-click run script, examples
gallery review, CI running the fast tiers, a fresh-machine install test.

**Later:** named parameters, Sweep/Loft tools, Text entity, section view,
assemblies, the user's personal project.

---

## 8. The per-tool ritual (P3 onward)

1. **Spec** — one page in `specs/<tool>.md`: the three sentences of what you
   click and see, the handle, the value box, failure messages, the five-step
   user checklist. User approves.
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
8. **Review, then the checklist** — right after the CODE commit Claude says
   "recommended now: `/code-review high`" (the user runs it; it is worth its
   tokens once per shipped tool — the taper review found 4 real bugs the
   tests had not). Findings are fixed and committed BEFORE the user runs the
   five-step checklist, so the user never tests what a robot would catch.
   Docs / plan / memory commits get no review. The review runs on HEAD: a
   docs commit on top of the code hides it, so review first, then stamp the
   plan.

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
  the user asks. The user's checklist replaces most browser verification.
- **The user's server:** launch detached with `studio.py`, never `dev.py`;
  restart after backend changes and let it open the browser.
- **Model by task** (decided 2026-09-04, after both 5-hour windows died on
  2026-09-03 at roughly 7-8M weighted tokens each). **Fable 5.1 thinks:**
  specs, kernel and geometry decisions, guards, probes, the tool framework,
  root causes. **Opus 5 reviews and fixes:** the `/code-review` agents
  (`CLAUDE_CODE_SUBAGENT_MODEL` in the user settings), the pass that applies
  the findings, e2e wiring, docs, plan and memory updates (`/model
  claude-opus-5` for that chat; the next tool starts a fresh chat on Fable).
  Per token Opus is half of Fable, Sonnet 5 a fifth (pure docs turns).
- **Effort `high` by default** (`/effort`); `xhigh` only for the day's hard
  kernel question. Output tokens are the most expensive class, and effort
  decides how many there are.
- **A fresh chat per tool, and after any pause over an hour.** Resuming
  rewrites the whole context to cache at 1.25x; a fresh chat costs CLAUDE.md
  plus the memory. The 1M window (`[1m]`) is off, so a chat that runs long
  compacts near 200k instead of growing to 650k per call.
- **One `/code-review high` per shipped tool**, on the code commit, agents on
  Opus. Never twice on one commit; never re-launch one the limit killed until
  the window resets. `/usage` before starting it.

---

## 10. Open items carried over (deduplicated; launch-blocking marked ★)

| Pri | Item | Source |
|-----|------|--------|
| P3 | **Pattern has no drag ghost (improvement, deferred by the user 2026-09-06: "we will do that later").** Hole (c6a2377), Extrude and Revolve show a translucent ghost while the handle moves; Pattern's ring and arrows move only the number until release, and a pattern rebuild costs the kernel 250–500 ms. Plan: the pattern plan returns a tessellated mesh of the seed's DELTA (before − after / after − before — `document.delta_features` computes it already); the browser instances N−1 translucent copies about the plan's axis / along its directions, following the drag AND the typed count at once (type 6, see five ghosts before the kernel confirms); a browser test compares the ghost copies' positions with the real copies after release, because Full / partial angle and Spacing / Extent would then exist twice — the 2026-09-01 "ghost goes the other way" class. Marks only (dots on the ring, ticks on the arrow) was considered and rejected: honest but far less useful. Roughly half a day. | user checklist 2026-09-06 |
| P3 | **Pattern's count is typed, not dragged.** Fusion has a quantity handle beside the ring / arrow (parity rule 3). | specs/pattern.md |
| P3 | **Pattern lacks Fusion's Symmetric distribution and per-copy Suppress.** | specs/pattern.md |
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
| P1 | **The BROWSER tier is not green: 8 of 137 fail, all pre-existing** (measured 2026-09-05 against a clean worktree at 083855d — identical failures, so today's review fixes cause none of them). Seven belong to the delete / strike-out work of an earlier concurrent session: `test_tree_delete.py` (5), `test_tree_history.py::test_sketch_nests_with_its_consumer`, `test_small_face_and_fold.py::test_deleting_the_folded_row_removes_the_boolean_too` — a consumed sketch no longer nests under its consumer, so the delete button the tests reach for is not there. The eighth, `test_revolve_tool.py::test_open_from_the_tree_row_and_drag_the_ring`, is ORDER-DEPENDENT: green alone and green after the recovery journeys, red when it follows the measure / taper / snap / origin-plane files (the revolve ghost never appears). **Re-measured 2026-09-06 (the Hole review fixes):** it is red after `test_hole_tool test_extrude_direction test_fillet_tool` too — so the trigger is not those four files, it is length or a leaked gizmo/pick from ANY earlier tool journey. Attributed to the baseline: the identical sequence on a stashed-clean tree fails identically (`ghost visible: False`), so today's fixes do not cause it. R6 says red means red — this is the debt to clear before launch, and the order-dependent one first, because it hides a real bug or a real test flaw and no one can tell which while it only fails in company. | measured 2026-09-05 |
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
| P1 | MCP doorbell re-fires on every page load and flips the active tab, even under a dialog. Needs a consume-once arrival marker. | BACKLOG |
| P1 | A suppressed final boolean promotes its TOOL to the result (viewport shows the cutter). | BACKLOG |
| P2 | `/api/open/{file}` and `/api/export` use unsanitised names for file paths. | reader 2026-09-02 |
| P2 | `imports/` holds 48 leftover STEP files written by tests (`my-box-N`, `roundtrip-N`, 9 MB) and no design references any import today. Route test uploads to a temp dir first, THEN re-include `imports/*.step` in `.gitignore` (tried in P0, reverted: it would have tracked the junk). | verified 2026-09-02 |
| P2 | `blocks.py:369` calls `is_valid()` as a method (property in build123d 0.11) inside a bare except — the as-is Solid fast path is likely dead. | reader 2026-09-02 |
| P2 | Right-edge tool panels cover the chat column where failures are reported. Dock tool panels in the viewport pane. | BACKLOG |
| P2 | Compressor sample rebuild ~1–2 min. | BACKLOG |
| P3 | `text` sketch entity; Measure P3 pinned dimensions / P4 named parameters; Fusion nav preset; nav legend on the design tab; axes triad; Fit = zoom-to-fit; Extrude v2 (Start offset, To object); vendor three.js; LICENSE; units label; CI. | MANUAL-DESIGN, MEASURE-PLAN, BACKLOG |
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
