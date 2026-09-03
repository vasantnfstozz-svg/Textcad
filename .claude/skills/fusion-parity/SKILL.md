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
   default. The TREE is a selection surface too (user mandate 2026-09-01:
   "when I touch the sketch in the feature tree, it should also work"): a
   selected tree row feeds the tool exactly like a viewport pick, an explicit
   argument beats a lingering pick, and clicking a tree row REPLACES the
   viewport pick — one selection set, like Fusion (tree.js selectFeature
   calls viewport.clearPick).
3. **Direct manipulation first.** Numbers come from dragging handles in the
   viewport (arrow perpendicular to the profile/face, riding the moving face,
   fixed comfortable size, always rendered on top). The panel is only the
   value box for exact figures — never a form you must fill before seeing
   anything.
4. **No jumps — and no lies (user mandate 2026-09-01).** Opening a tool must
   not visibly change the model, and the value boxes must tell the TRUTH:
   Extrude opens with distance 0 because nothing has been extruded yet ("it
   should be 0, even I am not extruding" — the old 1mm default read as a
   phantom extrusion). Geometry appears when the USER drags or types; a
   0-distance OK creates nothing and says so in chat; never build a
   zero-thickness solid. Corollaries: the cut into-the-body flip runs at
   apply time as a ONE-SHOT (first positive value flips negative, after that
   the sign is the user's — deliberate upward trim cuts stay possible), and
   THROUGH ALL with an untouched 0 seeds direction INTO the body for face
   sketches (only the sign matters to a through cut).
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
   that face. A cut wants `through: true` unless the depth is the point.
   Two hard-won corollaries:
   * **A face gives the plane its POSITION, never its ORIENTATION.** The frame
     is canonicalised to that axis's principal plane (Z-facing -> XY, X -> YZ,
     Y -> XZ) so `(x, y)` means the same on every face. Deriving it from the
     face's OUTWARD normal buys one sign rule for "into the material" and pays
     with a silent MIRROR on any -Z/-X/+Y face (an entity at (10, 8) landed at
     y = -8; the esp32 cavity came out mirrored and non-manifold). Consequence
     to teach, not to fix: into the material is `flip` from a top face and
     no-flip from a bottom one.
   * **Pick the datum that carries the invariant.** Top face for features OF
     the top surface; BOTTOM face for anything that must survive a thickness
     change — a cavity is "leave a 3mm floor" (`face:"bottom", offset:3`), not
     "9mm deep", and a screw boss is "4mm of standoff above the floor". Get it
     backwards and thinning the stock eats the floor (esp32 at T=10: a 1.0mm
     floor, 0.5mm under the seats). To clear everything above such a plane use
     `through: true` with no flip — it runs up and out of the top, so it can
     never breach the floor.
   NEVER a `sketch` with a nonzero absolute offset once a body exists:
   that hardcodes the base thickness, so changing it strands every downstream
   feature (251 of the 274 sketches authored before this rule did exactly
   that — the user: "the way you are drawing is not good for editing, people
   will get confused"). face+offset is equally expressive and it RIDES the
   geometry. Linted and REJECTED in author.py for AI/MCP-authored trees.
12. **The tree reads sketch-first, consumer-below.** A sketch OWNS its group
   row and what consumed it nests underneath (tree.js `sketchesOf`), because
   that is the order the part was built in.

13. **Viewport navigation mapping (user mandate 2026-08-31).** RIGHT-drag
   PANS ("move the body front and back, up and down — right click I don't
   wanna rotate"), MIDDLE-drag orbits, wheel zooms — IDENTICAL in the design
   tab and sketch mode. LEFT orbits in design (user's call, diverges from
   Fusion) and draws in sketch; Shift+LEFT pans everywhere as the fallback.
   One mapping app-wide, set only in viewport.buildControls. Locked in by
   tests/e2e/test_camera_zup.py::test_navigation_mapping_is_the_same_in_both_tabs.

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
- **TAPER SIGN IS FUSION'S (user decision 2026-09-03):** NEGATIVE narrows,
  POSITIVE flares — the public `taper` param of extrude / extrude_face, the
  panel box and the ring all speak this sign; `sketch._fusion_taper()` is the
  one place it turns into the kernel helpers' historical "positive narrows".
  **TAPER SEMANTICS ARE FUSION'S (user tested Fusion, 2026-09-03):** the
  DISTANCE is a MAXIMUM. Any angle up to ±89° builds; when the narrowing
  walls meet before the distance, the solid ends where they meet (a full
  cone / pyramid / ridge, lower as the angle steepens, flat at 90°). Never
  clamp the angle. `sketch.collapse_offset()` measures the meeting depth on
  the kernel's 2D offset, `_apex_cap` shortens the build to 99.9% of it (the
  exact tip is a broken solid for OCCT), the plan reports it as
  `limits.inradius`, the ghost ends where the solid will, the chat says once
  that the tip comes before the distance.
- **ONE TOOL, ONE AXIS (2026-09-01).** Every gizmo of a tool must take its
  direction from the OP THAT WILL BUILD THE SOLID, not from what happens to be
  at hand. Extrude carried three: the arrow used the picked face's OUTWARD
  normal, the ghost box grew along the sketch frame's z_dir, and the solid
  followed the backend — `extrude_face` goes along the outward normal,
  `extrude_sketch` along the sketch's plane. Because `face_sketch_plane`
  CANONICALISES that plane (+Z / +X / -Y — the same frame for both faces of an
  axis pair), the frame is OPPOSITE the outward normal on a bottom / -x / +y
  face, i.e. half the faces of a box. So a face pick grew the ghost away from
  the arrow, and a face sketch aimed the arrow away from the material (user:
  "when I am pushing the arrow mark one side, the ghost box goes to another
  side, but the body is generated as inteded direction sometimes").
  extrude.js now derives ONE `st.axis` and drives the ghost with a signed depth
  (`st.ghostSign`) so it grows along that axis in its own frame. Corollary:
  a FLIP checkbox must move the arrow when it is ticked, never be applied
  silently at apply time — negating only the built value made the arrow jump
  to the far side on release. Locked in by
  tests/e2e/test_extrude_direction.py (window.__vp.extrudeDirs() reports the
  arrow axis and the ghost's growth vector — assert their dot product > 0).
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
