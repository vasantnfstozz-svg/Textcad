"""probes/shell_probe.py — what build123d's `offset` does when asked to SHELL a
solid (LAUNCH-PLAN P4, Shell tool). Run before writing sketch.shell — rule 1.

Questions:
  1. signature of offset(); does `openings` take one Face or a list?
  2. inward shell of a box, top open: exact volume?  two faces open?  a side face?
  3. OUTWARD (positive amount) with openings — what comes back, and its volume
  4. Kind.ARC vs Kind.INTERSECTION — which keeps the corners sharp (Fusion)?
  5. no openings: a closed hollow body — volume, closed_shell verdict
  6. a wall too thick (t >= half the body): exception class, or a "valid" lie?
  7. every corpus body, top face open, t = 2 — health
  8. a CURVED face as the opening (a cylinder's wall)
"""
import inspect
import sys
import traceback

import build123d as b3d
from build123d import offset, Kind, Axis

sys.path.insert(0, ".")
import inspector                         # noqa: E402
from tests.gauntlet import BODIES        # noqa: E402

print("1. signature:", inspect.signature(offset))


def report(label, fn):
    try:
        out = fn()
    except Exception as e:               # noqa: BLE001 — the point is the class
        print(f"   {label}: RAISED {type(e).__module__}.{type(e).__name__}: {str(e)[:100]}")
        return None
    try:
        v = out.volume
        health = inspector.health(out)
        closed = inspector.closed_shell(out)
        n_solids = len(out.solids())
        print(f"   {label}: volume={v:.2f} solids={n_solids} closed={closed} health={health}")
    except Exception as e:               # noqa: BLE001
        print(f"   {label}: result unreadable: {type(e).__name__}: {e}")
    return out


box = b3d.Box(50, 50, 30)                # centred: top at z=15
top = box.faces().sort_by(Axis.Z)[-1]
bottom = box.faces().sort_by(Axis.Z)[0]
side = box.faces().sort_by(Axis.X)[-1]

print("2. inward, box 50x50x30, t=3")
print("   expected top-open: 75000 - 44*44*27 =", 75000 - 44 * 44 * 27)
report("top open (Face)", lambda: offset(box, amount=-3, openings=top))
report("top open (list)", lambda: offset(box, amount=-3, openings=[top]))
report("top+side open", lambda: offset(box, amount=-3, openings=[top, side]))
report("side only", lambda: offset(box, amount=-3, openings=side))
report("top+bottom (a tube)", lambda: offset(box, amount=-3, openings=[top, bottom]))

print("3. OUTWARD, t=3, top open — expected 56*56*33 - 75000 =", 56 * 56 * 33 - 75000,
      "if the wall is added outside with the top left open at z=15")
o = report("outward top open ARC", lambda: offset(box, amount=3, openings=top))
if o is not None:
    bb = o.bounding_box(); print("      bbox", bb.min, bb.max)
o = report("outward top open INTERSECTION",
           lambda: offset(box, amount=3, openings=top, kind=Kind.INTERSECTION))
if o is not None:
    bb = o.bounding_box(); print("      bbox", bb.min, bb.max)

print("4. corners: inward ARC vs INTERSECTION (volumes differ if a corner is rounded)")
report("inward ARC", lambda: offset(box, amount=-3, openings=top, kind=Kind.ARC))
report("inward INTERSECTION", lambda: offset(box, amount=-3, openings=top, kind=Kind.INTERSECTION))

print("5. closed hollow (no openings), t=3 — expected", 75000 - 44 * 44 * 24)
report("closed ARC", lambda: offset(box, amount=-3))
report("closed INTERSECTION", lambda: offset(box, amount=-3, kind=Kind.INTERSECTION))

print("6. too thick: the box is 30 tall, so t=15 leaves nothing, t=14.9 a sliver, t=25 impossible")
for t in (12, 14.9, 15, 15.1, 25, 40):
    report(f"t={t} top open", lambda t=t: offset(box, amount=-t, openings=top, kind=Kind.INTERSECTION))
for t in (24.9, 25, 25.1, 40):
    report(f"t={t} closed", lambda t=t: offset(box, amount=-t, kind=Kind.INTERSECTION))

print("7. corpus, top face open, t=2, INTERSECTION")
for name, mk in BODIES.items():
    s = mk()
    f = s.faces().sort_by(Axis.Z)[-1]
    report(name, lambda s=s, f=f: offset(s, amount=-2, openings=f, kind=Kind.INTERSECTION))
    report(name + " ARC", lambda s=s, f=f: offset(s, amount=-2, openings=f))

print("8. a CURVED opening: the cylinder's wall")
cyl = b3d.Cylinder(25, 40)
wall = [f for f in cyl.faces() if f.geom_type.name == "CYLINDER"][0]
report("cyl wall open", lambda: offset(cyl, amount=-2, openings=wall, kind=Kind.INTERSECTION))
report("cyl cap open", lambda: offset(cyl, amount=-2, openings=cyl.faces().sort_by(Axis.Z)[-1],
                                       kind=Kind.INTERSECTION))
