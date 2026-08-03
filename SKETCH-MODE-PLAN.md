# Sketch Mode — Fusion-parity overhaul (development sheet)

**Mandate (user, 2026-08-03):** sketch mode must work like Fusion 360. Four
reported failures, all root-caused below. Execute the steps IN ORDER, one
commit per step, each verified before moving on. P2 backlog items stay out of
scope unless listed here.

**How to work (non-negotiable, per project skills):**
- Load skills FIRST: `textcad-dev` + `fusion-parity` (before any code),
  `ui-verify` (before claiming any frontend step done), `debug-studio` (when
  anything misbehaves), `ship-check` (before each commit).
- Probe-first: never call a build123d/three.js API from memory — scratchpad
  probe, then real code.
- After ANY JS/CSS change: bump `main.js?v=N` in static/index.html
  (currently v=33) and hard-refresh. After ANY backend change: RESTART the
  test server (python never hot-reloads; `dev.py` is the auto-reload
  launcher). A stale server/browser has burned hours twice — see skills.
- Python is `C:\Python314\python.exe`. Full suite: `python -m pytest tests -q`
  (148 green as of commit c5b6c28; `tests/test_taper_gauntlet.py` is
  UNCOMMITTED WIP from an older session — exclude it with
  `--ignore=tests/test_taper_gauntlet.py` if it's still uncommitted/red).
- Commit style: capability + proof, `git commit -F <msgfile>` (heredocs break
  in PowerShell), author flags per textcad-dev.

**Reusable browser-verify harness (worked 8/8 for the trim tool):**
Playwright sync API; `PYTHONIOENCODING=utf-8`; fresh server
(`python -c "import uvicorn, studio; uvicorn.run(studio.app, port=8141)"`).
Import the LIVE module instances in `page.evaluate`:
`const sk = await import('/static/js/sketcher.js')` (same instance main.js
uses). Drive sketching with bus events:
`bus.emit('sk3d-down',{x,y,tol:0.4}); bus.emit('sk3d-up',{})`.
GOTCHA: `setSketchTool(kind)` TOGGLES — tools stay active after each shape;
never re-select between shapes. Useful ids: `#sk3dHelp` (hint), `#chatLog`,
`#skEntities .skent` (entity cards), `#tabstrip .tab`. Camera handle for
asserts: `window.__vp` (viewport.js:87). Take screenshots and LOOK at them —
a CSS regression once passed every DOM check and failed only visually.

---

## Confirmed root causes (found 2026-08-03, file refs verified)

| # | User report | Root cause |
|---|-------------|-----------|
| 1 | "Once I picked a plane/face for the 2nd sketch I can only see the flat plate, can't rotate" | Face sketches still open the DOCKED 2D SVG editor: `sketcher.js enterMode()` (~line 114) branches `if (!skOnFace)` → 3D in-viewport, `else` → `dlg().show()` docked dialog. The docked editor is a separate flat screen — no orbit, model invisible. Violates fusion-parity rule 9 ("a mode is never a separate screen"). Plane sketches already orbit (right-drag) — users don't discover it, and face sketches can't at all. |
| 2 | "When I extrude the 2nd sketch, the first solid box goes blank" | Only the RESULT (tip feature's solid) is rendered as a real face-tagged body; every other leaf solid becomes a translucent grey GHOST: `studio.py get_model()` (~line 416, `bodies` list is `_plain_mesh` ghosts), `viewport.js addBodies()` (~line 654). Extrude-from-sketch defaults `op='new'` (`extrude.js:162`) → 2nd body becomes tip → 1st body turns ghost ("blank"). Fusion shows ALL bodies solid. |
| 3 | "The coordinate planes are not aligned with the design/box" | TWO bugs. (a) `viewport.js buildOriginPlanes()` (~line 214) positions the XY/XZ/YZ quads at **fitCenter** (model bbox center) — but clicking one starts the sketch on the TRUE origin plane (offset 0). The quad is drawn where the sketch will NOT be. (b) The whole viewport orbits **Y-up** (`buildControls`, viewport.js:40, `camera.up=(0,1,0)`) while build123d/CAD is **Z-up** (`GROUND` plane z=0, viewport.js:28; ground grid rotated into XY). Orbiting rolls the horizon; nothing feels aligned. |
| 4 | "I want to start a sketch at the box's edges — need selecting/snapping to those edges like the origin" | While sketching, snap points only include the sketch's own entities + origin (`sketcher.js collectSnapPoints()` ~line 339; `faceRef` outline only in face mode). The model's edges/vertices (already served by `/api/model` `edges` polylines + `faces` meta) are never projected into the sketch plane as snap targets. |

---

## S0 — Preflight — ✅ DONE 2026-08-03

1. ✅ Taper WIP committed on its own (**8e9f519**, user's choice): the
   flat-BSPLINE seam fix + `tests/gauntlet.py` corpus + skill updates.
   Working tree clean.
2. ✅ `python -m pytest tests -q` → **161 passed** (includes 13 gauntlet tests).
3. ✅ One fresh `python dev.py 8124`, verified current: `/api/doc` = empty
   "untitled", `/api/sketch/trim/pieces` → 4 pieces (today's code),
   `main.js?v=33`.

**S0 findings that change how S1–S4 must be verified:**

- **ORPHANED SERVERS WERE MULTI-BINDING PORT 8124.** Three processes were
  LISTENING on 127.0.0.1:8124 at once (Windows permits this without
  SO_EXCLUSIVEADDRUSE), so requests were answered by whichever bound last —
  nondeterministic. Root cause: `uvicorn reload=True` runs a PARENT +
  spawned CHILD (`multiprocessing.spawn ... --multiprocessing-fork`);
  killing the parent leaves the CHILD holding the socket, and `netstat`
  keeps printing LISTENING for already-dead PIDs. Before trusting ANY
  verification run: `Get-NetTCPConnection -LocalPort <p> -State Listen`,
  confirm the owning PID is `alive`, and kill children too. Recipe added to
  the debug-studio skill.
- **CORRECTION to a wrong first read:** those old processes were NOT serving
  5-day-old code. `dev.py` auto-reloads on every repo `.py` change (a reload
  child had respawned the same morning) and `static/*` is read from disk per
  request under no-cache headers. **A running dev.py is never stale.**
- **THEREFORE complaint #1 needs one confirmation before S4 is built.** The
  in-viewport orbit-while-sketching work (`9c44ca4`, 07/31) WAS being
  served. Two live hypotheses remain: (a) the user sketched on a FACE —
  which genuinely still opens the flat docked editor (S4's verified root
  cause, unaffected), or (b) their browser TAB had been open since before
  07/31, so it was running pre-v2 JS from memory (no reload → no-cache
  headers can't help). ASK which one, or reproduce both, before deleting the
  docked editor. S1/S2/S3/S5 root causes were read from CURRENT source and
  stand regardless.
- The user's unsaved in-progress session (sketch1 XZ → extrude1 → sketch2
  YZ — literally the "second body goes blank" repro) was rescued from the
  doomed process to `designs/my-part.tcad.json` and re-verified: it loads
  and rebuilds `ok=True` under current code. **Use it as the S3 test case.**

## S1 — Z-up world (smallest step, biggest feel win)

**Goal:** the viewport orbits like a CAD tool: Z stays up, horizon level.

- `viewport.js buildControls(up)` (line ~36): default up becomes
  `new THREE.Vector3(0, 0, 1)` (keep the parameter override for sketch mode).
  The OrbitControls freeze-at-construction gotcha is already solved here —
  controls are REBUILT on up change; don't regress that.
- Check every `setView` pose (viewport.js:633): `top` looks down -Z with
  up=+Z → degenerate (view dir ∥ up). Give `top` a tiny Y component the way
  `front` already has a tiny Z (`c.z + d*0.001` pattern), or set a distinct
  up for the top pose. PROBE by orbiting after each preset — the frozen-axis
  bug shows as "orbit dead / 34 change events, zero movement".
- `sketch3d.js exitSketch3D()` calls `setOrbitUp(null)` → must restore Z-up
  (it will, once the default changes — verify).
- Lighting positions (viewport.js:69) may need a nudge so the key light comes
  from above (+Z), not +Y.
- **Verify (browser):** load flange sample; orbit from iso — the ground grid
  must stay "floor", never become a wall mid-orbit; all 3 view buttons land
  sensibly; enter+exit sketch mode, orbit still Z-up after exit. Screenshot
  iso + top and LOOK.
- **Tests:** e2e assert via `window.__vp`: after `setView('top')` orbit by
  dispatching pointer events → camera.position changes (no dead orbit).

## S2 — Origin planes must tell the truth

**Goal:** the plane quad you click is EXACTLY where the sketch will land
(Fusion's origin planes pass through the origin, always).

- `viewport.js buildOriginPlanes()` (~214): position each quad ON its true
  plane: zero out the position component along the plane's normal (XY quad:
  z=0 always; keep in-plane centering near the model so the quad covers it —
  e.g. XY quad centered at (fitCenter.x, fitCenter.y, 0)). Same for the edge
  outlines and labels (offset the label IN the plane only).
- Size: `s = max(fitRadius*1.15 + in-plane distance of fitCenter from origin,
  55)` so the quad still covers a model far from the origin.
- While here: `openSketchEditor(plane)` focuses the camera via
  `pendingFocus` — pass the model's in-plane center as focus so the user
  starts looking at their part, not at a distant origin.
- **Verify (browser):** create a box `move`d to (60, 40, 0); Create Sketch →
  the XY quad must lie in z=0 UNDER the box, and clicking it must open a
  sketch whose grid coincides with the quad's plane (screenshot both).
- **Tests:** e2e: quad meshes' world z (for XY) == 0 regardless of model
  position (read via `window.__vp`/scene or a small exported probe).

## S3 — Multi-body viewport: no body ever "goes blank"

**Goal:** every unconsumed solid body renders as a REAL solid (Fusion's
Bodies folder), fully lit, pickable. Ghost-grey is reserved for previews.

- `studio.py get_model()` (~416): return EVERY leaf body face-tagged, not
  just the result. Shape: `bodies: [{id, positions, indices, faceId, faces,
  edges}]` — reuse the existing per-face tessellation loop (extract it into a
  helper `_tagged_mesh(part)`), one entry per leaf solid INCLUDING the
  result. Keep `sketches` as-is. Face/edge ids must carry the body id
  (e.g. `faces[i].body = fid`) so picking stays unambiguous.
- `viewport.js loadMesh/addBodies`: render each body with the normal solid
  material + crisp edge lines (same as today's result mesh). Keep a
  body→mesh map; `pickAt` raycasts ALL body meshes; `S.pickedFace` gains the
  body/feature id; `/api/face-outline` and `sketch.extrude_face` calls must
  receive WHICH body was picked (today they resolve on `doc.result()` —
  extend the endpoints to accept an optional `feature_id` and resolve the
  face on that body: `studio.py face_outline` ~527, extrude flow in
  `extrude.js`).
- `Document.leaf_solid_ids()` already exists — reuse; per-feature meshes are
  in `doc._parts`.
- Fit/fitToObjects: include all bodies (mostly already does).
- Extrude default stays `op='new'` — with all bodies visible, "New body" is
  no longer perceived as data loss. (Fusion-style auto-Join when profiles
  touch is a LATER nicety — note in BACKLOG, don't build now.)
- **Verify (browser):** box at origin; second sketch on XY beside it;
  extrude 'New body' → BOTH boxes fully solid, both face-pickable; extrude
  with Join → single fused body. The exact user repro: two sketches, extrude
  the 2nd — the 1st must NOT dim.
- **Tests:** pytest on `/api/model`: doc with 2 leaf solids → 2 face-tagged
  bodies; picking metadata carries body ids. E2E: DOM/scene assert 2 meshes
  with the solid material.

## S4 — Face sketches live IN the viewport (kill the docked 2D editor)

**Goal:** sketching on a face == sketching on a plane: same in-viewport mode,
model visible, orbit free (fusion-parity rule 9). This is complaint #1.

- Entry: `sketcher.js openSketchOnFace()` (~202) currently opens the docked
  dialog. Instead: fetch `/api/face-outline` (already returns the plane's
  world `frame` {origin, x_dir, y_dir, z_dir} — added for the extrude ghost)
  → `enterSketch3D(frame, …)` exactly like plane sketches; store `skOnFace`
  for the feature to create. `enterMode()` loses its `else` branch — ONE
  path.
- `faceRef` (grey reference outline + snap points) must render in 3D: add it
  to `draw3D()` as a shape (grey, closed, holes as separate loops) — today it
  only renders in the SVG `draw()`.
- Finish flow — DECISION (recommended): a face sketch on Finish creates the
  `sketch_on_face` feature ONLY (no auto boss/pocket, Fusion doesn't); the
  user then runs Extrude, which already accepts sketches and picked faces.
  The old side-strip Depth/Join-Cut UI dies with the docked editor. If the
  user objects during review, the alternative is a small floating
  depth/join popup after Finish — ask, don't assume.
- `editSketch(feature)` (~177): route BOTH kinds into the viewport mode
  (plane sketches by plane name; face sketches by re-resolving the face via
  its stored face_center/face_normal → `/api/face-outline` frame).
- Retire the docked SVG editor path once nothing uses it: `#sketchDialog`
  markup, `draw()`/`entitySVG()` SVG-only branches, `onDown/onMove/onUp`
  SVG handlers. DELETE code rather than leaving a dead mode (textcad-dev
  altitude rule) — but only in the same commit as passing tests, and keep
  `outlinePts`/geometry helpers used by `draw3D`.
- Watch: `sk3d-*` bus handlers are gated `inPlane3D()` = `sketchActive &&
  !skOnFace` — that gate must become just `sketchActive`.
  `test_sketch_dialog_display_is_gated_by_open` and other dialog tests will
  need updating/removal with intent (they locked the OLD behavior).
- **Verify (browser):** box → pick top face → Create Sketch → grid appears ON
  the top face IN the 3D scene, box still visible, right-drag orbits while
  the circle tool is active; draw a circle snapped to the face outline;
  Finish → feature lands; Extrude it into a boss with Join. Screenshot the
  tilted mid-sketch orbit — that IS the user's complaint fixed.
- **Tests:** pytest: sketch_on_face feature from the new flow rebuilds
  (existing coverage mostly holds); e2e: camera position changes while
  sketch tool active on a FACE sketch (the literal regression).

## S5 — Snap to the model while sketching (start lines at box edges)

**Goal:** hovering near an existing body's edge/corner while sketching snaps
to it, with a marker+label, exactly like origin/center snaps. Complaint #4.

- Data: `/api/model` now (post-S3) serves per-body `edges` polylines. In
  sketch mode, build plane-local snap candidates: for each body edge point
  (endpoints, midpoints; arc centers from `faces` meta where cheap):
  distance-to-plane < tol (e.g. 0.5mm) → project into plane coords → snap
  point labeled `edge`/`corner`. ALSO project silhouette vertices that are
  NEAR the plane? NO — keep v1 strictly to on-plane geometry (Fusion's
  automatic project of coincident geometry); a full "Project Geometry"
  command is later.
- Wire into `sketcher.js collectSnapPoints()` (~339): merge model snaps
  (compute once per sketch-enter / doc change, cache; do NOT refetch per
  mousemove). Marker style: existing orange cross; label says `model edge` /
  `model corner`.
- Also draw the on-plane model edges faintly (dashed grey) in `draw3D()` so
  the user SEES what's snappable (like faceRef but for any body cut by the
  sketch plane).
- **Verify (browser):** box top face sketch → hovering a top corner shows the
  snap cross + `model corner`; click-start a line exactly there; entity
  card x/y equals the corner coords. Sketch on XY beside a box sitting on
  z=0 → its bottom edges are snappable.
- **Tests:** pytest for the projection helper (pure math — put it in
  `sketch.py` or a small `sketch_snap.py`, testable without a browser):
  box edges → expected plane-local points for XY and a face plane. E2E: one
  snap-and-draw pass.

## S6 — Discoverability polish (tiny, do last)

- Hint bar (`#sk3dBar`, sketcher.js `updateHint`): always append
  "right-drag orbit · middle pan · Look At re-faces the plane" — the user
  did not know orbit existed (complaint #1 was half this).
- On entering sketch mode with a body present, do NOT tween fully flat-on if
  it would hide the model? Keep Fusion behavior (it DOES go flat-on) — just
  make the hint visible. No code beyond the hint unless the user asks.
- **Verify:** screenshot shows the hint; 30-second manual orbit sanity.

## S7 — Ship

- Full `python -m pytest tests -q` green; run the S1–S5 e2e script once
  end-to-end on a fresh server; update BACKLOG.md (move these items to Done
  with commit hashes, note the auto-Join idea under P2/later); final commit;
  remind the user: restart their server + Ctrl+F5.

---

**Out of scope (explicitly parked, P2 list):** measure tools, axes triad
widget (S1 fixes the feel; the triad is still worth doing later), viewport
camera Fit quirks, sketch constraints/solver, type-while-drawing dimensions,
trim of tangent-contact shapes, Fusion auto-Join on touching extrudes.
