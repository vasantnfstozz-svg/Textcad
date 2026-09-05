"""probes/revolve_face_probe.py -- P3b (2026-09-05): can a picked FACE be a
Revolve profile, and what does the kernel do about
  (1) a Face wrapped as a Sketch (the object revolve_sketch's guards read),
  (2) a BOTTOM face (stored reversed relative to the canonical plane),
  (3) an axis that IS one of the face's own edges (r_lo = 0),
  (4) a face carrying a hole,
  (5) rotating the result about the axis (Two sides / Symmetric),
  (6) straight edges read in plane-local coords and turned back into an Axis,
  (7) a straight-but-BSPLINE edge (fused taper seam) as the axis.
Run: set PYTHONIOENCODING=utf-8; C:\Python314\python.exe probes\revolve_face_probe.py
"""
import math
import sys
sys.path.insert(0, ".")
import build123d as b3d
from build123d import Axis, Plane, Sketch, Vector

import inspector
import sketch as sk
from tests.gauntlet import BODIES, planar_faces


def pappus(r_bar, area, deg):
    return 2 * math.pi * abs(r_bar) * area * abs(deg) / 360


def report(label, solid, expect=None):
    h = inspector.health(solid)
    v = solid.volume
    c = solid.center()
    extra = f" expect={expect:.3f} ratio={v / expect:.5f}" if expect else ""
    print(f"  {label}: health={h or 'ok'} vol={v:.3f}{extra} "
          f"centre=({c.X:.2f},{c.Y:.2f},{c.Z:.2f}) pieces={len(solid.solids())}")
    return solid


def wrap(face):
    """A face as the Sketch object revolve_sketch's guards read."""
    s = Sketch([face])
    return sk._on_plane(s, sk.face_sketch_plane(face))


def straight_edges_local(face):
    pl = sk.face_sketch_plane(face)
    out = []
    for e in face.outer_wire().edges():
        if not sk._is_straight(e):
            continue
        a, b = pl.to_local_coords(e @ 0), pl.to_local_coords(e @ 1)
        out.append(((round(a.X, 4), round(a.Y, 4), round(a.Z, 4)),
                    (round(b.X, 4), round(b.Y, 4), round(b.Z, 4)), e.geom_type.name))
    return pl, out


def axis_from_local(pl, p, q):
    a = pl.from_local_coords(Vector(p[0], p[1], 0))
    b = pl.from_local_coords(Vector(q[0], q[1], 0))
    return Axis(a, b - a)


box = BODIES["box"]()
bb = box.bounding_box()
print("box bbox", bb.min, bb.max)
faces = planar_faces(box)
top = next(f for i, f, c, n in faces if n[2] > 0.9)
bot = next(f for i, f, c, n in faces if n[2] < -0.9)

print("\n(1)(6) top face: straight edges in the canonical plane's local coords")
pl, edges = straight_edges_local(top)
print("  plane origin", pl.origin, "x", pl.x_dir, "z", pl.z_dir)
for e in edges:
    print("  ", e)

# revolve the top face about its first edge, a quarter turn and a full turn
p, q, _ = edges[0]
ax = axis_from_local(pl, p, q)
s_top = wrap(top)
ext = sk.revolve_extent(s_top, ax)
print("  extent about edge0:", ext)
w = abs(ext[1] - ext[0])            # radial reach
L = abs(ext[3] - ext[2])            # along the axis
area = top.area
print(f"  face area {area:.2f}, radial reach {w:.2f}, axial {L:.2f}")
for deg in (90, 360, -90):
    report(f"top about edge0 {deg}", sk._revolve(s_top, axis=ax, revolution_arc=deg),
           pappus(w / 2, area, deg))

print("\n(2) BOTTOM face (reversed) about ITS first edge")
plb, edges_b = straight_edges_local(bot)
pb, qb, _ = edges_b[0]
axb = axis_from_local(plb, pb, qb)
s_bot = wrap(bot)
extb = sk.revolve_extent(s_bot, axb)
print("  extent:", extb)
wb = abs(extb[1] - extb[0])
for deg in (90, 360):
    report(f"bottom about edge0 {deg}", sk._revolve(s_bot, axis=axb, revolution_arc=deg),
           pappus(wb / 2, bot.area, deg))

print("\n(3) the canonical u / v axes through the plane origin: do they straddle?")
for name in ("u", "v"):
    try:
        print("  ", name, sk.revolve_extent(s_top, sk.revolve_axis(s_top, name)))
    except Exception as e:
        print("  ", name, "->", type(e).__name__, e)

print("\n(4) plate_with_hole top face about an outer edge")
pwh = BODIES["plate_with_hole"]()
ptop = next(f for i, f, c, n in planar_faces(pwh) if n[2] > 0.9)
plh, edges_h = straight_edges_local(ptop)
print("  edges:", edges_h)
s_h = wrap(ptop)
axh = axis_from_local(plh, *edges_h[0][:2])
print("  extent:", sk.revolve_extent(s_h, axh))
for deg in (90, 360):
    report(f"holed face about edge0 {deg}", sk._revolve(s_h, axis=axh, revolution_arc=deg))
print("  inner-wire straight edges would be:",
      [(e.geom_type.name, sk._is_straight(e)) for wv in ptop.inner_wires() for e in wv.edges()])

