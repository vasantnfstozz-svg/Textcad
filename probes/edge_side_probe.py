"""Probe (2026-09-07): tell an INSIDE corner (concave edge) from an OUTSIDE edge
(convex), for the Fillet panel's group chips ("inside vertical" = every pocket
corner of a part in one click).

Rule: at the edge's midpoint m, with tangent d and the two faces A, B and their
outward normals nA, nB: let tA be the direction from the edge INTO face A (in
A's surface, perpendicular to d). The edge is concave when tA points the same
way as nB (the other face folds TOWARD A's interior), convex when it points
against it. Box top edge: tA = -X (into the top), nB = +X -> convex. Pocket
floor rim: tA = -X (into the floor), wall nB = -X -> concave.

tA = +-(nA x d): the sign is the one whose test point lies ON face A.
Tangent faces (a round meeting a plane, |tA . nB| ~ 0) are neither.

VERDICT (measured): the distance rule gives every expected count on a pocketed
box (4/4/4/12), a rounded box (8 tangent seams -> None) and a boss on a plate
(the base circle is the one inside edge); 0.7 s for esp32-remote's 609 edges,
where EVERY upright is a smooth seam (its pocket corners are already round) and
the floor rims are arcs — which is why "horizontal" means "lies flat", not
"parallel to X or Y". The orientation shortcut below (interior on the left of
the oriented wire) disagreed on 5-12 edges of every body in ALL flip variants
and is NOT shipped; blocks.edge_side is the distance rule, cached per body.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build123d import Axis, Box, Pos, Vector           # noqa: E402
import blocks                                          # noqa: E402
from document import Document                          # noqa: E402


def in_face_dir(face, edge, m, d):
    n = face.normal_at(m)
    c = n.cross(d)
    if c.length < 1e-9:
        return None, n
    c = c.normalized()
    eps = min(0.3, 0.05 * edge.length)
    dplus = face.distance_to(m + c * eps)
    dminus = face.distance_to(m - c * eps)
    return (c if dplus <= dminus else -c), n


def side(part, edge, by_edge):
    faces = by_edge.get(blocks._shape_key(edge), [])
    if len(faces) != 2:
        return None
    a, b = faces
    m = edge @ 0.5
    d = (edge % 0.5).normalized()
    ta, _ = in_face_dir(a, edge, m, d)
    if ta is None:
        return None
    nb = b.normal_at(m)
    s = ta.dot(nb)
    if abs(s) < 0.05:
        return None                      # tangent: neither
    return "inside" if s > 0 else "outside"


def direction(edge):
    """vertical = a straight edge along Z; horizontal = the edge LIES FLAT (a
    line along X/Y, but also a flat arc or circle: a pocket's rounded floor rim
    is horizontal to anyone who machines it); other = the rest"""
    zs = [(edge @ t).Z for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
    if max(zs) - min(zs) < 1e-6:
        return "horizontal"
    if blocks._gtype(edge) == "LINE" and abs((edge % 0.5).normalized().Z) > 0.999:
        return "vertical"
    return "other"


# ---- the FAST rule: orientation instead of distance queries ----------------
# A face's wire runs so that the face's interior is on the LEFT when walking an
# edge in its oriented direction with the outward normal up. So the direction
# INTO face A at the edge is nA x d_oriented, with d flipped for a REVERSED edge
# (as it sits in A's wire) and again for a REVERSED face. No distance query.
from OCP.TopAbs import TopAbs_Orientation                # noqa: E402


def orientations(part):
    """(face key, edge key) -> the edge's orientation inside that face's wire"""
    out = {}
    for f in part.faces():
        fk = blocks._shape_key(f)
        for e in f.edges():
            out[(fk, blocks._shape_key(e))] = e.wrapped.Orientation()
    return out


MODE = "both"        # which flips: "both" (edge + face), "edge" only, "face" only


def side_fast(edge, by_edge, orient, mode=None):
    mode = mode or MODE
    ek = blocks._shape_key(edge)
    faces = by_edge.get(ek, [])
    if len(faces) != 2:
        return None
    a, b = faces
    m = edge @ 0.5
    d = (edge % 0.5).normalized()
    if mode in ("both", "edge") and \
            orient.get((blocks._shape_key(a), ek)) == TopAbs_Orientation.TopAbs_REVERSED:
        d = -d
    if mode in ("both", "face") and \
            a.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        d = -d
    na, nb = a.normal_at(m), b.normal_at(m)
    s = na.cross(d).dot(nb)
    if abs(s) < 0.05:
        return None
    return "inside" if s > 0 else "outside"


def census(part, label):
    by_edge = blocks._edge_faces(part)
    t0 = time.perf_counter()
    counts, slow = {}, {}
    for e in part.edges():
        slow[blocks._shape_key(e)] = side(part, e, by_edge)
        k = (slow[blocks._shape_key(e)], direction(e))
        counts[k] = counts.get(k, 0) + 1
    dt = time.perf_counter() - t0
    t0 = time.perf_counter()
    orient = orientations(part)
    fast = {blocks._shape_key(e): side_fast(e, by_edge, orient) for e in part.edges()}
    dt2 = time.perf_counter() - t0
    disagree = [k for k in slow if slow[k] != fast[k]]
    print(f"{label}: {len(part.edges())} edges — distance rule {dt * 1e3:.0f} ms, "
          f"orientation rule ({MODE}) {dt2 * 1e3:.0f} ms, disagreements {len(disagree)}")
    for mode in ("both", "edge", "face"):
        alt = {blocks._shape_key(e): side_fast(e, by_edge, orient, mode) for e in part.edges()}
        print(f"   flips={mode}: {sum(1 for k in slow if slow[k] != alt[k])} disagreements")
    for k in sorted(counts, key=str):
        print(f"   {k}: {counts[k]}")
    return counts


# 1. the pocket box: 40x30x20 with a 20x12 pocket 5 deep
pocket = Box(40, 30, 20) - Pos(0, 0, 10) * Box(20, 12, 10)
c = census(pocket, "pocket box")
assert c[("inside", "vertical")] == 4, "the 4 pocket corners"
assert c[("inside", "horizontal")] == 4, "the 4 floor rims"
assert c[("outside", "vertical")] == 4, "the 4 box corners"
assert c[("outside", "horizontal")] == 12, "top rim 4 + bottom rim 4 + pocket opening 4"
print("pocket box: every count as expected")

# 2. a rounded box: the fillet faces meet the flats tangentially -> neither
from build123d import fillet                           # noqa: E402
rounded = fillet(Box(40, 30, 20).edges().filter_by(Axis.Z), 5)
census(rounded, "box with rounded uprights (tangent seams must be None)")

# 2b. a boss on a plate: its base circle is an INSIDE horizontal edge (an arc,
# which "parallel to X or Y" would miss), its top circle an outside one, and
# the cylinder's seam touches one face only -> neither
from build123d import Cylinder                         # noqa: E402
boss = Box(40, 30, 10) + Pos(0, 0, 10) * Cylinder(5, 10)
c = census(boss, "boss on a plate")
assert c[("inside", "horizontal")] == 1 and c[("outside", "horizontal")] == 9, c
assert c.get((None, "vertical"), 0) == 1, "the seam"

# 3. the real thing
doc = Document.load(str(Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "esp32-remote.tcad.json"))
assert doc.rebuild(), doc.tree()
census(doc.result(), "esp32-remote")
