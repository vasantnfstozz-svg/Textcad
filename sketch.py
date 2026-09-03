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
import re
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

# ---------------------------------------------------------------------------
# What each entity kind is DIMENSIONED by
#
# The feature tree renders its editable rows from this, so a sketch shows
# "width 40 / height 20" instead of a wall of raw JSON. It lives here, next to
# _entity(), because that is the only other place that knows an entity's field
# names — and a drift test asserts every kind _entity() accepts appears here.
#
# (key, label, unit). `unit` is a display hint only; everything is mm/deg.
# ---------------------------------------------------------------------------

ENTITY_FIELDS = {
    "rectangle":       [("w", "width", "mm"), ("h", "height", "mm")],
    "circle":          [("r", "radius", "mm")],
    "ellipse":         [("rx", "radius X", "mm"), ("ry", "radius Y", "mm")],
    "slot":            [("length", "length (overall)", "mm"),
                        ("height", "height", "mm")],
    "regular_polygon": [("radius", "radius", "mm"),
                        ("sides", "sides", "count")],
    # geometry lives in a coordinate list, not in dimensions: the tree shows a
    # summary and sends the user to the sketch editor rather than 40 numbers
    "polygon":         [],
    "path":            [],
}

# every entity can be placed and turned
ENTITY_COMMON = [("x", "x", "mm"), ("y", "y", "mm"),
                 ("rotation", "angle", "deg")]

# kinds where a DIAMETER row is offered next to the radius: a machinist reads a
# bore as a diameter, and the user asked for exactly this ("i can able to change
# outer diameter and inner diameter")
ENTITY_DIAMETER = {"circle": "r", "regular_polygon": "radius"}

# entities whose shape is a coordinate list -> what to count in the summary
ENTITY_GEOMETRY = {"polygon": "points", "path": "segments"}


def entity_schema() -> dict:
    """JSON-safe description of every entity kind, for the UI."""
    return {
        "fields": {k: [{"key": a, "label": b, "unit": c} for a, b, c in v]
                   for k, v in ENTITY_FIELDS.items()},
        "common": [{"key": a, "label": b, "unit": c} for a, b, c in
                   ENTITY_COMMON],
        "diameter": ENTITY_DIAMETER,
        "geometry": ENTITY_GEOMETRY,
        "modes": ["add", "subtract"],
    }


def entity_kinds_in_code() -> set:
    """The kinds _entity() actually accepts, read out of its own source. Used by
    the drift test: a new kind must not reach users as raw JSON."""
    import inspect
    src = inspect.getsource(_entity)
    return set(re.findall(r'k == "([a-z_]+)"', src))


def _validate_dims(e: dict, k: str) -> None:
    """Every declared dimension must be a POSITIVE number.

    build123d silently absolutises a negative size: Rectangle(-5, 40) builds
    the same face as Rectangle(5, 40) (probed). With dimensions now editable
    straight from the feature tree, a typo'd minus sign would quietly give the
    user a different part with a green check next to it — the one failure this
    project refuses to allow. So refuse it here, naming the field the way the
    tree labels it."""
    for key, label, unit in ENTITY_FIELDS.get(k, []):
        if key not in e:
            continue
        v = e[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k} {label} must be a number, got {e[key]!r}")
        if v <= 0:
            raise ValueError(f"{k} {label} must be greater than 0, got {v:g}"
                             + (" (a negative size silently builds the "
                                "positive one)" if v < 0 else ""))


def _entity(e: dict):
    """One 2D primitive, positioned in the sketch plane's local coordinates."""
    k = e.get("kind")
    _validate_dims(e, k)
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
    # Rotate FIRST (about the shape's own centre — every primitive above is
    # built centred on the local origin), THEN translate. The old order
    # rotated the already-positioned shape about the PLANE ORIGIN, so any
    # rotated entity (slots drawn right-to-left carry rotation=180, vertical
    # ones ±90) teleported to a point-reflected position the moment the
    # sketch was built — while the editor, which rotates locally, showed it
    # where the user drew it. (User report 2026-08-05: "after finishing it,
    # it goes completely to different shape".)
    if rot:
        s = s.rotate(Axis.Z, rot)
    s = Pos(x, y) * s
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


