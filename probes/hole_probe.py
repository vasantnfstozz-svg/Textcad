"""probes/hole_probe.py — what the kernel does with holes (LAUNCH-PLAN.md rule 1:
probe before you build; specs/hole.md). Run from the repo root:

    set PYTHONIOENCODING=utf-8
    C:\\Python314\\python.exe probes\\hole_probe.py

FOUND 2026-09-06 (each drove a decision in sketch.hole / toolplan.plan_hole):

§1  build123d's Hole / CounterBoreHole / CounterSinkHole are BUILDER-mode tools:
    Hole(3, 8) spans z = -8..+8 (double length, about the location), Hole(3)
    without a depth raises "No depth provided", and `is_valid` is a PROPERTY
    (calling it: "'bool' object is not callable" — the hallucination CLAUDE.md
    warns about). Not used: the op builds its own cutter.
§2  A hand-built cutter (Cylinder / Cylinder + Cylinder / Cylinder + Cone in a
    plane at the hole point whose z points INTO the material) removes EXACTLY
    the formula volume — blind, through, counterbore, countersink — and the
    result is healthy, with or without a 1 mm overshoot above the face (the
    coplanar cap is fine, so the cutter starts AT the face like Fusion's).
§3  Two "successes" that must be refused: a hole centred inside an existing
    hole removes 0 mm³ (the annular face's centre), and a ⌀60 hole on a 50 mm
    face comes back as an OPEN SHELL that OCCT calls valid.
§4  Every flat face of every gauntlet body takes a blind ⌀4 hole at its centre
    (BSPLINE-flat taper walls included).
§5  Face.is_inside(point, tolerance) says whether the centre is on the face
    (True on the boundary, False 0.1 mm past it, False 0.5 mm off the plane);
    Edge.make_line(...).intersect(solid) returns the pieces of the line INSIDE
    the solid — the first piece from the face is the material under the point
    (box: 20, wedge's slanted face: 45.96).
§6  face_profile_plane coordinates: (5, 7, 10) on a box's top face -> (5, 7);
    (5, 7, -10) on the bottom face -> (5, 7) — the same x / y a sketch on that
    face uses, so `at` reads like a sketch coordinate.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build123d as b3d                                   # noqa: E402
from build123d import Align, Axis, Box, Cone, Cylinder, Edge, Plane, Vector  # noqa: E402

import inspector                                           # noqa: E402
import sketch as sk                                        # noqa: E402
from gauntlet import BODIES, planar_faces                  # noqa: E402

PI = math.pi
A = (Align.CENTER, Align.CENTER, Align.MIN)


def section(title):
    print(f"\n=== {title} ===")


def report(label, solid, expected=None):
    v = solid.volume
    extra = f" expected {expected:.3f} diff {v - expected:+.4f}" if expected is not None else ""
    print(f"{label}: vol {v:.3f}{extra} health {inspector.health(solid)}")


def cutter(pl_into, r, depth, kind="simple", cb_r=0, cb_d=0, cs_r=0, cs_ang=90, over=0.0):
    """the op's cutter, as sketch.hole_cutter builds it (`over` = start above the face)"""
    frame = Plane(pl_into.origin - pl_into.z_dir * over, x_dir=pl_into.x_dir, z_dir=pl_into.z_dir)
    body = frame * Cylinder(r, depth + over, align=A)
    if kind == "cbore":
        body = body + (frame * Cylinder(cb_r, cb_d + over, align=A))
    if kind == "csink":
        half = math.radians(cs_ang / 2)
        h = (cs_r - r) / math.tan(half)
        body = body + (frame * Cone(bottom_radius=cs_r + over * math.tan(half), top_radius=r,
                                    height=h + over, align=A))
    return body


section("1. build123d's own hole objects")
h = b3d.Hole(3, 8)
bb = h.bounding_box()
print("Hole(3, 8) spans z", round(bb.min.Z, 3), "..", round(bb.max.Z, 3), "(double length)")
try:
    b3d.Hole(3)
except Exception as e:
    print("Hole(3):", type(e).__name__, e)
print("is_valid is a property:", isinstance(Box(1, 1, 1).is_valid, bool))

