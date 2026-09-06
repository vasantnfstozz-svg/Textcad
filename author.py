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

The loop mirrors generate.py: author -> validate -> rebuild -> verify -> feed
every failure back -> retry. Failures are per-node and diagnostic.
"""

from __future__ import annotations
import json
import re

import document
from document import Document, CREATORS, MODIFIERS, op_params


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
       "length", "amount", "offset", "dx", "dy", "dz", "x", "y", "z",
       "pitch_circle_dia", "rx", "ry", "inner_r", "outer_r", "tip_radius",
       "diameter", "cbore_diameter", "cbore_depth", "csink_diameter"}
_DEG = {"angle", "angle2", "angle_deg", "rotation", "inlet_angle", "exit_angle",
        "csink_angle"}
# an `axis` that is NOT the world-axis enum: revolve's takes "u" / "v", a world
# name or a line [[u1, v1], [u2, v2]] in the sketch plane (see its OP_NOTE) —
# an enum here would tell the AI the one form that cannot work on a face
_NO_ENUM = {("revolve", "axis"), ("revolve_face", "axis")}

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
    "rotate": "Spins the part about the chosen axis THROUGH THE ORIGIN.",
    "mirror": "Mirrors across a principal plane and RETURNS A COPY.",
    "fillet": "vertical = the 4 upright corner edges (round a box's corners); "
              "radius must be < half the adjacent wall thickness. `edges` may "
              "also be a list of picked edges (the Studio tool writes these).",
    "shell": "Hollows to walls of `thickness`; open_face removes that face.",
    "revolve": "Spins the sketch about an axis IN its plane: \"v\" / \"u\" (the plane's "
               "own axes through the sketch origin — they ride the geometry), a world "
               "axis \"X\"/\"Y\"/\"Z\" lying in the plane, or a line in the sketch's own "
               "coordinates [[u1, v1], [u2, v2]] (one of the profile's straight edges). "
               "The profile must lie entirely to one side. angle is signed; angle2 adds "
               "a second side the other way; both=true sweeps angle to EACH side "
               "(Fusion's Symmetric, the same key as extrude's).",
    "revolve_face": "Revolves a flat face of the input body (face_center + face_normal "
                    "from a real pick) about a line in the face's plane, normally one of "
                    "its straight edges: axis=[[u1, v1], [u2, v2]]. Returns only the new "
                    "solid; fuse/cut it with the body.",
    "hole": 'Drills ONE hole into the input body from a flat face and RETURNS THE '
            'BODY WITH THE HOLE (no sketch, no cut feature). Name the face '
            '(face="top"/"bottom"/"+x"/… — never compute a face_center) and place '
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
                      '"+y"|"-y" (never compute a face_center yourself). The '
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
        if n in _ENUMS and (op_name, n) not in _NO_ENUM:
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
    document will accept from it cannot drift apart."""
    def entry(name, kind, inputs):
        params = [{"name": n, "default": d} for n, d in op_params(name)]
        return {"op": name, "kind": kind, "inputs": inputs,
                "params": _annotate(name, params), "note": OP_NOTES.get(name)}

    cat = [entry(name, "creator", 0) for name in CREATORS]
    cat += [entry(name, "modifier", 1) for name in MODIFIERS]
    cat.append(entry("move", "modifier", 1))
    from document import COMBINERS
    cat += [entry(name, "combiner", 2) for name in COMBINERS]
    return cat


def _catalog_text() -> str:
    lines = []
    for c in op_catalog():
        ps = ", ".join(p["name"] + (f"={p['default']}" if p["default"] is not None
                                    else "") for p in c["params"])
        need = {"creator": "no inputs", "modifier": "1 input",
                "combiner": "2+ inputs"}[c["kind"]]
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
requirement here. Respond with ONLY a JSON object, no prose, no markdown:

{{"name": "short-part-name",
 "features": [
   {{"id": "unique_name", "op": "<op>", "params": {{...}}, "inputs": ["upstream_id", ...]}},
   ...
 ],
 "spec": {{"n_solids": 1, ...optional: "symmetry": N, "tip_radius": mm, "size": [x,y,z or null], "holes": {{"5": 2}}, "tol": 0.5}}
}}

(spec "holes" maps NUMERIC hole radius in mm -> count; e.g. {{"5": 2}} means
two 5mm-radius holes.)

ALLOWED OPERATIONS (the ONLY ops that exist — anything else is rejected):
{_catalog_text()}

RULES AND CONVENTIONS:
- Units: mm and degrees. Z is the vertical/rotation axis. All ops return solids.
- POSITIONING (critical): disc, plate, tube, polygon_plate and hex_plate are
  CENTERED at the origin — they span Z from -thickness/2 to +thickness/2.
  revolve_profile spans EXACTLY the z values in its points. curved_blade
  stands on Z=0 up to its height. Use "move" to align pieces BEFORE booleans.
