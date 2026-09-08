# REVIEW-BRIEF.md — instructions for the reviewing model

> **How this file works.** It is written fresh for ONE review and REPLACED for
> the next one, so it stays short and the reviewer pays for one small read.
> The review runs in a separate tool (opencode in its read-only **Plan** mode,
> a model from OpenRouter) inside this repository folder. The user pastes one
> line there:
>
> ```
> Read REVIEW-BRIEF.md and do exactly what it says. Put the whole report in your final answer.
> ```
>
> The report is then pasted back into the Claude Code chat, where every
> finding is reproduced by measurement, given a test that is RED before the
> fix, and then fixed — or rejected with a one-line reason.

---

## What you are reviewing

**TextCAD Studio** is a local web app for building CAD models as a feature
tree (FastAPI backend in Python on build123d/OpenCASCADE, plain ES-module
frontend with a three.js viewport). This review covers **one module: the 2D
sketcher** — the tool the user draws profiles with before extruding,
revolving or cutting them. It has never been reviewed as a whole.

You are a **bug finder**, not a refactorer. The user is not a code engineer
and wants a list of things that misbehave, each with the exact input that
triggers it.

## Rules of engagement

1. **Read-only.** Do not edit or create any file. Do not start the server
   (`studio.py`, port 8123 — the user's live server is running; a second one
   on that port is a known trap). Do not run anything under `tests/e2e/`
   (those write to the design library). You MAY run the fast tests of this
   module for orientation: `C:\Python314\python.exe -m pytest tests/test_sketch_snap.py -q`
   and the other `tests/test_*sketch*.py` files.
2. **Stay in scope.** Read the files below; follow a call out of them only
   when a finding depends on it. Do not review Extrude, Revolve, Hole, Fillet,
   Pattern or Mirror — they get their own review.
3. **Comments are history, not clutter.** A comment saying what the user saw
   on which date records a real past bug. Do not report comments as noise.
4. **The frontend must not re-derive backend facts.** Plane frames, axes,
   normals, origins, safe ranges come from a server response, never from JS
   math (LAUNCH-PLAN rule R1). `test_launch_rules.py` greps for hand-written
   frame vectors. If you find a place where JS computes such a fact itself,
   that is a finding — name the line.
5. **Two failures are banned by design:** a kernel exception reaching the
   user (OpenCASCADE errors derive from `Exception`, not `RuntimeError`), and
   a "successful" invalid or non-manifold solid. A degenerate sketch entity
   that reaches the kernel unvalidated is a finding.
6. **Do not propose fixes.** One clause of a hint is fine; a patch is not.
   No style, naming, formatting or "consider refactoring" remarks. Both
   linters (Ruff, ESLint) already run at zero on this code.

## Scope — the files, and what each does

| File | Lines | Role |
|---|---|---|
| `static/js/sketcher.js` | 2082 | the 2D editor: tools (line, rectangle, circle, polygon, path with arcs, image trace), snapping (`smartSnap`, `collectSnapPoints`, `sketchSnap`), drag handles and resize (`entityHandles`, `resizeGrab`, `applyResize`, `pointerDown/Move/Up`), the scale gizmo (`scaleSel` … `commitScale`), modify ops (`mirrorEntity`, `duplicateEntity`, `offsetEntity`), trim (`fetchTrimPieces`, `trimClick`), dimension editing (`buildDimEditor`, `drawDimFields`, `routeDigitToDrawBox`, `commitDrawDims`), enter/exit/finish/cancel and the "did anything change" test (`sameSketch`, `stableJson`, `finishEmpty`), sketching on a body face (`openSketchOnFace`, `fetchFaceOutline`) |
| `static/js/sketch3d.js` | 439 | the sketch plane inside the 3D viewport: frame, grid, flat-on view, orbit-up, pointer mapping from screen to plane |
| `sketch.py` | 1669 | backend. **In scope:** `entity_schema`, `_validate_dims`, `_entity`, `_compose`, `_path_face`, `make_sketch`, `sketch_plane`, `named_face`, `face_plane`, `face_sketch_plane`, `_face_frame`, `face_outline_2d`, `pick_face`, `sketch_on_face`, `_signed_area`, `collapse_offset`. **Out of scope:** everything from `extrude_face` downward (extrude, taper, revolve, hole, loft, sweep) |
| `sketch_trim.py` | 429 | trim: `trim_pieces` splits entities at intersections, `trim_apply` rebuilds entities from the kept faces |
| `studio.py` | — | the sketch endpoints only: `/api/sketch-mesh/{feature_id}` (l.1591), `/api/sketch/snap` (1670), `/api/sketch/trim/pieces` (1685), `/api/sketch/arc-radius` (1696), `/api/sketch/trim/apply` (1709), `/api/sketch/kinds` (2632) |
| `toolplan.py` | — | the `sketch` tool's plan branch only (grep `"sketch"`): it returns the plane frame the sketcher draws on |
| tests | — | what is already covered: `tests/test_e2_sketch.py`, `test_e5_sketch_on_face.py`, `test_sketch_corner.py`, `test_sketch_snap.py`, `test_sketch_trim.py`; browser: `tests/e2e/test_face_sketch_in_viewport.py`, `test_sketch_empty_exit.py`, `test_sketch_scale.py` (read, do not run) |