section("2. a hand-built cutter: exact volumes, healthy")
box = Box(50, 50, 20)
V0 = box.volume
top = Plane((5, 5, 10), z_dir=(0, 0, -1))                # INTO the box at (5, 5) on the top face
r, d = 3, 8
report("blind r3 d8", box - cutter(top, r, d), V0 - PI * r * r * d)
report("blind r3 d8, 1 mm overshoot", box - cutter(top, r, d, over=1.0), V0 - PI * r * r * d)
report("through r3", box - cutter(top, r, 40), V0 - PI * r * r * 20)
report("counterbore r3 d8 + r5 x 2", box - cutter(top, r, d, "cbore", cb_r=5, cb_d=2),
       V0 - PI * r * r * d - PI * (25 - 9) * 2)
cs_r, ang = 6, 90
hc = (cs_r - r) / math.tan(math.radians(ang / 2))
cone_extra = PI * hc / 3 * (cs_r ** 2 + cs_r * r + r ** 2) - PI * r * r * hc
report("countersink r3 d8 + r6 @ 90", box - cutter(top, r, d, "csink", cs_r=cs_r, cs_ang=ang),
       V0 - PI * r * r * d - cone_extra)
report("depth == thickness", box - cutter(top, r, 20), V0 - PI * r * r * 20)
report("over the edge (a notch)", box - cutter(Plane((24, 0, 10), z_dir=(0, 0, -1)), r, d))

section("3. the two 'successes' the op refuses")
report("centre off the body: nothing removed", box - cutter(Plane((40, 0, 10), z_dir=(0, 0, -1)), r, d), V0)
plate = BODIES["plate_with_hole"]()
report("centre inside the existing hole: nothing removed",
       plate - cutter(Plane((0, 0, 5), z_dir=(0, 0, -1)), 2, 5), plate.volume)
report("r30 on a 50 mm face: an OPEN SHELL", box - cutter(top, 30, 8))

section("4. every flat face of every gauntlet body: a blind hole at its centre")
for name, make in BODIES.items():
    solid = make()
    for idx, face, c, n in planar_faces(solid):
        pl = Plane(origin=c, z_dir=(-n[0], -n[1], -n[2]))
        try:
            out = solid - cutter(pl, 2, 5)
            problems = inspector.health(out)
            dv = solid.volume - out.volume
            flag = "" if not problems and dv > 0 else f"  <-- {problems or 'no material removed'}"
            print(f"{name}.f{idx} removed {dv:.3f}{flag}")
        except Exception as e:
            print(f"{name}.f{idx} RAISED {type(e).__name__}: {str(e)[:100]}")

section("5. on the face? how thick underneath?")
top_face = box.faces().sort_by(Axis.Z)[-1]
for p in [(5, 5, 10), (25.0, 0, 10), (25.1, 0, 10), (5, 5, 10.5)]:
    print("  is_inside", p, top_face.is_inside(p))
ann = [f for f in plate.faces() if abs(f.normal_at(f.center()).Z) > 0.9 and f.center().Z > 0][0]
print("  annular face centre", [round(v, 3) for v in tuple(ann.center())],
      "is_inside:", ann.is_inside(ann.center()), "| (20, 0, z):", ann.is_inside((20, 0, ann.center().Z)))


def material_along(solid, origin, direction, span=1e4):
    o = Vector(*origin)
    dd = Vector(*direction).normalized()
    pieces = Edge.make_line(o - dd * 1e-3, o + dd * span).intersect(solid)
    segs = sorted((min(a, b), max(a, b)) for a, b in
                  (((e @ 0 - o).dot(dd), (e @ 1 - o).dot(dd)) for e in pieces.edges()))
    return [(round(a, 4), round(b, 4)) for a, b in segs]


print("  box top (5,5) down:", material_along(box, (5, 5, 10), (0, 0, -1)))
w = BODIES["wedge"]()
sl = [f for f in w.faces() if abs(f.normal_at(f.center()).X - 0.707) < 0.01][0]
c = sl.center()
n = sl.normal_at(c)
print("  wedge slanted face inward:", material_along(w, tuple(c), (-n.X, -n.Y, -n.Z)))

section("6. face_profile_plane coordinates read like a sketch's")
fpl = sk.face_profile_plane(top_face)
uv = fpl.to_local_coords(Vector(5, 7, 10))
print("  top face: (5, 7, 10) -> uv", [round(v, 3) for v in tuple(uv)][:2])
bot = box.faces().sort_by(Axis.Z)[0]
bpl = sk.face_profile_plane(bot)
print("  bottom face: (5, 7, -10) -> uv", [round(v, 3) for v in tuple(bpl.to_local_coords(Vector(5, 7, -10)))][:2],
      "| frame z", [round(v, 3) for v in tuple(bpl.z_dir)], "vs outward normal",
      [round(v, 3) for v in tuple(bot.normal_at(bot.center()))])
