"""probes/mirror_probe.py — what the kernel does with a MIRROR of a feature or
a body (LAUNCH-PLAN.md rule 1: probe before you build; specs/mirror.md). Run
from the repo root:

    set PYTHONIOENCODING=utf-8
    C:\\Python314\\python.exe probes\\mirror_probe.py

The idea under test: Fusion's Mirror of a FEATURE is the feature's DELTA
(probes/pattern_probe.py §1: before − after = what it removed, after − before
= what it added) reflected across a plane and applied to the body's current
state — one copy, a reflection instead of a rotation. A mirror of a BODY is
the body fused with its reflection (Fusion's Join).

FOUND 2026-09-06 (each drove a decision in pattern.py / toolplan.plan_mirror):
see the printed sections §1–§10; the findings are written up in the docstring
of pattern.mirror and in specs/mirror.md once measured.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build123d as b3d                                    # noqa: E402
from build123d import Box, Cylinder, Plane, Pos, Vector    # noqa: E402

import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402
from gauntlet import BODIES, planar_faces                   # noqa: E402

PI = math.pi
PLUG = PI * 9 * 12
TOP = dict(face_center=[0.0, 0.0, 6.0], face_normal=[0.0, 0.0, 1.0])


def say(tag, *xs):
    print(f"§{tag}", *xs)


def health(p):
    return inspector.health(p, check_valid=False)


def plane(origin, normal):
    return Plane(origin=Vector(*origin), z_dir=Vector(*normal))


# §1 --------------------------------------------------------------------------
b = Pos(20, 0, 0) * Box(10, 10, 10)
m = b.mirror(Plane.YZ)
say(1, "type", type(m).__name__, "valid", m.is_valid, "vol", round(m.volume, 6),
    "centre", [round(c, 6) for c in m.center()], "health", health(m))
m2 = b.mirror(plane((5, 0, 0), (1, 0, 0)))
say(1, "offset plane x=5 -> centre", [round(c, 6) for c in m2.center()], "valid", m2.is_valid)
m3 = b.mirror(plane((5, 0, 0), (-1, 0, 0)))
say(1, "same plane, normal flipped -> centre", [round(c, 6) for c in m3.center()])

# §2 --------------------------------------------------------------------------
box = Box(80, 80, 12)
holed = sk.hole(box, **TOP, at=[20, 0], diameter=6, depth=1, through=True)
removed = box - holed
img = removed.mirror(Plane.YZ)
out = holed - img
say(2, "removed by the image", round(holed.volume - out.volume, 6), "one plug", round(PLUG, 6),
    "image centre", [round(c, 6) for c in img.center()], "health", health(out),
    "solids", len(out.solids()))

# §3 --------------------------------------------------------------------------
through = removed.mirror(plane((20, 0, 0), (1, 0, 0)))      # the hole's own axis plane
out3 = holed - through
say(3, "plane through the seed removes", repr(holed.volume - out3.volume),
    "(image & seed).volume", round((through & removed).volume, 6))

# §4 --------------------------------------------------------------------------
off = removed.mirror(plane((50, 0, 0), (1, 0, 0)))          # image at x = 80: off the plate
out4 = holed - off
say(4, "plane off the body removes", repr(holed.volume - out4.volume),
    "(image & seed).volume", round((off & removed).volume, 6))

# §5 --------------------------------------------------------------------------
boss = Cylinder(5, 8).move(b3d.Location((20, 0, 10)))
bossed = box + boss
added = bossed - box
out5 = bossed + added.mirror(Plane.YZ)
say(5, "boss: added", round(out5.volume - bossed.volume, 6), "one boss", round(PI * 25 * 8, 6),
    "health", health(out5))
corner = [e for e in box.edges().filter_by(b3d.Axis.Z) if e.center().X > 0 and e.center().Y > 0]
fil = box.fillet(3, corner)
sliver = box - fil                                            # what the fillet took away
out5b = fil - sliver.mirror(Plane.YZ)
say(5, "fillet: faces", len(fil.faces()), "->", len(out5b.faces()),
    "removed", round(fil.volume - out5b.volume, 6), "one sliver", round(sliver.volume, 6),
    "health", health(out5b))

# §6 --------------------------------------------------------------------------
half = Pos(20, 0, 0) * Box(40, 30, 12)                       # x in [0, 40]
join = half + half.mirror(plane((40, 0, 0), (1, 0, 0)))      # across its own +x face
say(6, "join across +x face: vol", round(join.volume, 6), "= 2x", round(2 * half.volume, 6),
    "solids", len(join.solids()), "health", health(join), "faces", len(join.faces()))
apart = half + half.mirror(plane((50, 0, 0), (1, 0, 0)))
say(6, "join across x=50 (10 mm off): solids", len(apart.solids()), "health", health(apart),
    "type", type(apart).__name__)

# §7 --------------------------------------------------------------------------
selfie = half + half.mirror(plane((20, 0, 0), (1, 0, 0)))    # its own mid-plane
say(7, "mid-plane join: vol", round(selfie.volume, 6), "= body", round(half.volume, 6),
    "solids", len(selfie.solids()), "health", health(selfie))

# §8 --------------------------------------------------------------------------
tangent = holed - removed.mirror(plane((28.5, 0, 0), (1, 0, 0)))   # image centre 37, r 3: touches x = 40
say(8, "tangent image: is_valid", tangent.is_valid, "health", health(tangent),
    "removed", round(holed.volume - tangent.volume, 6))
notch = holed - removed.mirror(plane((30.5, 0, 0), (1, 0, 0)))     # image centre 41, r 3: straddles x = 40
say(8, "straddling image: health", health(notch), "removed", round(holed.volume - notch.volume, 6))

# §9 --------------------------------------------------------------------------
wedge = BODIES["wedge"]()
faces = planar_faces(wedge)
tilted = next((f for _, f, _, n in faces
               if all(abs(abs(n[i]) - 1) > 1e-3 for i in range(3))), None)
if tilted is not None:
    c = b3d.Face(tilted.outer_wire()).center()
    n = tilted.normal_at(tilted.center())
    doubled = wedge + wedge.mirror(plane(tuple(c), tuple(n)))          # a BODY across its slope
    say(9, "wedge body across its slope: vol", round(doubled.volume, 6), "= 2x", round(2 * wedge.volume, 6),
        "solids", len(doubled.solids()), "health", health(doubled), "normal", [round(x, 3) for x in n])
    base = max((f for _, f, _, _ in faces), key=lambda f: f.area)
    bc, bn = base.center(), base.normal_at(base.center())
    mid = wedge.bounding_box().center()
    try:
        wh = sk.hole(wedge, face_center=list(bc), face_normal=list(bn), at=[3, 0],
                     diameter=2, depth=1, through=True)
        rem = wedge - wh
        out9 = wh - rem.mirror(plane(tuple(mid), tuple(n)))             # a hole across a TILTED mid-plane
        say(9, "hole across a tilted plane through the centre: removed", round(wh.volume - out9.volume, 6),
            "one plug", round(rem.volume, 6), "health", health(out9))
    except ValueError as e:
        say(9, "hole refused:", e)
else:
    say(9, "wedge has no tilted face?", [n for _, _, _, n in faces])

# §10 -------------------------------------------------------------------------
for name, mk in sorted(BODIES.items()):
    solid = mk()
    fs = planar_faces(solid)
    _, face, _, normal = max(fs, key=lambda t: t[1].area)
    pl = sk.face_profile_plane(face)
    bb = face.bounding_box()
    span = min(s for s in (bb.size.X, bb.size.Y, bb.size.Z) if s > 1e-6)
    loc = pl.to_local_coords(face.center())
    try:
        h = sk.hole(solid, face_center=list(face.center()), face_normal=list(normal),
                    at=[loc.X + span * 0.25, loc.Y], diameter=3, depth=1, through=True)
    except ValueError as e:
        say(10, name, "hole refused:", str(e)[:80])
        continue
    rem = solid - h
    mid = solid.bounding_box().center()
    res = []
    for ax, nv in (("X", (1, 0, 0)), ("Y", (0, 1, 0)), ("Z", (0, 0, 1))):
        try:
            o = h - rem.mirror(plane(tuple(mid), nv))
            d = h.volume - o.volume
            res.append(f"{ax}: removed {d if abs(d) < 1e-3 else round(d, 4)!r} health {health(o)}")
        except Exception as e:                                  # noqa: BLE001
            res.append(f"{ax}: KERNEL {type(e).__name__}: {e}")
    say(10, name, "| plug", round(rem.volume, 4), "|", " | ".join(res))
