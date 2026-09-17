"""Sweep probe 7: reversing a wire; mitre legs shorter than the reach;
Vector.rotate; the two faces + edge sweep; face_profile's signature."""
import math, sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
from build123d import BuildLine, Line, ThreePointArc, Plane, Circle, Wire, Transition, sweep, Vector, Axis
import inspector, sketch as sk
def L(*pts, plane=Plane.XZ):
    with BuildLine(plane) as pl:
        for a, b in zip(pts, pts[1:]):
            Line(a, b)
    return pl.wire()
w = L((0, 0), (0, 20), (20, 20))
r1 = Wire([e.reversed() for e in reversed(w.edges())])
print("reversed via edges: start", r1.start_point(), "end", r1.end_point(), "len", r1.length)
try:
    r2 = w.reversed()
    print("Wire.reversed(): start", r2.start_point(), "end", r2.end_point())
except Exception as ex:
    print("Wire.reversed EXC", type(ex).__name__, ex)
# arc reversed keeps geometry?
with BuildLine(Plane.XZ) as pl:
    Line((0, 0), (0, 20)); ThreePointArc((0, 20), (2.93, 27.07), (10, 30))
w2 = pl.wire()
r3 = Wire([e.reversed() for e in reversed(w2.edges())])
print("arc wire reversed start", r3.start_point(), "end", r3.end_point(), "len", round(r3.length, 3), "orig", round(w2.length, 3))
A = math.pi * 9
prof = Circle(3)
for leg in (1.0, 2.0, 3.0, 4.0, 6.0, 8.0):
    w3 = L((0, 0), (0, leg), (leg, leg), (leg, 2 * leg))
    try:
        q = sweep(prof, path=w3, transition=Transition.RIGHT)
        print(f"legs {leg}: vol {q.volume:8.2f} A*L {A*w3.length:8.2f} ratio {q.volume/(A*w3.length):.3f} health {inspector.health(q)}")
    except Exception as ex:
        print(f"legs {leg}: EXC {type(ex).__name__} {str(ex)[:60]}")
# a single 90-degree corner far from the ends but a SHARP one: reach 3, legs 20
w4 = L((0, 0), (0, 20), (20, 20))
q = sweep(prof, path=w4, transition=Transition.RIGHT)
print("single corner ratio", round(q.volume / (A * w4.length), 4), inspector.health(q))
# a 150-degree turn (sharp hairpin-ish)
w5 = L((0, 0), (0, 20), (-10, 20 - 10 * math.tan(math.radians(30))))
q = sweep(prof, path=w5, transition=Transition.RIGHT)
print("150deg turn ratio", round(q.volume / (A * w5.length), 4), inspector.health(q))
print("Vector.rotate:", Vector(1, 0, 0).rotate(Axis((0, 0, 0), (0, 0, 1)), 90))
print("face_profile sig:", inspect.signature(sk.face_profile))
print("_loops sig:", [n for n in dir(__import__('toolplan')) if n.startswith('_loops')])
