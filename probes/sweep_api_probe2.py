"""Sweep probe 2: RIGHT on a tangent path; a bend tighter than the profile;
a closed loop path; a two-circle profile; a face profile; path drawn away
from the profile (reversed)."""
import math
from build123d import (BuildLine, BuildSketch, Circle, Line, ThreePointArc,
                       Plane, Transition, sweep, Box, Rectangle, Pos)
from OCP.BRepCheck import BRepCheck_Analyzer
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import inspector
ok = lambda s: BRepCheck_Analyzer(s.wrapped).IsValid()
A = math.pi * 9
with BuildSketch(Plane.XY) as prof:
    Circle(3)
def bent(r):
    with BuildLine(Plane.XZ) as pl:
        Line((0, 0), (0, 20))
        ThreePointArc((0, 20), (r * (1 - math.cos(math.pi/4)), 20 + r * math.sin(math.pi/4)), (r, 20 + r))
        Line((r, 20 + r), (r + 20, 20 + r))
    return pl.wire()
w = bent(10)
for tr in (Transition.TRANSFORMED, Transition.RIGHT, Transition.ROUND):
    q = sweep(prof.sketch, path=w, transition=tr)
    print("tangent path", tr.name, "vol", round(q.volume, 3), "A*L", round(A * w.length, 3), "valid", ok(q), "health", inspector.health(q))
for r in (3.0, 2.5, 2.0, 1.0):
    w = bent(r)
    try:
        q = sweep(prof.sketch, path=w, transition=Transition.RIGHT)
        print("bend r", r, "vol", round(q.volume, 3), "A*L", round(A * w.length, 3), "valid", ok(q), "health", inspector.health(q))
    except Exception as e:
        print("bend r", r, "EXC", type(e).__name__, str(e)[:80])
# closed loop path: a 40x30 rectangle loop on XZ, circle profile r=3 at its corner (0,0)
with BuildLine(Plane.XZ) as pl:
    Line((0, 0), (0, 30)); Line((0, 30), (40, 30)); Line((40, 30), (40, 0)); Line((40, 0), (0, 0))
w = pl.wire()
print("closed?", w.is_closed, "len", w.length)
for tr in (Transition.RIGHT, Transition.ROUND):
    try:
        q = sweep(prof.sketch, path=w, transition=tr)
        print("loop", tr.name, "vol", round(q.volume, 3), "A*L", round(A * w.length, 3), "valid", ok(q), "solids", len(q.solids()), "health", inspector.health(q))
    except Exception as e:
        print("loop", tr.name, "EXC", type(e).__name__, str(e)[:80])
# two-circle profile
with BuildSketch(Plane.XY) as two:
    Circle(3); 
    with BuildSketch(Plane.XY) as _t: pass
two_sk = Pos(0, 0) * two.sketch + Pos(10, 0) * two.sketch
print("two faces?", len(two_sk.faces()))
q = sweep(two_sk, path=bent(10), transition=Transition.RIGHT)
print("two circles vol", round(q.volume, 3), "2*A*L", round(2 * A * bent(10).length, 3), "solids", len(q.solids()), "valid", ok(q))
# a face profile: top face of a box, path from the face centre going +Z then bending
b = Box(10, 10, 5)
top = max(b.faces(), key=lambda f: f.center().Z)
with BuildLine(Plane.XZ) as pl:
    Line((0, 2.5), (0, 22.5)); Line((0, 22.5), (20, 22.5))
q = sweep(top, path=pl.wire(), transition=Transition.RIGHT)
print("face profile vol", round(q.volume, 3), "A*L", 100 * 40, "valid", ok(q))
# path drawn AWAY from the profile: from (0,20)->(0,0) on XZ (ends at the profile)
with BuildLine(Plane.XZ) as pl:
    Line((0, 20), (0, 0))
q = sweep(prof.sketch, path=pl.wire())
bb = q.bounding_box()
print("reversed path vol", round(q.volume, 3), "z", bb.min.Z, bb.max.Z, "(expected 0..20 if it left from the profile)")
# in-plane path angle guard: tangent vs profile normal
with BuildLine(Plane.XZ) as pl:
    Line((0, 0), (20, 20))   # 45 deg
q = sweep(prof.sketch, path=pl.wire())
print("45deg path vol", round(q.volume, 3), "A*L", round(A * pl.wire().length, 3), "A*L*cos45", round(A * pl.wire().length * math.cos(math.pi/4), 3), "valid", ok(q))
