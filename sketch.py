"""
sketch.py — E2: the 2D sketch system, the heart of manual CAD.

A SKETCH is a 2D profile drawn on a plane, built from entities (rectangles,
circles, polygons, slots, ellipses) each added or subtracted. Sketches are
then turned into solids by the sketch-consuming operations:

    sketch  -> extrude  (straight pull normal to the plane)
            -> revolve  (spin around an axis)
            -> loft     (blend between 2+ sketches on parallel planes)
            -> sweep    (drag a profile along a path)

Everything is EXPLICITLY dimensioned (a rectangle is 40x20 at (x,y)); there is
no constraint solver in this version — that is a later stage. All API used
here is confirmed against build123d 0.11.1.
"""

from __future__ import annotations
import build123d as b3d
from build123d import (
    Rectangle, Circle, Ellipse, Polygon, SlotCenterToCenter, RegularPolygon,
    Pos, Axis, Plane, BuildLine, BuildSketch, Spline, Polyline, Line,
    ThreePointArc, make_face,
    extrude as _extrude, revolve as _revolve, loft as _loft, sweep as _sweep,
)

_PLANES = {"XY": Plane.XY, "XZ": Plane.XZ, "YZ": Plane.YZ}
_AXES = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}


# ---------------------------------------------------------------------------
# 2D entities -> a composite Sketch on a plane
# ---------------------------------------------------------------------------

def _entity(e: dict):
    """One 2D primitive, positioned in the sketch plane's local coordinates."""
    k = e.get("kind")
    x, y = float(e.get("x", 0)), float(e.get("y", 0))
    rot = float(e.get("rotation", 0))
    if k == "rectangle":
        s = Rectangle(float(e["w"]), float(e["h"]))
    elif k == "circle":
        s = Circle(float(e["r"]))
    elif k == "ellipse":
        s = Ellipse(float(e["rx"]), float(e["ry"]))
    elif k == "slot":
        s = SlotCenterToCenter(float(e["length"]), float(e["height"]))
    elif k == "regular_polygon":
        s = RegularPolygon(float(e["radius"]), int(e["sides"]))
    elif k == "polygon":
        pts = [(float(p[0]), float(p[1])) for p in e["points"]]
        if len(pts) < 3:
            raise ValueError("polygon entity needs >= 3 points")
        s = Polygon(*pts)
    elif k == "path":
        s = _path_face(e)
    else:
        raise ValueError(f"unknown sketch entity kind '{k}'")
    s = Pos(x, y) * s
    if rot:
        s = s.rotate(Axis.Z, rot)
    return s


def _compose(entities: list):
    """Combine entities (add/subtract) into a 2D sketch in local coords."""
    result = None
    for e in entities:
        shape = _entity(e)
        mode = e.get("mode", "add")
        if result is None:
            if mode == "subtract":
                raise ValueError("sketch: first entity cannot be a subtraction")
            result = shape
        else:
            result = result - shape if mode == "subtract" else result + shape
    if result is None:
        raise ValueError("sketch has no entities")
    return result


def _path_face(e: dict):
    """A closed profile chained from LINE and ARC segments — the free-drawing
    tool. Format:
        {"kind": "path", "start": [x, y], "segments": [
            {"type": "line", "to": [x, y]},
            {"type": "arc", "via": [x, y], "to": [x, y]},   # 3-point arc
        ]}
    The profile auto-closes with a straight line back to the start."""
    segs = e.get("segments") or []
    if not segs:
        raise ValueError("path entity needs at least 1 segment")
    start = tuple(float(v) for v in (e.get("start") or [0, 0]))
    with BuildSketch() as sk:
        with BuildLine():
            cur = start
            for s in segs:
                to = tuple(float(v) for v in s["to"])
                if s.get("type") == "arc":
                    via = tuple(float(v) for v in s["via"])
                    ThreePointArc(cur, via, to)
                else:
                    Line(cur, to)
                cur = to
            if abs(cur[0] - start[0]) > 1e-6 or abs(cur[1] - start[1]) > 1e-6:
                Line(cur, start)                        # auto-close
        make_face()
    return sk.sketch


