"""
author.py — AI design authoring: natural language -> a feature TREE.

This is v2's replacement for raw-code generation inside the Studio, and it is
the strongest anti-hallucination design yet. The model does NOT write Python.
It emits a JSON feature tree whose nodes may ONLY be operations from the
verified registry (document.KNOWN_OPS). That means:

  * it cannot invent API — unknown ops are rejected at validation, by name;
  * every node it CAN use is a tested block or a boolean;
  * the result is immediately an editable document (feature tree), so the
    user can refine it manually afterwards — no orphan code blobs.

Since P5 (LAUNCH-PLAN.md §5 step B) the model works ONE STEP PER REPLY,
through the same Document.add(strict=True) + lint + rebuild the toolbar's
Add Feature uses (`author_steps`); a refused or broken step is undone before
the model hears about it. `_to_document` still validates a WHOLE tree for the
MCP build_design door, where another AI authors the tree itself.
"""

from __future__ import annotations
import json
import re
import time

import judge
from document import Document, CREATORS, MODIFIERS, REQUIRED, op_params


# ---------------------------------------------------------------------------
# The op catalog shown to the model (and to the UI's Add Feature dialog)
# ---------------------------------------------------------------------------

# Parameter metadata so the dialog can render dropdowns for enums, show units,
# and state positioning conventions instead of bare snake_case + "number".
_ENUMS = {
    "axis": ["X", "Y", "Z"],
    "plane": ["XY", "XZ", "YZ"],
    "edges": ["all", "top", "bottom", "vertical", "horizontal"],
    "open_face": ["top", "bottom", "none"],
    "kind": ["simple", "counterbore", "countersink"],     # hole
}
_MM = {"radius", "bolt_radius", "thickness", "height", "width", "depth",
       "length", "amount", "offset", "dx", "dy", "dz", "x", "y", "z", "distance",
       "pitch_circle_dia", "rx", "ry", "inner_r", "outer_r", "tip_radius",
       "diameter", "cbore_diameter", "cbore_depth", "csink_diameter"}
_DEG = {"angle", "angle2", "angle_deg", "rotation", "inlet_angle", "exit_angle",
        "csink_angle"}
# an `axis` that is NOT the world-axis enum: revolve's takes "u" / "v", a world
# name or a line [[u1, v1], [u2, v2]] in the sketch plane (see its OP_NOTE) —
# an enum here would tell the AI the one form that cannot work on a face
_NO_ENUM = {("revolve", "axis"), ("revolve_face", "axis"),
            ("mirror", "plane")}      # also a face, a mid-plane, {origin, normal}
# ...and ops whose parameter of a shared NAME takes a different VOCABULARY.
# `polar_pattern`'s axis is not `rotate`'s: pattern.axis_of resolves it against
# sketch.FACE_DIRS ("+z", "top", …) and refuses "X" / "Y" / "Z" by name, so the
# shared enum offered the model — and the Add Feature dialog's dropdown, which
# renders `enum` as a <select> (dialogs.js:330) — three values that fail every
# time (measured 2026-09-16, section 13 review).
_ENUMS_BY_OP = {
    ("polar_pattern", "axis"): ["+z", "-z", "+x", "-x", "+y", "-y"],
}

# op -> one-line convention note (anchoring, direction, operand meaning)
OP_NOTES = {
    "plate": "Centered on the origin in X, Y AND Z (spans ±thickness/2 in Z).",
    "disc": "Centered on the origin; spans ±thickness/2 in Z. radius, not diameter.",
    "tube": "Centered on the origin; spans ±height/2 in Z.",
    "ball": "Centered on the origin.",
    "cone": "Centered on the origin; spans ±height/2 in Z.",
    "hex_plate": "Centered on the origin; spans ±thickness/2 in Z.",
    "polygon_plate": "Centered on the origin.",
    "move": "RELATIVE offset in mm from the part's current (origin-centered) position.",
    "rotate": "Spins the part about the chosen axis. `pivot` says where the axis "
              "passes: \"center\" turns the body IN PLACE about its own centre (what "
              "you almost always want; the Rotate tool's choice), an explicit "
              "[x, y, z] is a point of your own, and ABSENT or \"origin\" is the WORLD "
              "ORIGIN — a body that does not sit on the origin MOVES as it turns.",
    "scale": "Scales about the body's OWN CENTRE, so it stays where it is "
             "(2 = double size). Note this is NOT rotate's pivot: rotate turns "
             "about the world origin.",
    "mirror": "plane \"XY\"/\"XZ\"/\"YZ\" (through the origin), a face {\"face\": \"top\"}, "
              "the body's mid-plane {\"mid\": \"X\"} or {\"origin\", \"normal\"}. With "
              "\"join\": true the body is fused with its reflection (one symmetric part); "
              "with \"seed\": a feature's id that FEATURE is mirrored on the body instead. "
              "Without either it RETURNS ONLY THE COPY (legacy).",
    "fillet": "vertical = the 4 upright corner edges (round a box's corners); "
              "radius must be < half the adjacent wall thickness. `edges` may "
              "also be a list of picked edges (the Studio tool writes these).",
    "shell": "Hollows the body to walls of `thickness`; `faces` lists the flat faces "
             "to remove by name ([\"top\"], or [] for a closed hollow); direction "
             "inside keeps the outside where it is.",
    "revolve": "Spins the sketch about an axis IN its plane: \"v\" / \"u\" (the plane's "
               "own axes through the sketch origin — they ride the geometry), a world "
               "axis \"X\"/\"Y\"/\"Z\" lying in the plane, or a line in the sketch's own "
               "coordinates [[u1, v1], [u2, v2]] (one of the profile's straight edges). "
               "The profile must lie entirely to one side. angle is signed; angle2 adds "
               "a second side the other way; both=true sweeps angle to EACH side "
               "(Fusion's Symmetric, the same key as extrude's).",
    "loft": "A COMBINER of 2+ single-profile sketches on DIFFERENT planes, blended "
            "in the order given — they must step one way along the loft (a middle "
            "section listed last folds the solid back through itself and is "
            "refused). `ruled=true` joins them with straight walls, otherwise a "
            "smooth spline (three sections r5-r2-r5 smooth is 25 per cent slimmer "
            "than ruled — a real spline, not a defect).",
    "sweep": "Drags the sketch profile along a PATH SKETCH: `path` is the id of a "
             "sketch whose entities are OPEN paths — {\"kind\": \"path\", \"closed\": "
             "false, \"start\": [u, v], \"segments\": [{\"type\": \"line\", \"to\": [u, v]}, "
             "{\"type\": \"arc\", \"via\": [u, v], \"to\": [u, v]}]} — drawn on a plane "
             "PERPENDICULAR to the profile and STARTING on the profile (the kernel "
             "sweeps from the profile's centre along the path's shape). `distance` in "
             "mm along the path, or full=true for the whole path. Bends tighter than "
             "the profile reaches and paths leaving in the profile's plane are "
             "refused. The path sketch is referenced, not consumed. (`path_points` "
             "[[x,y,z],…] is the legacy form.)",
    "sweep_face": "Sweeps a flat face of the input body (face_center + face_normal from "
                  "a real pick) along a path sketch named in `path`, like sweep. "
                  "Returns only the new solid; fuse/cut it with the body.",
    "revolve_face": "Revolves a flat face of the input body (face_center + face_normal "
                    "from a real pick) about a line in the face's plane, normally one of "
                    "its straight edges: axis=[[u1, v1], [u2, v2]]. Returns only the new "
                    "solid; fuse/cut it with the body.",
    "hole": 'Drills ONE hole into the input body from a flat face and RETURNS THE '
            'BODY WITH THE HOLE (no sketch, no cut feature). Name the face '
            '(face="top"/"bottom"/"+x"/… — never compute a face_center or '
            'face_area) and place '
            'it with at=[x, y] in that face\'s own coordinates — on the flat, '
            'axis-aligned faces of a part exactly the x/y a sketch_on_face on that '
            'face uses; on a TILTED face the hole measures in the face\'s true '
            'plane and a sketch measures in the principal plane it snaps to, so '
            'the two differ (measure from the face itself, do not copy a sketch '
            'coordinate). diameter + depth in mm from the '
            'face into the material; through=true runs out the far side. kind '
            '"counterbore" adds a flat seat (cbore_diameter > diameter, cbore_depth '
            '< depth), "countersink" a conical one (csink_diameter > diameter, '
            'csink_angle, 90 is usual). One feature per hole; the centre must lie '
            'on the face.',
    "extrude": "Pulls the sketch normal to its plane, i.e. AWAY from the face a "
               "face-sketch sits on. flip=true pulls the other way (INTO the "
               "body = pocket/hole). through=true ignores the distance and runs "
               "past the material — what a cutting tool almost always wants. "
               "both = symmetric (BOTH ways).",
    "cut": "First input MINUS the rest (by tree order). Keep body first.",
    "sketch": "For the BASE only (no body exists yet). offset shifts the plane "
              "along its normal (mm).",
    "sketch_on_face": 'Sketch on a face of an existing body — the offset method. '
                      'Say WHICH face by name: face="top"|"bottom"|"+x"|"-x"|'
                      '"+y"|"-y" (never compute a face_center or face_area '
                      'yourself — they belong to a mouse click). The '
                      'face gives the plane its POSITION only; x/y always mean '
                      'what they mean in a plane sketch, on every face. offset '
                      'moves the plane along +Z (Z-facing faces), +X (X-facing) '
                      'or -Y (Y-facing): from the TOP face offset -3 is 3mm '
                      'below it, from the BOTTOM face offset 3 IS 3mm above the '
                      'bottom. The face is re-resolved every rebuild, so the '
                      'sketch RIDES it when upstream dimensions change.',
    "import_stl": "Imports an EXISTING .stl file (UI upload or absolute path). "
                  "Only use when the user names a real file — NEVER invent a "
                  "filename. STL units read as mm; scale resizes on import.",
    "import_step": "Imports an EXISTING .step/.stp file as exact BREP solids "
                   "(a design exported from here re-imports losslessly). Only "
                   "use when the user names a real file — NEVER invent a "
                   "filename.",
}


