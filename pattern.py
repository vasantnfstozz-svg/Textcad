"""pattern.py — Circular and Rectangular Pattern, and Mirror (LAUNCH-PLAN.md P4,
specs/pattern.md, specs/mirror.md): the ops `polar_pattern` / `linear_pattern`,
grown from "N copies of a body" to Fusion's "pattern a FEATURE", and `mirror`,
grown from "the reflected copy of a body" the same way — a mirror is a pattern
with one copy and a reflection instead of a rotation (probes/mirror_probe.py).

THE IDEA (probes/pattern_probe.py): a feature's DELTA is what it removed
(the body before it minus the body after it) and what it added (after minus
before) — two booleans, whatever the feature's op was. A pattern repeats that
delta about an axis or along a direction and applies it to the body's CURRENT
state: the removed part is cut again at every copy, the added part fused
again. A hole, a pocket, a boss and a fillet all pattern the same way (§1–§4),
and the op never needs to know how the seed was made. With no seed the input
body itself is the seed — the legacy behaviour every existing design relies
on, signature-compatible.

The document hands the op the seed's two bodies as `_before` / `_after`
(Document._eval; `document.delta_features` is the ONE resolver of what "the
feature" means — the tree's own folding rule). Underscored parameters are
not user parameters: op_params leaves them out of the catalogue.

Every failure is a sentence in the op's own words; a copy that lands off the
body (removes EXACTLY nothing — §7), a pattern that leaves an open shell (a
copy tangent to an edge — §7) and a kernel exception are all refused, never a
"successful" broken body.
"""
from __future__ import annotations

import math

import build123d as b3d
from build123d import Axis, Location, Plane, Vector

import inspector
import sketch as sk

PATTERN_OPS = ("polar_pattern", "linear_pattern")
SEEDED_OPS = PATTERN_OPS + ("mirror",)      # every op that repeats a FEATURE's delta (a `seed` param)
DISTANCE_TYPES = ("spacing", "extent")
_TOL = 1e-9          # "exactly nothing": a boolean that misses changes the volume by 0.0
                     # (probes/mirror_probe.py §10: an image ON the seed differs by ≤ 3e-11)