- The spec encodes the USER's requirement. If verification fails, fix the
  GEOMETRY to meet the spec — NEVER weaken or change the spec to match wrong
  geometry.
- Features evaluate in list order; "inputs" must reference EARLIER ids.
- creators take no inputs; modifiers exactly 1; fuse/cut/intersect 2 or more
  (cut = first input minus the rest).
- revolve_profile points are [radius, z] pairs (radius >= 0), auto-closed —
  use it for any axisymmetric body (hubs, pulleys, shafts, bottles).
- curved_blade makes ONE turbomachinery-style backswept blade standing on the
  XY plane; combine with polar_pattern for impellers/fans; angles from radial.
- polar_pattern copies its input N times evenly around Z — features meant to
  fuse with a body MUST physically overlap it (touching is not enough). To
  repeat a FEATURE of a body (a bolt circle of one hole, teeth from one boss)
  add it AFTER the body's latest feature with "seed": that feature's id and
  "axis": {{"face": "top"}} (a flat face: its normal through its centre; a bore's
  wall: its own axis) — "angle" 360 is a full circle, less spreads the copies
  from the seed to that angle.
- "rotate" orients parts: cylinders are upright by default — a WHEEL or axle is
  rotate(axis "X" or "Y", 90). "mirror" returns the mirrored COPY (fuse it with
  the original for symmetric pairs, e.g. left/right fenders).
- "fillet"/"chamfer" round or bevel edges ("all"/"top"/"bottom") — use small
  values (radius well under half the local thickness or they fail). "shell"
  hollows a solid into walls (open_face "top" makes cups/containers).
- "linear_pattern" repeats a body in a straight line (count, dx, dy, dz) — or a
  FEATURE of a body with "seed" plus "direction" [x, y, z], "distance" and
  "distance_type" ("spacing" between copies, or "extent" they all fit in);
  "count2" / "direction2" / "distance2" make it a grid.
- The final feature in the list is the part. It must be ONE watertight solid,
  so end with a fuse if you built separate pieces.
