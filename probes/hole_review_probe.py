"""What the kernel says about the Hole review's fixes (2026-09-06).

Run:  python probes/hole_review_probe.py

Every fix in the review of 5336c82 that touches geometry is measured here
BEFORE it is written (house rule 1). Sections:

  1  a THROUGH_MM (2 m) cutter removes exactly what the bbox-length one did
  2  the "nothing was cut" floor: what a real small hole removes, and what a
     cutter that misses leaves behind (is the difference exactly 0.0?)
  3  provenance: which feature owns a hole's bore face (measure must be able
     to drive `hole.diameter`), and its counterbore seat
  4  the marker frame's handedness on every face of a box
  5  the countersink cone height: the op's expression == the cutter's
"""
import math
import sys
import time

import build123d as b3d

sys.path.insert(0, ".")
import inspector                                       # noqa: E402
import provenance                                      # noqa: E402
import sketch as sk                                    # noqa: E402
from document import Document                          # noqa: E402
from tests.gauntlet import BODIES, planar_faces        # noqa: E402

PI = math.pi
OK, BAD = "ok  ", "BAD "


def say(*a):
    print(*a, flush=True)


# --------------------------------------------------------------- 1. through ---
say("\n1. THROUGH: a 2 m cutter vs today's bounding-box + 1 mm")
for name, make in BODIES.items():
    body = make()
    span = body.bounding_box().size.length + 1.0
    faces = [t for t in planar_faces(body)][:3]
    for _i, face, c, n in faces:
        pl = sk.face_profile_plane(face)
        if pl is None:
            continue
        loc = pl.to_local_coords(b3d.Vector(*c))
        try:
            _pl, centre, nn = sk.hole_frame(face, [loc.X, loc.Y])[:3]
        except Exception as e:
            say(f"   {name}: skipped ({str(e)[:60]})")
            continue
        into = nn * -1.0
        out = []
        for dep in (span, sk.THROUGH_MM):
            tool = sk.hole_cutter(pl, centre, into, 4.0, dep)
            try:
                res = body - tool
                out.append((round(body.volume - res.volume, 6), inspector.health(res)))
            except Exception as e:
                out.append(("EXC", str(e)[:60]))
        same = out[0][0] == out[1][0] and not out[0][1] and not out[1][1]
        say(f"   {OK if same else BAD}{name:18s} bbox={out[0][0]}  2m={out[1][0]} "
            f"health={out[0][1] or []}/{out[1][1] or []}")
        break                                   # one face per body is enough

# ------------------------------------------------------------ 2. nothing cut ---
say("\n2. NOTHING WAS CUT: the floor")
big = b3d.Box(200, 100, 50)
say(f"   body volume {big.volume:g} mm3 -> today's threshold 1e-6*V = {1e-6 * big.volume:g} mm3")
for d, dep in ((1.0, 1.0), (2.0, 3.0), (0.5, 0.5)):
    out = big - sk.hole_cutter(b3d.Plane.XY.offset(25), b3d.Vector(10, 10, 25),
                               b3d.Vector(0, 0, -1), d, dep)
    removed = big.volume - out.volume
    expect = PI * (d / 2) ** 2 * dep
    say(f"   D{d} x {dep}: removed {removed:.6f} (formula {expect:.6f}) "
        f"{'REFUSED today' if removed <= 1e-6 * big.volume else 'passes today'}")
miss = big - b3d.Box(1, 1, 1).moved(b3d.Pos(500, 0, 0))
say(f"   a cutter that misses entirely: difference = {big.volume - miss.volume!r} "
    f"(exactly 0.0? {big.volume - miss.volume == 0.0})")
tiny = b3d.Box(1e7 ** (1 / 3), 1e7 ** (1 / 3), 1e7 ** (1 / 3))
t2 = tiny - sk.hole_cutter(b3d.Plane.XY.offset(tiny.bounding_box().max.Z),
                           b3d.Vector(0, 0, tiny.bounding_box().max.Z),
                           b3d.Vector(0, 0, -1), 1.0, 1.0)