def _annotate(op_name: str, params: list[dict]) -> list[dict]:
    for p in params:
        n = p["name"]
        if (op_name, n) in _ENUMS_BY_OP:
            p["enum"] = list(_ENUMS_BY_OP[(op_name, n)])
        elif n in _ENUMS and (op_name, n) not in _NO_ENUM:
            p["enum"] = _ENUMS[n]
        elif n in _MM:
            p["unit"] = "mm"
        elif n in _DEG:
            p["unit"] = "deg"
        elif n in ("count", "sides"):
            p["unit"] = "count"
        elif n == "factor":
            p["unit"] = "×"
    return params


def op_catalog() -> list[dict]:
    """Machine-readable list of every legal operation and its parameters.

    The parameters come from `document.op_params` — the SAME source the edit
    guard refuses unknown keys against, so what this shows the AI and what the
    document will accept from it cannot drift apart.

    A parameter with no default carries `"required": True` and a `"default"`
    of None, so the Add Feature dialog's `p.default ?? ''` keeps behaving
    exactly as it did while the fact itself is on the response (R1: a field,
    never re-derived). The sentinel itself never leaves this function — this
    list is JSON, served by /api/ops and by the MCP doorbell."""
    def entry(name, kind, inputs):
        params = [{"name": n, "default": None if d is REQUIRED else d,
                   **({"required": True} if d is REQUIRED else {})}
                  for n, d in op_params(name)]
        return {"op": name, "kind": kind, "inputs": inputs,
                "params": _annotate(name, params), "note": OP_NOTES.get(name)}

    cat = [entry(name, "creator", 0) for name in CREATORS]
    # a construction plane: no input off a principal plane, one body off a face
    import sketch as _sk
    cat += [entry(name, "plane", 0) for name in sorted(_sk.PLANE_PRODUCERS)]
    cat += [entry(name, "modifier", 1) for name in MODIFIERS]
    cat.append(entry("move", "modifier", 1))
    from document import COMBINERS
    cat += [entry(name, "combiner", 2) for name in COMBINERS]
    return cat


def _catalog_text() -> str:
    """The signature list in the prompt, with REQUIRED said out loud.

    It used to render a parameter with no default and one whose default is
    None the same way — both bare — so `hole(face_center, face_normal, face,
    face_area, at=(0.0, 0.0), ...)` read as four required parameters the
    prompt then forbids the model to compute, while `extrude(amount, ...)`
    read the same and really did need one. Now a bare `*` means required and
    every other parameter shows the value it takes when left out, so nothing
    in the line is a guess (LAUNCH-PLAN §10, 2026-09-17)."""
    def shown(p):
        if p.get("required"):
            return p["name"] + "*"
        return p["name"] + "=" + ("null" if p["default"] is None
                                  else str(p["default"]))

    lines = ["  (* = REQUIRED; every other parameter may be left out and takes "
             "the value shown)"]
    for c in op_catalog():
        ps = ", ".join(shown(p) for p in c["params"])
        need = {"creator": "no inputs", "modifier": "1 input",
                "combiner": "2+ inputs",
                "plane": "no inputs off a principal plane, 1 body off its face"}[c["kind"]]
        lines.append(f"  {c['op']}({ps})  [{c['kind']}, {need}]")
    return "\n".join(lines)