- Always include a spec with at least {{"n_solids": 1}}. Match spec strictness
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
(auto-closes; use path for profiles mixing straight edges and arcs);
mode "add" or "subtract"; first must be add).
A sketch_on_face has ONE input (the body) and params
{{"face":"top|bottom|+x|-x|+y|-y","offset":mm,"entities":[...]}} — same
entities, and offset is measured from that face along the axis in rule 2
(from "top" negative goes into the material; from "bottom" positive is the
height above it). Do NOT send face_center/face_normal; the named face is
resolved from the real geometry at every rebuild.
extrude params {{"amount":mm,"flip":false,"through":false,"both":false}}; revolve {{"axis":"Z",
"angle":360}} (draw the profile on XZ at positive X to revolve about Z). Sketch
features have no volume — only the extrude/revolve/loft result is a solid.
"""


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


def lint_tree(features) -> list[str]:
    """History-quality rules for AUTHORED trees (AI/MCP paths only — the
    manual UI records history naturally, one action per feature)."""
    problems = []
    sketches = [f for f in features if f.op == "sketch"]
    for f in sketches:
        n = len(f.params.get("entities") or [])
        if n > 10:
            problems.append(
                f"sketch '{f.id}' crams {n} entities into one feature — "
                f"split the artwork into logical sketches (one per design "
                f"element, each with its own extrude, fused/cut together)")
    if len(features) == 2 and len(sketches) == 1:
        n = len(sketches[0].params.get("entities") or [])
        if n > 4:
            problems.append(
                f"the whole design is ONE sketch ({n} entities) + one "
                f"consumer — that is a blob, not a design history. Record "
                f"it as steps: base_sketch -> base_extrude, then each "
                f"element as its own sketch -> extrude, fused or cut")
    # THE OFFSET METHOD (user mandate 2026-08-27). Once a body exists, a
    # sketch floating at an absolute Z is the banned old habit: it hardcodes
    # the base thickness into every downstream feature, so 251 of the 274
    # sketches authored before this rule broke the moment a base dimension
    # changed. face+offset is exactly as expressive (any Z is reachable as an
    # offset from a face) and it rides the geometry — so there is no
    # legitimate reason left to write the absolute form.
    import sketch as _sk
    body_yet = False
    for f in features:
        if f.op == "sketch" and body_yet and float(f.params.get("offset") or 0):
            problems.append(
                f"sketch '{f.id}' floats at absolute Z (offset "
                f"{f.params['offset']}) even though a body already exists — "
                f"that hardcodes the base thickness and breaks the moment it "
                f"changes. Use sketch_on_face on the current body instead: "
                f'{{"face":"top","offset":<depth from that face, negative = '
                f'into the material>}}, then extrude with flip/through and '
                f"cut or fuse")
        if f.op not in _sk.SKETCH_PRODUCERS:
            body_yet = True
    generic = [f.id for f in features if _GENERIC_ID.match(f.id)]
    if generic:
        problems.append(
            f"ids {generic} are meaningless — name features after what "
            f"they ARE (base_plate, web_sketch, eye_cut...)")
    return problems


def _to_document(data: dict) -> Document:
    """Validate + construct. Raises ValueError with a diagnostic message."""
    if not isinstance(data.get("features"), list) or not data["features"]:
        raise ValueError("JSON must contain a non-empty 'features' list")
    doc = Document(name=str(data.get("name", "untitled"))[:60])
    for f in data["features"]:
        doc.add(f["id"], f["op"], f.get("params") or {}, f.get("inputs") or [],
                strict=True)          # a hallucinated key is named, not stored
    lint = lint_tree(doc.features)
    if lint:
        raise ValueError("history lint: " + "; ".join(lint))
    spec = data.get("spec") or {}
    known = {"size", "volume", "holes", "n_solids", "symmetry", "tip_radius",
             "com", "require_manifold", "tol", "vol_tol"}
    doc.spec = {k: v for k, v in spec.items() if k in known}
    if doc.spec.get("holes"):
        try:
            doc.spec["holes"] = {float(k): int(v)
                                 for k, v in doc.spec["holes"].items()}
        except (TypeError, ValueError):
            raise ValueError(
                'spec "holes" keys must be NUMERIC radii in mm, e.g. '
                '{"5": 1} for one 5mm-radius hole — not placeholder words')
    if "symmetry" in doc.spec:
        s = doc.spec["symmetry"]
        if not isinstance(s, int) or isinstance(s, bool) or not 2 <= s <= 64:
            raise ValueError(
                'spec "symmetry" must be an INTEGER 2..64 counting discrete '
                'features around Z (blade count, bolt count). OMIT it entirely '
                'for axisymmetric/revolved parts — never "infinite"')
    return doc


def author_design(prompt: str, model, max_attempts: int = 4):
    """Returns (Document | None, transcript: list[str])."""
    messages = [{"role": "system", "content": AUTHOR_PROMPT},
                {"role": "user", "content": prompt}]
    transcript: list[str] = []

    for attempt in range(1, max_attempts + 1):
        raw = model.generate(messages)
        messages.append({"role": "assistant", "content": raw})

        # gate 1: is it valid JSON referencing only legal ops?
        try:
            doc = _to_document(_parse(raw))
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            transcript.append(f"attempt {attempt}: invalid tree — {e}")
            messages.append({"role": "user", "content":
                f"That was rejected before building: {e}\n"
                "Return corrected JSON only."})
            continue

        # gate 2 + 3: geometry health per node, spec verification
        ok = doc.rebuild()
        if ok:
            transcript.append(f"attempt {attempt}: PASS")
            return doc, transcript

        problems = []
        for f in doc.features:
            problems += [f"[{f.id}] {p}" for p in f.problems]
        problems += [f"[spec] {p}" for p in doc.spec_problems]
        transcript.append(f"attempt {attempt}: " + "; ".join(problems))
        messages.append({"role": "user", "content":
            "The tree built with these problems:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\nFix the tree. Return corrected JSON only."})

    return None, transcript


# ---------------------------------------------------------------------------
# Self-test with a fake model — proves validation + repair without an API key
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    class FakeAuthor:
        """Emits a bad tree (unknown op) first, then a correct washer."""
        def __init__(self):
            self.calls = 0
        def generate(self, messages):
            self.calls += 1
            if self.calls == 1:
                return json.dumps({"name": "washer", "features": [
                    {"id": "body", "op": "torus", "params": {"r": 20}}]})
            return json.dumps({
                "name": "washer-40",
                "features": [
                    {"id": "body", "op": "disc",
                     "params": {"radius": 20, "thickness": 4}},
                    {"id": "hole", "op": "with_center_hole",
                     "params": {"radius": 10}, "inputs": ["body"]},
                ],
                "spec": {"n_solids": 1, "holes": {"10": 1}, "tol": 0.5},
            })

    doc, transcript = author_design("a washer, 40mm outer, 20mm hole, 4mm thick",
                                    FakeAuthor())
    print("\n".join(transcript))
    assert doc is not None, "authoring failed"
    print(doc.tree())
    print("volume:", doc.get("hole").volume)