print("\n(5) Two sides / Symmetric = one revolve of the TOTAL, rotated back")
total = sk._revolve(s_top, axis=ax, revolution_arc=90)
c0 = total.center()
n = pl.z_dir
d_plane0 = (c0 - pl.origin).dot(n)
sym = total.rotate(ax, -45)
d_sym = (sym.center() - pl.origin).dot(n)
print(f"  90 one-sided: centroid {d_plane0:.3f} mm off the profile plane; "
      f"rotated -45: {d_sym:.3f} mm (symmetric => 0)")
report("  symmetric 90 health", sym)
two = sk._revolve(s_top, axis=ax, revolution_arc=120).rotate(ax, -30)   # 90 one way, 30 the other
report("  two sides 90+30 health", two, pappus(w / 2, area, 120))
# which way does a POSITIVE arc turn? centroid of the +90 sweep vs n and the radial
radial = n.cross(ax.direction).normalized()
rel = c0 - ax.position
rel = rel - ax.direction * rel.dot(ax.direction)
print(f"  +90 centroid: along radial {rel.dot(radial):.3f}, along n {rel.dot(n):.3f} "
      f"(right-handed about the axis => n-component sign tells the sweep side)")
print("  rotate(ax, -30) moved the centroid from n =", f"{d_plane0:.3f}",
      "to", f"{(two.center() - pl.origin).dot(n):.3f}")

print("\n(7) fused_taper_seam: a face with a straight-but-BSPLINE edge as the axis")
fts = BODIES["fused_taper_seam"]()
found = 0
for i, f, c, nrm in planar_faces(fts):
    plf, ef = straight_edges_local(f)
    bs = [e for e in ef if e[2] != "LINE"]
    if not bs:
        continue
    found += 1
    s_f = wrap(f)
    axf = axis_from_local(plf, *bs[0][:2])
    ext = sk.revolve_extent(s_f, axf)
    print(f"  face {i} n={tuple(round(x, 2) for x in nrm)} bspline edge {bs[0][:2]} extent={ext}")
    if ext and not ext[4]:
        try:
            report(f"  face {i} about bspline edge 90", sk._revolve(s_f, axis=axf, revolution_arc=90))
        except Exception as e:
            print("   ->", type(e).__name__, str(e)[:120])
    if found >= 2:
        break
print("  faces with a bspline straight edge:", found)

print("\n(8) cylinder end cap: no straight edge, centred on the origin")
cyl = BODIES["cylinder"]()
cap = next(f for i, f, c, n in planar_faces(cyl) if n[2] > 0.9)
plc, ec = straight_edges_local(cap)
print("  straight edges:", ec)
s_c = wrap(cap)
for name in ("u", "v"):
    print("  ", name, sk.revolve_extent(s_c, sk.revolve_axis(s_c, name)))

print("\n(9) an axis ON an edge of the profile: exact vs a few microns off, and what")
print("    is_manifold makes of the cone apexes (found by the gauntlet, 2026-09-05)")
from OCP.BRep import BRep_Tool
from OCP.TopExp import TopExp
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
hexpts = [[30, 0], [15, 25.980762113533157], [-15, 25.980762113533157], [-30, 0],
          [-15, -25.980762113533157], [15, -25.980762113533157]]
hexa = sk.make_sketch(plane="XY", entities=[{"kind": "polygon", "points": hexpts}])
edge0 = hexa.faces()[0].outer_wire().edges()[0]
A, B = edge0 @ 0, edge0 @ 1
exact = Axis(A, B - A)
off = Axis(A, B - A + Vector(0, 0, 0))
rounded = Axis(Vector(30, 0, 0), Vector(15, 25.9808, 0) - Vector(30, 0, 0))    # the stored 4-decimal line
for label, ax in (("exact edge", exact), ("4-decimal line (3.8e-5 mm off)", rounded)):
    r = sk._revolve(hexa, axis=ax, revolution_arc=90)
    m = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(r.wrapped, TopAbs_EDGE, TopAbs_FACE, m)
    census = {}
    for i in range(1, m.Extent() + 1):
        key = (m.FindFromIndex(i).Size(), BRep_Tool.Degenerated_s(b3d.Edge(m.FindKey(i)).wrapped))
        census[key] = census.get(key, 0) + 1
    print(f"  {label}: faces={len(r.faces())} min_area={min(f.area for f in r.faces()):.2e} "
          f"is_manifold={r.is_manifold} valid={r.is_valid} edges by (faces, degenerated)={census}")
print("  => exact: the axis edge collapses; two DEGENERATED apex edges (1 face each) make")
print("     is_manifold False although the shell is closed (no free bounds, OCCT valid).")
print("     off by microns: an 8th face, a sliver of area 4e-4 (a parallel offset, as on the")
print("     hexagon's horizontal sides, gives a hair-thin CYLINDER that even reports manifold).")
print("     1e-7 mm off: a raw Standard_OutOfRange from MakeRevol; 1e-6: StdFail_NotDone.")
for eps in (1e-7, 1e-6):
    d = Vector(0, 0, 1).cross(B - A).normalized() * eps
    try:
        sk._revolve(hexa, axis=Axis(A + d, B - A), revolution_arc=90)
        print(f"  shifted {eps:.0e} mm: built")
    except Exception as e:
        print(f"  shifted {eps:.0e} mm: {type(e).__name__}: {str(e)[:60]}")