AUTHOR_PROMPT = f"""You design 3D objects as FEATURE TREES for a parametric
CAD system — ANY object: mechanical parts, products, furniture, toys, and
stylized models of real-world things (cars, rockets, buildings, animals).
NEVER refuse a design request. When an object's true shape is organic or more
complex than the available operations, build the best RECOGNIZABLE STYLIZED
approximation from the primitives you have (a car = body slab + cabin +
cylinder wheels + fused details) — a toy-like model is a success, a refusal
is a failure. Do not reject anything for "machinability"; that is not a
requirement here.

YOU WORK ONE STEP PER REPLY, exactly like a person using the CAD tools: add
ONE feature, see what it built, add the next. Respond with ONLY a JSON
object, no prose, no markdown — one of these four:

{{"name": "short-part-name", "plan": ["...", "..."], "add": {{"id": "unique_name", "op": "<op>", "params": {{...}}, "inputs": ["upstream_id", ...]}}}}
    adds one feature to the tree ("name" and "plan" are read on your first
    reply only — "plan" lists the 3-10 must-have ELEMENTS of the request in
    plain words WITHOUT sizes or numbers, one per entry, each one something
    a later step builds, e.g. ["back shell", "camera opening on the back",
    "charging-port opening"]; "done" is checked against that list);
{{"edit": {{"feature_id": "an_id_in_the_tree", "param": "radius", "value": 12}}}}
    changes ONE parameter of a feature already in the tree — never rebuild
    from scratch what one number can fix;
{{"remove": "an_id_in_the_tree"}}
    takes back a step OF YOUR OWN that nothing else builds on (your last
    step) — a feature that was in the tree before you started is the user's
    and is refused;
{{"done": true, "spec": {{"n_solids": 1, ...optional: "symmetry": N, "tip_radius": mm, "size": [x,y,z or null], "holes": {{"5": 2}}, "tol": 0.5}}}}
    the part is complete (spec "holes" maps NUMERIC hole radius in mm ->
    count; {{"5": 2}} means two 5mm-radius holes).

ONE of those four per reply — never two in one. After every reply you are
told what the step built (status, volume, size, the bodies now in the tree)
or the sentence it was REFUSED with. A refused step is NOT in the tree: send
a corrected step, not the next one. A step that builds broken geometry is
undone the same way. Think the whole part through before the first step,
then record it step by step.

ALLOWED OPERATIONS (the ONLY ops that exist — anything else is rejected):
{_catalog_text()}

RULES AND CONVENTIONS:
- Units: mm and degrees. Z is the vertical/rotation axis. All ops return solids.
- POSITIONING (critical): disc, plate, tube, ball and cone are
  CENTERED at the origin — they span Z from -thickness/2 to +thickness/2.
  polygon_plate and hex_plate are NOT: they stand on Z=0 and run up to
  +thickness, so a hex nut's mid-plane is at +thickness/2, not at 0.
  revolve_profile spans EXACTLY the z values in its points. Use "move" to
  align pieces BEFORE booleans.
- The spec encodes the USER's requirement. If verification fails, fix the
  GEOMETRY to meet the spec — NEVER weaken or change the spec to match wrong
  geometry.
- Features evaluate in the order they were added; "inputs" must reference
  ids ALREADY in the tree.
- creators take no inputs; modifiers exactly 1; fuse/cut/intersect 2 or more
  (cut = first input minus the rest).
- revolve_profile points are [radius, z] pairs (radius >= 0), auto-closed —
  use it for any axisymmetric body (hubs, pulleys, shafts, bottles).
- polar_pattern copies its input N times evenly around Z — features meant to
  fuse with a body MUST physically overlap it (touching is not enough). To
  repeat a FEATURE of a body (a bolt circle of one hole, teeth from one boss)
  add it AFTER the body's latest feature with "seed": that feature's id and
  "axis": {{"face": "top"}} (a flat face: its normal through its centre; a bore's
  wall: its own axis) — "angle" 360 is a full circle, less spreads the copies
  from the seed to that angle.
- "rotate" orients parts: cylinders are upright by default — a WHEEL or axle is
  rotate(axis "X" or "Y", 90). "mirror" with "join": true makes a body symmetric
  about a plane (its reflection fused on — model one half, then mirror it across
  the flat FACE where the halves meet, {{"face": "+x"}}, or an origin plane the
  half sits against; NOT {{"mid": "X"}} — that is the body's OWN centre, so the
  reflection stays inside it and the part does not grow); with "seed": a
  feature's id it mirrors THAT feature (a hole, a boss) across the plane on the
  body — {{"mid": "X"}} is the plane for that, the body's centre across X — add
  it after the body's latest feature. Without "join" or "seed" it returns only
  the mirrored COPY (fuse it yourself).
- "fillet"/"chamfer" round or bevel edges ("all"/"top"/"bottom") — use small
  values (radius well under half the local thickness or they fail). "shell"
  hollows a solid into walls ("faces": ["top"] makes cups/containers; [] a
  closed hollow) — the thickness must be well under half the body's size.
- "linear_pattern" repeats a body in a straight line (count, dx, dy, dz) — or a
  FEATURE of a body with "seed" plus "direction" [x, y, z], "distance" and
  "distance_type" ("spacing" between copies, or "extent" they all fit in);
  "count2" / "direction2" / "distance2" make it a grid.
- The LAST feature you add is the part. It must be ONE watertight solid,
  so end with a fuse if you built separate pieces.
- "done" carries a spec with at least {{"n_solids": 1}} when you are building
  a NEW design. When you are ADDING to a design that already exists, its spec
  is the user's — kept exactly as it is, or left absent — and you send none.
  Match spec strictness
  to the request: for ENGINEERING parts with explicit dimensions, encode them
  (size/holes/symmetry, tight tol). For STYLIZED/creative models (cars,
  animals, buildings), keep the spec MINIMAL — {{"n_solids": 1}} plus at most
  the overall length with a generous "tol" (5-20mm). Do not invent tight
  dimensional requirements the user never asked for and then fight them.
- spec "symmetry" is ONLY for discrete repeated features (N blades, N bolts),
  as an integer. Bodies of revolution are inherently round — omit symmetry.
RECORD A DESIGN HISTORY (critical — the tree IS the product, not just the
solid; the user will open it in a CAD feature tree, rename features, reopen
each one in the tool that created it, and edit dimensions):
- Author the tree as the SEQUENCE OF STEPS a Fusion 360 user would take:
  sketch a profile, extrude it, sketch the next element, extrude and
  fuse/cut it, and so on. One logical design element per step, with
  meaningful ids (base_sketch, base_extrude, web_sketch, web_cut...).
- DECOMPOSE the part into its natural features, one per node: a water
  bottle is body + shoulder + neck + lip + inner cavity (cut), NOT one
  giant profile. A bracket is base_plate + ribs + each hole group.
  5-12 features is typical; 1-2 features for a non-trivial part is WRONG.
- Every dimension the user might want to change (diameters, heights, wall
  thickness, counts, angles) must appear as a NUMERIC param on some feature.
  Hollow containers: build the outer solid, then CUT a scaled inner solid —
  so wall thickness is controlled by the difference in their params.
- NO transform chains: rotate→rotate→move on a primitive is unreadable
  history. Place geometry where it belongs by drawing the sketch entities
  at the right coordinates (entity x/y, rotation), and keep at most ONE
  move/rotate per feature when truly needed (e.g. laying a wheel on its
  side). polar_pattern/linear_pattern replace repeated copies.
- Primitives (disc, plate, tube, ball...) are for solids whose primitive
  params ARE the editable dimensions (a washer = disc + with_center_hole).
  revolve_profile is for genuinely curved axisymmetric sections only.

NAMED PARAMETERS: a design may carry a top-level "parameters" object,
{{"wall": {{"expr": "3", "comment": "wall thickness"}}, "depth": {{"expr":
"wall*2"}}}}, and any NUMERIC feature param may then be a formula string
naming them ("amount": "wall*2", "radius": "bore/2"). Formulas use numbers,
parameter names, + - * / ** and min/max/abs/round/sqrt/floor/ceil/sin/cos/tan
(degrees) — nothing else. Use them when one dimension governs several
features (a wall thickness, a bolt size), so changing it once moves all.

SKETCH -> EXTRUDE IS THE PRIMARY WORKFLOW — required for logos, emblems,
text-like artwork, plates with cutouts, brackets, and any flat/prismatic
shape: make a "sketch" feature (a creator), then an "extrude"/"revolve"/
"sweep" feature consuming it, or "loft" consuming two sketches.

BASE FIRST, THEN SKETCH ON THE BASE — THE OFFSET METHOD
(user mandate 2026-08-27; this is the single most important rule here)
1. Build the BASE BODY first: base_sketch ("sketch", plane XY, offset 0) ->
   base ("extrude"). That solid is the stock every later feature refers to.
2. EVERY sketch after the base is a "sketch_on_face" whose input is the
   CURRENT body (the newest solid — the latest cut/fuse result, not the raw
   base), naming its face: {{"face":"top","offset":0,"entities":[...]}}.
   The face positions the plane; x/y in the entities mean exactly what they
   mean in a plane sketch, on every face. offset moves the plane along +Z for
   a top/bottom face (+X for +x/-x, -Y for front/back), and flip extrudes the
   other way.
3. State depth as a DEPTH FROM THAT FACE, never as an absolute Z:
   * pocket 3mm deep in the top   -> sketch_on_face face "top" offset 0,
     then extrude {{"amount":3,"flip":true}}, then cut
   * boss 4mm tall on the top     -> sketch_on_face face "top" offset 0,
     then extrude {{"amount":4}}, then fuse
   * a round hole (through or blind, plain / counterbore / countersink) ->
     ONE "hole" feature on the current body: {{"face":"top","at":[x,y],
     "diameter":6,"through":true}} (or "depth":8) — no sketch, no cut
   * MANY identical round holes (a bolt circle, a grid of tapping holes) ->
     ONE sketch_on_face holding all the circles, then extrude
     {{"through":true,"flip":true}} and cut. One "hole" feature each is right
     for a handful; thirty of them is thirty tree rows and thirty kernel cuts
   * a non-round cut right through -> sketch_on_face face "top" offset 0,
     then extrude {{"through":true,"flip":true}}, then cut
   * something starting partway in (a pilot hole in a 3mm recess floor) ->
     sketch_on_face face "top" offset -3, then extrude flip/through, cut
   A cut should use through=true unless the depth is the point; a tool that
   stops inside material slices it and leaves loose pieces.
3b. PICK THE DATUM THAT CARRIES THE INVARIANT. Measure from the TOP face what
   is a feature OF the top surface (a recess, an engraving, a groove). Measure
   from the BOTTOM face what must survive a change of stock thickness — a
   cavity is not "9mm deep", it is "leave a 3mm floor"; a boss the board bolts
   to is not "5mm below the lid", it is "4mm of standoff above the floor". From
   the bottom face the offset IS that height: {{"face":"bottom","offset":3}}.
   Get this backwards and making the plate thinner eats the floor instead of
   the cavity. To cut everything ABOVE such a plane, extrude from it with
   {{"through":true}} and no flip: it runs up and out of the top, so it can
   never breach the floor.
4. NEVER write a "sketch" with a nonzero absolute offset once a body exists.
   That is the banned old habit: it hardcodes an absolute Z, so changing the
   base thickness leaves every feature floating at the wrong height and the
   user has to re-derive dozens of numbers by hand. face+offset is exactly as
   expressive and it RIDES the geometry. This is linted and REJECTED.
FLAT-ARTWORK RECIPE (a logo IS 2D artwork extruded — never a pile of 3D
primitives): base_sketch (the outline or backing shape) -> base_extrude
(2-5mm) -> then EACH raised element: own sketch_on_face on the base "top" ->
own extrude -> fuse with the base; EACH engraved/pierced element: own
sketch_on_face on the base "top" -> own extrude (flip/through) -> cut from
the base. Draw shapes at their final x/y in the sketch.
HARD LIMITS (linted — trees breaking them are REJECTED before building):
- a sketch may hold AT MOST 10 entities; split larger artwork into logical
  sketches (one per design element);
- a design that is just ONE sketch + ONE extrude may hold at most 4
  entities in that sketch — anything richer must be recorded as history
  (base + per-element features as above).
A sketch's params are
{{"plane":"XY|XZ|YZ", "offset":mm, "entities":[...]}} where each entity is
{{"kind":"rectangle","w":..,"h":..,"x":0,"y":0,"mode":"add"}} (kinds:
rectangle w/h, circle r, ellipse rx/ry, slot length/height (length = OVERALL
end-to-end, must exceed height), regular_polygon
radius/sides, polygon points[[x,y]...], path {{"start":[x,y],"segments":[
{{"type":"line","to":[x,y]}} or {{"type":"arc","via":[x,y],"to":[x,y]}}...]}}
(auto-closes; use path for profiles mixing straight edges and arcs),
text {{"text":"WORD","size":mm}} (a word as glyph faces centred on x/y, font
optional, default Arial — a name or logo lettering; mode "subtract" inside a
plate's face sketch, extruded as a cut, is an engraving);
mode "add" or "subtract"; first must be add).
A sketch_on_face has ONE input (the body) and params
{{"face":"top|bottom|+x|-x|+y|-y","offset":mm,"entities":[...]}} — same
entities, and offset is measured from that face along the axis in rule 2
(from "top" negative goes into the material; from "bottom" positive is the
height above it). Do NOT send face_center/face_normal/face_area; the named
face is resolved from the real geometry at every rebuild (those three are what
a mouse click in the app leaves behind, and only it can fill them in).
extrude params {{"amount":mm,"flip":false,"through":false,"both":false}}; revolve {{"axis":"Z",
"angle":360}} (draw the profile on XZ at positive X to revolve about Z). Sketch
features have no volume — only the extrude/revolve/loft result is a solid.
"""


