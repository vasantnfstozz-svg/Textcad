"""probes/s10_r3_numeric_door_remeasure.py — round THREE re-measures round two's
numeric door on CURRENT master, after Named parameters landed.

Round two (26be9e3) closed 14 raw-Python messages across 7 ops by refusing a
non-number in a numeric parameter at rebuild. Named parameters (127f350) then
rewrote the same code path: `_check_numeric_params` grew a `values` argument and
a FORMULA branch, and `Document._resolved` now evaluates any string in a numeric
parameter through `paramexpr`. This probe puts the SAME 14 doors plus the new
formula doors to a real rebuild and prints what the feature row says.

A row is RAW when the sentence carries Python's own words (TypeError,
"could not convert", "unsupported operand", "not iterable", "unhashable",
"object is not", "argument must be", "cannot use", "invalid literal").

Run:  C:\\Python314\\python.exe probes\\s10_r3_numeric_door_remeasure.py
"""
import sys

sys.path.insert(0, ".")

from document import Document, CREATORS, MODIFIERS   # noqa: E402

ONE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]

BASE = {
    "plate": {"width": 20, "depth": 20, "thickness": 5},
    "disc": {"radius": 10, "thickness": 5},
    "ball": {"radius": 10},
    "cone": {"bottom_radius": 10, "top_radius": 5, "height": 10},
    "tube": {"outer_radius": 10, "inner_radius": 5, "height": 10},
    "polygon_plate": {"sides": 6, "circumradius": 10, "thickness": 5},
    "hex_plate": {"across_flats": 20, "thickness": 5},
    "sketch": {"entities": ONE, "plane": "XY", "offset": 0.0},
    "with_center_hole": {"radius": 2},
    "with_bolt_circle": {"count": 4, "bolt_radius": 1, "pitch_circle_dia": 14},
    "fillet": {"radius": 1, "edges": "all"},
    "chamfer": {"length": 1, "edges": "all"},
    "shell": {"thickness": 1},
    "scale": {"factor": 2},
    "rotate": {"axis": "Z", "angle_deg": 45},
    "polar_pattern": {"count": 3, "axis": "+z"},
    "linear_pattern": {"count": 3, "dx": 20},
    "hole": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
             "diameter": 3, "depth": 2},
    "extrude_face": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                     "amount": 3},
    "revolve_face": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                     "axis": [[-5, -5], [5, -5]], "angle": 90},
    "sketch_on_face": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                       "entities": ONE, "offset": 0.0},
    "extrude": {"amount": 4},
    "revolve": {"axis": "Z", "angle": 180},
    "move": {"x": 1, "y": 2, "z": 3},
}
SKETCH_FED = {"extrude", "revolve"}

RAW_WORDS = ("TypeError", "could not convert", "unsupported operand",
             "is not iterable", "unhashable", "object is not",
             "argument must be", "cannot use", "invalid literal",
             "not enough values", "too many values", "object has no attribute",
             "NoneType", "'str' object", "'int' object", "'bool' object",
             "not supported between", "takes no arguments", "IndexError",
             "KeyError", "AttributeError", "ZeroDivisionError")


def build(op, params, params_doc=None):
    d = Document(name="n")
    for nm, ex in (params_doc or {}).items():
        d.set_parameter(nm, ex)
    if op in CREATORS:
        d.add("p1", op, params, [])
    elif op in SKETCH_FED:
        d.add("s1", "sketch", {"entities": [{"kind": "rectangle", "x": 8,
                                             "y": 0, "w": 6, "h": 6,
                                             "mode": "add"}],
                               "plane": "XZ", "offset": 0.0}, [])
        d.add("p1", op, params, ["s1"])
    else:
        d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
        d.add("p1", op, params, ["b1"])
    try:
        d.rebuild()
    except Exception as e:
        return f"RAISED {type(e).__name__}: {e}"
    f = d.get("p1")
    return f"{f.status:7s} vol={f.volume} :: " + " | ".join(f.problems or [])


def classify(out):
    if out.startswith("ok"):
        return "BLD"
    if any(w in out for w in RAW_WORDS):
        return "RAW"
    return "   "


BADS = [None, "", "   ", "8mm", True, [1, 2], {"a": 1},
        "1/0", "wall*2", "sqrt(-1)", "0-9999999999", "-5", "1e400"]

if __name__ == "__main__":
    ops = [o for o in BASE if o in CREATORS or o in MODIFIERS or o == "move"]
    raw = blds = sentences = 0
    raws = []
    for op in ops:
        base = BASE[op]
        print(f"\n{op}  BASELINE -> {build(op, base)}")
        for k in sorted(Document.numeric_params(op)):
            if k not in base:
                continue
            for bad in BADS:
                out = build(op, {**base, k: bad})
                tag = classify(out)
                if tag == "RAW":
                    raw += 1
                    raws.append((op, k, bad, out))
                elif tag == "BLD":
                    blds += 1
                else:
                    sentences += 1
                print(f"  {tag} {k}={bad!r:14s} -> {out[:150]}")
    print(f"\nRAW Python: {raw}   builds anyway: {blds}   a sentence: {sentences}")
    for op, k, bad, out in raws:
        print(f"  RAW  {op}.{k} = {bad!r} -> {out[:160]}")