## What counts as a finding

A concrete input on which the code does the wrong thing. For this module,
the classes that matter most, roughly in order of harm:

- **The saved sketch differs from what was drawn** — coordinates, arc
  via-points, path closure, entity `mode` (add/cut), the `x, y` offsets that
  some entities carry and others do not.
- **A change is silently dropped or silently applied** — `sameSketch` /
  `stableJson` decide whether an edit triggers a rebuild; a false "same" loses
  an edit, a false "different" rebuilds for nothing. Typed dimension values
  (`commitDrawDims`, `routeDigitToDrawBox`) versus dragged ones.
- **Snapping moves a point the user did not intend** — to a stale model point
  after the body changed, to a point on another plane, past the 0.1 mm grid
  floor; exact circle centres and design-centre snaps are meant to be exact.
- **A pointer state machine that gets stuck** — several tools (draw, resize,
  scale, trim, path, image trace) share one canvas and one
  `pointerDown/Move/Up`; look for a tool switch, Escape, double-click or a
  lost `pointerup` that leaves a flag set.
- **Async races** — `openSketchOnFace`, `fetchFaceOutline`, `fetchPlaneFrame`,
  `fetchTrimPieces` are awaited while the user can still click. One is
  already known (see below); report a *different, concrete* one only.
- **Trim** — pieces computed from one sketch state and applied to another;
  `_pick_face` / `_face_contains` tolerances; entities that come back from
  `trim_apply` with a different kind or orientation than they went in.
- **Face sketches** — the outline and frame come from the server; any JS
  that derives a normal, an axis or an "up" from geometry itself (rule R1).
- **Validation gaps in `sketch.py`** — zero radius, zero-length line,
  self-intersecting or open path, a polygon with two identical points,
  NaN or string numbers from the JSON, reaching build123d unchecked.

Not findings: performance unless it is quadratic in the number of entities;
anything about Extrude/Revolve/Hole; the items in the known list below.

## Where I would look hardest (a guess, so you do not have to trust it)

`pointerDown/Move/Up` and what `setTool` / `cancelSketch` reset;
`commitDrawDims` and `applyResize` (two paths that write the same entity
fields); `sameSketch` / `stableJson`; `openSketchOnFace` → `enterMode` when
the plan or the outline arrives after the user moved on; `sketch_trim._pick_face`.

## Output format — exactly this, nothing else

Order by severity: **P0** wrong geometry saved or data lost · **P1** blocks a
basic drawing action · **P2** hurts daily use · **P3** polish. At most 15
findings. If you have fewer than 5 with confidence high or medium, say so —
do not pad the list.

```
### F1 · P<0-3> · <one line: what goes wrong>
- File: <path>:<line>  (and a second path:line if two places interact)
- Trigger: <the exact user action or the exact input data>
- Expected: <one line>
- Actual: <one line>
- Confidence: high | medium | low — <why: read the whole path / a test contradicts it / could not follow one branch>
- Evidence: <1–3 quoted lines from the file, verbatim>
```

Then two short closing sections:

```
### Checked and found OK
<up to 8 one-liners: areas you read fully and found sound, so they are not re-checked>

### Could not judge without running the app
<up to 5 one-liners>
```

## Already known — do NOT report

- The **`enterMode()` race**: opening a sketch is async (frame, and for a
  face sketch the outline, come from the server) and a second plane click or
  a tool started in that window races it. Known, planned as one "starting…"
  lock (LAUNCH-PLAN §10, P3).
- **`face_sketch_plane` snaps a face tilted under 25° to the nearest
  principal plane**, which does not contain the face. Known and deliberately
  parked: the offset-method sign rules and every stored face sketch were
  written for the snapped frame (§10, P2).
- **`sketcher.js` calls `loadMesh()` five times after its own document
  changes** — redundant since the viewport follows the document (rule R3),
  left in until the sketch-mode scene is audited (§10, P3).
- Five tools hand-type "a value typed before the plan arrived waits for it"
  (§10, P3).
- The pre-existing red browser tests (`tests/e2e/test_tree_delete.py`, five;
  the order-dependent revolve ring test) belong to other work.
- Lint-class output: unused names, `a = x; b = y` on one line, single-letter
  geometry variables, module-level `let` declared lower in a file than a
  function that uses it. Both linters run at zero with those rules ignored on
  purpose.