# The SAME conventions, for the door that takes a WHOLE tree in one answer:
# the MCP `build_design`, where another AI authors the tree itself. Only the
# protocol paragraph differs, and it is a real difference — `list_operations`
# handed that AI the step-loop prompt above ("YOU WORK ONE STEP PER REPLY …
# one of these four"), which describes a conversation build_design does not
# have: every reply shaped like it is rejected with "JSON must contain a
# non-empty 'features' list" (section 13 review, 2026-09-16). Everything from
# ALLOWED OPERATIONS down is shared verbatim, so the two doors can never
# teach different geometry.
_CONV_FROM = AUTHOR_PROMPT.find("ALLOWED OPERATIONS")   # never raise at import
_SHARED_CONVENTIONS = (AUTHOR_PROMPT[_CONV_FROM:] if _CONV_FROM >= 0
                       else AUTHOR_PROMPT)

TREE_PROMPT = """You design 3D objects as FEATURE TREES for a parametric CAD
system — ANY object: mechanical parts, products, furniture, toys, and stylized
models of real-world things. NEVER refuse a design request; build the best
RECOGNIZABLE STYLIZED approximation from the operations you have.

You author the WHOLE tree in ONE JSON object — no prose, no markdown:

{"name": "short-part-name",
 "features": [{"id": "unique_name", "op": "<op>", "params": {...},
               "inputs": ["upstream_id", ...]}, ...],
 "spec": {"n_solids": 1, ...optional: "symmetry": N, "tip_radius": mm,
          "size": [x, y, z or null], "holes": {"5": 2}, "tol": 0.5}}

Every feature is validated against the registry BEFORE anything is built (a
hallucinated op or parameter is rejected by name), every feature's geometry is
health-checked, and the finished design is verified against "spec" — the
numbers are measured, never trusted. spec "holes" maps a NUMERIC hole radius
in mm to a count; every spec key is measured or the tree is refused, so do not
invent one. Features evaluate in the order you list them and "inputs" must
name ids ALREADY listed above them.

The rules below are the ones TextCAD's own authoring loop follows; where they
speak of "done" and the spec it carries, that is the "spec" key above.

""" + _SHARED_CONVENTIONS


# ---------------------------------------------------------------------------
# Author -> validate -> rebuild -> verify -> repair loop
# ---------------------------------------------------------------------------

