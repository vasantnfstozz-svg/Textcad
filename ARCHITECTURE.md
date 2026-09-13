# TextCAD architecture

How the software works, for someone who has to change it. Written 2026-09-02
from the code at HEAD 253c7bc. Where a statement is a design intention rather
than shipped code it says so. The rules for changing any of this are in
[LAUNCH-PLAN.md](LAUNCH-PLAN.md) §3.

## 1. One picture

```
 user click / AI call
        │
        ▼
 static/js (tool → selection → params)          browser
        │  POST /api/feature/add  (soon: POST /api/tool/plan first)
        ▼
 studio.py  ── HTTP only; multi-tab STATE; child of supervise.py ── server
        │
        ▼
 document.py  Document.rebuild()
        │  every feature: op from CREATORS / MODIFIERS / COMBINERS
        │  → blocks.py / sketch.py build geometry (build123d / OCCT)
        │  → inspector.health()  LAYER 1: a sane, single, watertight solid?
        │  → inspector.verify()  LAYER 2: the RIGHT part? (Spec)
        ▼
 /api/doc (tree + status)   /api/model (tagged mesh: bodies, faces, edges, sketches)
        │                            │
        ▼                            ▼
 tree.js renders the history     viewport.js draws it (three.js)
```

Nothing raises to the user. A failed feature gets a red dot and a spoken
reason in chat; a broken solid is refused, never shown.

## 2. The two walls every part must clear

`inspector.py` is the whole verification story and is geometry-agnostic:

- `health(part, check_valid=True)` — Layer 1. Four facts: has a solid,
  positive volume, manifold/watertight, valid (OCCT `BRepCheck`, ~270 ms on a
  large solid, so intermediates pass `check_valid=False` and only the RESULT
  gets the full check). It must NEVER call `measure()` (that once ate 65% of
  a 22 s rebuild). Known limits: it does not detect a part in two pieces
  (`document.n_solids()` does), and it ignores the manifold flag for any
  sphere-bearing solid (build123d 0.11 false negative).
- `measure(part)` — mass, area, centre of mass, topology counts, face-type
  histogram, cylinder radii (a heuristic hole census), max radius,
  rotational symmetry.
- `verify(part, Spec)` — Layer 2: size, volume, hole count by radius,
  n_solids, symmetry, tip radius, centre of mass. `tol` is absolute mm and is
  reused for every length check; `vol_tol` is relative.

`engine.py` (Layer 1 oracle for raw LLM scripts) and `check.py` belong to the
2026-07 code-generation prototype; Studio does not use them.

## 3. The feature tree (`document.py`)

A design is a `Document`: `name`, `spec`, and an ordered list of `Feature`
nodes (`id`, `op`, `params`, `inputs`, `suppressed`) forming a DAG. Every
`op` must come from one of three registries, so an AI cannot invent API:

| Registry | Meaning | Examples |
|---|---|---|
| `CREATORS` | no geometric inputs | `plate`, `disc`, `tube`, `sketch`, `import_stl`, `import_step` |
| `MODIFIERS` | exactly one upstream part | `extrude`, `extrude_face`, `revolve`, `revolve_face`, `sweep`, `sketch_on_face`, `fillet`, `chamfer`, `shell`, `polar_pattern`, `linear_pattern`, `rotate`, `mirror`, `scale`, `with_center_hole`, `with_bolt_circle` |
| `COMBINERS` | two or more upstream parts | `fuse`, `cut`, `intersect`, `loft` |

`move` is special-cased (in `KNOWN_OPS`, in no registry) — a known wart.
`KNOWN_OPS` is derived from the registries, which is why registering an op
makes it legal in trees, the op catalog, the ribbon (once added to `icons.js`
and `ribbon.js`) and MCP at once (see the `add-operation` skill).

**Rebuild.** Content-addressed and cached: a feature's signature covers its op,
params (rounded to 9 decimals) and its inputs' signatures, so renaming keeps
every cache entry and editing one parameter invalidates exactly that feature
and its descendants. Failures are cached too (a broken param is not
re-evaluated every rebuild). Intermediates are health-checked without
`is_valid`; the result gets the full check and then `verify` against the
spec. `_heal_stranding_cuts` may set `through: True` on a cut tool when — and
only when — the cut left more pieces than it was handed and through-all
provably restores the count; an explicit `through: False` is respected.

**Editing.** `Document.edit(id, param, value)` changes params that already
exist (adding a new key must go through `f.params` directly — the reason
`/api/edit` can silently no-op today, LAUNCH-PLAN.md §10). The AI never
regenerates a design during an edit.

