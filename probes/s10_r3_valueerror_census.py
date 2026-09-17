"""probes/s10_r3_valueerror_census.py — what a FOREIGN FILE can make the feature
row say, over EVERY parameter of EVERY op.

`blocks.plain_cause` passes a bare `ValueError` through verbatim, on the
assumption that a ValueError came from our own code and is therefore already a
sentence. `Document.add(strict=False)` opens a design written by another build,
so a parameter can hold anything at all by the time the rebuild unpacks it.
This probe measures the assumption: every parameter of every op gets each
hostile value in turn, and the resulting feature row is classified —

  PY      the row carries PYTHON's own words (a Python fact, not a thing to change)
  BLD     the feature BUILT anyway (a silent answer to a value nobody meant)
  ok      a sentence

Read-only: nothing is saved, no design in `designs/` is touched.

Run:  C:\\Python314\\python.exe probes\\s10_r3_valueerror_census.py
"""
import sys

sys.path.insert(0, ".")

from document import Document, CREATORS, MODIFIERS   # noqa: E402

ONE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
RECT = [{"kind": "rectangle", "x": 8, "y": 0, "w": 6, "h": 6, "mode": "add"}]

BASE = {
    "plate": {"width": 20, "depth": 20, "thickness": 5},
    "disc": {"radius": 10, "thickness": 5},
    "ball": {"radius": 10},
    "cone": {"bottom_radius": 10, "top_radius": 5, "height": 10},
    "tube": {"outer_radius": 10, "inner_radius": 5, "height": 10},
    "polygon_plate": {"sides": 6, "circumradius": 10, "thickness": 5},
    "hex_plate": {"across_flats": 20, "thickness": 5},
    "revolve_profile": {"points": [[0, 0], [5, 0], [5, 5], [0, 5]]},
    "curved_blade": {"inner_radius": 5, "outer_radius": 12,
                     "inlet_angle_deg": 30, "exit_angle_deg": 50,
                     "height": 6, "thickness": 1.5},
    "sketch": {"entities": ONE, "plane": "XY", "offset": 0.0},
    "with_center_hole": {"radius": 2},
    "with_bolt_circle": {"count": 4, "bolt_radius": 1, "pitch_circle_dia": 14},
    "fillet": {"radius": 1, "edges": "all"},
    "chamfer": {"length": 1, "edges": "all"},
    "shell": {"thickness": 1, "direction": "inside"},
    "scale": {"factor": 2},
    "rotate": {"axis": "Z", "angle_deg": 45, "pivot": None},
    "polar_pattern": {"count": 3, "axis": "+z", "angle": 360.0},
    "linear_pattern": {"count": 3, "dx": 20, "distance_type": "spacing"},
    "mirror": {"plane": "YZ"},
    "hole": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
             "diameter": 3, "depth": 2, "at": [0, 0], "kind": "simple"},
    "extrude_face": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                     "amount": 3},
    "revolve_face": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                     "axis": [[-9, -9], [-9, 9]], "angle": 90},
    "sketch_on_face": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                       "entities": ONE, "offset": 0.0},
    "extrude": {"amount": 4},
    "revolve": {"axis": "Z", "angle": 180},
    "move": {"x": 1, "y": 2, "z": 3},
}
SKETCH_FED = {"extrude", "revolve", "sweep"}

BADS = [None, "", "abc", True, 0, [1, 2], {"a": 1}, [], [[1, 2]]]

PY_WORDS = ("TypeError", "could not convert", "unsupported operand",
            "is not iterable", "unhashable", "object is not",
            "argument must be", "cannot use", "invalid literal",
            "not enough values", "too many values", "object has no attribute",
            "NoneType", "not supported between", "ZeroDivisionError",
            "IndexError", "KeyError", "AttributeError", "list index",
            "string indices", "must be str", "takes no", "positional argument",
            "'float' object", "'int' object", "'str' object", "'bool' object",
            "'list' object", "'dict' object", "Traceback")


def build(op, params):
    d = Document(name="n")
    if op in CREATORS:
        d.add("p1", op, params, [])
    elif op in SKETCH_FED:
        d.add("s1", "sketch", {"entities": RECT, "plane": "XZ", "offset": 0.0}, [])
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


if __name__ == "__main__":
    ops = [o for o in BASE if o in CREATORS or o in MODIFIERS or o == "move"]
    py, bld, sent = 0, 0, 0
    pys, blds = [], []
    for op in ops:
        base = BASE[op]
        good = build(op, base)
        if not good.startswith("ok"):
            print(f"!! {op} BASELINE NOT OK -> {good[:120]}")
        for k in base:
            for bad in BADS:
                out = build(op, {**base, k: bad})
                if any(w in out for w in PY_WORDS):
                    py += 1
                    pys.append((op, k, bad, out))
                elif out.startswith("ok"):
                    bld += 1
                    blds.append((op, k, bad, out))
                else:
                    sent += 1
    print(f"\nPYTHON in the row: {py}   built anyway: {bld}   a sentence: {sent}")
    print("\n--- PYTHON ---")
    for op, k, bad, out in pys:
        print(f"  {op}.{k} = {bad!r:10s} -> {out[:130]}")
    print("\n--- BUILT ANYWAY ---")
    for op, k, bad, out in blds:
        print(f"  {op}.{k} = {bad!r:10s} -> {out[:110]}")
