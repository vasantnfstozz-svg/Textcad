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
import inspect
import json
import re

import document
from document import Document, CREATORS, MODIFIERS


# ---------------------------------------------------------------------------
# The op catalog shown to the model (and to the UI's Add Feature dialog)
# ---------------------------------------------------------------------------

def op_catalog() -> list[dict]:
    """Machine-readable list of every legal operation and its parameters."""
    cat = []
    for name, fn in CREATORS.items():
        params = [{"name": p.name,
                   "default": (None if p.default is inspect._empty else p.default)}
                  for p in inspect.signature(fn).parameters.values()]
        cat.append({"op": name, "kind": "creator", "inputs": 0, "params": params})
    for name, fn in MODIFIERS.items():
        sig = list(inspect.signature(fn).parameters.values())[1:]  # skip part
        params = [{"name": p.name,
                   "default": (None if p.default is inspect._empty else p.default)}
                  for p in sig]
        cat.append({"op": name, "kind": "modifier", "inputs": 1, "params": params})
    cat.append({"op": "move", "kind": "modifier", "inputs": 1,
                "params": [{"name": "x", "default": 0},
                           {"name": "y", "default": 0},
                           {"name": "z", "default": 0}]})
    from document import COMBINERS
    for name in COMBINERS:
        cat.append({"op": name, "kind": "combiner", "inputs": 2, "params": []})
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
  fuse with a body MUST physically overlap it (touching is not enough).
- "rotate" orients parts: cylinders are upright by default — a WHEEL or axle is
  rotate(axis "X" or "Y", 90). "mirror" returns the mirrored COPY (fuse it with
  the original for symmetric pairs, e.g. left/right fenders).
- "fillet"/"chamfer" round or bevel edges ("all"/"top"/"bottom") — use small
  values (radius well under half the local thickness or they fail). "shell"
  hollows a solid into walls (open_face "top" makes cups/containers).
- "linear_pattern" repeats a feature in a straight line (count, dx, dy, dz).
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
DESIGN FOR EDITABILITY (critical — the tree IS the product, not just the
solid; the user will open it in a CAD feature tree and edit it):
- DECOMPOSE the part into its natural engineering features, one per node,
  with meaningful ids: a water bottle is body + shoulder + neck + lip +
  inner cavity (cut), NOT one giant profile. A bracket is base_plate +
  ribs + each hole group. 5-12 features is typical; 1-2 features for a
  non-trivial part is WRONG.
- Every dimension the user might want to change (diameters, heights, wall
  thickness, counts, angles) must appear as a NUMERIC param on some feature.
  Hollow containers: build the outer solid, then CUT a scaled inner solid —
  so wall thickness is controlled by the difference in their params.
- revolve_profile is for genuinely curved/contoured sections only; where a
  section is a simple cylinder or ring, use disc/tube instead (their radius/
  thickness params are directly editable; buried profile points are not).

SKETCH WORKFLOW (for shapes the primitives don't cover): make a "sketch"
feature (a creator), then a "extrude"/"revolve"/"sweep" feature consuming it,
or "loft" consuming two sketches. A sketch's params are
{{"plane":"XY|XZ|YZ", "offset":mm, "entities":[...]}} where each entity is
{{"kind":"rectangle","w":..,"h":..,"x":0,"y":0,"mode":"add"}} (kinds:
rectangle w/h, circle r, ellipse rx/ry, slot length/height, regular_polygon
radius/sides, polygon points[[x,y]...]; mode "add" or "subtract"; first must be
add). extrude params {{"amount":mm,"both":false}}; revolve {{"axis":"Z",
"angle":360}} (draw the profile on XZ at positive X to revolve about Z). Sketch
features have no volume — only the extrude/revolve/loft result is a solid.
"""


# ---------------------------------------------------------------------------
# Author -> validate -> rebuild -> verify -> repair loop
# ---------------------------------------------------------------------------

def _parse(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(raw)


def _to_document(data: dict) -> Document:
    """Validate + construct. Raises ValueError with a diagnostic message."""
    if not isinstance(data.get("features"), list) or not data["features"]:
        raise ValueError("JSON must contain a non-empty 'features' list")
    doc = Document(name=str(data.get("name", "untitled"))[:60])
    for f in data["features"]:
        doc.add(f["id"], f["op"], f.get("params") or {}, f.get("inputs") or [])
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
