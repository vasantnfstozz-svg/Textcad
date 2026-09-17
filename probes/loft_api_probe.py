"""Loft tool probe 1: what build123d's loft does with the sections a user can
actually pick — mismatched vertex counts, three sections smooth vs ruled,
coplanar, out-of-order along the axis, a tiny section, a tilted section, a
laterally offset section, a twisted rectangle — and what health says."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from build123d import loft  # noqa: E402

import inspector  # noqa: E402
import sketch as sk  # noqa: E402


def circ(z, r=5.0, x=0.0, plane="XY"):
    return sk.make_sketch(plane=plane, offset=z, entities=[{"kind": "circle", "r": r, "x": x, "mode": "add"}])


def rect(z, w=10.0, h=10.0, rot=0.0):
    return sk.make_sketch(plane="XY", offset=z, entities=[{"kind": "rectangle", "w": w, "h": h, "rotation": rot, "mode": "add"}])


def run(label, sections, expect=None, **kw):
    try:
        out = loft(list(sections), **kw)
        v = float(out.volume)
        h = inspector.health(out)
        ok = "" if expect is None else f"  expect~{expect:.1f} ratio {v / expect:.3f}"
        print(f"{label:38s} vol {v:10.3f}{ok}  solids {len(out.solids())}  health {h}")
        return out
    except Exception as e:
        print(f"{label:38s} EXC {type(e).__name__}: {str(e)[:70]}")


frustum = lambda r1, r2, h: math.pi * h / 3 * (r1 * r1 + r1 * r2 + r2 * r2)
run("cylinder r5 z0->z20", [circ(0), circ(20)], math.pi * 25 * 20)
run("cone r5->r2 z0->z20", [circ(0), circ(20, 2)], frustum(5, 2, 20))
run("circle -> rectangle 10x10", [circ(0), rect(20)], (math.pi * 25 + 100) / 2 * 20)
run("rect -> rect 90deg twist", [rect(0), rect(20, rot=90)], 100 * 20)
run("rect -> rect 45deg twist", [rect(0), rect(20, rot=45)], 100 * 20)
run("3 circles r5,r2,r5 smooth", [circ(0), circ(10, 2), circ(20)], 2 * frustum(5, 2, 10))
run("3 circles r5,r2,r5 ruled", [circ(0), circ(10, 2), circ(20)], 2 * frustum(5, 2, 10), ruled=True)
run("2 circles ruled==smooth?", [circ(0), circ(20)], math.pi * 25 * 20, ruled=True)
run("coplanar z0,z0", [circ(0), circ(0, 3)])
run("out of order z0,z20,z10", [circ(0), circ(20), circ(10, 2)], 2 * frustum(5, 2, 10))
run("out of order z0,z20,z10 ruled", [circ(0), circ(20), circ(10, 2)], 2 * frustum(5, 2, 10), ruled=True)
run("tiny top r0.01", [circ(0), circ(20, 0.01)], frustum(5, 0.01, 20))
run("tilted top 30deg (XZ-ish)", [circ(0), sk.make_sketch(plane="XY", offset=20, entities=[{"kind": "circle", "r": 5, "mode": "add"}]).rotate(sk.Axis.X, 30)], None)
run("lateral offset x40 z20", [circ(0), circ(20, x=40)], math.pi * 25 * 20)
run("lateral offset x40 z2 (nearly flat)", [circ(0), circ(2, x=40)], math.pi * 25 * 2)
run("section in YZ vs XY (perpendicular planes)", [circ(0), circ(20, plane="YZ")], None)
run("3 sections zigzag x0,x40,x0", [circ(0), circ(10, x=40), circ(20)], math.pi * 25 * 20)
run("same sketch twice", [circ(0), circ(0)])
