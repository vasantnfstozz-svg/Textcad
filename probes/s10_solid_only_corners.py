"""probes/s10_solid_only_corners.py — the hard half of the census.

A circle sketch has ONE edge and no corner, so "fillet does not fit" proves
nothing about a sketch the kernel COULD round in 2D. build123d's fillet and
chamfer are defined on a Sketch as well as a Part. Before any of these six ops
is called solid-only, each is put to a RECTANGLE sketch (four corners, plenty
of room) and to a sketch with area around a hole's position.

Run:  C:\\Python314\\python.exe probes\\s10_solid_only_corners.py
"""
import sys

sys.path.insert(0, ".")

from document import Document                       # noqa: E402

RECT = [{"kind": "rectangle", "x": 0, "y": 0, "w": 40, "h": 30, "mode": "add"}]
BIG_CIRCLE = [{"kind": "circle", "x": 0, "y": 0, "r": 20, "mode": "add"}]

CASES = [
    ("fillet", {"radius": 3, "edges": "all"}),
    ("fillet", {"radius": 0.5, "edges": "all"}),
    ("chamfer", {"length": 3, "edges": "all"}),
    ("chamfer", {"length": 0.5, "edges": "all"}),
    ("shell", {"thickness": 2}),
    ("shell", {"thickness": 0.5}),
    ("with_center_hole", {"radius": 5}),
    ("with_bolt_circle", {"count": 4, "bolt_radius": 1.5,
                          "pitch_circle_dia": 20}),
    ("hole", {"face_center": [0, 0, 0], "face_normal": [0, 0, 1],
              "diameter": 4, "depth": 2}),
    ("hole", {"face_center": [0, 0, 0], "face_normal": [0, 0, 1],
              "diameter": 4, "through": True}),
]

for entities, label in ((RECT, "rect 40x30"), (BIG_CIRCLE, "circle r20")):
    print("=" * 78)
    print(f"sketch: {label}")
    print("=" * 78)
    for op, params in CASES:
        d = Document(name="c")
        d.add("s1", "sketch", {"entities": entities, "plane": "XY",
                               "offset": 0.0}, [])
        d.add("p1", op, params, ["s1"])
        try:
            d.rebuild()
        except Exception as e:
            print(f"  {op:18s} {str(params)[:36]:38s} RAISED {type(e).__name__}: {e}")
            continue
        f = d.get("p1")
        print(f"  {op:18s} {str(params)[:36]:38s} -> {f.status:7s} vol={f.volume}")
        for pr in (f.problems or []):
            print(f"        {pr}")
    print()
