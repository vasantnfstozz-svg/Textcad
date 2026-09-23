"""PROBE - review of Sweep (36ee69c), 2026-09-23: WHERE does the kernel turn
the profile? The module comment says "the kernel moves the path so its START
sits at the profile's CENTRE". The ring in sweep_review_probe.py section E
came out 1.45 % heavy on a bend, exactly what a path through the ring's BOX
centre (not its centroid) gives. So: sweep one profile along the same bent
path started at different points ON the profile's plane and read where the
solid goes and how much of it there is.

Run: python probes/memcap.py --gb 4 --timeout 600 -- python probes/sweep_pivot_probe.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d            # noqa: E402

import sketch as sk                # noqa: E402

RIGHT = b3d.Transition.RIGHT


def bend(start, R=10.0, up=10.0, run=10.0):
    x0, y0 = start
    mid = (x0 + R - R * math.cos(math.radians(45)), y0, up + R * math.sin(math.radians(45)))
    return b3d.Wire([b3d.Line((x0, y0, 0), (x0, y0, up)),
                     b3d.ThreePointArc((x0, y0, up), mid, (x0 + R, y0, up + R)),
                     b3d.Line((x0 + R, y0, up + R), (x0 + R + run, y0, up + R))])


sq = (b3d.Plane.XY * b3d.Rectangle(4, 4)).faces()
for start in ((0, 0), (1.5, 0), (-1.5, 0), (0, 1.5), (5, 0), (-5, 0)):
    w = bend(start)
    out = b3d.sweep(b3d.Sketch(children=list(sq)), path=w, transition=RIGHT)
    bb = out.bounding_box()
    al = 16 * w.length
    print(f"square 4x4, path starts at {start}: vol {out.volume:9.3f}  A*L {al:9.3f} "
          f"ratio {out.volume / al:.4f}  valid {out.is_valid}  "
          f"bbox x {bb.min.X:7.2f}..{bb.max.X:7.2f} z {bb.min.Z:6.2f}..{bb.max.Z:6.2f}")
    try:
        sk._sweep_solid(list(sq), w, 0, True)
        print("      op: builds")
    except ValueError as e:
        print("      op:", str(e)[:120])

print("-- a bend TIGHTER than the square's half-width from an off-centre start")
for start, R in (((1.5, 0), 2.5), ((-1.5, 0), 2.5), ((0, 0), 2.5)):
    w = bend(start, R=R)
    out = b3d.sweep(b3d.Sketch(children=list(sq)), path=w, transition=RIGHT)
    print(f"   start {start} R {R}: vol {out.volume:.3f} A*L {16 * w.length:.3f} valid {out.is_valid}")
    try:
        sk._sweep_solid(list(sq), w, 0, True)
        print("      op: builds")
    except ValueError as e:
        print("      op:", str(e)[:120])

print("-- the dangerous half: a fold the guards cannot see when the pivot is off-centre")
from OCP.BOPAlgo import BOPAlgo_CheckerSI            # noqa: E402
from OCP.TopTools import TopTools_ListOfShape        # noqa: E402


def self_hits(solid) -> bool:
    chk = BOPAlgo_CheckerSI()
    lst = TopTools_ListOfShape()
    lst.Append(solid.wrapped)
    chk.SetArguments(lst)
    chk.SetRunParallel(False)
    chk.Perform()
    return chk.HasErrors()


def arc_path(start, R, deg, up=10.0, run=50.0):
    """up +Z from `start`, an arc of `deg` degrees and radius R turning toward
    +X, then a straight run along the new tangent."""
    x0, y0 = start
    t = math.radians(deg)
    cx, cz = x0 + R, up
    end = (cx - R * math.cos(t), y0, cz + R * math.sin(t))
    mid = (cx - R * math.cos(t / 2), y0, cz + R * math.sin(t / 2))
    tan = (math.sin(t), 0, math.cos(t))
    far = (end[0] + run * tan[0], y0, end[2] + run * tan[2])
    return b3d.Wire([b3d.Line((x0, y0, 0), (x0, y0, up)),
                     b3d.ThreePointArc((x0, y0, up), mid, end),
                     b3d.Line(end, far)])


for start, R, deg in (((0, 0), 2.9, 30), ((-1, 0), 2.9, 30), ((-1, 0), 2.9, 60),
                      ((-1.5, 0), 3.2, 20), ((-1, 0), 4.0, 30)):
    w = arc_path(start, R, deg)
    out = b3d.sweep(b3d.Sketch(children=list(sq)), path=w, transition=RIGHT)
    try:
        sk._sweep_solid(list(sq), w, 0, True)
        op = "BUILDS"
    except ValueError as e:
        op = "refuses: " + str(e)[:70]
    print(f"   start {start} R {R} arc {deg}: valid {out.is_valid} self-intersects "
          f"{self_hits(out)} ratio {out.volume / (16 * w.length):.4f}  op {op}")

print("-- the same with a CIRCLE r2 (the profile whose fold OCCT calls valid)")
circ = (b3d.Plane.XY * b3d.Circle(2)).faces()
area = circ[0].area
for start, R, deg in (((0, 0), 2.5, 30), ((-1, 0), 2.5, 30), ((-1, 0), 2.5, 90),
                      ((-0.8, 0), 2.3, 45), ((-1, 0), 3.5, 90)):
    w = arc_path(start, R, deg)
    out = b3d.sweep(b3d.Sketch(children=list(circ)), path=w, transition=RIGHT)
    try:
        sk._sweep_solid(list(circ), w, 0, True)
        op = "BUILDS"
    except ValueError as e:
        op = "refuses: " + str(e)[:70]
    print(f"   start {start} R {R} arc {deg}: valid {out.is_valid} self-intersects "
          f"{self_hits(out)} ratio {out.volume / (area * w.length):.4f}  op {op}")