**Suppress, strike, remove.** A suppressed node passes its first input's part
through. `strike()` (the tree's ✕) suppresses exactly the set an auto delete
plan would remove — reversible, rows stay struck through; `unstrike()` also
revives struck ancestors. `remove()` deletes for real (a `cut` sweeps its tool
prism and that prism's sketch). `consumed_ids()` is THE rule for what is
hidden as consumed: face-reference ops (`sketch_on_face`, `extrude_face`, `revolve_face`)
never consume their body; suppressed features consume nothing; a live feature
consuming a struck id consumes what that id resolves to.

**Rollback bar** (`doc.rollback`) hides everything after a feature — used
transiently for edit isolation; not saved (`to_data()` omits it).
`to_step()` un-parks it for export and refuses by name when the tail has
unbuilt features, so an intermediate cutter can never be exported as the part.

**Serialisation.** `to_data()` / `from_data()` ⇄ `designs/<slug>.tcad.json`
(`name`, `spec`, `features`). The recipe is the artifact; STEP is derived.

## 4. Geometry modules

- `blocks.py` — the verified block library. Every function self-tests; the
  `EXPORTS` dict is the catalog. Also `import_stl` (via `Mesher`, binary only,
  ascii converted; multi-body → `Compound`, never fused) and `import_step`.
- `sketch.py` — 2D entities (`path`, `rectangle`, `circle`, `regular_polygon`,
  `slot`, `ellipse`, `polygon`; `mode` add/subtract; rotate about own centre
  THEN translate), `make_sketch`, `extrude_sketch` (one/both sides, taper,
  `through` = ±2000 mm and no taper), `revolve_sketch`, `sweep_sketch`,
  `loft`, `extrude_face`, `revolve_face`, `sketch_on_face`, `named_face`, `face_sketch_plane`, `face_profile_plane`.
  **The offset method:** a face gives a sketch plane its POSITION only; the
  frame is canonicalised to the axis's principal plane so `(x, y)` means the
  same on every face; consequence: "into the material" is `flip` on a top
  face and no-flip on a bottom one. Negative dimensions are refused (build123d
  silently absolutises them). Taper pre-straightens BSPLINE seam edges before
  OCCT's 2D offset (which otherwise returns garbage or crashes the server).
  Open P0: clockwise `polygon` winding is not normalised.
- `sketch_trim.py`, `sketch_snap.py`, `sketch_corner.py` — stateless solvers
  behind `/api/sketch/trim/*`, `/api/sketch/snap`, `/api/sketch/arc-radius`.
- `imgtrace.py` — PNG/JPG → polygon entities (OpenCV); SVG is rasterised in
  the browser first. Traced polygons are bbox-centred: position lives in
  `e.x/e.y`, not in `points`.
- `meshrepair.py` — STL repair ladder (weld, split, voxel remesh, guarded
  decimation) for real-world Fusion exports.
- `provenance.py` — face → the feature (and sketch entity) that made it, via
  exact bounding boxes; the basis for Measure's drivers and the pick box's
  "created by".
- `measure.py` — read-only measurement kernel (face/edge/pair distances,
  diameters, calipers) plus driver resolution: a **driven** dimension is one
  param in the tree (typed into exactly); a **derived** one is a consequence
  of two literals (changed by MOVING a named side); read-only is the honest
  fallback and always states its reason.

## 5. The server (`studio.py`, HTTP only)

`STATE["docs"]` maps tab-id → `{doc, ok, rebuild_ms, history(undo stack),
pending, clean_hash, source}`; `STATE["active"]` names the tab every `/api`
call operates on. It is a module global: reset it in fixtures, never run two
things against it at once. Errors return HTTP 200 with an `error` key
(pydantic 422 is the exception and fires before the handler).

Route groups (51 routes): tabs (`/api/tabs*`, `/api/new`) · document
(`/api/doc`, `/api/model`, `/api/sketch-mesh/{id}`, `/api/feature-mesh/{id}`)
· sketch helpers (`/api/sketch/*`, `/api/face-outline`) · features
(`/api/feature/{add,params,remove,rename,suppress,strike}`, `/api/edit`,
`/api/spec`, `/api/undo`, `/api/redo`, `/api/rollback`, `/api/face-feature`)
· measure (`/api/measure`, `/measure/probe`, `/measure/set`) · versions
(`/api/save`, `/api/versions*`) · library (`/api/designs`, `/api/open/{file}`,
`/api/sample/{name}`, `/api/examples`, `/api/design-preview/{file}`) · import
and export (`/api/trace-png`, `/api/import-stl`, `/api/import-step`,
`/api/export`) · AI (`/api/chat`) · catalogs (`/api/ops`, `/api/sketch/kinds`).

`/api/model` returns the **tagged mesh**: bodies with per-vertex `faceId`,
face metadata (type, `planar`, normal, centre, `circles`, per-type dimensions),
edge polylines, unconsumed sketches. Cached process-wide (`_MESH_CACHE`) and
per tab, keyed on the rebuild stamp `_geom_version`.

**Persistence.** `designs/<slug>.tcad.json` (design), `designs/<slug>.history/`
(version tree: `index.json` + `vN.json.gz`; see `history.py` — append dedupes
against the parent, `parent` defaults to `current` so restoring then editing
BRANCHES, snapshot written before index, a broken index is never overwritten,
`id_floor` keeps ids monotonic, `delete_after` trims a tail and resets it),
`.studio-session.json` (open tabs, restored on boot, active tab rebuilt
eagerly, others lazily; per-port file for non-8123 servers). Versions are
minted ONLY on explicit Save and on open/reload; tools, imports and AI edits
mark the tab dirty and add `pending` notes that become the save label.

**The kernel worker** (`kernelguard.py`, 2026-09-13). Crash recovery above is
the net; this is the fence in front of it. Three ops are known to segfault
OpenCASCADE on real bodies with no warning any bound can read — `fillet`,
`chamfer` and `shell` — so the part of each that touches the kernel runs in a
WARM child process instead of in the server: `blocks.blend_after_guards` and
`sketch.shell_after_guards`, both called identically by the in-process path and
by the worker, so there is one copy of the logic and not two. The worker's
death becomes a plain refusal and a red feature row; a call that outruns
`TEXTCAD_KERNEL_SECONDS` (default 900) is killed and says so; both are recorded
in `bugs/kernel-crashes.log` and both are oracles in `tests/journeys.py`, so a
crash made polite is still a finding. Warm because a fresh python that imports
build123d costs 10–30 s here (`probes/sidecar_cost.py`), and the replacement
after a death is started in the background so the user's next click is usually
warm again. The body crosses as a `.brep` (order and geometry preserved
exactly — `probes/sidecar_roundtrip.py`) and picks cross as INDICES plus a
fingerprint of each picked edge or face, which the worker re-measures before it
works: build123d silently DROPS an opening face that is not `IsSame` with a
face of the solid it offsets, and a re-resolve in the child could land on a
different edge, so a mismatch must fail the step — a crash turned into silent
wrong geometry would be worse than the crash. Both bodies are weighed on both
sides of the pipe for the same reason. `TEXTCAD_KERNEL_GUARD=0` runs everything
in-process, which is how the tests that spy on the raw kernel still reach it.
Deliberately NOT universal: booleans, 2D offsets and tessellation still run in
the server, and the supervisor below is what covers those.

**Crash recovery** (`supervise.py`, 2026-09-05). The kernel can segfault (a
fillet at radius 2.0 on esp32-remote's top rim, `probes/fillet_segfault_probe.py`)
and a segfault is not an exception. `python studio.py` therefore runs a light
supervisor that starts the server as a child (`TEXTCAD_SERVER_CHILD=1`) and
relaunches it after a crash the OS reported (NTSTATUS `0xC…` / a POSIX crash
signal — never after Ctrl+C, Stop-Process or exit 0), passing
`TEXTCAD_RECOVERED`. The session file is the checkpoint, written when the last
POST finishes and **no other is running** — POSTs overlap in FastAPI's
threadpool, and `edit_params` writes the new value into the feature before the
kernel is asked, so a checkpoint taken by a passing request during an 8-second
fillet would hand the relaunched server the very value that killed it. The
trade is deliberate: while a slow POST is in flight, a shorter one that
finishes skips its checkpoint, so a crash in that window costs those edits
too — losing a step is recoverable, a design that crashes every time it is
restored is not. The
in-flight set (`.studio-session[-PORT]-inflight.json` names the OLDEST live
POST) says what the dead process was doing; the child exposes that as
`recovery` on `/api/doc` — with `unbuilt`, since whether this server rebuilt
the restored tabs is the server's to say, not the browser's to infer (R1).
`api.js` waits for the server (5 min: the child rebuilds the active tab BEFORE
it opens the port), and `noteRecovery` both speaks the note once and emits
`server-recovered`, so every caller — a failed POST, a failed plan, the 3 s
watcher, boot — releases an open tool panel without having to remember to.
In `tool.js` an answer that lands in a session that has gone throws `GONE`,
caught once in `apply()`. A crash before the server ever served relaunches with
`TEXTCAD_SAFE_RESTORE=1` (tabs unbuilt, an empty tab active); so does the
second crash in a row that **nobody asked for** — no request in flight, moments
after the port opened — because those repeat by themselves (the recovered page
refetches `/api/model`), and the third stops. A fatal step the user retries is
not a loop: it leaves a marker, and costs one step every time. The child exits
on EOF of its stdin pipe, so a killed supervisor never leaves an orphan
listener. Tests: `tests/test_supervisor.py` (10 — the policy in process, plus
real processes and a real access violation), `tests/e2e/test_recovery.py`
(2 — what the user sees, including a crash inside a tool's own step).

**AI.** `author.py` builds a design ONE STEP PER MODEL REPLY
(`author_steps`, LAUNCH-PLAN.md P5): each reply is `add` one feature,
`edit` one parameter, `remove` its own last step, or `done` with a spec.
A step goes through exactly what the toolbar's Add Feature goes through —
`Document.add(strict=True)`, `lint_tree` (no absolute-offset sketch once a
body exists, no >10-entity sketch; the whole-design blob rule at `done`), a
rebuild — and a refused or broken step is undone before the model hears its
sentence, so the tree never holds a feature the kernel did not accept.
`/api/chat` routes `create` (a job in a NEW tab) and `add` (a job on the
design on screen, one snapshot = one Undo) to `_run_job`, which runs the loop
in a thread under `_KERNEL_LOCK` with an in-flight marker per step; the
browser follows `GET /api/chat/job/<id>` and prints every step as it lands.
`edit`/`delete` intents stay single requests. `_to_document` still validates
a whole tree for the MCP `build_design` door. Model access is OpenRouter via
`generate.OpenRouterModel`, key from the user registry.

**MCP** (`mcp_server.py`): six tools for external Claude sessions
(`build_design`, `design_part`, `design_compressor`, `verify_step`,
`measure_step`, `list_operations`); stdout IS the protocol, so geometry runs
inside `_quiet()`. A built design is announced to a running Studio, which
opens it in a tab (the "doorbell"; its re-fire on page load is an open item).

## 6. The frontend (`static/js`, plain ES modules)

One module, one job; modules never import each other to communicate — they
emit and listen on `bus.js` (`doc-updated`, `msg`, `sketch-on-face`,
`sketch-mode`, `settings-changed`, `view-changed`, `sk3d-*`) and share
`state.js` (`S`: `lastDoc`, `selected`, `pickedFace`, `pickedProfile`,
`modalTool`, `modalToolPanel`, …).

| Module | Job |
|---|---|
| `main.js` | boot, the 3 s watcher that reloads on doc changes, `ui v` stamp |
| `viewport.js` | three.js scene, Z-up camera and navigation (right-drag pans, middle-drag orbits, wheel zooms; left orbits in design, draws in sketch), picking (faces, edges, profiles; edge tolerance in screen px), pick highlight, origin planes, gizmos, `loadMesh()` |
| `sketch3d.js`, `grid3d.js`, `sketcher.js` | in-viewport sketch mode: adaptive grid (0.1 mm floor), tools, snapping (grid + model snaps from `/api/sketch/snap`), handles, drag-move, trim, mirror/offset/scale, Trace Image |
| `extrude.js` | THE reference tool: select-then-command from viewport or tree, arrow + taper ring gizmos, ghost, honest-zero, live verified preview, Join/Cut target default, edit-existing mode. Today 941 lines and the owner of geometry math the server already knows (LAUNCH-PLAN.md P1/P2 remove that) |
| `tree.js` | renders the history: sketch-first rows with consumers nested, actions (edit, extrude, strike/restore, rename), inline param edit, path arc radii, verify badge, warnings |
| `measure.js` | Measure & drive panel, A/B picks, draggable dimension line |
| `versions.js`, `doctabs.js` | version panel (dirty ●, save as version, update vN / push vN+1, trim, rename, delete, restore, star, diff); tabs with the 3-way close prompt |
| `ribbon.js`, `icons.js`, `dialogs.js`, `ask.js`, `placement.js`, `provenance.js`, `settings.js`, `chat.js`, `api.js` | ribbon tabs and tool registry, generic op dialog, in-app prompts (never native `prompt()`), click-to-place, pick box, settings (units, grid), chat pane, fetch helpers |

Conventions that bite: bump `main.js?v=` after any JS/CSS change (the
running app shows it as `ui v`); `loadMesh` short-circuits on an unchanged
`geom_version`, so imports and tab switches pass `force=true`; a mode is never
a separate screen; one command at a time (`S.modalTool`).

## 7. Tests (`tests/`)

- Backend: `tests/test_*.py` on FastAPI's `TestClient` (no server) and the
  document engine directly. `tests/gauntlet.py` is the body corpus for
  operation × geometry sweeps.
- Browser: `tests/e2e/` — one shared server + browser per session
  (`conftest.py`; waits on `controls.enabled`, prompts through `ask_*`
  helpers). Load only stable designs.
- `tests/fixtures/` — frozen design copies for tests that assert a specific
  design's content. Code tests never read `designs/`. `-m library` runs the
  opt-in checks on the live library. `TEXTCAD_HISTORY_ROOT` is autoused so no
  test writes a version history into the user's library.

## 8. What is deliberately NOT here

No sketch constraint solver, no assemblies in Studio (`assembly.py` is a
library), no named parameters or expressions (LAUNCH-PLAN.md later), no
sandbox around the legacy `engine.py` exec, no CI yet.
