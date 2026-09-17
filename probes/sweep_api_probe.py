"""Sweep tool probe 1: build123d sweep of a circle along an open line+arc path
on a perpendicular plane; partial path by Wire.trim; transitions on a sharp
corner; a profile whose plane contains the path tangent (the degenerate case)."""
import math
from build123d import (BuildLine, BuildSketch, Circle, Line, ThreePointArc,
                       Plane, Transition, sweep, Wire, Vector, Rectangle)
from OCP.BRepCheck import BRepCheck_Analyzer

def ok(s):
    return BRepCheck_Analyzer(s.wrapped).IsValid()

# profile: circle r=3 on XY at origin
with BuildSketch(Plane.XY) as prof:
    Circle(3)
# path on XZ: up 20 along +Z then arc to +X then line 20 -> a bent pipe
with BuildLine(Plane.XZ) as pl:
    Line((0, 0), (0, 20))
    ThreePointArc((0, 20), (10 * (1 - math.cos(math.pi/4)), 20 + 10 * math.sin(math.pi/4)), (10, 30))
    Line((10, 30), (30, 30))
w = pl.wire()
print("path length", w.length, "start", w.start_point(), "tangent0", w.tangent_at(0))
p = sweep(prof.sketch, path=w)
A = math.pi * 9
print("full sweep vol", p.volume, "A*L", A * w.length, "valid", ok(p), "solids", len(p.solids()))
# partial: trim the wire
for frac in (0.25, 0.5, 0.75):
    t = w.trim(0, frac)
    print("trim", frac, "len", t.length, "of", w.length, "start", t.start_point())
    q = sweep(prof.sketch, path=t)
    print("   vol", q.volume, "A*len", A * t.length, "valid", ok(q))
# sharp corner polyline, three transitions
with BuildLine(Plane.XZ) as pl2:
    Line((0, 0), (0, 20))
    Line((0, 20), (20, 20))
w2 = pl2.wire()
for tr in (Transition.TRANSFORMED, Transition.RIGHT, Transition.ROUND):
    try:
        q = sweep(prof.sketch, path=w2, transition=tr)
        print("corner", tr, "vol", q.volume, "A*L", A * w2.length, "valid", ok(q), "solids", len(q.solids()))
    except Exception as e:
        print("corner", tr, "EXC", type(e).__name__, str(e)[:80])
# degenerate: path in the profile's own plane (XY), leaving along +X
with BuildLine(Plane.XY) as pl3:
    Line((0, 0), (20, 0))
try:
    q = sweep(prof.sketch, path=pl3.wire())
    print("in-plane path vol", q.volume, "valid", ok(q), "solids", len(q.solids()))
except Exception as e:
    print("in-plane EXC", type(e).__name__, str(e)[:80])
# profile off the path start (path starts at x=10)
with BuildLine(Plane.XZ) as pl4:
    Line((10, 0), (10, 20))
q = sweep(prof.sketch, path=pl4.wire())
print("offset start vol", q.volume, "A*L", A * 20, "bbox", q.bounding_box().min, q.bounding_box().max)
# a spline path
from build123d import Spline
with BuildLine(Plane.XZ) as pl5:
    Spline((0, 0), (5, 10), (0, 20), (5, 30))
q = sweep(prof.sketch, path=pl5.wire())
print("spline vol", q.volume, "A*L", A * pl5.wire().length, "valid", ok(q))
