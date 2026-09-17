"""probes/s10_numeric_null_door.py — every NUMERIC parameter of every op set to
null and to "", measured through a real rebuild.

The §10 row names `extrude {"amount": null}` and `{"amount": ""}`. Before a
rebuild-time check is written, the whole door is measured: which ops already
answer with a sentence, which leak raw Python, and — the half that decides how
wide the check may be — which ops BUILD anyway, because refusing those would
take away work that is correct today.

`move` is measured too: `document._move_offsets` reads None as 0 ON PURPOSE
(the comment says so), so the check must leave `move` alone.

Run:  C:\\Python314\\python.exe probes\\s10_numeric_null_door.py
"""
import sys

sys.path.insert(0, ".")

from document import Document, CREATORS, MODIFIERS   # noqa: E402

ONE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]

BASE = {
    # creators
    "plate": {"width": 20, "depth": 20, "thickness": 5},
    "disc": {"radius": 10, "thickness": 5},
    "ball": {"radius": 10},
    "cone": {"bottom_radius": 10, "top_radius": 5, "height": 10},
    "tube": {"outer_radius": 10, "inner_radius": 5, "height": 10},
    "polygon_plate": {"sides": 6, "circumradius": 10, "thickness": 5},
    "hex_plate": {"across_flats": 20, "thickness": 5},
    "sketch": {"entities": ONE, "plane": "XY", "offset": 0.0},
    # modifiers on a solid
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
    # modifiers on a sketch
    "extrude": {"amount": 4},
    "revolve": {"axis": "Z", "angle": 180},
    "move": {"x": 1, "y": 2, "z": 3},
}
SKETCH_FED = {"extrude", "revolve"}


def build(op, params):
    d = Document(name="n")
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


ops = [o for o in BASE if o in CREATORS or o in MODIFIERS or o == "move"]
leaks = builds = sentences = 0
for op in ops:
    base = BASE[op]
    # the baseline must itself be sound, or nothing below means anything
    ok = build(op, base)
    print(f"\n{op}  BASELINE -> {ok}")
    for k in sorted(Document.numeric_params(op)):
        if k not in base:
            continue
        for bad in (None, ""):
            out = build(op, {**base, k: bad})
            tag = "   "
            if out.startswith("ok"):
                tag = "BLD"
                builds += 1
            elif ("TypeError" in out or "could not convert" in out
                  or "not supported between" in out):
                tag = "RAW"
                leaks += 1
            else:
                sentences += 1
            print(f"  {tag} {k}={bad!r:5s} -> {out}")

print(f"\nraw Python: {leaks}   builds anyway: {builds}   a sentence: {sentences}")
