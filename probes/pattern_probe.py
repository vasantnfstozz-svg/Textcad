"""probes/pattern_probe.py — what the kernel does with PATTERNS of a feature
(LAUNCH-PLAN.md rule 1: probe before you build; specs/pattern.md). Run from
the repo root:

    set PYTHONIOENCODING=utf-8
    C:\\Python314\\python.exe probes\\pattern_probe.py

The idea under test: Fusion's "pattern a FEATURE" without knowing the feature's
op — the feature's DELTA is what it removed (input body minus output body) and
what it added (output minus input); a pattern repeats that delta about an axis
or along a direction and applies it to the body's current state.

FOUND 2026-09-06 (each drove a decision in pattern.py / toolplan.plan_pattern):

§1  The delta is exact: box − holed box = ONE valid solid of the plug's formula
    volume (339.292); holed − box = an EMPTY Compound (0 solids, 0 faces). So
    "what a feature removed" and "what it added" are two booleans, whatever
    the feature's op was.
§2  Cutting N rotated copies of the plug from the holed box is exact and
    healthy for every N (a fused cutter gives the same result); copies that
    land HALF off a 40 mm plate cut a notch and the sum shows it — the op
    measures every copy.
§3  The ADDED delta of a boss (holed body + Cylinder) patterned 4× and fused
    = base + 4 bosses exactly, valid.
§4  A fillet's sliver patterned 4× about the box centre rounds all four
    corners exactly (10 faces): the delta idea covers fillets too.
§5  After a hole the top face's centre (GEOMETRY = MASS) moves 0.24 mm toward
    the material; Face(outer_wire).center() and CenterOf.BOUNDING_BOX stay at
    the true centre. The default axis goes through the OUTER wire's centre.
§6  A cylindrical Face has `axis_of_rotation` (Axis: position on the axis,
    direction along it) — the same answer as BRepAdaptor_Surface.Cylinder();
    Face.center() lies ON the cylinder, normal_at points radially.
§7  A copy that misses the body entirely removes EXACTLY 0.0 and the boolean
    "succeeds" (the Hole review's absolute floor applies per copy); a copy
    TANGENT to the face's edge comes back an OPEN SHELL that is_valid calls
    fine — health catches it; a copy over the edge (a notch) is healthy.
§8  Five disjoint blades fused = a Compound of 5 solids; inspector.health
    passes it (the legacy body pattern stays as it is), so separate copies
    are reported through result_pieces, not refused.
§9  Location(Vector) and Pos(Vector) both translate a Part; the face frame's
    x_dir on a top face is +X; six plugs 12 mm apart cut exactly.
§10 Part.rotate(Axis(origin, dir), deg) about an arbitrary axis lands where
    the formula says ((20, 0) about (10, 5) by 90° → (15, 15)).
§11 Every corpus body takes a 3× polar pattern of a through hole's delta on
    its largest flat face: valid, one solid, the removed volume = exactly 3
    plugs on all eight (the first run placed the seed from the face FRAME's
    origin — the world origin's foot, not the face centre — and two bodies
    "lost" copies over the edge: the seed must be placed from face.center()).
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build123d as b3d                                    # noqa: E402
from build123d import Axis, Box, Cylinder, Pos, Vector, Location  # noqa: E402

import inspector                                           # noqa: E402
import sketch as sk                                        # noqa: E402
from gauntlet import BODIES, planar_faces                  # noqa: E402


def vol(p):
    try:
        return round(float(p.volume), 3)
    except Exception as e:                                 # noqa: BLE001
        return f"volume? {type(e).__name__}"


def solids(p):
    try:
        return len(p.solids())
    except Exception as e:                                 # noqa: BLE001
        return f"solids? {type(e).__name__}"


def health(p):
    try:
        return inspector.health(p)
    except Exception as e:                                 # noqa: BLE001
        return f"health? {type(e).__name__}: {e}"


def section(n, title):
    print(f"\n§{n}  {title}")


def fuse_all(parts):
    while len(parts) > 1:
        parts = [parts[i] + parts[i + 1] if i + 1 < len(parts) else parts[i]
                 for i in range(0, len(parts), 2)]
    return parts[0]


# ---------------------------------------------------------------- §1 delta ---
section(1, "the DELTA of a hole: before - after = the plug, after - before = nothing")
box = Box(60, 40, 12)
top = max(box.faces(), key=lambda f: f.center().Z)
after = sk.hole(box, face_center=list(top.center()), face_normal=[0, 0, 1],
                at=[20, 0], diameter=6, depth=12, through=True)
removed = box - after
added = after - box
plug = math.pi * 9 * 12
print("  plug formula", round(plug, 3), " removed", vol(removed), "solids", solids(removed),
      " added", vol(added), "solids", solids(added), type(added).__name__)
print("  removed is_valid", removed.is_valid, " health", health(removed))
print("  added faces", len(added.faces()), " added.solids()", solids(added))

# ------------------------------------------------- §2 polar pattern of it ---
section(2, "N copies of the plug about the face's normal through the face centre, cut from `after`")
axis = Axis(top.center(), (0, 0, 1))
for n in (2, 4, 6, 8):
    cutters = [removed.rotate(axis, 360.0 * i / n) for i in range(1, n)]
    res = after
    for c in cutters:
        res = res - c
    print(f"  n={n}: volume", vol(res), "expected", round(box.volume - n * plug, 3),
          " valid", res.is_valid, " solids", solids(res), " health", health(res))
# one boolean with all cutters fused first
n = 6
cutter = fuse_all([removed.rotate(axis, 360.0 * i / n) for i in range(1, n)])
res2 = after - cutter
print("  fused-cutter n=6:", vol(res2), "valid", res2.is_valid, " solids", solids(res2))

# --------------------------------------------- §3 a boss (added material) ---
section(3, "a boss: the ADDED delta patterned and fused")
base = Box(60, 40, 12)
boss = Pos(20, 0, 6 + 4) * Cylinder(4, 8)
with_boss = base + boss
add = with_boss - base
print("  added", vol(add), "formula", round(math.pi * 16 * 8, 3), " solids", solids(add),
      " valid", add.is_valid)
n = 4
copies = [add.rotate(Axis((0, 0, 6), (0, 0, 1)), 360.0 * i / n) for i in range(1, n)]
res = with_boss
for c in copies:
    res = res + c
print(f"  n={n} fused: volume", vol(res), "expected", round(base.volume + n * math.pi * 16 * 8, 3),
      " valid", res.is_valid, " solids", solids(res), " health", health(res))

# ------------------------------------------------------ §4 a fillet delta ---
section(4, "a fillet's delta (a sliver) patterned 4x about the box centre")
b = Box(50, 50, 30)
vert = [e for e in b.edges() if abs(e.length - 30) < 1e-6]
e0 = max(vert, key=lambda e: e.center().X + e.center().Y)
fb = b.fillet(5, [e0])
sliver = b - fb
print("  sliver", vol(sliver), "formula", round((25 - 25 * math.pi / 4) * 30, 3),
      " solids", solids(sliver), " valid", sliver.is_valid)
res = fb
for i in range(1, 4):
    res = res - sliver.rotate(Axis((0, 0, 0), (0, 0, 1)), 90 * i)
print("  4 corners: volume", vol(res), "expected",
      round(b.volume - 4 * (25 - 25 * math.pi / 4) * 30, 3),
      " valid", res.is_valid, " health", health(res), " faces", len(res.faces()))

# ------------------------------------- §5 the face centre after a hole ---
section(5, "the seed face's centre: Face.center() moves with the hole; the outer wire's does not")
top_after = max((f for f in after.faces() if f.geom_type == b3d.GeomType.PLANE),
                key=lambda f: f.center().Z)
print("  top face wires", len(top_after.wires()), " inner", len(top_after.inner_wires()))
print("  Face.center()          ", top_after.center())
for name in ("GEOMETRY", "MASS", "BOUNDING_BOX"):
    try:
        c = top_after.center(getattr(b3d.CenterOf, name))
        print(f"  Face.center(CenterOf.{name:<12})", c)
    except Exception as e:                                 # noqa: BLE001
        print(f"  Face.center(CenterOf.{name}) ->", type(e).__name__, e)
outer = b3d.Face(top_after.outer_wire())
print("  Face(outer_wire).center()", outer.center(), " area", round(outer.area, 2))

# --------------------------------------------- §6 a cylindrical face's axis ---
section(6, "the axis of a cylindrical face (gear teeth around a bore)")
ring = Box(60, 60, 10) - Cylinder(10, 10)
cyl = [f for f in ring.faces() if f.geom_type == b3d.GeomType.CYLINDER][0]
for attr in ("axis_of_rotation", "axis", "location"):
    print(f"  face.{attr}:", getattr(cyl, attr, "<missing>"))
print("  face.normal_at(center):", cyl.normal_at(cyl.center()))
try:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    ad = BRepAdaptor_Surface(cyl.wrapped)
    ax = ad.Cylinder().Axis()
    loc, d = ax.Location(), ax.Direction()
    print("  BRepAdaptor cylinder axis: loc", (loc.X(), loc.Y(), loc.Z()),
          " dir", (d.X(), d.Y(), d.Z()), " radius", ad.Cylinder().Radius())
except Exception as e:                                     # noqa: BLE001
    print("  BRepAdaptor ->", type(e).__name__, e)
print("  Face.center()", cyl.center(), "  is the centre ON the surface?", cyl.is_inside(cyl.center()))

# ------------------------------------------ §7 a copy that lands off the body ---
section(7, "a copy that misses the body: what the boolean returns")
box7 = Box(60, 40, 12)
top7 = max(box7.faces(), key=lambda f: f.center().Z)
h7 = sk.hole(box7, face_center=list(top7.center()), face_normal=[0, 0, 1],
             at=[25, 0], diameter=6, depth=12, through=True)
plug7 = box7 - h7
for ang in (90, 180):                       # 90: (0, 25) is off a 40-wide plate (|y| <= 20)
    c = plug7.rotate(Axis(top7.center(), (0, 0, 1)), ang)
    r = h7 - c
    print(f"  copy at {ang} deg: removed", round(h7.volume - r.volume, 4), " valid", r.is_valid,
          " solids", solids(r), " cutter centre", c.center())
c = Pos(0, 17, 0) * plug7                   # centre at y=17, radius 3 -> reaches y=20 exactly
r = h7 - c
print("  copy tangent to the edge: removed", round(h7.volume - r.volume, 4), " valid", r.is_valid,
      " health", health(r))
c = Pos(0, 19, 0) * plug7                   # centre 1 mm from the edge: a notch
r = h7 - c
print("  copy over the edge (notch): removed", round(h7.volume - r.volume, 4), " valid", r.is_valid,
      " health", health(r))

# ------------------------------------------ §8 a BODY pattern's disjoint copies ---
section(8, "a body pattern: disjoint copies fused = a compound; what health says")
blade = Pos(20, 0, 0) * Box(24, 3, 10)
pat = fuse_all([blade.rotate(Axis.Z, 360.0 * i / 5) for i in range(5)])
print("  type", type(pat).__name__, " solids", solids(pat), " volume", vol(pat), " valid", pat.is_valid)
print("  health", health(pat))
print("  health(require_manifold=False)", inspector.health(pat, require_manifold=False))

# ----------------------------------------------- §9 a linear pattern of a hole ---
section(9, "a linear pattern of the plug along the face's u, spacing 12")
box9 = Box(80, 40, 12)
top9 = max(box9.faces(), key=lambda f: f.center().Z)
h9 = sk.hole(box9, face_center=list(top9.center()), face_normal=[0, 0, 1],
             at=[-30, 0], diameter=6, depth=12, through=True)
plug9 = box9 - h9
pl9 = sk.face_profile_plane(top9)
u = Vector(pl9.x_dir)
print("  face frame u", u, " v", pl9.y_dir)
res = h9
for i in range(1, 6):
    res = res - (Location(u * (12.0 * i)) * plug9)
print("  6 in a row: volume", vol(res), "expected", round(box9.volume - 6 * plug, 3),
      " valid", res.is_valid, " health", health(res))
print("  Pos(Vector) ok?", type(Pos(u * 12)).__name__, " Location(Vector) ok?",
      type(Location(u * 12)).__name__)

# ------------------------------------- §10 rotate about an arbitrary axis ---
section(10, "Part.rotate about an arbitrary axis: where the centre goes")
p = Pos(20, 0, 0) * Cylinder(3, 12)
for org, d in (((0, 0, 0), (0, 0, 1)), ((10, 5, 0), (0, 0, 1)), ((0, 0, 0), (1, 0, 0))):
    q = p.rotate(Axis(org, d), 90)
    print(f"  axis {org} {d}: centre {p.center()} -> {q.center()}")

# -------------------------------- §11 the delta on the nasty corpus bodies ---
section(11, "a through hole's delta, patterned 3x about the face normal through the face "
           "centre, on every corpus body")
for name, make in BODIES.items():
    solid = make()
    faces = planar_faces(solid)
    if not faces:
        print(f"  {name}: no flat face")
        continue
    idx, face, centre, normal = max(faces, key=lambda t: t[1].area)
    try:
        pl = sk.face_profile_plane(face)
        bb = face.bounding_box()
        span = min(s for s in (bb.size.X, bb.size.Y, bb.size.Z) if s > 1e-6)
        c = pl.to_local_coords(face.center())     # from the FACE centre (the frame's origin is the world's foot)
        at_local = Vector(c.X + span * 0.25, c.Y, 0)
        holed = sk.hole(solid, face_center=list(face.center()), face_normal=list(normal),
                        at=[at_local.X, at_local.Y], diameter=3, depth=1, through=True)
        delta = solid - holed
        ax = Axis(face.center(), tuple(normal))
        res = holed
        for i in range(1, 3):
            res = res - delta.rotate(ax, 120.0 * i)
        print(f"  {name}.f{idx}: delta {vol(delta)} solids {solids(delta)} -> result valid "
              f"{res.is_valid} solids {solids(res)} removed {round(solid.volume - res.volume, 3)} "
              f"(3 plugs = {round(3 * delta.volume, 3)}) health {health(res)}")
    except Exception as e:                                 # noqa: BLE001
        print(f"  {name}.f{idx}: {type(e).__name__}: {e}")

print("\nDONE")