# The six named directions an author can point at without inventing a
# coordinate. The UI always has a real pick (a face center + normal from the
# raycast), but a tree authored from TEXT does not — and "compute the top face
# center yourself" is exactly where a number gets hallucinated. Same vocabulary
# blocks.shell_out/fillet_edges already use.
FACE_DIRS = {
    "top": (0.0, 0.0, 1.0), "+z": (0.0, 0.0, 1.0),
    "bottom": (0.0, 0.0, -1.0), "-z": (0.0, 0.0, -1.0),
    "+x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0),
    "+y": (0.0, 1.0, 0.0), "-y": (0.0, -1.0, 0.0),
    "front": (0.0, -1.0, 0.0), "back": (0.0, 1.0, 0.0),
    "right": (1.0, 0.0, 0.0), "left": (-1.0, 0.0, 0.0),
}


def named_face(solid, name: str, align_tol: float = 0.001):
    """The OUTERMOST flat face pointing in a named direction ("top", "+x",
    "front"...). Used so a sketch can say WHICH face it lives on by name.

    Only faces whose outward normal really points that way are candidates
    (align > 1 - align_tol), and of those the one farthest along the direction
    wins — so "top" on a part with a pocket is the outer top face, not the
    pocket floor. Flatness is judged by face_plane(), so a dead-flat wall the
    kernel stores as a BSPLINE (loft/sweep leave those) still counts."""
    key = str(name).strip().lower()
    if key not in FACE_DIRS:
        raise ValueError(
            f"face '{name}' is not a direction — use one of "
            f"{sorted(set(FACE_DIRS))}, or give face_center/face_normal from "
            f"an actual pick")
    dx, dy, dz = FACE_DIRS[key]

    def scan(faces):
        best, best_reach = None, None
        for f in faces:
            pl = face_plane(f)
            if pl is None:
                continue                   # genuinely curved: not sketchable
            n = pl.z_dir
            if n.X * dx + n.Y * dy + n.Z * dz < 1.0 - align_tol:
                continue                   # not facing this way
            c = f.center()
            reach = c.X * dx + c.Y * dy + c.Z * dz
            if best_reach is None or reach > best_reach:
                best, best_reach = f, reach
        return best

    # Real parts carry hundreds of faces and this runs on every rebuild of
    # every feature, so try the kernel-typed planes first — face_plane()'s
    # 9-sample flatness probe only runs on the leftovers, and only when no
    # honest PLANE points this way.
    faces = solid.faces()
    typed = [f for f in faces if f.geom_type == b3d.GeomType.PLANE]
    best = scan(typed)
    if best is None and len(typed) != len(faces):
        best = scan([f for f in faces if f.geom_type != b3d.GeomType.PLANE])
    if best is None:
        raise ValueError(
            f"this solid has no flat face pointing '{name}' — pick a different "
            f"direction, or sketch on a principal plane")
    return best


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


def face_sketch_plane(face):
    """The plane a sketch on `face` is drawn in. Returns None when the face is
    genuinely curved.

    A face supplies the plane's POSITION. Its ORIENTATION is always the part's
    own — canonicalised to the principal plane of that axis (Z-facing -> XY,
    X-facing -> YZ, Y-facing -> XZ), the same three frames the sketcher and
    every `plane:` sketch already use. So `sketch_on_face` is exactly "a
    principal-plane sketch positioned by a face", and an entity at (x, y) means
    the same thing on every face of the part.

    Two things this deliberately avoids:

    * build123d's `Plane(face)` puts the origin at the face CENTROID. The top
      face of a shell is the rim minus every pocket cut so far, so its centroid
      MOVES whenever an upstream feature changes, dragging every entity with it.
    * Following the face's OUTWARD normal (what this did first, 2026-08-27)
      keeps one sign rule for "into the material" on every face, but a
      right-handed frame with the normal pointing -Z must mirror an in-plane
      axis: an entity authored at (10, 8) landed at world y = -8 on the bottom
      face, and the esp32 cavity came out mirrored and non-manifold. Uniform
      signs are not worth a silent mirror.

    The cost is that "into the material" is no longer one sign everywhere: on a
    top face it is a negative offset / `flip`, on a bottom face a positive
    offset / no flip. The author knows which side they are on, and getting it
    wrong cuts air — which fails loudly instead of quietly building the wrong
    part."""
    from build123d import Plane, Vector
    pl = face_plane(face)
    if pl is None:
        return None
    n = pl.z_dir
    for frame in (Plane.XY, Plane.YZ, Plane.XZ):
        if abs(n.dot(frame.z_dir)) > 0.9:        # this face's axis
            k = frame.z_dir
            return Plane(origin=k * k.dot(pl.origin),
                         x_dir=frame.x_dir, z_dir=k)
    # a genuinely oblique flat face (a tapered wall): no principal plane fits,
    # so derive a stable frame from the normal itself
    seed = next((c for c in (Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1))
                 if abs(n.dot(c)) < 0.9), Vector(1, 0, 0))
    return Plane(origin=n * n.dot(pl.origin),
                 x_dir=(seed - n * n.dot(seed)).normalized(), z_dir=n)


