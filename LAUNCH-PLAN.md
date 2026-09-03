# TextCAD launch plan — a robust, user-friendly CAD you can trust

> **Status: DRAFT for the user's approval, written 2026-09-02.** Agreed in
> conversation the same day. No code has changed yet. When approved, this file
> becomes the ACTIVE workstream sheet and every other plan file points here.
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

Sizes that matter: `extrude.js` 941 lines for one tool, `sketcher.js` 2078,
`studio.py` 2542, `viewport.js` 1844. 47 test files + 27 browser tests.

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
| R10 | **Every phase deletes more than it adds**, or it is another layer, not a fix. Record the line delta in the commit. | Cause 2 |
| R11 | **Token rules.** One Claude session per checkout. Check the `ui v` stamp and single server before debugging any browser report. Targeted tests while building, full suite only at ship. Probe scripts committed under `probes/` so no API is probed twice. No agent fan-outs on this project. | Cause 7 |

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

**P3 — Revolve, the first tool born on the framework.**
Axis derived from the profile, drawn in gold; drag a ring 0..360; backend
refuses (with a sentence) a profile that straddles the axis or an axis
perpendicular to the plane — both reached the user raw before (one as a raw
OCP exception, one as a "successful" solid of volume 0). *Acceptance:* the
tool lands in ~100–250 lines with no geometry maths; 40+ plan tests; 3–6
journey tests; volume cross-checked (Pappus). *Success metric for the whole
plan:* bugs the user finds in Revolve's first week, compared with Extrude's
history. *User does:* Revolve checklist.

**P4 — The rest of Tier 1, one tool per session.**
Order: Fillet/Chamfer on picked edges (needs edge picking + per-edge op) →
Hole → Pattern → Mirror → Shell → Move/Rotate → Push/Pull naming. Each: spec
(R8) → plan tests → tool → user checklist (R9) → ship-check → commit.

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

1. **Spec** — one page: the three sentences of what you click and see, the
   handle, the value box, failure messages, the five-step user checklist.
   User approves.
2. **Probe** — any kernel behaviour the tool relies on gets a probe script
   under `probes/<tool>_*.py`, committed.
3. **Plan tests** — table of (input geometry × selection × params → plan).
4. **Backend op guards** — every way the kernel can fail becomes a sentence
   naming what to change; no raw exception, no zero-volume "success".
5. **Tool declaration** — the `tool({...})` object; if it needs more than the
   framework offers, extend the framework (and Extrude gets it too).
6. **Journey tests** — real clicks on a frozen fixture, rendered + measured.
7. **Ship** — targeted tests during the work; at ship: the fast tiers +
   this tool's journeys, `ui v` bump, restart, the user's checklist, commit
   with capability + proof + line delta, push.

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

---

## 10. Open items carried over (deduplicated; launch-blocking marked ★)

| Pri | Item | Source |
|-----|------|--------|
| ★P0 | Clockwise `polygon` sketch entities silently refuse to fuse → non-manifold downstream. Normalise winding CCW in `sketch._entity` + test. | BACKLOG |
| ★P0 | `/api/edit` silent no-op when setting a param the feature does not already have (e.g. `through` on `{amount, flip}`) — reports success, changes nothing. | export-integrity notes |
| ★P0 | `/api/feature/remove` over-cascade: removing a tail cut with no dependents wiped a 14-feature tree (undo recovered). Not yet diagnosed. | export-integrity notes |
| P1 | LIVE esp32-remote: `esp_pillar_trim_tool` lacks `through: true` (safe only via the healer), and the current v16 is a broken WIP (unfused logo extrude → 35 pieces). Fix WITH the user in the app, not by editing the file under their open tab. | verified 2026-09-02 |
| done | Code tests read live `designs/` — frozen in P0 (fixtures + `library` marker). The e2e examples-tab test still opens `pump-impeller` from the library: allowed, it is a stable committed design (e2e rule). | 2026-09-02 |
| P1 | `sketcher.js` `PLANE_FRAMES` is the last hand copy of build123d's plane frames in the browser (used to place a NEW plane sketch's grid before any feature exists). Fix in P2: `/api/tool/plan {tool:"sketch", plane, offset}` returns the frame; the sketcher draws what it is told. | P1 2026-09-03 |
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
