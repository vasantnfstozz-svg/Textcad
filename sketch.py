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
    Pos, Axis, Plane, BuildLine, Spline, Polyline,
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
    else:
        raise ValueError(f"unknown sketch entity kind '{k}'")
    s = Pos(x, y) * s
    if rot:
        s = s.rotate(Axis.Z, rot)
    return s


def make_sketch(plane: str = "XY", offset: float = 0.0,
                entities: list | None = None):
    """Compose entities into one Sketch placed on a principal plane.

    plane: "XY", "XZ" or "YZ".  offset: shift the plane along its normal.
    entities: list of {"kind":..., ...params, "mode":"add"|"subtract"}.
    The first entity must be additive."""
    entities = entities or []
    if plane not in _PLANES:
        raise ValueError('sketch: plane must be "XY", "XZ" or "YZ"')
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
    pl = _PLANES[plane]
    if offset:
        pl = pl.offset(float(offset))
    return pl * result


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