def face_outline_2d(solid, face_center: list | None = None,
                    face_normal: list | None = None,
                    face: str | None = None, offset: float = 0.0):
    """Project a picked PLANAR face's boundary into its own plane's local 2D
    coordinates — the outer wire plus any inner wires (holes). Returned in the
    SAME frame the sketch entities are placed in, so the sketcher can show the
    selected surface as reference geometry to draw against.

    The face is named the same two ways sketch_on_face accepts: by geometry
    (`face_center` from a real pick) or by direction (`face="top"`, the
    authoring path) — so EVERY committed face sketch can be reopened for
    editing. `offset` shifts the frame exactly like sketch_on_face shifts the
    sketch plane, so the editor's grid lands where the sketch actually lives.

    -> {"outer": [[x,y],...], "holes": [[[x,y],...],...], "planar": bool}
    """
    if face:
        picked = named_face(solid, face)
    elif face_center is not None:
        picked = resolve_face(solid, face_center, face_normal)
    else:
        raise ValueError('face_outline_2d needs either face="top"/"+x"/... '
                         "or a face_center from an actual pick")
    pl = face_sketch_plane(picked)              # the SKETCH frame, world-aligned
    if pl is None:                              # genuinely curved — can't project
        return {"outer": [], "holes": [], "planar": False}
    off = float(offset or 0.0)
    if off:
        pl = pl.offset(off)                     # mirror sketch_on_face exactly

    def project(wire):
        poly = []
        for e in wire.edges():
            steps = 2 if e.geom_type == b3d.GeomType.LINE else 24
            for i in range(steps + 1):
                loc = pl.to_local_coords(e @ (i / steps))
                poly.append([round(loc.X, 3), round(loc.Y, 3)])
        return poly

    outer = picked.outer_wire()
    holes = [project(w) for w in picked.wires() if w.length != outer.length]

    def vec(v):
        return [round(v.X, 4), round(v.Y, 4), round(v.Z, 4)]

    # the plane's world frame, so a UI can draw ghost geometry in place
    frame = {"origin": vec(pl.origin), "x_dir": vec(pl.x_dir),
             "y_dir": vec(pl.y_dir), "z_dir": vec(pl.z_dir)}
    return {"outer": project(outer), "holes": holes, "planar": True,
            "frame": frame}


