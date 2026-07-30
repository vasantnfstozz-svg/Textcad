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
import math
import build123d as b3d
from build123d import (
    Rectangle, Circle, Ellipse, Polygon, SlotOverall, RegularPolygon,
    Pos, Axis, Plane, BuildLine, BuildSketch, Spline, Polyline, Line,
    ThreePointArc, make_face,
    extrude as _extrude, revolve as _revolve, loft as _loft, sweep as _sweep,
)

_PLANES = {"XY": Plane.XY, "XZ": Plane.XZ, "YZ": Plane.YZ}
_AXES = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}


def _to_bool(v, name: str) -> bool:
    """Strict boolean coercion. bool('false') is True in Python — a UI that
    sends the STRING 'false' must not silently flip a flag (this exact trap
    doubled every dialog-driven extrude before it was caught)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes"):
            return True
        if s in ("false", "0", "no", ""):
            return False
    raise ValueError(f"{name} must be true or false, got {v!r}")


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
        # length is the OVERALL end-to-end size — exactly what the sketcher
        # canvas draws and dimensions (SlotCenterToCenter would add height).
        length, height = float(e["length"]), float(e["height"])
        if length <= height:
            raise ValueError(f"slot length ({length}) must be greater than its "
                             f"height ({height}) — length is end-to-end overall")
        s = SlotOverall(length, height)
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


def _as_sketch(shape):
    """Normalize to a real Sketch. Combining DISJOINT entities (e.g. two
    separate bolt-hole circles) returns a Compound, which downstream code
    would then mistake for a (failed) solid — rewrap its faces instead."""
    if isinstance(shape, b3d.Sketch):
        return shape
    return b3d.Sketch(shape.faces())


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
    return _as_sketch(pl * _compose(entities or []))


def resolve_face(solid, face_center: list, face_normal: list | None = None):
    """Find the face of `solid` a user picked, by GEOMETRY (nearest center,
    same-facing normal) — so a stored pick survives parameter changes instead
    of breaking like a face index would. Shared by sketch_on_face and the
    face-outline projection."""
    faces = solid.faces()
    if not faces:
        raise ValueError("solid has no faces")
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

    return min(faces, key=score)


def face_plane(face, ang_tol_deg: float = 1.0, dist_tol: float = 1e-2):
    """A build123d Plane if `face` is geometrically FLAT — even when the kernel
    stores it as a BSPLINE / BEZIER / EXTRUSION surface. Taper, loft and sweep
    routinely produce a wall that is dead flat yet NOT typed PLANE; those must
    still be sketchable/extrudable. A surface is planar ⇔ its normal is constant
    and its points are coplanar. Returns None for genuinely curved faces."""
    from build123d import Plane
    try:
        c = face.center()
    except Exception:
        return None
    if face.geom_type == b3d.GeomType.PLANE:
        try:
            return Plane(face)
        except Exception:
            pass
    normals, pts = [], []
    for u in (0.15, 0.5, 0.85):
        for v in (0.15, 0.5, 0.85):
            try:
                p = face.position_at(u, v)
                n = face.normal_at(p)
                normals.append((n.X, n.Y, n.Z)); pts.append((p.X, p.Y, p.Z))
            except Exception:
                pass
    if len(normals) < 3:
        return None
    n0 = normals[0]
    cos_tol = math.cos(math.radians(ang_tol_deg))
    for n in normals[1:]:                       # every normal must be parallel
        if abs(n0[0]*n[0] + n0[1]*n[1] + n0[2]*n[2]) < cos_tol:
            return None
    for p in pts:                               # and every point coplanar
        if abs((p[0]-c.X)*n0[0] + (p[1]-c.Y)*n0[1] + (p[2]-c.Z)*n0[2]) > dist_tol:
            return None
    try:
        return Plane(origin=(c.X, c.Y, c.Z), z_dir=n0)
    except Exception:
        return None


def face_outline_2d(solid, face_center: list, face_normal: list | None = None):
    """Project a picked PLANAR face's boundary into its own plane's local 2D
    coordinates — the outer wire plus any inner wires (holes). Returned in the
    SAME frame the sketch entities are placed in, so the sketcher can show the
    selected surface as reference geometry to draw against.

    -> {"outer": [[x,y],...], "holes": [[[x,y],...],...], "planar": bool}
    """
    face = resolve_face(solid, face_center, face_normal)
    pl = face_plane(face)
    if pl is None:                              # genuinely curved — can't project
        return {"outer": [], "holes": [], "planar": False}

    def project(wire):
        poly = []
        for e in wire.edges():
            steps = 2 if e.geom_type == b3d.GeomType.LINE else 24
            for i in range(steps + 1):
                loc = pl.to_local_coords(e @ (i / steps))
                poly.append([round(loc.X, 3), round(loc.Y, 3)])
        return poly

    outer = face.outer_wire()
    holes = [project(w) for w in face.wires() if w.length != outer.length]

    def vec(v):
        return [round(v.X, 4), round(v.Y, 4), round(v.Z, 4)]

    # the plane's world frame, so a UI can draw ghost geometry in place
    frame = {"origin": vec(pl.origin), "x_dir": vec(pl.x_dir),
             "y_dir": vec(pl.y_dir), "z_dir": vec(pl.z_dir)}
    return {"outer": project(outer), "holes": holes, "planar": True,
            "frame": frame}


def sketch_on_face(solid, face_center: list, face_normal: list | None = None,
                   entities: list | None = None):
    """Draw a sketch ON a face of an existing solid (the Fusion workflow:
    pick a face, sketch, extrude a boss/cut). The face is resolved by GEOMETRY
    at every rebuild — the face whose center is nearest `face_center` (and whose
    normal best matches `face_normal`) — so it survives parameter changes
    instead of breaking like a stored face index would."""
    face = resolve_face(solid, face_center, face_normal)
    pl = face_plane(face)
    if pl is None:
        raise ValueError(
            f"sketch_on_face: the picked face is {face.geom_type.name} and not "
            f"flat — a sketch needs a PLANAR face. For a slot/pocket in a curved "
            f"surface, sketch on a principal plane (offset to the surface) and "
            f"extrude-cut through the body instead.")
    return _as_sketch(pl * _compose(entities or []))


# ---------------------------------------------------------------------------
# Sketch-consuming operations -> solids
# ---------------------------------------------------------------------------

def _tapered_extrude(profile, amount: float, taper: float):
    """extrude() with a FRIENDLY error when a steep taper makes the walls
    collapse or collide (e.g. a profile with a hole) — OCCT otherwise raises a
    bare RuntimeError('Unexpected result type')."""
    try:
        return _extrude(profile, amount=amount, taper=taper)
    except RuntimeError as e:
        if taper:
            raise ValueError(
                f"taper {taper}° is too steep for this profile at "
                f"{abs(amount)}mm — the walls collapse or collide before full "
                f"height; reduce the taper or the distance") from e
        raise


def extrude_face(solid, face_center: list, face_normal: list | None = None,
                 amount: float = 10.0, taper: float = 0.0, flip: bool = False):
    """Extrude a planar FACE of an existing solid (the Fusion workflow: click a
    face, press Extrude, pull the arrow). The face is resolved by GEOMETRY at
    every rebuild (nearest center + matching normal), so the pick survives
    parameter changes. Returns ONLY the extruded prism — combine it with the
    body via fuse (boss) or cut (pocket, with a negative/into amount).
    The face's exact outline is used — holes and curved edges included."""
    face = resolve_face(solid, face_center, face_normal)
    if face_plane(face) is None:               # flat BSPLINE/BEZIER walls are OK
        raise ValueError(
            f"extrude_face: the picked face is {face.geom_type.name} and not "
            f"flat — only planar faces can be extruded.")
    a = float(amount)
    if _to_bool(flip, "flip"):
        a = -a
    return _tapered_extrude(face, a, float(taper or 0.0))