def _parse(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Tree lint — the HISTORY contract, enforced (prompt wording alone drifts).
# A tree that "builds" but is an unreadable blob is rejected BEFORE geometry,
# with diagnostics the repair loop feeds back to the model.
# ---------------------------------------------------------------------------

_GENERIC_ID = re.compile(r"^(feature|node|item|part|f)_?\d*$", re.I)


def _literal(value) -> float:
    """A hardcoded NUMBER, or 0.0 for anything that is not one.

    A FORMULA ("lid_z", "wall*2") is a named number the design can be steered
    by, so it is not what the absolute-Z rule is about — and it must never
    reach a bare `float()`, which raises out of the whole lint and out of
    `lint_baseline` with it (2026-09-23). A numeric string ("9") is still the
    hardcoded form, so the rule keeps exactly the reach it had."""
    if isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _lint_items(features, final: bool = True) -> list[tuple]:
    """Every history-lint problem as (key, rank, sentence).

    `key` names the RULE and the feature it is about; `rank` is the number
    that must not RISE. Together they answer the only question a step-by-step
    job can fairly be asked — "is this problem one I WROTE?" — by comparing
    the tree now against the tree the job started with (`lint_baseline`,
    `_lint_since`). A problem whose key is new, or whose rank has gone up, is
    the job's; one the tree already carried is the user's news."""
    items = []
    sketches = [f for f in features if f.op == "sketch"]
    for f in sketches:
        n = len(f.params.get("entities") or [])
        if n > 10:
            items.append((("cram", f.id), n,
                          f"sketch '{f.id}' crams {n} entities into one "
                          f"feature — split the artwork into logical sketches "
                          f"(one per design element, each with its own "
                          f"extrude, fused/cut together)"))
    if final and len(features) == 2 and len(sketches) == 1:
        n = len(sketches[0].params.get("entities") or [])
        if n > 4:
            items.append((("blob",), n,
                          f"the whole design is ONE sketch ({n} entities) + "
                          f"one consumer — that is a blob, not a design "
                          f"history. Record it as steps: base_sketch -> "
                          f"base_extrude, then each element as its own "
                          f"sketch -> extrude, fused or cut"))
    # THE OFFSET METHOD (user mandate 2026-08-27). Once a body exists, a
    # sketch floating at an absolute Z is the banned old habit: it hardcodes
    # the base thickness into every downstream feature, so 251 of the 274
    # sketches authored before this rule broke the moment a base dimension
    # changed. face+offset is exactly as expressive (any Z is reachable as an
    # offset from a face) and it rides the geometry — so there is no
    # legitimate reason left to write the absolute form.
    # The OFFSET VALUE is part of the key: a number the model puts there is
    # the model's, even in a sketch that was already floating.
    # A sketch on a CONSTRUCTION PLANE measured from a FACE is not the banned
    # form: the plane row rides that face, so the sketch moves with the design
    # exactly as face+offset does. A plane off a PRINCIPAL plane rides nothing
    # — it is the same hardcoded absolute Z with one row in between, and the
    # first version of this exemption waved it through (a second code review,
    # 2026-09-23). An `offset_plane` is not a body either, so it must not be
    # what makes `body_yet` true.
    # The distance can sit in EITHER row, or be split between them, and each
    # row answers for the number IT holds — so the exemption turns on "does
    # this plane ride a face?", NEVER on "is this sketch on a plane row?".
    # Written the second way it had a door left: `offset_plane(XY, 0)` +
    # `sketch(plane=that, offset=12)` passed BOTH rules, because the plane rule
    # saw 0 and the sketch rule saw a plane row. Measured (a third code review,
    # 2026-09-23): it builds green with the boss on the base's top face at
    # z 12..15, and changing the base 12 -> 20 BURIES it — the exact failure
    # this rule exists to prevent.
    # A FORMULA offset ("lid_z") is a NAMED number, not a hardcoded one — and
    # `float()` on it raised ValueError out of `lint_baseline`, which runs on
    # the USER's own document when an AI job starts: asking the AI to change a
    # design that drives a sketch offset from a parameter answered "the model
    # failed: could not convert string to float".
    import sketch as _sk
    # the construction planes, and which of them ride a face (they have a body
    # input) rather than a hardcoded distance from a principal plane
    planes = {f.id: f for f in features if f.op in _sk.PLANE_PRODUCERS}
    said = set()                       # one sentence per plane, not per sketch on it
    body_yet = False
    for f in features:
        plane_row = (str((f.params.get("plane") or "XY")) if f.op == "sketch"
                     else "XY")
        on_plane_row = plane_row not in _sk.PRINCIPAL_PLANES
        pf = planes.get(plane_row) if on_plane_row else None
        rides_face = pf is not None and bool(pf.inputs)
        floats = _literal(pf.params.get("offset")) if pf is not None and not rides_face else 0.0
        if f.op == "sketch" and body_yet and floats and plane_row not in said:
            said.add(plane_row)
            items.append((("plane_offset", plane_row, floats), 0,
                          f"the construction plane '{plane_row}' that sketch "
                          f"'{f.id}' is drawn on floats at absolute Z (offset "
                          f"{floats:g}) even though a body already "
                          f"exists — an offset_plane off a principal plane "
                          f"hardcodes a Z exactly as a floating sketch does. "
                          f"Measure it from a FACE instead: offset_plane with "
                          f'inputs [the current body] and {{"face":"top",'
                          f'"offset":<depth from that face>}}'))
        if (f.op == "sketch" and body_yet and not rides_face
                and _literal(f.params.get("offset"))):
            items.append((("offset", f.id, _literal(f.params["offset"])), 0,
                          f"sketch '{f.id}' floats at absolute Z (offset "
                          f"{f.params['offset']}) even though a body already "
                          f"exists — that hardcodes the base thickness and "
                          f"breaks the moment it changes. Use sketch_on_face "
                          f"on the current body instead: "
                          f'{{"face":"top","offset":<depth from that face, '
                          f'negative = into the material>}}, then extrude '
                          f"with flip/through and cut or fuse"))
        if f.op not in _sk.SKETCH_PRODUCERS and f.op not in _sk.PLANE_PRODUCERS:
            body_yet = True
    for f in features:
        if _GENERIC_ID.match(f.id):
            items.append((("generic", f.id), 0,
                          f"id '{f.id}' is meaningless — name features after "
                          f"what they ARE (base_plate, web_sketch, eye_cut...)"))
    return items


def lint_tree(features, final: bool = True) -> list[str]:
    """History-quality rules for AUTHORED trees (AI/MCP paths only — the
    manual UI records history naturally, one action per feature), over the
    WHOLE tree: the MCP `build_design` door, where every feature is the
    model's. `final=False` while a design is still being built step by step:
    the "whole design is one blob" rule judges the FINISHED design and must
    not refuse the second step of a ten-step part."""
    return [t for _, _, t in _lint_items(features, final)]


def lint_baseline(features) -> dict:
    """What a tree ALREADY breaks when a job starts on it, as {key: rank}.

    A step-by-step job is answerable for the history it writes, not for the
    one it inherits — it may not remove the user's features, so a rule about
    them is a wall it can never get past. Measured over the saved library
    (probes/author_live_designs_probe.py, probes/s13_round2_probe.py): judged
    on the whole tree, 27 of the 50 designs refused the AI's first correct
    step for a sketch the USER drew, and scoping the verdict to the ids the
    job WROTE still refused an EDIT to any such feature on the same 27 —
    which is the one move the opening message invites. Three refusals give
    the job up and studio puts the snapshot back: "I did NOT change your
    design". `final=True` here because it is a superset: the blob rule is the
    only final-only rule, and a baseline may only ever forgive."""
    base = {k: r for k, r, _ in _lint_items(features, final=True)}
    if features:
        # ...with ONE rule a rank cannot carry. "The whole design is one sketch
        # + one consumer" is a fact about the WHOLE TREE that only comes into
        # being when the SECOND feature lands, so a baseline taken on a
        # one-feature tree can never hold it — and round one's blob rule had an
        # owner test (`all(mine(f.id) for f in features)`) that this mechanism
        # dropped. Measured 2026-09-17 (probes/s13_round3_probe3.py): the user
        # draws a sketch of five or more shapes and asks the AI to extrude it,
        # and `done` is refused for their own history's shape — three times,
        # after which studio puts the snapshot back ("I did NOT change your
        # design"). The rule judges a history the JOB wrote end to end, so a
        # tree it INHERITED is exempt, whatever shape it has or takes.
        base[("blob",)] = float("inf")
    return base


def _lint_since(features, baseline, final: bool = True) -> list[str]:
    """The lint problems a job is answerable for: the ones its tree did not
    already carry, and the ones it has made WORSE. `baseline=None` judges
    everything (a design being created from nothing, and any direct caller)."""
    return [t for k, r, t in _lint_items(features, final)
            if baseline is None or k not in baseline or r > baseline[k]]


def checked_spec(spec) -> dict:
    """The spec the model sent, with every key PROVEN checkable. Raises
    ValueError with the sentence to feed back.

    It used to keep the keys `inspector.Spec` knows and drop the rest in
    silence — so "DONE: every feature ok and the spec is met" (and the MCP
    `verify_step`'s "matches_spec": true, whose docstring says an empty
    mismatch list means the part PROVABLY matches) covered a requirement
    nothing had measured. A claim about a requirement that was never checked
    is the one thing this project may never make, so an unknown key is a
    refusal that names it. `size` and `com` must name all three axes for the
    same reason: verify() zips them against the measured triple, so
    {"size": [40, 30]} left Z unchecked and still answered "matches"."""
    spec = spec or {}
    if not isinstance(spec, dict):
        raise ValueError('"spec" must be an object like {"n_solids": 1}')
    known = {"size", "volume", "holes", "n_solids", "symmetry", "tip_radius",
             "com", "require_manifold", "tol", "vol_tol"}
    unknown = sorted(k for k in spec if k not in known)
    if unknown:
        raise ValueError(
            'nothing here can MEASURE spec ' + ", ".join(f'"{k}"' for k in unknown)
            + ', so a spec carrying it would claim a check that never ran. '
              'The requirements that are measured are: ' + ", ".join(sorted(known))
            + " — express the rest as geometry the tree builds")
    out = {k: v for k, v in spec.items() if k in known}
    for key in ("size", "com"):
        v = out.get(key)
        if v is not None and (not isinstance(v, (list, tuple)) or len(v) != 3):
            raise ValueError(
                f'spec "{key}" must name all THREE axes, [x, y, z], with null '
                f'for an axis you do not pin — {v!r} leaves an axis unchecked')
    if out.get("holes"):
        try:
            out["holes"] = {float(k): int(v) for k, v in out["holes"].items()}
        except (TypeError, ValueError, AttributeError):
            raise ValueError(
                'spec "holes" keys must be NUMERIC radii in mm, e.g. '
                '{"5": 1} for one 5mm-radius hole — not placeholder words')
    if "symmetry" in out:
        sy = out["symmetry"]
        if not isinstance(sy, int) or isinstance(sy, bool) or not 2 <= sy <= 64:
            raise ValueError(
                'spec "symmetry" must be an INTEGER 2..64 counting discrete '
                'features around Z (blade count, bolt count). OMIT it entirely '
                'for axisymmetric/revolved parts — never "infinite"')
    return out


def _to_document(data: dict) -> Document:
    """Validate + construct a WHOLE tree (the MCP `build_design` door, where
    another AI authors the tree itself). Raises ValueError with a diagnostic."""
    if not isinstance(data.get("features"), list) or not data["features"]:
        raise ValueError("JSON must contain a non-empty 'features' list")
    doc = Document(name=str(data.get("name", "untitled"))[:60])
    # named parameters first, so a feature's "wall*2" has something to name;
    # each one refused with its own sentence (a loop, a reserved word)
    params = data.get("parameters") or {}
    if not isinstance(params, dict):
        raise ValueError("'parameters' must be an object: {\"wall\": {\"expr\": \"3\"}}")
    # in ANY order, as a saved file loads them: `depth = wall*2` written above
    # `wall = 3` was refused as "no parameter named 'wall'" (review of Named
    # parameters, 2026-09-23). Round after round, until a round sets nothing;
    # then the first sentence left is the real one (a loop, a typo).
    pending = list(params.items())
    while pending:
        left, first = [], None
        for name, spec in pending:
            expr = spec.get("expr") if isinstance(spec, dict) else spec
            comment = spec.get("comment") if isinstance(spec, dict) else None
            try:
                doc.set_parameter(str(name), expr, comment)
            except ValueError as e:
                left.append((name, spec))
                first = first or e
        if len(left) == len(pending):
            raise first
        pending = left
    for f in data["features"]:
        doc.add(f["id"], f["op"], f.get("params") or {}, f.get("inputs") or [],
                strict=True)          # a hallucinated key is named, not stored
    lint = lint_tree(doc.features)
    if lint:
        raise ValueError("history lint: " + "; ".join(lint))
    doc.spec = checked_spec(data.get("spec"))
    return doc


# ---------------------------------------------------------------------------
# The step loop — the AI uses the same tools (LAUNCH-PLAN.md §5 step B, P5)
# ---------------------------------------------------------------------------
# The model adds ONE feature per reply. Each step goes through exactly what
# the toolbar's Add Feature goes through — Document.add(strict=True), the
# history lint, a rebuild — and is judged on its own: a refused or broken
# step is undone before the model hears about it, so the tree on screen never
# holds a feature the kernel did not accept. An "edit" points at one
# parameter of an earlier feature (never a regenerated tree); "done" carries
# the spec and is refused while the spec is not met. The loop gives up after
# MAX_FAILS refusals in a row and says so — a partial tree of verified
# features beats a whole tree of guesses.

MAX_STEPS = 40          # bounds the cost of a model that never says done
MAX_FAILS = 3           # refusals in a row before the loop gives up

# THE CHECKLIST. The model's first reply carries a "plan": the must-have
# elements of the request in words. When it says "done", the judge (judge.py,
# a small local yes/no model — never the kernel) is asked, per element, "is
# this in the design?" against a one-line-per-feature summary of the tree.
# An element it cannot find refuses "done" — at most CHECKLIST_CAP times per
# job, and NEVER as a counted failure: a judge is a guess with a probability,
# and a guess may not cost the user a verified design (three counted
# refusals give the job up and studio restores the snapshot). Past the cap,
# done is accepted and the unconfirmed elements are reported. No judge
# running -> no checklist -> done as before (judge.py fails open).
CHECKLIST_CAP = 2
MISSING_BELOW = 0.5     # P(yes) under this = "not found"
PLAN_MAX = 10
# ...and a clock for the CHAT JOB, which studio passes in. Steps are not the
# only way a job runs long, and an "add" job makes its tab READ-ONLY while it
# runs (studio._one_writer_per_tab): a model that is merely slow locks the
# user out of their own design with no Cancel to press. It is not the loop's
# own default, because the MCP design_part door has no tab to protect and a
# 40-step design legitimately outlasts five minutes.
MAX_SECONDS = 300


def _restore(doc: Document, data: dict) -> bool:
    """Put the tree back exactly as `data` (a to_data() snapshot) had it —
    the same road undo takes — keeping the document OBJECT, which a tab
    entry holds by identity, and with it the rollback bar and the build
    cache. Returns the rebuild's verdict, so a caller can record it."""
    fresh = Document.from_data(data)
    doc.name, doc.features, doc.spec = fresh.name, fresh.features, fresh.spec
    doc._mark_stale()
    return doc.rebuild()


def _bodies(doc: Document) -> str:
    ids = doc.leaf_solid_ids()
    return ", ".join(ids) if ids else "none yet"


def _plan_items(raw) -> list[str]:
    """The model's "plan" as clean short strings (at most PLAN_MAX)."""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, str):
            s = " ".join(item.split())[:80].strip(" .;:")
            if s and s.lower() not in (o.lower() for o in out):
                out.append(s)
    return out[:PLAN_MAX]


