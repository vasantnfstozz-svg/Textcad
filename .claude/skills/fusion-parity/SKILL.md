---
name: fusion-parity
description: The Fusion 360 interaction rules TextCAD Studio clones. MUST be loaded before building or changing ANY modeling tool (extrude, revolve, fillet, patterns, …) — it prevents "form-first" or "sketch-only" mistakes the user keeps having to correct.
---

# Fusion parity — how every modeling tool must behave

The user's goal: TextCAD Studio should FEEL like Fusion 360. They demo Fusion
workflows and paste Autodesk help pages; we clone the interaction. These rules
were each learned from a correction — do not regress them.

## The golden interaction rules

1. **Inputs are profiles AND faces AND bodies.** Fusion's create tools accept
   sketch profiles *or planar faces of existing solids* interchangeably.
   If a tool takes "a profile", wire BOTH paths (Extrude does: sketch mode +
   face mode via `S.pickedFace`). Never assume "sketch only".
2. **Select-then-command must work.** Whatever is picked in the viewport when
   a tool is pressed is the tool's input (face picked → Extrude extrudes THAT
   face, not the last sketch). Command-then-select is the fallback, not the
   default.
3. **Direct manipulation first.** Numbers come from dragging handles in the
   viewport (arrow perpendicular to the profile/face, riding the moving face,
   fixed comfortable size, always rendered on top). The panel is only the
   value box for exact figures — never a form you must fill before seeing
   anything.
4. **No jumps.** Opening a tool must not visibly change the model (start
   distances tiny, e.g. 1mm). Geometry changes when the USER drags or types.
5. **Live, real previews.** The preview is the actual verified rebuild
   (throttled, one in flight), never a fake overlay. Cancel removes every
   preview feature; OK keeps them; Esc = cancel.
6. **Operations compose.** Join/Cut/Intersect are separate features in the
   tree (fuse/cut/intersect with a target body) so everything stays editable.
   Pulling a face defaults to Join; dragging INTO the body + Cut = pocket.
   **The combine target defaults to the body the input lives on** — a face
   sketch targets the sketch's parent body walked to its CURRENT state
   (latest solid descendant), a plane sketch the newest solid. NEVER the
   first body in the tree (2026-08-24: that default cut the raw stock
   instead of the user's panel, and re-defaults must follow profile changes).
7. **Failures speak.** If a preview feature fails to build, say WHY in the
   chat immediately (warnIfFailed pattern) — never just a red dot.
8. **Contextual modes.** Entering a mode (sketch) swaps the ribbon to a green
   contextual tab with Finish/Cancel; leaving restores the normal tabs.
9. **ONE COMMAND AT A TIME (user mandate 2026-08-05 — applies to EVERY
   current and future design tool).** While a tool's panel is open (e.g.
   Extrude), every other design tool must REFUSE to start — chat message +
   flash the open panel (`dialogs.modalGuard()`, driven by `S.modalTool` /
   `S.modalToolPanel`) — until the user presses OK or Cancel. Never
   silently cancel the open tool, never let the user land in sketch mode
   with a tool panel still floating. A NEW tool with a panel MUST set
   S.modalTool/S.modalToolPanel on open and clear them on OK/Cancel, and
   its entry points must call modalGuard() first.
10. **A mode is never a separate screen.** Sketch mode is the NORMAL 3D view
   with sketch tools switched on: the model stays in place, the sketch is
   drawn on its plane in the scene, and the user can orbit / pan / zoom at
   any moment while drawing (left = draw, right = orbit, middle = pan).
   Never take the user to a flat 2D page they must leave to see their part.
   Corollary: any new "editor" belongs IN the viewport, not beside it.

11. **BASE FIRST, THEN SKETCH ON THE BASE — the offset method (user mandate
   2026-08-27).** Build the base body first, and every sketch after it is a
   `sketch_on_face` on the CURRENT body, naming its face
   (`face: "top"|"bottom"|"+x"|...`) with depth stated as an `offset` FROM
   that face — negative into the material. `flip: true` always means INTO the
   body, on every face; a cut wants `through: true` unless the depth is the
   point. NEVER a `sketch` with a nonzero absolute offset once a body exists:
   that hardcodes the base thickness, so changing it strands every downstream
   feature (251 of the 274 sketches authored before this rule did exactly
   that — the user: "the way you are drawing is not good for editing, people
   will get confused"). face+offset is equally expressive and it RIDES the
   geometry. Linted and REJECTED in author.py for AI/MCP-authored trees.
12. **The tree reads sketch-first, consumer-below.** A sketch OWNS its group
   row and what consumed it nests underneath (tree.js `sketchesOf`), because
   that is the order the part was built in.

## Gizmo/drag mechanics (hard-won, in viewport.js)

- Grab in a CAPTURE-phase pointerdown + `controls.enabled=false` so
  OrbitControls never fights the drag; move/up listeners on `window`.
- Resolve drags in SCREEN SPACE along the handle's on-screen direction
  (px-per-mm from projecting two axis points); fall back to ray-projection
  only when the axis points at the camera. Never rely on ray-projection alone
  (ambiguous head-on).
- THREE.Vector3 is MUTABLE: always `.clone()` before multiplyScalar/add on a
  stored vector (a shared-reference bug silently scaled the arrow's normal).
- Plane normals must be PROBED, not assumed: build123d XZ extrudes toward -Y.
- OrbitControls (three 0.160) FREEZES its orbit axis at construction —
  `setFromUnitVectors(object.up,(0,1,0))` lives in update()'s closure, so
  assigning `camera.up` later does nothing. Looking straight down an axis
  that is a pole of that frozen frame kills orbiting (flat-on XZ sat at
  phi=pi: 34 change events, zero camera movement). To orbit about a new up,
  REBUILD the controls (`viewport.setOrbitUp`), preserving position/target.
- When a click is raycast onto a plane, refuse it when the view is nearly
  edge-on (|ray·normal| < ~0.15) — the hit point runs away to hundreds of mm
  and makes degenerate geometry. Say why in the hint bar (rule 7).

## When unsure about a Fusion behavior

Do NOT guess and do NOT ask the user to explain step-by-step. In order:
1. Check this skill and the pasted help texts in git history / BACKLOG.
2. Ask the user for the specific Autodesk help page (they can paste it — the
   Extrude page defined the whole spec once).
3. Search the web for "Fusion 360 <tool> help" and read Autodesk's docs.
Encode any new rule you learn HERE so it is never re-explained.
