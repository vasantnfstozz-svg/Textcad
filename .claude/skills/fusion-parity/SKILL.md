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
7. **Failures speak.** If a preview feature fails to build, say WHY in the
   chat immediately (warnIfFailed pattern) — never just a red dot.
8. **Contextual modes.** Entering a mode (sketch) swaps the ribbon to a green
   contextual tab with Finish/Cancel; leaving restores the normal tabs.

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

## When unsure about a Fusion behavior

Do NOT guess and do NOT ask the user to explain step-by-step. In order:
1. Check this skill and the pasted help texts in git history / BACKLOG.
2. Ask the user for the specific Autodesk help page (they can paste it — the
   Extrude page defined the whole spec once).
3. Search the web for "Fusion 360 <tool> help" and read Autodesk's docs.
Encode any new rule you learn HERE so it is never re-explained.
