"""Is _project_wire's polygon ORDERED (so a shoelace centroid is safe), and how
far is _limits' sample-average centre from the profile's real centre?"""
import math
import os
import sys

os.environ.setdefault("TEXTCAD_NO_BROWSER", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sketch as sk                                  # noqa: E402
import toolplan                                      # noqa: E402
from document import Document                        # noqa: E402


def build(*feats):
    d = Document(name="probe")
    for fid, op, params, inputs in feats:
        d.add(fid, op, params, inputs)
    d.rebuild()
    return d


def shoelace(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


CASES = [
    ("circle r10", [{"kind": "circle", "r": 10}]),
    ("rect 30x20", [{"kind": "rectangle", "w": 30, "h": 20}]),
    ("ring 15/5", [{"kind": "circle", "r": 15},
                   {"kind": "circle", "r": 5, "mode": "subtract"}]),
    ("hex r12", [{"kind": "regular_polygon", "radius": 12, "sides": 6}]),
    ("slot", [{"kind": "slot", "length": 40, "height": 10}]),
    ("ellipse", [{"kind": "ellipse", "rx": 20, "ry": 8}]),
    ("two islands", [{"kind": "circle", "r": 10, "x": -20},
                     {"kind": "rectangle", "w": 20, "h": 20, "x": 20}]),
    ("L polygon", [{"kind": "polygon", "points": [[0, 0], [40, 0], [40, 10],
                                              [10, 10], [10, 30], [0, 30]]}]),
]

print(f"{'case':14s} {'faces':>5s} {'|shoelace|':>12s} {'face.area':>12s} "
      f"{'err':>10s}  sample-centre -> area-centre (mm apart)")
pl = sk.sketch_plane("XY", 0)
for name, ents in CASES:
    try:
        d = build(("s", "sketch", {"plane": "XY", "entities": ents}, []))
        prof = d._parts["s"]
        assert prof is not None, d.features[0].problems
    except Exception as e:                                    # noqa: BLE001
        print(f"{name:14s} SKIPPED ({type(e).__name__}: {e})")
        continue
    faces = list(prof.faces())
    loops = toolplan._loops(faces, pl)
    poly = 0.0
    for L in loops:
        poly += abs(shoelace(L["outer"]))
        for h in L["holes"]:
            poly -= abs(shoelace(h))
    real = sum(f.area for f in faces)
    lim, centre = toolplan._limits(loops)
    # the honest centre: the kernel's own area centroid of the faces
    ax = ay = tot = 0.0
    for f in faces:
        c = pl.to_local_coords(f.center())
        ax += f.area * c.X
        ay += f.area * c.Y
        tot += f.area
    ax, ay = ax / tot, ay / tot
    gap = math.hypot(centre[0] - ax, centre[1] - ay) if centre else float("nan")
    print(f"{name:14s} {len(faces):5d} {poly:12.4f} {real:12.4f} "
          f"{abs(poly - real) / real * 100:9.4f}%  "
          f"({centre[0]:7.3f},{centre[1]:7.3f}) -> ({ax:7.3f},{ay:7.3f})  {gap:7.3f}")

print("\nA BODY FACE (extrude_face mode uses picked.center(), not this centre):")
d = build(("t", "tube", {"outer_radius": 30, "inner_radius": 10,
                         "height": 20}, []))
part = d._parts["t"]
for fc in part.faces():
    p = sk.face_plane(fc)
    if p is not None and abs(p.z_dir.Z - 1) < 1e-6:
        loops = toolplan._loops([fc], p)
        poly = abs(shoelace(loops[0]["outer"])) - sum(
            abs(shoelace(h)) for h in loops[0]["holes"])
        print(f"  annulus top: shoelace {poly:.4f} vs face.area {fc.area:.4f} "
              f"({abs(poly - fc.area) / fc.area * 100:.4f}%)")
        break