def _feature_words(f) -> str:
    """One line of words about a feature, for a reader that sees only text."""
    p = f.params or {}
    bits = [f"{f.id}: {f.op}"]
    if f.op in ("sketch", "sketch_on_face"):
        where = p.get("face") if f.op == "sketch_on_face" else p.get("plane")
        if isinstance(where, dict):
            where = where.get("face") or where.get("name") or "face"
        # sizes ride along: a plan item that names one ("USB-C opening
        # 10x3 mm") read 0.37 against a summary without them and 0.97 with
        # (measured 2026-09-29 through the real judge)
        kinds: dict[str, int] = {}
        for e in p.get("entities") or []:
            k = e.get("kind", "entity") if isinstance(e, dict) else "entity"
            if isinstance(e, dict):
                if k == "rectangle" and "w" in e and "h" in e:
                    k = f"rectangle {e['w']:g}×{e['h']:g}"
                elif k == "circle" and "r" in e:
                    k = f"circle r{e['r']:g}"
                elif k == "slot" and "length" in e:
                    k = f"slot {e['length']:g} long"
            kinds[k] = kinds.get(k, 0) + 1
        drawn = ", ".join(f"{n} {k}" for k, n in kinds.items()) or "empty"
        bits.append(f"on {where}" if where else "")
        if p.get("offset"):
            bits.append(f"offset {p['offset']}")
        bits.append(drawn)
    else:
        nums = [f"{k} {v}" for k, v in p.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)][:4]
        words = [f"{k} {v}" for k, v in p.items() if isinstance(v, str)][:2]
        bits += nums + words
    if f.inputs:
        bits.append("of " + ", ".join(f.inputs))
    if f.suppressed:
        bits.append("(switched off)")
    return " — ".join(b for b in bits if b)


def _tree_words(request: str, doc: Document) -> str:
    """The design as text a small judge can read: the request, then one
    line per feature in build order. Fitted to the judge's window by
    dropping detail before dropping features."""
    head = "REQUEST: " + " ".join(request.split())[:300] + "\nDESIGN, in build order:\n"
    budget = judge.STATE_CHARS - len(head)
    for detail in (True, False):
        lines = [(_feature_words(f) if detail else f"{f.id}: {f.op}")
                 for f in doc.features]
        body = "\n".join("- " + ln for ln in lines)
        if len(body) <= budget:
            return head + body
    return (head + body)[:judge.STATE_CHARS]


def _checklist_missing(request: str, doc: Document, plan: list[str]) -> list[str]:
    """Plan elements the judge does NOT find in the design. [] when there
    is no judge to ask (fail open) — a missing judge is not a missing part."""
    if not plan or not doc.features:
        return []
    qs = {f"p{i}": ("Does the design contain this element (exact sizes do "
                    f"not matter): {item}?")
          for i, item in enumerate(plan)}
    got = judge.yes_no(_tree_words(request, doc), qs)
    if not got:
        return []
    return [item for i, item in enumerate(plan)
            if f"p{i}" in got and got[f"p{i}"] < MISSING_BELOW]


def _built(doc: Document, f) -> str:
    """One line of measured facts about a feature that just built ok."""
    if f.volume is None:
        n = len(f.params.get("entities") or [])
        where = f.params.get("face") or f.params.get("plane") or ""
        return (f"OK: '{f.id}' ({f.op}) is a sketch of {n} entit"
                f"{'y' if n == 1 else 'ies'} on {where}. Bodies: {_bodies(doc)}.")
    line = f"OK: '{f.id}' ({f.op}) built — volume {f.volume:g} mm³"
    part = doc._parts.get(f.id)
    if part is not None:
        import inspector
        size = inspector.measure(part).get("size")
        if size:
            line += " — size " + "×".join(f"{v:g}" for v in size) + " mm"
    if f.pieces and f.pieces > 1:
        line += (f" — in {f.pieces} separate pieces (fine for a cutting tool "
                 f"made of several shapes; the FINISHED part must be one piece)")
    # Warnings quote the feature they are about ('base_plate' and 'a' are
    # separate bodies...). A bare substring test made every warning belong to
    # a one-letter id, and 'boss' owned every line about 'boss_cut'.
    notes = [str(w).rstrip(".") for w in doc.warnings if f"'{f.id}'" in str(w)]
    if notes:
        line += ". Note: " + "; ".join(notes[:2])
    return line + f". Bodies: {_bodies(doc)}."


