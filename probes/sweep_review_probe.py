"""PROBE - review of the Sweep tool (36ee69c), 2026-09-23.

The brief's open questions, put to the KERNEL (the guard is bypassed with the
same `_sweep(..., transition=RIGHT)` call the op makes):

  A. The bend guard refuses `radius <= reach`, where reach is the profile's
     farthest point from its centre in ANY direction. A fold needs the
     profile to reach the bend's centre, which is ONE direction (in the
     path's plane, across the path). A flat strip bent across its thin side:
     refused by the guard - does the kernel build it right?
  B. The same for a sharp corner's mitre (reach * tan(turn/2)).
  C. The guard must still refuse the strip bent across its WIDE side.
  D. Obtuse / acute corners near the mitre limit (measured on 90 deg only).
  E. A ring (face with an off-centre hole): Sketch.center() vs where the
     kernel puts the path, and the Pappus check.
  F. A legacy smooth path_points spline starting perpendicular: Pappus.
  G. A sketch holding a closed shape AND an open path: revolve.

Run: python probes/memcap.py --gb 4 --timeout 900 -- python probes/sweep_review_probe.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d            # noqa: E402

import inspector                   # noqa: E402
import sketch as sk                # noqa: E402

RIGHT = b3d.Transition.RIGHT


def rect_face(w, h, cx=0.0, cy=0.0):
    return (b3d.Plane.XY * b3d.Pos(cx, cy) * b3d.Rectangle(w, h)).faces()[0]


def kernel(faces, wire):
    """What the op's kernel call gives with no guard: valid?, volume, A*L."""
    try:
        out = b3d.sweep(b3d.Sketch(children=list(faces)), path=wire, transition=RIGHT)
    except Exception as e:          # noqa: BLE001
        return f"kernel RAISES {type(e).__name__}"
    area = sum(f.area for f in faces)
    vol = out.volume
    return (f"valid={out.is_valid} health={inspector.health(out)[:1]} "
            f"vol={vol:.3f} A*L={area * wire.length:.3f} ratio={vol / (area * wire.length):.4f}")


def guard(faces, wire):
    try:
        g = sk.sweep_geometry(faces, wire)
        return f"guard OK (reach {g['reach']:.3f})"
    except ValueError as e:
        return f"guard REFUSES: {str(e)[:110]}"


def bend_path(R, up=10.0, run=10.0):
    """XZ plane: up +Z, a quarter bend of radius R toward +X, then along +X."""
    c = (R, 0, up)
    mid = (R - R * math.cos(math.radians(45)), 0, up + R * math.sin(math.radians(45)))
    return b3d.Wire([b3d.Line((0, 0, 0), (0, 0, up)),
                     b3d.ThreePointArc((0, 0, up), mid, (R, 0, up + R)),
                     b3d.Line((R, 0, up + R), (R + run, 0, up + R))]), c


print("== A. a 2 x 20 strip bent across its THIN side (x extent +-1), R = 5")
w, _c = bend_path(5)
thin = [rect_face(2, 20)]
print("  ", guard(thin, w))
print("  ", kernel(thin, w))
for R in (1.5, 1.1, 1.0, 0.9):
    w2, _ = bend_path(R)
    print(f"   R={R}: ", guard(thin, w2), "|", kernel(thin, w2))

print("== C. the same strip bent across its WIDE side (x extent +-10), R = 5")
wide = [rect_face(20, 2)]
print("  ", guard(wide, w))
print("  ", kernel(wide, w))

print("== B. the thin strip round a sharp 90 deg corner, legs 10 and 3")
corner = b3d.Wire([b3d.Line((0, 0, 0), (0, 0, 10)), b3d.Line((0, 0, 10), (3, 0, 10))])
print("  ", guard(thin, corner))
print("  ", kernel(thin, corner))
corner2 = b3d.Wire([b3d.Line((0, 0, 0), (0, 0, 10)), b3d.Line((0, 0, 10), (0.8, 0, 10))])
print("   leg 0.8:", guard(thin, corner2), "|", kernel(thin, corner2))

