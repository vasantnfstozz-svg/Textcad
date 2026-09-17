"""Sweep probe 5: an empty Sketch placed on a plane keeps attributes? mitre
legs shorter than the profile's reach; a U path; health on the folded bend."""
import math, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from build123d import (BuildLine, BuildSketch, Circle, Line, ThreePointArc, Plane, Pos,
                       Transition, sweep, Sketch)
import inspector
def L(*pts, plane=Plane.XZ):
    with BuildLine(plane) as pl:
        for a, b in zip(pts, pts[1:]):
            Line(a, b)
    return pl.wire()
A = math.pi * 9
prof = Circle(3)
e = Sketch()
e._tc_x = 1
placed = Plane.XZ * e
print("empty placed type", type(placed).__name__, "attr survives?", getattr(placed, "_tc_x", None), "faces", len(placed.faces()) if hasattr(placed, 'faces') else '?')
try:
    from sketch import _as_sketch
    print("_as_sketch(empty) ->", type(_as_sketch(placed)).__name__)
except Exception as ex:
    print("_as_sketch EXC", type(ex).__name__, ex)
# short legs vs reach 3: legs of 2, 3, 4, 8 mm in a zigzag
for leg in (2.0, 3.0, 4.0, 8.0):
    w = L((0, 0), (0, leg), (leg, leg), (leg, 2 * leg))
    try:
        q = sweep(prof, path=w, transition=Transition.RIGHT)
        print(f"legs {leg}: vol {q.volume:8.2f} A*L {A*w.length:8.2f} ratio {q.volume/(A*w.length):.3f} health {inspector.health(q)}")
    except Exception as ex:
        print(f"legs {leg}: EXC {type(ex).__name__} {str(ex)[:60]}")
# folded bend r=2 -> what does health / is_valid say, and the closed-shell verdict
w = None
with BuildLine(Plane.XZ) as pl:
    Line((0, 0), (0, 20)); ThreePointArc((0, 20), (2 * (1 - math.cos(math.pi/4)), 20 + 2 * math.sin(math.pi/4)), (2, 22)); Line((2, 22), (22, 22))
w = pl.wire()
q = sweep(prof, path=w, transition=Transition.RIGHT)
print("fold r=2 health", inspector.health(q), "closed", inspector.closed_shell(q) if hasattr(inspector, 'closed_shell') else '?', "vol", round(q.volume, 2), "A*L", round(A * w.length, 2))
# U path: both ends on the profile plane z=0
w = L((0, 0), (0, 20), (20, 20), (20, 0))
q = sweep(prof, path=w, transition=Transition.RIGHT)
print("U path vol", round(q.volume, 2), "A*L", round(A * w.length, 2), "health", inspector.health(q))
# a 90-degree corner right at the start (path leaves along +Z then immediately turns)
w = L((0, 0), (0, 1), (20, 1))
q = sweep(prof, path=w, transition=Transition.RIGHT)
print("corner 1mm after start vol", round(q.volume, 2), "A*L", round(A * w.length, 2), "health", inspector.health(q))
# distance smaller than the reach (a 1 mm sweep of an r=3 circle) - fine?
w = L((0, 0), (0, 1))
q = sweep(prof, path=w, transition=Transition.RIGHT)
print("1mm straight vol", round(q.volume, 3), "A*L", round(A, 3))