def sketch_on_face(solid, face_center: list | None = None,
                   face_normal: list | None = None,
                   entities: list | None = None, offset: float = 0.0,
                   face: str | None = None):
    """Draw a sketch ON a face of an existing solid (the Fusion workflow:
    pick a face, sketch, extrude a boss/cut). Two ways to say which face:

      * face="top"|"bottom"|"+x"|"-x"|"+y"|"-y"|"front"|"back"|"left"|"right"
        — the outermost flat face pointing that way (see named_face). This is
        the AUTHORING path: no coordinates to compute, so none to get wrong.
      * face_center (+ optional face_normal) — what the UI sends from a real
        raycast pick. Resolved by GEOMETRY at every rebuild (nearest center,
        best-matching normal) so it survives parameter changes instead of
        breaking like a stored face index would.

    `offset` shifts the sketch plane along the face's OUTWARD normal, so the
    sign means the same thing on every face of the part (probed 2026-08-27):

        offset < 0   INTO the material   (-3 = 3mm below the top face)
        offset > 0   out into the air    (+2 = 2mm clear of the face)

    This is the "offset method" (user mandate 2026-08-27): a pocket's plane is
    stated as a depth FROM A FACE, never as an absolute Z. Change the base
    thickness and the sketch rides with the face instead of being left behind
    — which is exactly what hardcoded principal-plane offsets did to 251 of
    the 274 sketches authored before this."""
    if face:
        # named direction ("top", "+x"): no coordinates to get wrong
        picked = named_face(solid, face)
    elif face_center is not None:
        picked = resolve_face(solid, face_center, face_normal)
    else:
        raise ValueError(
            'sketch_on_face needs either face="top"/"bottom"/"+x"/... or a '
            'face_center from an actual pick')
    pl = face_sketch_plane(picked)
    if pl is None:
        raise ValueError(
            f"sketch_on_face: the picked face is {picked.geom_type.name} and not "
            f"flat — a sketch needs a PLANAR face. For a slot/pocket in a curved "
            f"surface, sketch on a principal plane (offset to the surface) and "
            f"extrude-cut through the body instead.")
    off = float(offset or 0.0)
    if off:
        pl = pl.offset(off)
    return _as_sketch(pl * _compose(entities or []))


# ---------------------------------------------------------------------------
# Sketch-consuming operations -> solids
# ---------------------------------------------------------------------------

def _is_straight(edge, tol: float = 1e-4) -> bool:
    """True if `edge` is geometrically a straight segment, whatever the kernel
    stores it as. Fusing a tapered (lofted) body leaves seam edges typed
    BSPLINE that are dead straight — see _straighten_face."""
    try:
        p0, p1 = edge @ 0, edge @ 1
    except Exception:
        return False
    chord = (p1 - p0).length
    if chord < 1e-9:
        return False
    for i in range(1, 12):                      # every sample on the chord?
        try:
            p = edge @ (i / 12)
        except Exception:
            return False
        if ((p - p0).cross(p1 - p0)).length / chord > tol:
            return False
    return True


def _straighten_face(face):
    """Rebuild `face` with every straight-but-curve-typed edge replaced by a
    real LINE edge — or return it unchanged when there is nothing to fix.

    WHY: OCCT's 2D offset (BRepOffsetAPI_MakeOffset, which build123d uses for
    tapered extrudes) mis-handles BSPLINE edges. Offsetting such a wire toward
    ONE side silently returns a degenerate wire — measured: a 4-edge rectangle
    with one straight BSPLINE edge offset by +0.2mm came back as a SINGLE edge
    of length 50.4 instead of 161.6 — which then detonates inside make_loft
    (Standard_NoSuchObject, or an OCCT access violation that kills the
    process). The other side offsets fine, which is exactly why a taper works
    outward but fails inward on the same face. Straight BSPLINE seam edges are
    left behind by fusing a tapered body, so any face touching that seam is
    affected. Rebuilt as LINEs, all directions offset correctly."""
    try:
        outer = face.outer_wire()
        wires = face.wires()
    except Exception:
        return face
    inner = [w for w in wires if w.length != outer.length]

    def fix(wire):
        edges, changed = [], False
        for e in wire.edges():
            if e.geom_type != b3d.GeomType.LINE and _is_straight(e):
                edges.append(b3d.Edge.make_line(e @ 0, e @ 1)); changed = True
            else:
                edges.append(e)
        return (b3d.Wire(edges), True) if changed else (wire, False)

    new_outer, ch = fix(outer)
    new_inner, changed = [], ch
    for w in inner:
        nw, c = fix(w)
        new_inner.append(nw); changed = changed or c
    if not changed:
        return face
    try:
        rebuilt = b3d.Face(new_outer, new_inner) if new_inner \
            else b3d.Face(new_outer)
    except Exception:
        return face                             # never make things worse
    # only accept a faithful rebuild (same area to 0.1%)
    try:
        if face.area > 0 and abs(rebuilt.area - face.area) / face.area > 1e-3:
            return face
    except Exception:
        return face
    return rebuilt


