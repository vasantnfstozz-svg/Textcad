"""Sweep probe 3: WHERE does the solid go when the path does not touch the
profile (relative motion, or moved to the path)? Also: arc radius of an edge,
position/tangent at a length fraction, trimming a closed loop, a sketch with
zero faces."""
import math, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from build123d import (BuildLine, BuildSketch, Circle, Line, ThreePointArc, Plane,
                       Transition, sweep, Sketch, Compound)
A = math.pi * 9
with BuildSketch(Plane.XY) as prof:
    Circle(3)
def path(a, b, plane=Plane.XZ):
    with BuildLine(plane) as pl:
        Line(a, b)
    return pl.wire()
for name, w in [("touching up", path((0, 0), (0, 20))),
                ("away, forward (z 20->40)", path((0, 20), (0, 40))),
                ("away, reversed (z 40->20)", path((0, 40), (0, 20))),
                ("reversed into profile (z 20->0)", path((0, 20), (0, 0))),
                ("beside, x=10 forward", path((10, 0), (10, 20)))]:
    q = sweep(prof.sketch, path=w, transition=Transition.RIGHT)
    bb = q.bounding_box()
    print(f"{name:32s} vol {q.volume:8.3f} x {bb.min.X:6.1f}..{bb.max.X:6.1f} z {bb.min.Z:6.1f}..{bb.max.Z:6.1f}")
# arc radius, positions, tangents along a wire
with BuildLine(Plane.XZ) as pl:
    Line((0, 0), (0, 20))
    ThreePointArc((0, 20), (10 * (1 - math.cos(math.pi/4)), 20 + 10 * math.sin(math.pi/4)), (10, 30))
    Line((10, 30), (30, 30))
w = pl.wire()
for e in w.edges():
    print("edge", e.geom_type, "len", round(e.length, 3), "radius", getattr(e, "radius", None) if e.geom_type.name != "LINE" else "-")
for f in (0.0, 0.25, 0.5, 0.75, 1.0):
    print("at", f, "pos", w.position_at(f), "tan", w.tangent_at(f))
print("wire edges ordered?", [ (round(e.position_at(0).Z,2), round(e.position_at(1).Z,2)) for e in w.edges()])
# closed loop trim
with BuildLine(Plane.XZ) as pl:
    Line((0, 0), (0, 30)); Line((0, 30), (40, 30)); Line((40, 30), (40, 0)); Line((40, 0), (0, 0))
loop = pl.wire()
t = loop.trim(0, 0.5)
print("loop trim half len", t.length, "of", loop.length, "start", t.start_point(), "end", t.end_point())
# an empty sketch object
s = Sketch()
print("empty Sketch area", s.area, "faces", len(s.faces()))
try:
    q = sweep(s, path=w)
    print("sweep of empty sketch ->", type(q).__name__, getattr(q, 'volume', None))
except Exception as e:
    print("sweep of empty sketch EXC", type(e).__name__, str(e)[:80])
# sweep with distance 0 -> trim(0,0)?
try:
    t0 = w.trim(0, 0.0)
    print("trim 0..0 len", t0.length)
except Exception as e:
    print("trim 0..0 EXC", type(e).__name__, str(e)[:80])
