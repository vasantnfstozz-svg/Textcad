"""PROBE - review of the Loft tool (ec45cf1), 2026-09-23.

  A. The order guard: sections must step one way along the MEAN normal. A
     U-bend duct (up through a flat square, across through a vertical one,
     back down through a flat one) does not - is the kernel's loft sound?
     "Sound" is measured three ways: OCCT validity, the solid's volume
     against the ruled loft of the same sections, and whether the solid
     intersects ITSELF (a BOP self-interference check on its faces).
  B. The fold the guard was built for (parallel planes out of order) under
     the same measurements, so the two can be told apart.
  C. Twisted squares 45-85 deg: health with check_valid=False (what the op
     asks) against a full validity check.

Run: python probes/memcap.py --gb 4 --timeout 900 -- python probes/loft_review_probe.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d            # noqa: E402
from OCP.BOPAlgo import BOPAlgo_CheckerSI   # noqa: E402
from OCP.TopTools import TopTools_ListOfShape  # noqa: E402

import inspector                   # noqa: E402
import sketch as sk                # noqa: E402


def square(pl, s=4.0):
    return b3d.Sketch(children=[pl * b3d.Rectangle(s, s)])


def self_hits(solid) -> int:
    """How many self-interferences OCCT's checker finds in the solid."""
    chk = BOPAlgo_CheckerSI()
    lst = TopTools_ListOfShape()
    lst.Append(solid.wrapped)
    chk.SetArguments(lst)
    chk.SetRunParallel(False)
    chk.Perform()
    return chk.DS().Interferences().Size() if hasattr(chk.DS(), "Interferences") else \
        int(chk.HasErrors())


def report(name, sections):
    try:
        sk.loft_geometry(sections)
        g = "guard OK"
    except ValueError as e:
        g = "guard REFUSES: " + str(e)[:90]
    try:
        smooth = b3d.loft(sections)
        ruled = b3d.loft(sections, ruled=True)
        k = (f"valid={smooth.is_valid} vol={smooth.volume:.2f} ruled={ruled.volume:.2f} "
             f"ratio={smooth.volume / ruled.volume:.3f} self-hits={self_hits(smooth)}")
    except Exception as e:          # noqa: BLE001
        k = f"kernel RAISES {type(e).__name__}"
    print(f"   {name}: {g}\n      {k}")


print("== A. U-bend and 90 deg elbow")
A = square(b3d.Plane.XY)
B = square(b3d.Plane(origin=(10, 0, 10), x_dir=(0, 1, 0), z_dir=(1, 0, 0)))
C = square(b3d.Plane(origin=(20, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, -1)))
C_up = square(b3d.Plane(origin=(20, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, 1)))
report("elbow  XY -> YZ", [A, B])
report("U-bend XY -> YZ -> XY(-Z)", [A, B, C])
report("U-bend XY -> YZ -> XY(+Z normal)", [A, B, C_up])
B2 = square(b3d.Plane(origin=(20, 0, 20), x_dir=(0, 1, 0), z_dir=(1, 0, 0)))
C2 = square(b3d.Plane(origin=(40, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, -1)))
report("wide U-bend (r 20)", [A, B2, C2])

print("== B. the fold the guard exists for: parallel planes out of order")
P0 = square(b3d.Plane.XY)
P1 = square(b3d.Plane.XY.offset(20))
P2 = square(b3d.Plane.XY.offset(10))
report("z 0, 20, 10", [P0, P1, P2])
report("z 0, 10, 20", [P0, P2, P1])

print("== C. twisted squares")
for deg in (45, 60, 70, 80, 85):
    top = b3d.Sketch(children=[b3d.Plane.XY.offset(10) * b3d.Rot(0, 0, deg) * b3d.Rectangle(10, 10)])
    bot = b3d.Sketch(children=[b3d.Plane.XY * b3d.Rectangle(10, 10)])
    for ruled in (False, True):
        try:
            s = sk.loft_sketches([bot, top], ruled=ruled)
            print(f"   {deg} ruled={ruled}: op OK vol={s.volume:.2f} deep={inspector.health(s)[:1]} "
                  f"self-hits={self_hits(s)}")
        except ValueError as e:
            print(f"   {deg} ruled={ruled}: op REFUSES {str(e)[:80]}")
print("math check", math.pi)