def _first_problem(doc: Document, was_ok=frozenset(),
                   only=None) -> str | None:
    """The first RED feature this step is answerable for, as a sentence.

    `only` (an add/edit step) limits the question to the feature the step
    wrote plus the ones that were HEALTHY before it. A row that was already
    red is not the step's doing, and undoing a correct step for it locked
    the AI out of the design completely: measured 2026-09-11, three correct
    steps on a design with one red feature each came back "UNDONE — it built
    broken geometry" naming somebody else's feature, then "I did NOT change
    your design". `done` passes no `only` and judges the WHOLE tree, which
    is the whole point of done."""
    for f in doc.features:
        if f.status == "ok" or f.suppressed:
            continue
        if only is not None and f.id not in only:
            continue
        tag = " (it was fine before this step)" if f.id in was_ok else ""
        return f"'{f.id}' ({f.op}){tag}: " + "; ".join(f.problems)
    return None


def _apply_step(doc: Document, step: dict, protected=frozenset(),
                keep_spec: bool = False, authored=None, baseline=None
                ) -> tuple[bool, str, str | None]:
    """Apply ONE reply to the document. -> (ok, sentence, feature id).
    Never raises for the model's mistakes; the sentence is what it hears.
    On a refusal the document is exactly as it was.

    `protected`: ids that were in the tree BEFORE this job — the model may
    edit them but never remove them. `keep_spec`: the design already records
    the user's own requirement, so "done" may not write a spec over it.
    `authored`: the MUTABLE set of ids this job has written or changed — what
    `done`'s health question is asked about, together with the ones that were
    HEALTHY when the step started; a row the user left red is reported to
    them and is not the model's to be stopped by. `baseline`: what the tree
    already broke when the job started (`lint_baseline`) — the history lint
    answers for what this job wrote or made worse, not for what it inherited.
    None for either (a caller with no job, and every design the model creates
    from nothing) keeps the whole tree in scope."""
    before = doc.to_data()
    was_ok = {f.id for f in doc.features if f.status == "ok"}
    scope = None if authored is None else (was_ok | set(authored))
    # ONE step per reply, or none of the verification means anything: a reply
    # carrying {"add": ...} AND "done": true took the add road, came back ok,
    # and the loop then read "done" and FINISHED — no final lint, no spec, no
    # spec check. Measured 2026-09-11: two loose bodies and an empty spec
    # reported as "Designed ... each verified as it was added".
    acts = [k for k in ("add", "edit", "remove") if k in step]
    acts += ["done"] if step.get("done") else []
    if len(acts) > 1:
        return False, ("REFUSED: one step per reply — this one carried "
                       + " and ".join(f'"{a}"' for a in acts)
                       + '. Send them one at a time, "done" last'), None
    if "add" in step:
        a = step["add"]
        if not isinstance(a, dict) or not a.get("id") or not a.get("op"):
            return False, 'REFUSED: "add" needs {"id", "op", "params", "inputs"}', None
        fid = str(a["id"])
        try:
            doc.add(fid, str(a["op"]), a.get("params") or {},
                    a.get("inputs") or [], strict=True)
            lint = _lint_since(doc.features, baseline, final=False)
        except (ValueError, KeyError, TypeError) as e:
            _restore(doc, before)
            return False, f"REFUSED '{fid}': {e}", fid
        if lint:
            _restore(doc, before)
            return False, f"REFUSED '{fid}' (history lint): " + "; ".join(lint), fid
        doc.rebuild()
        f = doc.get(fid)
        bad = _first_problem(doc, was_ok, only=was_ok | {fid})
        if bad:
            _restore(doc, before)
            return False, f"UNDONE '{fid}' — it built broken geometry: {bad}", fid
        if authored is not None:
            authored.add(fid)
        return True, _built(doc, f), fid
    if "edit" in step:
        e = step["edit"]
        if not isinstance(e, dict) or not e.get("feature_id") or not e.get("param"):
            return False, 'REFUSED: "edit" needs {"feature_id", "param", "value"}', None
        fid = str(e["feature_id"])
        try:
            doc.edit(fid, str(e["param"]), e.get("value"))
        except (KeyError, ValueError, TypeError) as err:
            _restore(doc, before)
            return False, f"REFUSED edit of '{fid}': {err}", fid
        # An edit was the one step the lint never saw, so the banned
        # absolute-offset form could be edited INTO a tree a number at a time
        # (only `done` looked, by which point it was in). What it may NOT do
        # is refuse the edit for a problem the feature already had before this
        # job touched it — that was the same lock-out one door further on, on
        # 27 of the 50 saved designs (section 13 round two, 2026-09-17).
        lint = _lint_since(doc.features, baseline, final=False)
        if lint:
            _restore(doc, before)
            return False, (f"REFUSED edit of '{fid}' (history lint): "
                           + "; ".join(lint)), fid
        doc.rebuild()
        bad = _first_problem(doc, was_ok, only=was_ok | {fid})
        if bad:
            _restore(doc, before)
            return False, (f"UNDONE edit '{fid}.{e['param']}' = {e.get('value')!r} "
                           f"— with it the tree breaks at {bad}"), fid
        if authored is not None:
            authored.add(fid)
        return True, (f"OK: '{fid}.{e['param']}' = {e.get('value')!r}. "
                      + _built(doc, doc.get(fid))), fid
    if "remove" in step:
        fid = str(step["remove"])
        # Only a step of the model's OWN. "remove" is meant to take back its
        # last move; unguarded it deleted a feature the user had built and the
        # chat still said "Added one or more parameters" (measured 2026-09-11).
        if fid in protected:
            return False, (f"REFUSED remove of '{fid}': it was in the design "
                           f"before you started, so it is the user's, not "
                           f"yours to take back. Use edit to change it"), fid
        try:                     # strict: only a step nothing else builds on
            doc.remove(fid, mode="strict")
        except (KeyError, ValueError) as err:
            _restore(doc, before)
            return False, f"REFUSED remove of '{fid}': {err}", fid
        doc.rebuild()
        return True, f"OK: removed '{fid}'. Bodies: {_bodies(doc)}.", fid
    if step.get("done"):
        if not doc.leaf_solid_ids():
            return False, ("REFUSED done: the design has no solid body yet "
                           "(a sketch alone has no volume) — add features"), None
        lint = _lint_since(doc.features, baseline)
        if lint:
            return False, "REFUSED done (history lint): " + "; ".join(lint), None
        if keep_spec:
            # The design already records the USER's requirement, and it is
            # theirs. "done" used to overwrite it: an "add a hole" job turned
            # {"size":[40,30,5],"n_solids":1,"tol":0.5} into {"n_solids":1}
            # and reported success (measured 2026-09-11 — 31 of the user's 50
            # designs pin a size, 22 pin holes). So the model's spec is
            # dropped, theirs is kept, and done is judged on the tree's
            # HEALTH: whether the change they ASKED for still meets a
            # requirement written earlier is news for THEM, in the reply —
            # not a wall for the model to batter for three steps.
            doc.rebuild()
            bad = _first_problem(doc, only=scope)
            if bad:
                return False, f"REFUSED done: {bad}", None
            # A row that was ALREADY red when the job started is the user's
            # news, not a wall: `done` used to judge the whole tree, so one
            # feature they had left broken refused it — and three refusals
            # give the job up, after which studio puts the snapshot back and
            # every verified step is discarded ("I did NOT change your
            # design"). Worse, the only way past it was for the model to
            # rewrite a number the user set. It is reported instead.
            theirs = _first_problem(doc) if scope is not None else None
            still = (f" One feature was already broken before I started and "
                     f"still is — {theirs}" if theirs else "")
            if not doc.spec:
                return True, ("DONE: every feature I touched is ok; the design "
                              "records no spec, and adding to it does not write "
                              "one." + still), None
            miss = "; ".join(doc.spec_problems)
            return True, ("DONE: every feature I touched is ok. The design keeps "
                          "the spec it already recorded"
                          + (f", and no longer meets it: {miss}" if miss else "")
                          + "." + still), None
        try:
            doc.spec = checked_spec(step.get("spec"))
        except ValueError as err:
            return False, f"REFUSED done: {err}", None
        doc.spec.setdefault("n_solids", 1)
        if doc.rebuild():
            return True, "DONE: every feature ok and the spec is met.", None
        bad = _first_problem(doc, only=scope)
        if bad:                        # cannot happen after a clean step; belt
            _restore(doc, before)
            return False, f"REFUSED done: {bad}", None
        problems = "; ".join(doc.spec_problems)
        return False, (f"REFUSED done: the part does not meet the spec — "
                       f"{problems}. Fix the GEOMETRY with edit/add steps "
                       f"(never weaken the spec) and say done again"), None
    return False, ('REFUSED: reply with exactly one of {"add": {...}}, '
                   '{"edit": {...}}, {"remove": "id"} or {"done": true, "spec": {...}}'), None