def collapse_offset(face) -> float:
    """How far this face's outline can be offset INWARD before the material is
    gone — the depth at which a narrowing taper's walls MEET (a point for a
    circle or square, a ridge for a rectangle, wherever the medial axis peaks
    for an odd shape). Measured by bisection on the kernel's own 2D offset, so
    it is exact for any outline; holes cap it at half the thinnest wall
    (build123d offsets holes OUTWARD under a taper, so hole and outer wall
    meet in the middle).

    Used by the tapered extrude to end the solid where the walls meet (Fusion's
    semantics, user decision 2026-09-03) and reported by the tool plan as
    `limits.inradius`, so the handle, the ghost and the solid share one number."""
    from build123d import Kind, Plane
    pl = Plane(face)
    outer_w = face.outer_wire()
    outer = pl.to_local_coords(outer_w)
    bb = outer.bounding_box()
    hi = max(bb.size.X, bb.size.Y) / 2.0 + 1e-6      # this much surely eats everything

    def alive(o: float) -> bool:
        try:
            w = outer.offset_2d(-o, kind=Kind.INTERSECTION)
            if not w.edges():
                return False
            try:
                return abs(b3d.Face(w).area) > 1e-6
            except Exception:
                return abs(make_face(w).area) > 1e-6
        except Exception:
            return False

    lo = 0.0
    if alive(hi):                                    # cannot happen for a bounded face
        return hi
    for _ in range(18):                              # ~4e-6 of the size
        mid = (lo + hi) / 2.0
        if alive(mid):
            lo = mid
        else:
            hi = mid
    r = lo
    inner = face.inner_wires()
    if inner:
        def pts(w):
            return [w @ (i / 64) for i in range(64)]
        op = pts(outer_w)
        hp = [pts(h) for h in inner]
        thin = min((p - q).length for h in hp for p in h for q in op)
        for i in range(len(hp)):
            for j in range(i + 1, len(hp)):
                thin = min(thin, min((p - q).length for p in hp[i] for q in hp[j]))
        r = min(r, thin / 2.0)
    return r


# the tapered solid stops a hair short of the exact apex: OCCT reports the
# mathematically perfect tip as a broken solid (probed 2026-09-03 — a cone
# built at 100% of the meeting height fails, 99.9% builds and is watertight)
APEX_FRACTION = 0.999


def _apex_cap(profile, amount: float, taper: float) -> float:
    """FUSION SEMANTICS (user, 2026-09-03: "in Fusion they go until -90, until
    flat as the sketch — there is no limit"): the distance is a MAXIMUM. When a
    narrowing taper's walls meet before it, the solid ends where they meet — a
    complete cone / pyramid / ridge that gets lower as the angle steepens and
    lies flat on the sketch at 90°. Returns the amount actually built.
    `taper` is in the kernel helpers' convention (positive narrows)."""
    if taper <= 0 or not amount:
        return amount
    faces = [profile] if isinstance(profile, b3d.Face) else list(profile.faces())
    if not faces:
        return amount
    r = min(collapse_offset(f) for f in faces)
    h_apex = APEX_FRACTION * r / math.tan(math.radians(taper))
    if abs(amount) <= h_apex:
        return amount
    return math.copysign(h_apex, amount)


