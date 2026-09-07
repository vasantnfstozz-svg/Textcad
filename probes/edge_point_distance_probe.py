"""Probe (2026-09-07): distance from a point to an edge's curve, fast enough
to run over every edge of a real body for every click.

Why: a raw viewport pick sends the drawn polyline of an edge of the PREVIEW
body. Its points lie ON the parent edge of the input body even when the
preview trimmed it (a fillet shortens its neighbours by the radius), while the
midpoint moved by half the radius - so a nearest-MIDPOINT match can land on a
neighbouring edge. Point-to-curve distance is exact at any radius.

Questions: which API, is it bounded to the edge (not the infinite line), and
how long for ~600 edges x 3 sample points.
"""
import time
from build123d import Box, fillet
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.Extrema import Extrema_ExtPC
from OCP.gp import gp_Pnt

box = Box(40, 30, 12)
edges = box.edges()
top = [e for e in edges if abs(e.center().Z - 6) < 1e-6]
print("edges", len(edges), "top", len(top))

e = top[0]
p = e @ 0.3
print("build123d distance_to exists:", hasattr(e, "distance_to"))
try:
    print("  e.distance_to(p) =", e.distance_to(p))
except Exception as ex:
    print("  distance_to failed:", type(ex).__name__, ex)


def dist_pc(edge, pt):
    """bounded point-to-edge distance: interior extrema + the two ends"""
    ad = BRepAdaptor_Curve(edge.wrapped)
    g = gp_Pnt(*pt)
    best = min(ad.Value(ad.FirstParameter()).Distance(g),
               ad.Value(ad.LastParameter()).Distance(g))
    ext = Extrema_ExtPC(g, ad)
    if ext.IsDone():
        for i in range(1, ext.NbExt() + 1):
            best = min(best, ext.SquareDistance(i) ** 0.5)
    return best


print("on-edge point:", dist_pc(e, tuple(p)))
q = e @ 0.5
print("1mm above the edge:", dist_pc(e, (q.X, q.Y, q.Z + 1.0)))
a, b = e @ 0.0, e @ 1.0
beyond = a - (b - a) * 0.1
print("beyond the end along the line:", round(dist_pc(e, tuple(beyond)), 4),
      "expected", round((a - beyond).length, 4), "(bounded, not the infinite line)")

# timing: every edge of a 12-edge box against 3 samples of 15 result edges
res = fillet(top[0], 3)
t0 = time.perf_counter()
n = 0
for re_ in res.edges():
    for t in (0.0, 0.5, 1.0):
        pt = tuple(re_ @ t)
        for ie in edges:
            dist_pc(ie, pt)
            n += 1
dt = time.perf_counter() - t0
print(f"{n} point-edge distances in {dt:.3f}s -> {dt / n * 1e6:.1f} us each; "
      f"600 edges x 3 pts = {600 * 3 * dt / n * 1e3:.0f} ms")

# the scenario: which result edges lie on an input edge?
tol = 1e-3
on = off = 0
for re_ in res.edges():
    best = min(max(dist_pc(ie, tuple(re_ @ t)) for t in (0.0, 0.5, 1.0)) for ie in edges)
    if best < tol:
        on += 1
    else:
        off += 1
print("result edges lying on an input edge:", on, " fillet's own new edges:", off)

# a trimmed neighbour: shorter than its parent, midpoint moved, still ON it
for re_ in res.edges():
    c = re_ @ 0.5
    if abs(c.Z - 6) < 1e-6 and abs(re_.length - 30) > 1e-6 and abs(re_.length - 40) > 1e-6 \
            and str(re_.geom_type).endswith("LINE"):
        parent = min(edges, key=lambda ie: max(dist_pc(ie, tuple(re_ @ t)) for t in (0, .5, 1)))
        print(f"trimmed top edge: length {re_.length:.2f}, midpoint shift "
              f"{(re_ @ 0.5 - parent @ 0.5).length:.2f}mm, on-parent distance "
              f"{max(dist_pc(parent, tuple(re_ @ t)) for t in (0, .5, 1)):.2e}")
        break