def extrude_sketch(sketch, amount: float, both: bool = False,
                   amount2: float = 0.0, taper: float = 0.0, flip: bool = False):
    """Pull a sketch straight, normal to its plane, into a solid (Fusion-style
    Extrude). Direction:
      * one side   : amount  (flip = extrude the other way)
      * symmetric  : both=True — extrude `amount` to EACH side
      * two sides  : amount one way + amount2 the opposite way
    `taper` degrees tapers the walls (positive narrows as it extrudes)."""
    a = float(amount)
    if _to_bool(flip, "flip"):
        a = -a
    t = float(taper or 0.0)
    if _to_bool(both, "both"):
        try:
            return _extrude(sketch, amount=a, both=True, taper=t)
        except RuntimeError as e:
            if t:
                raise ValueError(
                    f"taper {t}° is too steep for this profile at {abs(a)}mm — "
                    f"the walls collapse or collide before full height; reduce "
                    f"the taper or the distance") from e
            raise
    solid = _tapered_extrude(sketch, a, t)
    amt2 = float(amount2 or 0.0)
    if amt2 > 0:                      # two-sided: opposite direction by amt2
        s2 = -1.0 if a >= 0 else 1.0
        solid = solid + _tapered_extrude(sketch, s2 * amt2, t)
    return solid


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
    smooth = _to_bool(smooth, "smooth")
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
SKETCH_PRODUCERS = {"sketch", "sketch_on_face"}


def is_sketch(obj) -> bool:
    return isinstance(obj, b3d.Sketch)