say(f"   1e7 mm3 body, D1 x 1 hole: removed {tiny.volume - t2.volume:.9f} "
    f"(formula {PI * 0.25:.9f})")

# ------------------------------------------------------------- 3. provenance ---
say("\n3. PROVENANCE: who owns a hole's bore face?")
d = Document(name="prov")
d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
d.add("h", "hole", {"face": "top", "at": [10, 5], "diameter": 6, "depth": 6,
                    "kind": "counterbore", "cbore_diameter": 12, "cbore_depth": 2}, ["b"])
say("   rebuild:", d.rebuild(), [f"{f.id}:{f.status}" for f in d.features])
part = d.result()
faces = provenance.picked_faces(d, "h", part)
for i, f in enumerate(faces):
    if f.geom_type != b3d.GeomType.CYLINDER:
        continue
    r = None
    try:
        r = f.wrapped and b3d.Face(f.wrapped).center()
    except Exception:
        pass
    surf = f.geom_type.name
    att = provenance.attribute_face(d, body_id="h", face_index=i)
    # the radius, straight off the cylinder
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    rad = BRepAdaptor_Surface(f.wrapped).Cylinder().Radius()
    say(f"   face {i} {surf} r={rad:.3f}: origin={att.get('origin')} "
        f"origin_op={att.get('origin_op')} sketch={att.get('sketch')} "
        f"feature={att.get('feature')} conf={att.get('confidence')}")

# ------------------------------------------------------------- 4. handedness ---
say("\n4. MARKER FRAME handedness on every face of a box")
box = b3d.Box(50, 50, 20)
for _i, face, c, n in planar_faces(box):
    pl = sk.face_profile_plane(face)
    nn = face.normal_at(face.center())
    hand_now = (pl.x_dir.cross(pl.y_dir)).dot(nn)          # today: z = the outward normal
    hand_new = (pl.x_dir.cross(pl.y_dir)).dot(pl.z_dir)    # proposed: the plane's own z
    say(f"   n=({n[0]:+.0f},{n[1]:+.0f},{n[2]:+.0f})  today={hand_now:+.1f} "
        f"{'LEFT-HANDED' if hand_now < 0 else ''}   proposed={hand_new:+.1f}")

# ----------------------------------------------------------------- 5. csink ---
say("\n5. COUNTERSINK cone height: the op's expression vs the cutter's")
for d_, cs_d, ang in ((6, 12, 90), (6, 12, 82), (4, 9.5, 100), (6, 6.001, 179)):
    a = (cs_d - d_) / 2.0 / math.tan(math.radians(ang / 2.0))
    b = (cs_d / 2.0 - d_ / 2.0) / math.tan(math.radians(ang / 2.0))
    say(f"   {OK if abs(a - b) < 1e-12 else BAD}D{d_} csink{cs_d}@{ang}: {a!r} vs {b!r}")

# --------------------------------------------------------------- 6. the cost ---
say("\n6. COST of material_depth on a plan (why it should be lazy)")
body = BODIES["fused_dprism_boss"]()
_i, face, c, n = planar_faces(body)[0]
pl = sk.face_profile_plane(face)
loc = pl.to_local_coords(b3d.Vector(*c))
_pl, centre, nn = sk.hole_frame(face, [loc.X, loc.Y])[:3]
t0 = time.perf_counter()
m = sk.material_depth(body, centre, nn * -1.0, sk.THROUGH_MM)
t1 = time.perf_counter()
say(f"   material_depth -> {m} in {(t1 - t0) * 1000:.0f} ms (this body is small; "
    f"the review measured 250-510 ms on esp32-remote)")
t0 = time.perf_counter()
v = body.volume
t1 = time.perf_counter()
say(f"   .volume -> {v:.1f} in {(t1 - t0) * 1000:.0f} ms (called 3x today)")