def make_sketch(plane: str = "XY", offset: float = 0.0,
                entities: list | None = None):
    """Compose entities into one Sketch placed on a principal plane.

    plane: "XY", "XZ" or "YZ".  offset: shift the plane along its normal.
    entities: list of {"kind":..., ...params, "mode":"add"|"subtract"}.
    The first entity must be additive."""
    if plane not in _PLANES:
        raise ValueError('sketch: plane must be "XY", "XZ" or "YZ"')
    pl = _PLANES[plane]
    if offset:
        pl = pl.offset(float(offset))
    return pl * _compose(entities or [])


def sketch_on_face(solid, face_center: list, face_normal: list | None = None,
                   entities: list | None = None):
    """Draw a sketch ON a face of an existing solid (the Fusion workflow:
    pick a face, sketch, extrude a boss/cut). The face is resolved by GEOMETRY
    at every rebuild — the face whose center is nearest `face_center` (and whose
    normal best matches `face_normal`) — so it survives parameter changes
    instead of breaking like a stored face index would."""
    faces = solid.faces()
    if not faces:
        raise ValueError("sketch_on_face: solid has no faces")
    cx, cy, cz = (float(v) for v in face_center)

    def score(f):
        c = f.center()
        d = (c.X - cx) ** 2 + (c.Y - cy) ** 2 + (c.Z - cz) ** 2
        if face_normal:
            try:
                n = f.normal_at(f.center())
                align = (n.X * face_normal[0] + n.Y * face_normal[1]
                         + n.Z * face_normal[2])
                d += (1.0 - align) * 25.0          # nudge toward same-facing
            except Exception:
                pass
        return d

    face = min(faces, key=score)
    from build123d import Plane
    return Plane(face) * _compose(entities or [])


# ---------------------------------------------------------------------------
# Sketch-consuming operations -> solids
# ---------------------------------------------------------------------------

def extrude_sketch(sketch, amount: float, both: bool = False):
    """Pull a sketch straight, normal to its plane, into a solid."""
    return _extrude(sketch, amount=float(amount), both=bool(both))


def revolve_sketch(sketch, axis: str = "Z", angle: float = 360.0):
    """Spin a sketch around a principal axis to make a solid of revolution.
    The sketch must sit entirely on one side of the axis (e.g. a profile on the
    XZ plane at positive X, revolved about Z)."""
    if axis not in _AXES:
        raise ValueError('revolve: axis must be "X", "Y" or "Z"')
    return _revolve(sketch, axis=_AXES[axis], revolution_arc=float(angle))


def loft_sketches(sketches: list):
    """Blend between two or more sketches (usually on parallel, offset planes)
    to make a smoothly-transitioning solid."""
    if len(sketches) < 2:
        raise ValueError("loft needs at least 2 sketches")
    return _loft(list(sketches))


def sweep_sketch(sketch, path_points: list, smooth: bool = False):
    """Drag a profile sketch along a path defined by 3D points [[x,y,z],...].
    smooth=True fits a spline through the points; otherwise straight segments."""
    pts = [(float(p[0]), float(p[1]), float(p[2])) for p in path_points]
    if len(pts) < 2:
        raise ValueError("sweep path needs >= 2 points")
    with BuildLine() as bl:
        if smooth and len(pts) >= 3:
            Spline(*pts)
        else:
            Polyline(*pts)
    return _sweep(sketch, path=bl.line)


# ops that produce a 2D sketch (not a solid) — the document engine checks these
# for area, not solid health
SKETCH_PRODUCERS = {"sketch"}


def is_sketch(obj) -> bool:
    return isinstance(obj, b3d.Sketch)