_WORLD_NORMALS = {"XY": (0, 0, 1), "XZ": (0, 1, 0), "YZ": (1, 0, 0),
                  "X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}


# ------------------------------------------------------------------ vectors ---

def _vec(v, what: str, op: str) -> Vector:
    try:
        x, y, z = (float(c) for c in v)
    except (TypeError, ValueError):
        raise ValueError(f"{op}: {what} must be [x, y, z] (got {v!r})") from None
    return Vector(x, y, z)


def _unit(v, what: str, op: str) -> Vector:
    d = _vec(v, what, op)
    if d.length < 1e-9:
        raise ValueError(f"{op}: {what} must not be the zero vector")
    return d.normalized()


def _count(n, what: str, op: str, least: int = 1) -> int:
    try:
        f = float(n)
    except (TypeError, ValueError):
        raise ValueError(f"{op}: {what} must be a whole number ≥ {least} (got {n!r})") from None
    if abs(f - round(f)) > 1e-9 or round(f) < least:
        raise ValueError(f"{op}: {what} must be a whole number ≥ {least} (got {n!r})")
    return int(round(f))


def face_word(normal: Vector) -> str:
    """'top' / 'bottom' / '+x' … for a principal normal, 'tilted' otherwise."""
    for name in ("top", "bottom", "+x", "-x", "+y", "-y"):
        dx, dy, dz = sk.FACE_DIRS[name]
        if normal.X * dx + normal.Y * dy + normal.Z * dz > 0.999:
            return name
    return "tilted"


# --------------------------------------------------------------------- axis ---

def face_axis(face):
    """The axis a picked face means: a FLAT face gives its outward normal
    through the centre of its OUTER wire (probe §5 — the face's own centroid
    moves with every hole cut into it), a cylindrical face its own axis (§6).
    Returns (origin, direction, words)."""
    if sk.face_plane(face) is not None:
        centre = b3d.Face(face.outer_wire()).center()
        n = face.normal_at(face.center())
        return centre, n.normalized(), f"normal of the {face_word(n)} face through its centre"
    if face.geom_type in (b3d.GeomType.CYLINDER, b3d.GeomType.CONE):
        ax = face.axis_of_rotation
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            r = BRepAdaptor_Surface(face.wrapped).Cylinder().Radius()
            what = f"the ⌀{2 * r:g} bore"
        except Exception:                          # a cone has no one radius
            what = f"the {face.geom_type.name.lower()} face"
        return Vector(ax.position), Vector(ax.direction).normalized(), f"axis of {what}"
    raise ValueError(f"the picked face is {face.geom_type.name} — an axis comes from a "
                     f"flat face (its normal) or a cylindrical one (its own axis)")


def axis_of(solid, axis, op: str = "polar_pattern"):
    """The stored `axis`, resolved on `solid`: None = world Z through the origin
    (the legacy behaviour), a world name ("+Z", "top", …) through the origin,
    a face ({face_center, face_normal} or {face: "top"} — resolved by geometry
    at every rebuild, so it rides an upstream change), or an explicit
    {origin, dir}. Returns (origin: Vector, direction: Vector, words)."""
    if axis is None:
        return Vector(0, 0, 0), Vector(0, 0, 1), "world Z through the origin"
    if isinstance(axis, str):
        key = axis.strip().lower()
        if key not in sk.FACE_DIRS:
            raise ValueError(f"{op}: axis '{axis}' is not a world axis — use one of "
                             f"{sorted(set(sk.FACE_DIRS))}, a face, or {{origin, dir}}")
        d = Vector(*sk.FACE_DIRS[key])
        return Vector(0, 0, 0), d, f"world {face_word(d).upper().replace('TOP', '+Z').replace('BOTTOM', '-Z')} through the origin"
    if isinstance(axis, dict):
        if axis.get("dir") is not None:
            o = _vec(axis.get("origin") or (0, 0, 0), "the axis origin", op)
            d = _unit(axis["dir"], "the axis direction", op)
            return o, d, (f"the axis through ({o.X:g}, {o.Y:g}, {o.Z:g}) "
                          f"along ({d.X:.3g}, {d.Y:.3g}, {d.Z:.3g})")
        if axis.get("face") or axis.get("face_center") is not None:
            try:
                face = sk.pick_face(solid, axis.get("face_center"), axis.get("face_normal"),
                                    axis.get("face"))
            except ValueError as e:
                raise ValueError(f"{op}: the axis face is gone — {e}; click a face for the axis") from None
            try:
                return face_axis(face)
            except ValueError as e:
                raise ValueError(f"{op}: {e}") from None
    raise ValueError(f"{op}: `axis` must be a world axis name (\"+Z\"), a face "
                     f"({{face_center, face_normal}} or {{face: \"top\"}}), or {{origin, dir}} "
                     f"(got {axis!r})")


# -------------------------------------------------------------------- delta ---

def _nonempty(part):
    """a boolean's result that actually holds material, else None"""
    try:
        if len(part.solids()) == 0 or float(part.volume) < _TOL:
            return None
    except Exception:
        return None
    return part


def _overlaps(a, b) -> bool:
    """do two shapes share material? — what tells a copy that lands ON the seed
    from one that lands off the body. It carries its OWN guard: the boolean is
    only the discriminator, so a kernel failure here must cost the accurate
    sentence, not replace it with "the kernel could not build" (P4 review)."""
    try:
        return _nonempty(a & b) is not None
    except Exception:                        # OCP errors are Exception, not RuntimeError
        return False


def delta(before, after):
    """(removed, added): what the feature took away and what it put on — each
    a solid or None (probe §1: a hole's `added` is an empty Compound)."""
    return _nonempty(before - after), _nonempty(after - before)


def _seed(feature, seed, before, after, op, verb: str = "repeat"):
    """the body to pattern on and the (removed, added) pair to repeat; a body
    seed repeats the body itself (added = the body, removed = None)"""
    if not seed:
        return None, feature
    if before is None or after is None:
        raise ValueError(f"{op}: the seed '{seed}' needs its before / after bodies — this op "
                         f"runs inside a document, which hands them over")
    removed, added = delta(before, after)
    if removed is None and added is None:
        raise ValueError(f"{op}: '{seed}' neither removed nor added material — there is "
                         f"nothing to {verb}")
    return removed, added


def _repeat(body, removed, added, moves, op: str, what: str, label=None, noun: str = "the pattern"):
    """Apply the delta at every copy (`moves`: shape -> moved shape), measuring
    each one: a cut that changes nothing either landed off the body (probe §7)
    or ON the seed itself (a copy that does not move it — a mirror plane
    through the feature, a seed on the pattern's axis; the image ∩ seed tells
    the two apart), a fuse that adds nothing lies inside it. Then health (an
    open shell from a copy tangent to an edge is_valid calls fine — §7).
    `label(k, n)` names a copy in the sentences, `noun` the whole result."""
    n = len(moves) + 1
    label = label or (lambda k, n: f"copy {k} of {n}")
    result = body
    for k, move in enumerate(moves, start=2):
        try:
            if removed is not None:
                image = move(removed)
                v0 = float(result.volume)
                result = result - image
                if abs(v0 - float(result.volume)) < _TOL:
                    if _overlaps(image, removed):
                        raise ValueError(f"{op}: {label(k, n)} is the seed itself (it lands where "
                                         f"the seed already is) — {what}")
                    raise ValueError(f"{op}: {label(k, n)} lands off the body (nothing to "
                                     f"cut there) — {what}")
            if added is not None:
                v0 = float(result.volume)
                result = result + move(added)
                if abs(float(result.volume) - v0) < _TOL:
                    raise ValueError(f"{op}: {label(k, n)} adds nothing (it lies inside the "
                                     f"body) — {what}")
        except ValueError:
            raise
        except Exception:                        # OCP errors are Exception, not RuntimeError
            raise ValueError(f"{op}: the kernel could not build {label(k, n)} — {what}") from None
    problems = inspector.health(result, check_valid=False)
    if problems:
        runs = "a copy runs" if n > 2 else "it runs"
        raise ValueError(f"{op}: {noun} leaves a broken solid ({problems[0]}) — {runs} "
                         f"exactly along an edge of the body; {what}")
    return result


def _fuse_all(parts):
    while len(parts) > 1:                        # pairwise: far cheaper than a chain
        parts = [parts[i] + parts[i + 1] if i + 1 < len(parts) else parts[i]
                 for i in range(0, len(parts), 2)]
    return parts[0]


def _body_pattern(body, copies, op: str, what: str):
    """a BODY seed: the union of the body and its moved copies (the legacy
    behaviour, kept exactly — separate copies come back as separate pieces,
    which the document reports; probe §8).

    What it must NOT do is measure the union against the body and refuse when
    they match: a body that is already n-fold symmetric about the axis patterns
    to itself, and every such design in the wild built before this op grew a
    seed. Refusing here would fail it at REBUILD — the one thing a saved design
    may never do (P4 code review). A pattern that asks for no motion at all is
    a different thing, and is refused where the motion is decided, by name."""
    try:
        return _fuse_all([body] + copies)
    except Exception:
        raise ValueError(f"{op}: the kernel could not fuse the copies — {what}") from None


# ---------------------------------------------------------------- circular ---

def polar_angles(count: int, angle: float) -> list[float]:
    """the copies' angles beyond the seed: Full (360) spreads count copies
    evenly round the circle; a partial angle spreads them from 0 to the angle
    inclusive (Fusion's Angle type)"""
    if count < 2:
        return []
    step = angle / count if abs(angle - 360.0) < 1e-9 else angle / (count - 1)
    return [step * i for i in range(1, count)]


def polar_pattern(feature, count, axis=None, angle: float = 360.0,
                  seed: str | None = None, _before=None, _after=None):
    """Circular Pattern: `count` copies of the seed (a feature of `feature`'s
    history, or the body itself when `seed` is None) about `axis` — None =
    world Z through the origin (legacy), a world name, a face (a flat face's
    normal through its centre, a bore's own axis) or {origin, dir} — spread
    over `angle` degrees (360 = a full circle, Fusion's Full; less spreads the
    copies from the seed to the angle). Returns the body WITH the copies."""
    op = "polar_pattern"
    n = _count(count, "count", op)
    try:
        a = float(angle if angle is not None else 360.0)
    except (TypeError, ValueError):
        raise ValueError(f"{op}: the angle must be a number (got {angle!r})") from None
    if not 0 < a <= 360.0 + 1e-9:
        raise ValueError(f"{op}: the angle must be between 0 and 360 (got {a:g}) — 360 is a full circle")
    origin, d, _ = axis_of(feature, axis, op)
    removed, added = _seed(feature, seed, _before, _after, op)
    if n == 1:
        return feature                           # only the seed: nothing to repeat
    ax = Axis(origin, d)
    what = "a smaller count, another angle, or another axis"
    if not seed:
        return _body_pattern(feature, [feature.rotate(ax, t) for t in polar_angles(n, a)], op, what)
    moves = [(lambda t: (lambda s: s.rotate(ax, t)))(t) for t in polar_angles(n, a)]
    return _repeat(feature, removed, added, moves, op, what)


# ------------------------------------------------------------- rectangular ---

def linear_steps(count: int, distance: float, distance_type: str) -> list[float]:
    """the copies' offsets beyond the seed along one direction: Spacing puts
    them `distance` apart, Extent fits them inside `distance` (the last copy
    AT the distance)"""
    if count < 2:
        return []
    step = distance if distance_type == "spacing" else distance / (count - 1)
    return [step * i for i in range(1, count)]


def linear_pattern(feature, count, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
                   direction=None, distance: float = 0.0, distance_type: str = "spacing",
                   count2: int = 1, direction2=None, distance2: float = 0.0,
                   seed: str | None = None, _before=None, _after=None):
    """Rectangular Pattern: `count` copies of the seed (a feature of
    `feature`'s history, or the body itself when `seed` is None) along
    `direction` (a world unit vector) at `distance` — Spacing: that far apart,
    Extent: all inside that distance — and, when `count2` ≥ 2, `count2` rows
    along `direction2` at `distance2`, a grid. Without a `direction` the legacy
    step (dx, dy, dz) per copy applies. Returns the body WITH the copies."""
    op = "linear_pattern"
    n = _count(count, "count", op)
    removed, added = _seed(feature, seed, _before, _after, op)
    what = "a smaller count, a shorter distance, or another direction"
    if direction is None:                        # legacy: a world step per copy
        step = _vec((dx or 0.0, dy or 0.0, dz or 0.0), "the step (dx, dy, dz)", op)
        if n == 1:
            return feature
        if step.length < 1e-9:                   # every copy lands ON the seed
            raise ValueError(f"{op}: the step is 0, so all {n} copies land on the seed — give "
                             f"dx, dy or dz (or a direction and a distance)")
        moves = [(lambda i: (lambda s: Location(step * i) * s))(i) for i in range(1, n)]
        if not seed:
            return _body_pattern(feature, [m(feature) for m in moves], op, what)
        return _repeat(feature, removed, added, moves, op, what)
    dt = str(distance_type or "spacing").lower()
    if dt not in DISTANCE_TYPES:
        raise ValueError(f"{op}: distance_type must be 'spacing' or 'extent' (got {distance_type!r})")
    d1 = _unit(direction, "the direction", op)
    n2 = _count(count2 if count2 is not None else 1, "count2", op)
    dist = float(distance or 0.0)
    if n >= 2 and abs(dist) < 1e-9:
        raise ValueError(f"{op}: the distance must not be 0 with {n} copies — drag the arrow or "
                         f"type a distance")
    d2, dist2 = None, float(distance2 or 0.0)
    if n2 >= 2:
        if direction2 is None:
            raise ValueError(f"{op}: a second direction is needed for {n2} rows (direction2)")
        d2 = _unit(direction2, "the second direction", op)
        if abs(dist2) < 1e-9:
            raise ValueError(f"{op}: the second distance must not be 0 with {n2} rows — drag "
                             f"the second arrow or type a distance")
    offsets = []
    for j in [0.0] + linear_steps(n2, dist2, dt):
        for i in [0.0] + linear_steps(n, dist, dt):
            if i == 0.0 and j == 0.0:
                continue
            offsets.append(d1 * i + (d2 * j if d2 is not None else Vector(0, 0, 0)))
    if not offsets:
        return feature
    moves = [(lambda o: (lambda s: Location(o) * s))(o) for o in offsets]
    if not seed:
        return _body_pattern(feature, [m(feature) for m in moves], op, what)
    return _repeat(feature, removed, added, moves, op, what)


# ------------------------------------------------------------------- mirror ---

def plane_of(solid, plane, op: str = "mirror"):
    """The stored `plane`, resolved on `solid` (specs/mirror.md): a world name
    ("XY" / "XZ" / "YZ" — through the origin, the legacy form), a face
    ({face_center, face_normal} or {face: "top"} — its plane through the centre
    of its OUTER wire, resolved by geometry at every rebuild), the body's
    mid-plane ({mid: "X"} — the bounding-box centre, so it rides a resize) or an
    explicit {origin, normal}. Returns (Plane, words). A plane is an origin and
    a normal: the same plane with the normal flipped mirrors the same way
    (probes/mirror_probe.py §1)."""
    if isinstance(plane, str):
        key = plane.strip().upper()
        if key not in ("XY", "XZ", "YZ"):
            raise ValueError(f"{op}: plane '{plane}' is not an origin plane — use \"XY\", \"XZ\" or "
                             f"\"YZ\", a face, a mid-plane ({{mid: \"X\"}}) or {{origin, normal}}")
        return (Plane(origin=(0, 0, 0), z_dir=Vector(*_WORLD_NORMALS[key])),
                f"the {key} plane (through the origin)")
    if isinstance(plane, dict):
        if plane.get("normal") is not None:
            o = _vec(plane.get("origin") or (0, 0, 0), "the plane origin", op)
            n = _unit(plane["normal"], "the plane normal", op)
            return Plane(origin=o, z_dir=n), (f"the plane through ({o.X:g}, {o.Y:g}, {o.Z:g}) "
                                              f"with normal ({n.X:.3g}, {n.Y:.3g}, {n.Z:.3g})")
        if plane.get("mid"):
            key = str(plane["mid"]).strip().upper()
            if key not in ("X", "Y", "Z"):
                raise ValueError(f"{op}: mid must be \"X\", \"Y\" or \"Z\" (got {plane['mid']!r})")
            c = solid.bounding_box().center()
            return (Plane(origin=c, z_dir=Vector(*_WORLD_NORMALS[key])),
                    f"the body's mid-plane across {key}")
        if plane.get("face") or plane.get("face_center") is not None:
            try:
                face = sk.pick_face(solid, plane.get("face_center"), plane.get("face_normal"),
                                    plane.get("face"))
            except ValueError as e:
                raise ValueError(f"{op}: the plane face is gone — {e}; click a face for the plane") from None
            if sk.face_plane(face) is None:
                raise ValueError(f"{op}: the picked face is {face.geom_type.name} — a mirror plane "
                                 f"is a flat face, an origin plane or the body's mid-plane")
            n = face.normal_at(face.center()).normalized()
            return (Plane(origin=b3d.Face(face.outer_wire()).center(), z_dir=n),
                    f"the {face_word(n)} face's plane")
    raise ValueError(f"{op}: plane must be \"XY\", \"XZ\" or \"YZ\", a face ({{face_center, "
                     f"face_normal}} or {{face: \"top\"}}), a mid-plane ({{mid: \"X\"}}) or "
                     f"{{origin, normal}} (got {plane!r})")


def mirror(feature, plane="YZ", seed: str | None = None, join: bool = False,
           _before=None, _after=None):
    """Mirror: the seed's delta (a feature of `feature`'s history) reflected
    across `plane` and applied to the body again — what it removed is cut, what
    it added is fused (probes/mirror_probe.py §2, §5) — or, with no seed, the
    body itself: fused with its reflection when `join` (Fusion's Join, §6), the
    reflected COPY alone otherwise (the legacy behaviour every saved design
    relies on). A body mirrored across its own symmetry plane is itself and is
    not refused (§7). Returns the body WITH the mirror image."""
    op = "mirror"
    pl, _ = plane_of(feature, plane, op)
    removed, added = _seed(feature, seed, _before, _after, op, verb="mirror")
    what = "pick a plane beside the feature, through the body"
    if not seed:
        try:
            # the OPERATION, not Shape.mirror: a fresh object. Shape.mirror copies
            # a sketch's recorded plane (_tc_plane) along, and after a reflection
            # that plane is stale — a revolve about its "u" / "v" would lie
            # (tests/test_revolve_tool.py: a mirrored sketch must refuse u / v)
            copy = b3d.mirror(feature, about=pl)
        except Exception:                        # OCP errors are Exception, not RuntimeError
            raise ValueError(f"{op}: the kernel could not build the mirror image — pick another plane") from None
        if not join:
            return copy
        return _body_pattern(feature, [copy], op, "pick another plane")
    return _repeat(feature, removed, added, [lambda s: s.mirror(pl)], op, what,
                   label=lambda k, n: f"the mirror image of '{seed}'", noun="the mirror image")


# ------------------------------------------------ what the PLAN needs to know ---

def legacy_step(params: dict):
    """A LEGACY linear_pattern's per-copy step (dx, dy, dz) read as the stored
    form the tool edits: (direction, distance), or None when there is no step.
    ONE place turns the old parameters into the new ones — without it the panel
    opens such a feature aimed at world X and the first distance typed silently
    re-aims the pattern (P4 code review)."""
    try:
        step = Vector(float(params.get("dx") or 0.0), float(params.get("dy") or 0.0),
                      float(params.get("dz") or 0.0))
    except (TypeError, ValueError):
        return None
    if step.length < 1e-9:
        return None
    d = step.normalized()
    return [round(d.X, 9), round(d.Y, 9), round(d.Z, 9)], round(step.length, 6)


def seed_centre(removed, added, body) -> Vector:
    """where the seed IS: the centroid of the material it changed (its removed
    part first — a hole's plug), else the body's own centre"""
    part = removed if removed is not None else added
    return part.center() if part is not None else body.center()


def _touches(face, bb) -> bool:
    """does the face's plane meet the delta's bounding box?"""
    pl = sk.face_plane(face)
    if pl is None:
        return False
    n, o = Vector(pl.z_dir), Vector(pl.origin)
    lo, hi = bb.min, bb.max
    ds = [(Vector(x, y, z) - o).dot(n)
          for x in (lo.X, hi.X) for y in (lo.Y, hi.Y) for z in (lo.Z, hi.Z)]
    return min(ds) <= 1e-3 and max(ds) >= -1e-3


def seed_face(before, removed, added):
    """the flat face of the body BEFORE the seed that the seed sits on: the
    largest one whose plane touches the delta's bounding box (a hole's plug
    touches the face it was drilled from, a boss the face it stands on, a
    fillet's sliver the faces round its edge). None for a body seed."""
    part = removed if removed is not None else added
    if part is None or before is None:
        return None
    bb = part.bounding_box()
    cands = [f for f in before.faces() if _touches(f, bb)]
    if not cands:
        return None

    def rank(f):                # the largest; a through hole touches top AND
        n = f.normal_at(f.center())   # bottom alike — the upper one is the one
        return (round(f.area, 6), n.Z, n.X, n.Y)   # a user drilled from
    return max(cands, key=rank)


def stored_face(solid, face) -> dict:
    """the face in the ONE stored form the op resolves by geometry — read off
    the body the op will receive, so the plan stores what the op will find"""
    got = sk.resolve_face(solid, list(face.center()), list(face.normal_at(face.center())))
    c, n = got.center(), got.normal_at(got.center())
    return {"face_center": [round(c.X, 4), round(c.Y, 4), round(c.Z, 4)],
            "face_normal": [round(n.X, 4), round(n.Y, 4), round(n.Z, 4)]}