def _taper_offset_problem(profile, amount: float, taper: float):
    """Replicate the 2D offset build123d will perform for a tapered extrude and
    report a problem STRING if it comes back degenerate — before OCCT is handed
    that garbage and crashes the process (an access violation would take the
    whole server down, so this check must happen here, not in an except:).

    Mirrors Solid.extrude_taper: the loft path (the fragile one) is used unless
    the direction matches the face normal AND the plane faces up AND the taper
    is positive AND there are no holes; offset = -|amount| * tan(taper)."""
    if not taper:
        return None
    try:
        face = profile if isinstance(profile, b3d.Face) else None
        if face is None:
            faces = profile.faces()
            if len(faces) != 1:
                return None                     # multi-face: let build123d try
            face = faces[0]
        pl = b3d.Plane(face)
        direction = pl.z_dir * amount
        inner = face.inner_wires()
        if (direction.normalized() == face.normal_at()
                and pl.z_dir.Z > 0 and taper > 0 and not inner):
            return None                         # robust DPrism path, no offset
        # (when DPrism goes the wrong way and _taper_loft takes over, the loft
        # checks its own offset wires — see there)
        off = -abs(amount) * math.tan(math.radians(taper))
        if abs(off) < 1e-9:
            return None
        for i, wire in enumerate([face.outer_wire()] + list(inner)):
            flip = -1 if i > 0 else 1           # build123d flips inner wires
            local = pl.to_local_coords(wire)
            n_before = len(local.edges())
            try:
                res = local.offset_2d(flip * off, kind=b3d.Kind.INTERSECTION)
            except Exception as e:
                return (f"the {'hole' if i else 'outline'} cannot be offset by "
                        f"{abs(off):.3f}mm ({type(e).__name__})")
            n_after = len(res.edges())
            # the degenerate signature: a polygon collapses to one or two
            # edges (the BSPLINE-seam garbage that access-violated OCCT came
            # back as a SINGLE edge). A wire merely LOSING an edge is normal —
            # the 0.07mm top of a near-collapsed wedge wall vanishes under any
            # inward offset and the loft builds fine (2026-09-03); refusing
            # that made a flipped taper on such a wall impossible.
            if n_after < n_before and n_before >= 3 and n_after < 3:
                return (f"the {'hole' if i else 'outline'} collapses when "
                        f"offset by {abs(off):.3f}mm "
                        f"({n_before} edges -> {n_after})")
    except Exception:
        return None                             # a check must never break a build
    return None


def _tapered_extrude(profile, amount: float, taper: float):
    """extrude() with the taper failure modes handled honestly:
      * straight BSPLINE seam edges (from a fused tapered body) are rebuilt as
        LINEs first, which makes the offset — and the extrude — actually work;
      * a genuinely degenerate offset is caught BEFORE OCCT crashes on it;
      * kernel errors are reported as-is instead of being blamed on the taper.
    OCP raises Standard_NoSuchObject etc., which derive from Exception and NOT
    from RuntimeError — an `except RuntimeError` here never caught them and the
    raw kernel error reached the feature tree."""
    if abs(taper) >= 90:
        raise ValueError(f"taper {-taper:g}° — a wall cannot lean past flat (90°); "
                         f"use a smaller angle")
    outward = None          # a FACE's outward normal, captured BEFORE any rebuild
    if taper:
        if isinstance(profile, b3d.Face):
            fp = face_plane(profile)
            outward = fp.z_dir if fp is not None else None
            # _straighten_face may rebuild the face with its normal FLIPPED
            # (measured 2026-09-03 on a fused body's wall) — every direction
            # decision below uses `outward`, never the rebuilt face's normal
            profile = _straighten_face(profile)
        amount = _apex_cap(profile, amount, taper)   # the walls may meet first
        problem = _taper_offset_problem(profile, amount, taper)
        if problem:
            raise ValueError(
                f"taper {-taper:g}° over {abs(amount):g}mm does not work on this "
                f"profile: {problem}. Try a smaller taper, a shorter distance, "
                f"or taper the other way.")
    solid = None
    tried_loft = False
    try:
        solid = _extrude(profile, amount=amount, taper=taper)
        # A FACE OF A SOLID can come out on the WRONG SIDE of a tapered build:
        # build123d hands an upward, narrowing, hole-less face to OCCT's
        # LocOpe_DPrism, which follows the face's INTERNAL orientation (a face
        # made by an earlier taper is stored reversed), and the straightened
        # face may carry a flipped normal. Either way the stub landed INSIDE
        # the body (user 2026-09-03: "it goes to the opposite direction").
        # Measure the side against the ORIGINAL outward normal; if the kernel
        # went the wrong way, build the loft along that explicit direction.
        if taper and outward is not None \
                and not _same_side(solid, profile, amount, outward):
            tried_loft = True
            solid = None                    # never keep the wrong-sided solid
            solid = _taper_loft(profile, amount, taper, outward)
    except Exception as e:
        if not taper:
            raise
        err = e
        if outward is not None and not tried_loft:   # the other construction may work
            try:
                solid = _taper_loft(profile, amount, taper, outward)
            except Exception as e2:
                err = e2
        if solid is None:
            raise ValueError(
                f"taper {-taper:g}° over {abs(amount):g}mm failed on this profile "
                f"({type(err).__name__}: {str(err)[:100]}). Try a smaller taper, "
                f"a shorter distance, or taper the other way.") from err
    if taper:
        # A tapered extrude can also SUCCEED into a broken solid (measured on
        # an L-bracket's reflex corner and a DPrism boss face: an open shell /
        # OCCT-invalid result). Handing that to a fuse corrupts the model
        # silently, so refuse it here — a failed feature beats a bad body.
        import inspector                       # local: avoids an import cycle
        problems = inspector.health(solid)
        if problems:
            # OCCT's loft-based taper INTERMITTENTLY flags valid geometry as
            # an invalid solid (probed on a 97mm extrude from a tilted face:
            # taper 10° and 31° "invalid", 5/20/40° fine — same volumes).
            # ShapeFix heals the bookkeeping; accept the repair only if it
            # passes health with the volume unchanged (0.1%).
            healed = _shapefix(solid)
            if healed is not None and not inspector.health(healed):
                return healed
            raise ValueError(
                f"taper {-taper:g}° over {abs(amount):g}mm produces a broken solid "
                f"on this profile ({problems[0]}). Try a smaller taper, a "
                f"shorter distance, or taper the other way.")
    return solid


