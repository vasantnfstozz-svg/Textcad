"""Sweep probe 4: what ANCHORS the sweep (the profile's centre?) and does the
PATH DIRECTION matter (an L path forward vs reversed; partial trims)."""
import math, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from build123d import (BuildLine, BuildSketch, Circle, Line, Plane, Pos,
                       Transition, sweep, Rectangle)
def L(*pts, plane=Plane.XZ):
    with BuildLine(plane) as pl:
        for a, b in zip(pts, pts[1:]):
            Line(a, b)
    return pl.wire()
def bb(q):
    b = q.bounding_box()
    return f"x {b.min.X:6.1f}..{b.max.X:6.1f}  y {b.min.Y:6.1f}..{b.max.Y:6.1f}  z {b.min.Z:6.1f}..{b.max.Z:6.1f}"
# profile centred at (5, 0) on XY; path at x=10 straight up -> anchored where?
with BuildSketch(Plane.XY) as prof:
    with BuildSketch(Plane.XY) as _: pass
prof = Pos(5, 0) * Circle(3)  # a Sketch translated
print("profile centre", prof.center())
q = sweep(prof, path=L((10, 0), (10, 20)), transition=Transition.RIGHT)
print("centre(5,0) path x=10 up :", bb(q))
# an off-centre profile: rectangle 2x10 with centre (5,0) -> the anchor could be the centre of mass or bbox
prof2 = Pos(5, 0) * Rectangle(2, 10)
q = sweep(prof2, path=L((10, 0), (10, 20)), transition=Transition.RIGHT)
print("rect centre(5,0) path x=10:", bb(q))
# L path forward: up 20 then +X 20 ; reversed: from (20,20) -> (0,20) -> (0,0)
prof0 = Circle(3)
fwd = L((0, 0), (0, 20), (20, 20)); rev = L((20, 20), (0, 20), (0, 0))
print("fwd start", fwd.start_point(), "rev start", rev.start_point())
qf = sweep(prof0, path=fwd, transition=Transition.RIGHT); qr = sweep(prof0, path=rev, transition=Transition.RIGHT)
print("L forward :", bb(qf), "vol", round(qf.volume, 1))
print("L reversed:", bb(qr), "vol", round(qr.volume, 1))
for f in (0.3, 0.7):
    tf = fwd.trim(0, f); tr = rev.trim(0, f)
    print(f" trim {f}: fwd start {tf.start_point()} end {tf.end_point()} -> {bb(sweep(prof0, path=tf, transition=Transition.RIGHT))}")
    print(f" trim {f}: rev start {tr.start_point()} end {tr.end_point()} -> {bb(sweep(prof0, path=tr, transition=Transition.RIGHT))}")
# a path whose start is NOT in the profile plane and not at the profile at all: L at z 20..40
far = L((7, 20), (7, 40), (27, 40))
q = sweep(prof0, path=far, transition=Transition.RIGHT)
print("far L (start (7,0,20)):", bb(q))
# a path starting at the profile centre but leaving at 45 deg then vertical
sk = L((0, 0), (10, 10), (10, 30))
q = sweep(prof0, path=sk, transition=Transition.RIGHT)
print("45deg-then-up:", bb(q), "vol", round(q.volume, 1), "A*L", round(math.pi*9*sk.length, 1))
