"""Round FOUR: round three's census, confirmed independently AND widened.

probes/s10_r3_valueerror_census.py measured "114 rows of Python before, 14
after, and all 14 in sketch.py". Two things it did not do:

  * it walked 27 ops. Five of KNOWN_OPS were never in its table — `sweep`,
    `sweep_face` and `loft` (the Tier 2 tools, shipped INSIDE the range under
    review), and `import_stl` / `import_step`.
  * it classified a row as "a sentence" whenever it was not Python. Since
    round three, `plain_cause` can also SWALLOW a refusal and answer
    `blocks.NOT_A_SENTENCE`, which reads like a sentence and is not one —
    a row that must be counted separately.

Every op of KNOWN_OPS that takes parameters, every parameter, nine hostile
values, through a real rebuild. Read-only: nothing in designs/ is touched.

Run: C:\\Python314\\python.exe probes/s10_r4_census.py
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blocks                                                      # noqa: E402
from document import CREATORS, MODIFIERS, Document                 # noqa: E402

ONE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
RECT = [{"kind": "rectangle", "x": 8, "y": 0, "w": 6, "h": 6, "mode": "add"}]
RAIL = [{"kind": "path", "closed": False, "start": [0, 0],
         "segments": [{"kind": "line", "to": [0, 20]}]}]

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
    # --- NEW in round four: the five ops the round-three table never held ----
    "sweep": {"path": "rail", "full": True},
    "sweep_face": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                   "path": "rail", "full": True},
    "import_stl": {"file": "nowhere.stl", "scale": 1.0},
    "import_step": {"file": "nowhere.step", "scale": 1.0},
}
SKETCH_FED = {"extrude", "revolve", "sweep"}
NEEDS_RAIL = {"sweep", "sweep_face"}
FILE_OPS = {"import_stl", "import_step"}

BADS = [None, "", "abc", True, 0, [1, 2], {"a": 1}, [], [[1, 2]]]

PY_WORDS = ("TypeError", "could not convert", "unsupported operand",
            "is not iterable", "unhashable", "object is not",
            "argument must be", "cannot use", "invalid literal",
            "not enough values", "too many values", "object has no attribute",
            "NoneType", "not supported between", "ZeroDivisionError",
            "IndexError", "KeyError", "AttributeError", "list index",
            "string indices", "must be str", "takes no", "positional argument",
            "'float' object", "'int' object", "'str' object", "'bool' object",
            "'list' object", "'dict' object", "Traceback", "sequence item")


def build(op, params):
    d = Document(name="n")
    if op in NEEDS_RAIL:
        d.add("rail", "sketch", {"entities": RAIL, "plane": "XZ",
                                 "offset": 0.0}, [])
    if op in CREATORS:
        d.add("p1", op, params, [])
    elif op in SKETCH_FED:
        d.add("s1", "sketch", {"entities": RECT, "plane": "XY",
                               "offset": 0.0}, [])
        d.add("p1", op, params, ["s1"])
    else:
        d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
        d.add("p1", op, params, ["b1"])
    try:
        d.rebuild()
    except Exception as e:                                         # noqa: BLE001
        return "RAISED " + "".join(
            traceback.format_exception_only(type(e), e)).strip()
    f = d.get("p1")
    return f"{f.status:7s} vol={f.volume} :: " + " | ".join(f.problems or [])


if __name__ == "__main__":
    ops = [o for o in BASE if o in CREATORS or o in MODIFIERS or o == "move"]
    print(f"{len(ops)} ops, {len(BADS)} hostile values each\n")
    py, bld, swallowed, sent = 0, 0, 0, 0
    pys, blds, swal = [], [], []
    for op in ops:
        base = BASE[op]
        good = build(op, base)
        # an import of a file that is not there is SUPPOSED to be red
        if not good.startswith("ok") and op not in FILE_OPS:
            print(f"!! {op} BASELINE NOT OK -> {good[:130]}")
        for k in base:
            for bad in BADS:
                out = build(op, {**base, k: bad})
                if any(w in out for w in PY_WORDS):
                    py += 1
                    pys.append((op, k, bad, out))
                elif blocks.NOT_A_SENTENCE in out:
                    swallowed += 1
                    swal.append((op, k, bad, out))
                elif out.startswith("ok"):
                    bld += 1
                    blds.append((op, k, bad, out))
                else:
                    sent += 1
    print(f"\nPYTHON in the row: {py}   swallowed by plain_cause: {swallowed}"
          f"   built anyway: {bld}   a sentence: {sent}")
    print("\n--- PYTHON (the scoreboard) ---")
    for op, k, bad, out in pys:
        print(f"  {op}.{k} = {bad!r:10s} -> {out[:140]}")
    print("\n--- SWALLOWED (a refusal turned into the fallback line) ---")
    for op, k, bad, out in swal:
        print(f"  {op}.{k} = {bad!r:10s} -> {out[:140]}")
    print("\n--- BUILT ANYWAY ---")
    for op, k, bad, out in blds:
        print(f"  {op}.{k} = {bad!r:10s} -> {out[:120]}")
