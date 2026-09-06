"""The OPERATION GAUNTLET — a reusable corpus of nasty-but-legal bodies plus
the invariant every modeling operation must satisfy on every one of them.

WHY THIS EXISTS
A CAD operation is never "one feature": it is the feature TIMES every kind of
geometry a user can feed it. Extrude+taper passed on a box and shipped, then
failed on a pentagon face of a FUSED body (one taper direction only) — because
fusing a tapered body leaves straight BSPLINE seam edges that OCCT's 2D offset
mishandles. Testing an op once tests one cell of a large grid.

HOW TO USE IT (for the next op — fillet, revolve, shell, pattern, …)

    from tests.gauntlet import BODIES, planar_faces, assert_op

    for name, make in BODIES.items():
        solid = make()
        for idx, face, center, normal in planar_faces(solid):
            for param in (...):
                assert_op(f"{name}.f{idx} p={param}",
                          lambda: my_op(solid, center, normal, param))

`assert_op` encodes the contract: an operation either produces a HEALTHY solid
or raises a FRIENDLY ValueError. A raw kernel exception reaching the caller is
itself a failure — the user must never see Standard_NoSuchObject.

Every real bug adds its geometry here, so the corpus only grows.
"""
from __future__ import annotations

import build123d as b3d
from build123d import (Plane, Rectangle, Circle, RegularPolygon, Polygon,
                       Pos, extrude)

import inspector
import sketch as sk


# ---------------------------------------------------------------------------
# The corpus. Each entry returns a fresh solid (never share build123d objects
# between cases — an op may mutate topology in place).
# ---------------------------------------------------------------------------

def _box():
    """the easy case everything is accidentally developed against"""
    return extrude(Plane.XY * Rectangle(50, 50), amount=30)


def _wedge():
    """slanted + pentagon faces: a chamfered corner, no right angle to lean on"""
    prof = Polygon((-25, -20), (25, -20), (25, 5), (10, 20), (-25, 20),
                   align=None)
    return extrude(Plane.XY * prof, amount=50)


def _hex_prism():
    return extrude(Plane.XY * RegularPolygon(30, 6), amount=25)


def _plate_with_hole():
    """a face carrying an INNER wire — taper flips the inner offset direction"""
    return extrude(Plane.XY * (Rectangle(60, 60) - Circle(10)), amount=10)


def _l_bracket():
    """NON-CONVEX outline (a reflex corner) — offsets can self-intersect"""
    prof = Polygon((0, 0), (60, 0), (60, 20), (20, 20), (20, 50), (0, 50),
                   align=None)
    return extrude(Plane.XY * prof, amount=30)


def _cylinder():
    """planar end caps on a body whose side face must be refused, not crash"""
    return b3d.Cylinder(25, 40)


def _fused_taper_seam():
    """THE REGRESSION BODY (2026-07-31): a box fused with a FLARING tapered
    boss. The fuse leaves the box's side faces carrying straight BSPLINE seam
    edges — geometry that made an inward taper fail while outward worked."""
    base = extrude(Plane.XY * Rectangle(50, 50), amount=30)
    boss = extrude(Plane((0, 0, 30)) * Rectangle(40, 40), amount=20, taper=-8)
    return base + boss


def _fused_dprism_boss():
    """a NARROWING tapered boss (the DPrism code path) fused onto a box —
    the sibling of _fused_taper_seam with the other taper sign"""
    base = extrude(Plane.XY * Rectangle(50, 50), amount=20)
    boss = extrude(Plane((0, 0, 20)) * Rectangle(30, 30), amount=15, taper=20)
    return base + boss


BODIES = {
    "box": _box,
    "wedge": _wedge,
    "hex_prism": _hex_prism,
    "plate_with_hole": _plate_with_hole,
    "l_bracket": _l_bracket,
    "cylinder": _cylinder,
    "fused_taper_seam": _fused_taper_seam,
    "fused_dprism_boss": _fused_dprism_boss,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def planar_faces(solid):
    """[(index, face, center_xyz, normal_xyz)] for every FLAT face — including
    flat-but-BSPLINE ones, which are legal picks (see sketch.face_plane)."""
    out = []
    for i, f in enumerate(solid.faces()):
        if sk.face_plane(f) is None:
            continue                                  # genuinely curved
        try:
            c = f.center()
            n = f.normal_at(c)
        except Exception:
            continue
        out.append((i, f, [c.X, c.Y, c.Z], [n.X, n.Y, n.Z]))
    return out


def face_edge_kinds(face):
    """geom types around a face's outer wire — the discriminator that mattered
    ('BSPLINE' present => the fragile offset path)"""
    try:
        return [e.geom_type.name for e in face.outer_wire().edges()]
    except Exception:
        return []


class GauntletFailure(AssertionError):
    pass


def assert_op(label: str, call, allow_failure: bool = True):
    """THE CONTRACT. Run `call()` and require one of:
      * a healthy solid (manifold, positive volume), or
      * a friendly ValueError explaining what to change (only if allowed).
    Anything else — a kernel exception type, an empty/invalid solid — fails.

    Returns the solid on success, else None.
    """
    try:
        result = call()
    except ValueError as e:
        if not allow_failure:
            raise GauntletFailure(f"{label}: refused but must succeed — {e}")
        msg = str(e)
        if len(msg) < 20:
            raise GauntletFailure(f"{label}: unhelpful error message {msg!r}")
        # a friendly message names the operation's own vocabulary, never the
        # kernel's internals
        for leak in ("TopoDS", "NCollection", "Standard_", "BRep"):
            if leak in msg and "taper" not in msg.lower():
                raise GauntletFailure(
                    f"{label}: kernel jargon leaked to the user: {msg[:120]}")
        return None
    except Exception as e:                     # noqa: BLE001 — that IS the bug
        raise GauntletFailure(
            f"{label}: raw {type(e).__name__} reached the caller — every "
            f"failure must arrive as a friendly ValueError: {str(e)[:120]}")
    if result is None:
        raise GauntletFailure(f"{label}: returned None")
    problems = inspector.health(result)
    if problems:
        raise GauntletFailure(f"{label}: unhealthy solid — {problems}")
    if result.volume <= 0:
        raise GauntletFailure(f"{label}: non-positive volume {result.volume}")
    return result


def holed_faces(name: str, diameter: float = 3.0):
    """(solid, [(face index, face, the body WITH a through hole a quarter-span
    from the face's centre, the face's span)]) for every flat face of a corpus
    body — the SEED the Pattern and Mirror gauntlets repeat. A face that refuses
    the hole is skipped: that is Hole's own gauntlet's business."""
    solid = BODIES[name]()
    cases = []
    for idx, face, _centre, normal in planar_faces(solid):
        pl = sk.face_profile_plane(face)
        bb = face.bounding_box()
        span = min(s for s in (bb.size.X, bb.size.Y, bb.size.Z) if s > 1e-6)
        c = pl.to_local_coords(face.center())          # a quarter-span from the FACE centre
        try:                                           # (the frame's origin is the world's foot)
            holed = sk.hole(solid, face_center=list(face.center()), face_normal=list(normal),
                            at=[c.X + span * 0.25, c.Y], diameter=diameter, depth=1, through=True)
        except ValueError:
            continue
        cases.append((idx, face, holed, span))
    return solid, cases