def author_steps(doc: Document, request: str, model, on_step=None, guard=None,
                 max_steps: int = MAX_STEPS, max_fails: int = MAX_FAILS,
                 max_seconds: float | None = None   # None: no clock
                 ) -> tuple[bool, list[str]]:
    """Let the model build `request` INTO `doc`, one verified step at a time.

    `doc` may be empty (a new design) or the user's current design (the
    model then adds to it — its tree is shown first). `on_step(event)` hears
    every step as it lands: {"kind": add|edit|done|refused|gave_up, "text",
    "id", "ok": the tree's health now}. `guard()` is a context manager the
    caller may wrap each kernel step in (the server takes its kernel lock
    and in-flight marker there). -> (finished, transcript)."""
    protected = frozenset(f.id for f in doc.features)   # the user's own work
    authored: set[str] = set()          # what THIS job wrote: what it answers for
    baseline = lint_baseline(doc.features)   # ...and what it did NOT write
    # Adding to a design that ALREADY EXISTS never writes a spec. Keying this
    # on "does it have a spec" left the 8 live designs that carry none open to
    # the model writing one over them (measured 2026-09-11, review round two):
    # a requirement the user never set, that their status bar then reports
    # against. A spec is the model's to author only on a design it is creating.
    keep_spec = bool(doc.features)
    tree = [{"id": f.id, "op": f.op, "params": f.params, "inputs": f.inputs}
            for f in doc.features]
    opening = f"REQUEST: {request}\n\n"
    if tree:
        opening += (f"CURRENT TREE (add to it; do not rebuild what exists; "
                    f"these features are the user's — you may edit a number "
                    f"in one, never remove one):\n{json.dumps(tree)}\n"
                    f"BODIES: {_bodies(doc)}\n")
        opening += (f"THE DESIGN'S SPEC IS THE USER'S and is kept as it is — "
                    f"do not send one: {json.dumps(doc.spec, default=str)}\n"
                    if doc.spec else
                    "THE DESIGN RECORDS NO SPEC, and adding to it does not "
                    "write one — do not send a spec with done.\n")
        opening += "\nFirst step?"
    else:
        opening += "The tree is empty. First step?"
    messages = [{"role": "system", "content": AUTHOR_PROMPT},
                {"role": "user", "content": opening}]
    transcript: list[str] = []
    fails = 0
    pending_name = None       # the model's name, held until a step LANDS
    plan: list[str] = []      # the model's must-have list, read once
    first = True              # ...on its first reply, whatever the tree
    checks = 0                # checklist refusals so far (<= CHECKLIST_CAP)

    def say(kind, text, fid=None):
        transcript.append(text)
        if on_step:
            on_step({"kind": kind, "text": text, "id": fid,
                     "ok": all(f.status == "ok" or f.suppressed
                               for f in doc.features) and not doc.spec_problems})

    # A parked rollback bar means the kernel does not build past it: every
    # step lands "stale (after rollback bar)" and is undone as broken geometry
    # (measured 2026-09-11), and nothing the model added could be verified
    # anyway — which is the one thing this loop exists to do.
    if doc.rollback is not None:
        say("gave_up", f"the rollback bar is parked at '{doc.rollback}', so "
                       f"the tree below it is not built and no step could be "
                       f"checked — release the bar and ask again")
        return False, transcript

    deadline = None if max_seconds is None else time.monotonic() + max_seconds
    for step_no in range(max_steps):
        steps_left = max_steps - step_no - 1     # after this one
        if deadline is not None and time.monotonic() >= deadline:
            say("gave_up", f'GAVE UP: {max_seconds:g} seconds without "done"; '
                           f'{len(doc.features)} verified feature(s) stand.')
            return False, transcript
        raw = model.generate(messages)
        messages.append({"role": "assistant", "content": raw})
        step = None
        soft = False          # a checklist refusal is not a counted failure
        try:
            step = _parse(raw)
            if not isinstance(step, dict):
                raise ValueError("not an object")
        except (ValueError, json.JSONDecodeError) as e:
            ok, text, fid = False, f"REFUSED: that was not one JSON object ({e})", None
        else:
            # "name" is read while the tree is still empty — but only APPLIED
            # once a step lands, or a refused step renamed the tab on its way
            # out ("sports-car" stuck to a design whose only step was an
            # unknown op). It is held instead of dropped, so a model that
            # names itself once and is then refused still names its design.
            naming = not doc.features
            if naming and isinstance(step.get("name"), str):
                pending_name = step["name"].strip()[:60] or pending_name
            if first:
                plan, first = _plan_items(step.get("plan")), False
            # THE CHECKLIST (see CHECKLIST_CAP): "done" is first read against
            # the plan by the judge, before the kernel is asked anything.
            # ...and only while at least two steps remain to act on it: a
            # refusal the model has no room to answer would just spend the
            # last steps (the smoke job of 2026-09-29 gave up at step 40
            # with a checklist refusal as its second-to-last line).
            unconfirmed = (_checklist_missing(request, doc, plan)
                           if step.get("done") and plan and steps_left >= 2
                           else [])
            if unconfirmed and checks < CHECKLIST_CAP:
                checks += 1
                soft = True
                ok, text, fid = False, (
                    "REFUSED done (checklist): not found in the design — "
                    + "; ".join(unconfirmed) + ". Add each one as its own "
                    "step (or edit what stands), then say done again."), None
            elif guard is not None:
                with guard():
                    ok, text, fid = _apply_step(doc, step, protected,
                                                keep_spec, authored, baseline)
            else:
                ok, text, fid = _apply_step(doc, step, protected, keep_spec,
                                            authored, baseline)
            if ok and step.get("done") and unconfirmed:
                text += (" Checklist could not confirm: "
                         + "; ".join(unconfirmed) + ".")
            if ok and naming and pending_name:
                doc.name = pending_name
        if ok and step.get("done"):
            say("done", text)
            return True, transcript
        if ok:
            fails = 0
            say(next(k for k in ("add", "edit", "remove") if k in step), text, fid)
            messages.append({"role": "user", "content": text + " Next step?"})
            continue
        if not soft:
            fails += 1
        say("refused", text, fid)
        if fails >= max_fails:
            say("gave_up", f"GAVE UP after {fails} refused steps in a row; "
                           f"{len(doc.features)} verified feature(s) stand.")
            return False, transcript
        # "corrected step" after a checklist refusal drew prose twice in the
        # 2026-09-29 smoke job (nothing was wrong with the last step)
        messages.append({"role": "user", "content": text + (
            " Send the step that adds it (JSON only)." if soft
            else " Send the corrected step (JSON only).")})
    say("gave_up", f'GAVE UP: {max_steps} steps without "done".')
    return False, transcript


def author_design(prompt: str, model, max_attempts: int = 4):
    """A whole design from a sentence, on a fresh document, through the step
    loop. Returns (Document | None, transcript) — the MCP `design_part` door."""
    doc = Document(name="untitled")
    finished, transcript = author_steps(doc, prompt, model,
                                        max_fails=max(1, max_attempts - 1))
    return (doc if finished else None), transcript


# ---------------------------------------------------------------------------
# Self-test with a fake model — proves validation + repair without an API key
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    class FakeAuthor:
        """Emits a bad step (unknown op) first, then a correct washer, one
        feature per reply."""
        def __init__(self):
            self.replies = [
                {"name": "washer", "add": {"id": "body", "op": "torus",
                                           "params": {"r": 20}}},
                {"name": "washer-40", "add": {"id": "body", "op": "disc",
                                              "params": {"radius": 20, "thickness": 4}}},
                {"add": {"id": "hole", "op": "with_center_hole",
                         "params": {"radius": 10}, "inputs": ["body"]}},
                {"done": True, "spec": {"n_solids": 1, "holes": {"10": 1}, "tol": 0.5}},
            ]
        def generate(self, messages):
            return json.dumps(self.replies.pop(0))

    doc, transcript = author_design("a washer, 40mm outer, 20mm hole, 4mm thick",
                                    FakeAuthor())
    print("\n".join(transcript))
    assert doc is not None, "authoring failed"
    print(doc.tree())
    print("volume:", doc.get("hole").volume)
