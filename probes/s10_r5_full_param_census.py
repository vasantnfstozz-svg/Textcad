r"""Round FIVE, part 5: the parameters round four's census never reached.

probes/s10_r4_census.py walks `for k in base` -- the keys its own BASE dict
sets up for each op, not every parameter the op HAS. So `mirror`'s `seed` and
`join`, `linear_pattern`'s eight extra placement parameters, `sweep`'s
`distance` / `path_points` / `smooth`, `shell`'s `open_face`, and every other
parameter left at its default were never fed a hostile value. Round four's own
P0 (`move {"x": true}` sliding the body 1 mm, green) was in a key BASE did
set; this asks the same question of the ones it did not.

Every parameter of every op that takes one, nine hostile values each, through
a real rebuild. Read-only: nothing in designs/ is touched.

Run: C:\Python314\python.exe probes/s10_r5_full_param_census.py
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blocks                                                      # noqa: E402
from document import (CREATORS, MODIFIERS, Document,               # noqa: E402
                      op_params)

ONE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
RECT = [{"kind": "rectangle", "x": 8, "y": 0, "w": 6, "h": 6, "mode": "add"}]
RAIL = [{"kind": "path", "closed": False, "start": [0, 0],
         "segments": [{"kind": "line", "to": [0, 20]}]}]

# the same wiring as round four's census, so the two tables are comparable
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
    rows = 0
    py, bld, swallowed, sent = 0, 0, 0, 0
    pys, blds, swal = [], [], []
    for op in ops:
        base = BASE[op]
        good = build(op, base)
        if not good.startswith("ok") and op not in FILE_OPS:
            print(f"!! {op} BASELINE NOT OK -> {good[:130]}")
        # EVERY parameter the op takes, not only the ones BASE sets
        every = [n for n, d in op_params(op)]
        for k in every:
            was_default = k not in base
            for bad in BADS:
                out = build(op, {**base, k: bad})
                rows += 1
                tag = "DEFAULT" if was_default else "base   "
                if any(w in out for w in PY_WORDS):
                    py += 1
                    pys.append((tag, op, k, bad, out))
                elif blocks.NOT_A_SENTENCE in out:
                    swallowed += 1
                    swal.append((tag, op, k, bad, out))
                elif out.startswith("ok"):
                    bld += 1
                    blds.append((tag, op, k, bad, out, good))
                else:
                    sent += 1
    print(f"\n{rows} rows over {len(ops)} ops")
    print(f"PYTHON in the row: {py}   swallowed: {swallowed}   "
          f"built anyway: {bld}   a sentence: {sent}")
    print("\n--- PYTHON ---")
    for tag, op, k, bad, out in pys:
        print(f"  [{tag}] {op}.{k} = {bad!r:10s} -> {out[:130]}")
    print("\n--- SWALLOWED ---")
    for tag, op, k, bad, out in swal:
        print(f"  [{tag}] {op}.{k} = {bad!r:10s} -> {out[:130]}")
    print("\n--- BUILT ANYWAY, and the volume MOVED (the silent class) ---")
    for tag, op, k, bad, out, good in blds:
        mine = out.split("::")[0].strip()
        theirs = good.split("::")[0].strip()
        if mine != theirs:
            print(f"  [{tag}] {op}.{k} = {bad!r:10s} -> {mine}   "
                  f"(default builds {theirs})")
    print("\n--- BUILT ANYWAY, same volume as the default ---")
    for tag, op, k, bad, out, good in blds:
        mine = out.split("::")[0].strip()
        theirs = good.split("::")[0].strip()
        if mine == theirs:
            print(f"  [{tag}] {op}.{k} = {bad!r:10s} -> {mine}")