def _same_side(solid, face, amount: float, outward) -> bool:
    """Does the extruded solid lie on the side of `face` its amount asked for?
    (centre of mass along the face's ORIGINAL outward normal; a prism off a
    face never straddles it)"""
    try:
        d = (solid.center() - face.center()).dot(outward)
        return (d > 0) == (float(amount) > 0)
    except Exception:
        return True                             # a check must never break a build


def _taper_loft(face, amount: float, taper: float, outward):
    """A tapered extrude of a FACE OF A SOLID along its OUTWARD normal, built as
    a loft from the face to its 2D-offset copy moved by `amount` — the same
    construction build123d's `Solid.extrude_taper` uses for every case but one.

    The one it does differently is the bug (user, 2026-09-03: "I tried a
    taper on the triangle face and it goes in the opposite direction"): when a
    face points upward, the taper narrows and the face has no holes, build123d
    hands the job to OCCT's `LocOpe_DPrism`, which follows the face's INTERNAL
    orientation rather than its outward normal. A face created by an earlier
    taper is stored reversed, so the tapered stub landed INSIDE the body while
    the untapered one went outside (measured: +2.50 vs -2.40 mm along the
    normal on a 45° wedge wall). Here the direction is explicit — the same
    `face_plane` normal the untapered extrude and the tool's plan use — so the
    tapered and untapered results always lie on the same side. `taper` is in
    the kernel helpers' convention (positive narrows), like _extrude."""
    from build123d import Kind, Location, Plane, Solid, Vector
    n = outward                  # the ORIGINAL face's normal, never the rebuilt face's
    direction = Vector(n.X, n.Y, n.Z) * float(amount)
    offset_amt = -direction.length * math.tan(math.radians(taper))
    pl = Plane(face)                            # a 2D frame for the offset only
    wires = [face.outer_wire()] + face.inner_wires()
    solids = []
    for i, wire in enumerate(wires):
        flip = -1 if i > 0 else 1               # holes taper the other way
        local = pl.to_local_coords(wire)
        try:
            shrunk = local.offset_2d(flip * offset_amt, kind=Kind.INTERSECTION)
        except Exception as e:                  # the offset eats the whole wire
            raise ValueError(
                f"the walls meet before the end: the {'hole' if i else 'outline'} "
                f"cannot be offset by {abs(offset_amt):.2f}mm ({type(e).__name__}) "
                f"— use a smaller taper or a shorter distance") from e
        # never hand OCCT a degenerate wire (the garbage that once
        # access-violated the whole server): a polygon offset must stay a
        # polygon — a circle (1 edge) is fine, 1-2 edges from 3+ is not
        if len(wire.edges()) >= 3 and len(shrunk.edges()) < 3:
            raise ValueError(
                f"the {'hole' if i else 'outline'} collapses when offset by "
                f"{abs(offset_amt):.3f}mm ({len(wire.edges())} edges -> "
                f"{len(shrunk.edges())})")
        moved = pl.from_local_coords(shrunk)
        moved.move(Location(direction))
        solids.append(Solid.make_loft([wire, moved]))
    solid = solids[0]
    if len(solids) > 1:
        solid = solid.cut(*solids[1:])
    return solid