print("== D. circle r=3 round 45 / 135 deg corners (mitre 1.243 / 7.243)")
disc = [(b3d.Plane.XY * b3d.Circle(3)).faces()[0]]
for turn, legs in ((45, (0.8, 1.2, 1.3, 2.0)), (135, (6.0, 7.0, 7.3, 8.0))):
    for leg in legs:
        t = math.radians(turn)
        end = (leg * math.sin(t), 0, 10 + leg * math.cos(t))
        pw = b3d.Wire([b3d.Line((0, 0, 0), (0, 0, 10)), b3d.Line((0, 0, 10), end)])
        print(f"   turn {turn} leg {leg}: ", guard(disc, pw), "|", kernel(disc, pw))

print("== E. a ring: 20 x 10 plate with an off-centre r2 hole at x=+6")
ring = (b3d.Plane.XY * b3d.Rectangle(20, 10)) - (b3d.Plane.XY * b3d.Pos(6, 0) * b3d.Circle(2))
faces = ring.faces()
print("   Sketch.center():", b3d.Sketch(children=list(faces)).center(),
      " face.center():", faces[0].center())
straight = b3d.Wire([b3d.Line((0, 0, 0), (0, 0, 20))])
print("  ", guard(faces, straight), "|", kernel(faces, straight))
try:
    out = sk._sweep_solid(faces, straight, 0, True)
    bb = out.bounding_box()
    print(f"   op builds vol={out.volume:.3f} bbox x {bb.min.X:.3f}..{bb.max.X:.3f}")
except ValueError as e:
    print("   op REFUSES:", e)
curved, _ = bend_path(15)
print("   bent R15:", guard(faces, curved), "|", kernel(faces, curved))
try:
    print("   op on bent R15 vol:", round(sk._sweep_solid(faces, curved, 0, True).volume, 3))
except ValueError as e:
    print("   op on bent R15 REFUSES:", e)

print("== F. legacy smooth path_points, perpendicular start")
prof = b3d.Sketch(children=[b3d.Plane.XY * b3d.Circle(2)])
for pts in ([(0, 0, 0), (0, 0, 10), (5, 0, 20), (15, 0, 25)],
            [(0, 0, 0), (0, 0, 10), (5, 5, 20), (15, 0, 30)]):
    try:
        out = sk.sweep_sketch(prof, path_points=pts, smooth=True)
        print("   builds, vol", round(out.volume, 3))
    except ValueError as e:
        print("   REFUSED:", str(e)[:140])
    with b3d.BuildLine() as bl:
        b3d.Spline(*pts)
    spw = bl.wire()
    print("     start slant:", round(math.degrees(math.acos(abs(spw.tangent_at(0).Z))), 2),
          "|", kernel(prof.faces(), spw))

print("== G. a sketch with a rectangle AND an open path, revolved")
ents = [{"kind": "rectangle", "w": 4, "h": 6, "x": 10, "y": 0},
        {"kind": "path", "closed": False, "start": [-5, -5], "segments": [{"type": "line", "to": [5, 5]}]}]
mixed = sk.make_sketch(plane="XZ", entities=ents)
print("   faces:", len(mixed.faces()), "edges:", len(mixed.edges()), "paths:", len(sk.sketch_paths(mixed)))
for axis in ("v", "Z"):
    try:
        s = sk.revolve_sketch(mixed, axis=axis, angle=360)
        print(f"   revolve {axis}: vol {s.volume:.3f} solids {len(s.solids())} faces-only "
              f"{len(s.faces())} valid {s.is_valid}")
    except ValueError as e:
        print(f"   revolve {axis} REFUSED:", str(e)[:150])
closed_only = sk.make_sketch(plane="XZ", entities=ents[:1])
s = sk.revolve_sketch(closed_only, axis="Z", angle=360)
print(f"   closed only, revolve Z: vol {s.volume:.3f}")