def _shapefix(solid):
    """Repair an OCCT-invalid solid; None unless the repair is FAITHFUL
    (same volume to 0.1%) — a repair must never quietly change geometry."""
    try:
        from OCP.ShapeFix import ShapeFix_Shape
        fixer = ShapeFix_Shape(solid.wrapped)
        fixer.Perform()
        healed = b3d.Solid(fixer.Shape())
        if solid.volume > 1e-9 and \
                abs(healed.volume - solid.volume) / solid.volume < 1e-3:
            return healed
    except Exception:
        pass
    return None


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
    return _tapered_extrude(face, a, _fusion_taper(taper))


def _fusion_taper(taper) -> float:
    """The public taper sign is FUSION'S (user decision 2026-09-03, Autodesk
    help: "a negative angle tapers the extrusion inward, a positive value
    outward"). The kernel helpers below keep their historical convention
    (positive narrows), so this is the ONE place the sign turns around."""
    return -float(taper or 0.0)


# How far a "through all" cut reaches. Anything longer than the part is
# equivalent — a cutting tool that overshoots removes exactly the same material
# — and 2 m is far past any plate this tool works with while staying well inside
# OCCT's comfortable range.
THROUGH_MM = 2000.0


def extrude_sketch(sketch, amount: float, both: bool = False,
                   amount2: float = 0.0, taper: float = 0.0, flip: bool = False,
                   through: bool = False):
    """Pull a sketch straight, normal to its plane, into a solid (Fusion-style
    Extrude). Direction:
      * one side   : amount  (flip = extrude the other way)
      * symmetric  : both=True — extrude `amount` to EACH side
      * two sides  : amount one way + amount2 the opposite way
    `taper` degrees tapers the walls — FUSION'S SIGN (user decision
    2026-09-03): NEGATIVE narrows as it extrudes, POSITIVE flares outward.
    (Before 2026-09-03 positive narrowed; saved designs were migrated.)
    FUSION'S SEMANTICS too: `amount` is a MAXIMUM. If the narrowing walls meet
    before it, the solid ends where they meet (see _apex_cap) — any angle up
    to ±90 builds, steeper is simply lower.

    `through` = THROUGH ALL: ignore the distance and run far past the material,
    keeping the direction. This is what a CUTTING tool almost always wants. A
    tool that stops INSIDE material does not clear it — it slices it, and
    whatever was above the cut is left as a loose piece. That is what happened
    when a pillar trim was shortened from 6 mm to 2 mm: it took a band out of
    four pillars and left their caps floating (user, 2026-08-26: "if i am
    increasing or decreasing the extrude value, it should increase or decrease,
    it should not create a new body"). With `through` the depth simply cannot
    land inside the part, so the cut can only ever clear.

    Taper is ignored for a through cut: a 2 m tapered prism collapses."""
    a = float(amount)
    if _to_bool(flip, "flip"):
        a = -a
    t = _fusion_taper(taper)
    if _to_bool(through, "through"):
        a = THROUGH_MM if a >= 0 else -THROUGH_MM
        t = 0.0
    if _to_bool(both, "both"):
        try:
            return _extrude(sketch, amount=_apex_cap(sketch, a, t), both=True,
                            taper=t)
        except Exception as e:
            if t:
                raise ValueError(
                    f"taper {-t:g}° over {abs(a):g}mm (symmetric) failed on this "
                    f"profile ({type(e).__name__}: {str(e)[:80]}). Try a "
                    f"smaller taper, a shorter distance, or the other way.") from e
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

# ops whose solid input is only a FACE REFERENCE (where to work), never
# geometric consumption: a sketch drawn on a box's face does not eat the box,
# and extrude_face outputs a separate boss solid while the source body lives
# on. The document engine must NOT count their inputs as "consumed" or the
# referenced body vanishes from the viewport the moment the sketch is used
# (reported: "after finishing the sketch and extruding, the main body
# vanishes").
FACE_REFERENCE_OPS = {"sketch_on_face", "extrude_face"}


def is_sketch(obj) -> bool:
    return isinstance(obj, b3d.Sketch)
