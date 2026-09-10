"""
blocks.py — Phase 2: the verified building-block library.

The single biggest source of hallucination is asking the LLM to INVENT geometry
code from scratch. The fix: give it a curated set of small, already-TESTED
helper functions and tell it to COMPOSE from these instead. You cannot
hallucinate an API you are only calling.

Every function here:
  * takes plain numeric parameters,
  * returns a build123d `Part` (a real solid) using only API confirmed on this
    machine (build123d 0.11.1, algebra mode),
  * is exercised in the self-test at the bottom and validated with
    inspector.health(), so the library is guaranteed sound before the LLM ever
    touches it.

Convention: parts are built centered on the origin, extruded along +/-Z, so the
hole/pattern helpers (which cut tall cutters along Z) work regardless of scale.
"""

from __future__ import annotations
import functools
import math
import os
import re
import struct
import tempfile
from collections import OrderedDict
from pathlib import Path
from build123d import (
    Box, Cylinder, Sphere, Cone, Pos, PolarLocations, BuildSketch, RegularPolygon, BuildLine, Polyline, Spline, make_face,
    trace, extrude, revolve, Axis, Plane, Part, Mesher, Solid, Compound,
    scale as _b3d_scale,
    fillet as _b3d_fillet, chamfer as _b3d_chamfer, offset as _b3d_offset,
    import_step as b3d_import_step,
)
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve      # point-to-edge distance (resolve_edge)
from OCP.Extrema import Extrema_ExtPC
from OCP.gp import gp_Pnt

import inspector          # health of every fillet / chamfer result
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid

_AXES = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}


# ---------------------------------------------------------------------------
# Primitive solids
# ---------------------------------------------------------------------------

def plate(width: float, depth: float, thickness: float) -> Part:
    """A rectangular plate centered on the origin (X=width, Y=depth, Z=thickness)."""
    return Box(width, depth, thickness)


def disc(radius: float, thickness: float) -> Part:
    """A solid cylinder (disc) centered on the origin, axis along Z."""
    return Cylinder(radius=radius, height=thickness)


def ball(radius: float) -> Part:
    """A solid sphere centered on the origin. Great for domes (cut in half
    with a box), rounded ends, knobs, and stylized organic shapes."""
    return Sphere(radius=radius)


def cone(bottom_radius: float, top_radius: float, height: float) -> Part:
    """A (truncated) cone centered on the origin, axis along Z — spans
    -height/2 to +height/2. top_radius=0 gives a sharp point. Use for tapers,
    funnels, nose shapes, stylized bodies."""
    return Cone(bottom_radius=bottom_radius, top_radius=top_radius,
                height=height)


def tube(outer_radius: float, inner_radius: float, height: float) -> Part:
    """A hollow tube / ring / washer, axis along Z. inner < outer required."""
    if inner_radius >= outer_radius:
        raise ValueError("tube: inner_radius must be < outer_radius")
    return Cylinder(radius=outer_radius, height=height) - Cylinder(
        radius=inner_radius, height=height)


def polygon_plate(sides: int, circumradius: float, thickness: float) -> Part:
    """A regular-polygon prism (hex nut stock, etc.), axis along Z.
    circumradius = distance from center to a corner."""
    with BuildSketch() as sk:
        RegularPolygon(radius=circumradius, side_count=sides)
    return extrude(sk.sketch, amount=thickness)


def hex_plate(across_flats: float, thickness: float) -> Part:
    """A hexagonal plate specified by its across-flats (wrench) size."""
    circumradius = across_flats / math.sqrt(3.0)   # AF = circumradius * sqrt(3)
    return polygon_plate(6, circumradius, thickness)


def revolve_profile(points: list[tuple[float, float]]) -> Part:
    """Revolve a 2D profile 360 deg about the Z axis to make an axisymmetric
    solid (hub, pulley, shaft, shroud). `points` are (radius, z) pairs in the XZ
    plane; the profile is auto-closed. All radii must be >= 0. This is the
    workhorse for turned/turbomachinery-style parts."""
    if len(points) < 3:
        raise ValueError("revolve_profile: need at least 3 points")
    pts = [(float(r), float(z)) for r, z in points]
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine():
            Polyline(*pts, close=True)
        make_face()
    return revolve(sk.sketch, axis=Axis.Z)


def curved_blade(inner_radius: float, outer_radius: float,
                 inlet_angle_deg: float, exit_angle_deg: float,
                 height: float, thickness: float) -> Part:
    """A real turbomachinery-style curved (backswept) blade, standing on the XY
    plane and extruded up +Z by `height`.

    The blade follows a CAMBER LINE computed by integrating the blade-angle law
    d(theta) = tan(beta)/r * dr, with beta varying linearly from
    `inlet_angle_deg` (at inner_radius) to `exit_angle_deg` (at outer_radius).
    Angles are measured from the radial direction; 0 = straight radial blade,
    positive = backswept. Typical centrifugal impeller: inlet 20-40, exit 40-60.

    The result is intersected with a cylinder of `outer_radius`, so the tip
    radius is EXACT by construction. The inner end sits at `inner_radius` —
    make that SMALLER than the hub's local radius so the blade overlaps into
    the hub and fuses (touching is not enough).
    """
    if inner_radius >= outer_radius:
        raise ValueError("curved_blade: inner_radius must be < outer_radius")
    if thickness <= 0 or height <= 0:
        raise ValueError("curved_blade: height and thickness must be positive")

    # camber line: beta(r) linear, theta integrated with tan(beta)/r
    n = 16
    pts, theta = [], 0.0
    for i in range(n + 1):
        t = i / n
        r = inner_radius + (outer_radius - inner_radius) * t
        pts.append((r * math.cos(theta), r * math.sin(theta)))
        if i < n:
            beta = math.radians(inlet_angle_deg
                                + (exit_angle_deg - inlet_angle_deg) * t)
            theta += math.tan(beta) / r * ((outer_radius - inner_radius) / n)

    with BuildSketch() as sk:
        with BuildLine():
            Spline(*pts)
        trace(line_width=thickness)
    blade = extrude(sk.sketch, amount=height)
    # trim to the exact tip radius (trace() overshoots at the rounded tip)
    return blade & Cylinder(radius=outer_radius, height=4 * height)


# ---------------------------------------------------------------------------
# Feature operations (take a part, return a modified part)
# ---------------------------------------------------------------------------

def _tall_cutter(radius: float, span: float = 1.0e5) -> Part:
    """A cylinder tall enough to cut clean through any reasonably-sized part."""
    return Cylinder(radius=radius, height=span)


def with_center_hole(part: Part, radius: float) -> Part:
    """Drill a through-hole on the Z axis at the origin."""
    return part - _tall_cutter(radius)


def with_bolt_circle(part: Part, count: int, bolt_radius: float,
                     pitch_circle_dia: float) -> Part:
    """Drill `count` through-holes evenly on a bolt circle of the given pitch
    circle diameter (PCD), centered on the origin, axis along Z."""
    if count < 1:
        raise ValueError("with_bolt_circle: count must be >= 1")
    cutter = _tall_cutter(bolt_radius)
    result = part
    for loc in PolarLocations(radius=pitch_circle_dia / 2.0, count=count):
        result = result - (loc * cutter)
    return result


def polar_pattern(feature: Part, count: int, **kw) -> Part:
    """The union of `count` copies of `feature`, evenly rotated about Z — the
    N-fold symmetric parts (impeller blades) the AI builds from ONE feature.
    Lives in pattern.py now (P4: a pattern repeats a FEATURE too; see there
    for `axis`, `angle`, `seed`); this name stays for the legacy callers."""
    from pattern import polar_pattern as op
    return op(feature, count, **kw)


# ---------------------------------------------------------------------------
# Transform / finishing operations (E1) — take a part, return a new part
# ---------------------------------------------------------------------------

def rotate(part: Part, axis: str = "Z", angle_deg: float = 90.0) -> Part:
    """Rotate a part about the X, Y or Z axis (through the origin). The way to
    lay a cylinder on its side: rotate(wheel, "X", 90)."""
    if axis not in _AXES:
        raise ValueError('rotate: axis must be "X", "Y" or "Z"')
    return part.rotate(_AXES[axis], angle_deg)


def mirror_copy(part: Part, plane="YZ", join: bool = False) -> Part:
    """`mirror` in a script — ONE grammar with the feature tree's op
    (`pattern.mirror`, specs/mirror.md). `plane` is an origin plane name
    ("XY" / "XZ" / "YZ"), the body's mid-plane ({"mid": "X"}) or an explicit
    {"origin", "normal"}; `join=True` returns the part fused with its
    reflection (Fusion's Join: one symmetric solid), the default the reflected
    COPY alone, as every older script expects. A picked face needs the tree."""
    import pattern                      # pattern -> sketch -> blocks: never at import time
    return pattern.mirror(part, plane, join=join)


def scale_uniform(part: Part, factor: float) -> Part:
    """Uniformly scale a part about its own SHAPE CENTRE, so the body stays
    where it is (2 = double size).

    Measured 2026-09-10: build123d's scale() is centre-based, not
    origin-based, and this said "about the origin" for as long as it existed.
    `rotate` below is the one that turns about the WORLD origin, so the two
    Transform buttons do NOT share a pivot -- stated here and in
    author.OP_NOTES because a wrong pivot is not visible in a signature."""
    if factor <= 0:
        raise ValueError("scale: factor must be positive")
    return _b3d_scale(part, by=factor)


def linear_pattern(feature: Part, count: int, dx: float = 0.0,
                   dy: float = 0.0, dz: float = 0.0, **kw) -> Part:
    """Union of `count` copies of a feature stepped by (dx, dy, dz) each time
    (copy 0 stays in place), e.g. a row of 4 wheels: count=4, dx=30. Lives in
    pattern.py now (P4: `direction`, `distance`, a second direction, `seed`);
    this name stays for the legacy callers."""
    from pattern import linear_pattern as op
    return op(feature, count, dx, dy, dz, **kw)


# ---------------------------------------------------------------- edges ----
# Fillet / Chamfer take edges TWO ways (specs/fillet-chamfer.md): a GROUP name
# (the AI's vocabulary: "all" / "top" / ...) or a list of PICKED edges stored by
# GEOMETRY — never by index, which the next upstream change would reshuffle.
# A picked edge is "the edge shared by these two faces", each face by its
# centre + normal (resolve_face, the rule the face pick already lives by), with
# the midpoint as the tie-breaker when the faces share several edges. Probed
# 2026-09-04 (probes/fillet_edges_probe.py): after a chamfer ATE the edge the
# resolved faces share nothing and the feature says so, where the nearest
# midpoint would have quietly rounded the bevel's new edge instead. The same
# probe found the second banned failure live: a fillet larger than the corner
# fillet next to it "succeeds" as an INVALID solid — so every result is
# health-checked before it is returned.

_EDGE_RULES = ("all", "top", "bottom", "vertical", "horizontal")


def resolve_face(solid, face_center: list, face_normal: list | None = None):
    """Find the face of `solid` a user picked, by GEOMETRY (nearest center,
    same-facing normal) — so a stored pick survives parameter changes instead
    of breaking like a face index would. Shared by sketch_on_face, extrude_face,
    the face-outline projection and the edge pick (two faces name an edge)."""
    rows = _face_rows(solid)
    if not rows:
        raise ValueError("solid has no faces")
    cx, cy, cz = (float(v) for v in face_center)

    def score(row):
        _f, (x, y, z), n = row
        d = (x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2
        if face_normal and n is not None:
            align = n[0] * face_normal[0] + n[1] * face_normal[1] + n[2] * face_normal[2]
            d += (1.0 - align) * 25.0          # nudge toward same-facing
        return d

    return min(rows, key=score)[0]


def _face_rows(solid) -> list:
    """(face, centre, normal) for every face of a shape, measured ONCE per shape
    object and kept beside it (_cached). resolve_face is asked for BOTH stored
    faces of every picked edge on every plan, and a face centre is a BRepGProp
    integration (0.14 ms): 254 faces x 96 calls was 15 s of a 33 s click on
    esp32-remote (profiled 2026-09-08). A face the kernel will not measure is
    never the nearest; a normal it will not give costs that face its nudge, as
    before."""
    return _cached(solid, "faces", lambda: _measure_face_rows(solid))


def _measure_face_rows(solid) -> list:
    rows = []
    for f in solid.faces():
        try:
            c = f.center()
        except Exception:
            continue
        try:
            n = f.normal_at(c)
            n = (float(n.X), float(n.Y), float(n.Z))
        except Exception:
            n = None
        rows.append((f, (float(c.X), float(c.Y), float(c.Z)), n))
    return rows


def _shape_key(shape):
    """Identity of a TopoDS shape (its TShape hash — unique within one part,
    1.5 us; see studio._shape_key for the measurement)."""
    return hash(shape.wrapped)


def _v3(v) -> list[float]:
    return [round(float(v.X), 4), round(float(v.Y), 4), round(float(v.Z), 4)]


def _gtype(edge) -> str:
    return str(edge.geom_type).split(".")[-1]


# id(shape) -> [the shape, {slot: (its TopoDS shape, its hash, value)}]
_SHAPE_CACHES = OrderedDict()
_MAX_SHAPE_CACHES = 8       # bodies; ~1.3 MB of python wrappers each at 200 faces


def _cached(shape, slot: str, build):
    """A per-shape memo that lives BESIDE the shape, never on it. Stored as an
    attribute it rides along in build123d's __deepcopy__ — and moved() /
    `Pos * part` copy first and move second, so a moved body inherited its
    parent's face centres at the OLD position and resolve_face named the wrong
    face (probes/shape_cache_probe.py; the fast tier caught it on a moved
    plate).

    Keyed on the IDENTITY of the python object, so a copy is a miss, and
    BOUNDED, oldest out. A weak key could never expire here: the memo holds the
    shape's own Faces and Edges and every one of them points back at the shape
    (Face.topo_parent), so the value kept its own key alive and every
    superseded body stayed in the process for good — 8 throwaway bodies, 8 live
    entries (probes/shape_cache_leak_probe.py §1).

    Freshness is TWO tests because an in-place `part.move()` mutates the SAME
    TopoDS shape: IsEqual then compares it with itself and says True, so the
    stored hash — which the move does change — is what catches it. (The old
    comment credited IsEqual; what actually saved that answer was hash(Part)
    changing, which orphaned the entry and inserted a second immortal one.)"""
    key = id(shape)
    ent = _SHAPE_CACHES.get(key)
    if ent is not None and ent[0] is shape:
        hit = ent[1].get(slot)
        if hit is not None and hit[1] == _shape_key(shape) \
                and hit[0].IsEqual(shape.wrapped):
            _touch(key)
            return hit[2]
    else:
        ent = [shape, {}]                  # holding the shape is what makes id() safe
    value = build()
    ent[1][slot] = (shape.wrapped, _shape_key(shape), value)
    _SHAPE_CACHES[key] = ent
    _touch(key)
    while len(_SHAPE_CACHES) > _MAX_SHAPE_CACHES:
        try:
            _SHAPE_CACHES.popitem(last=False)
        except KeyError:                   # another request evicted it first
            break
    return value


def _touch(key):
    """newest end of the memo — the body in hand must not be the one evicted"""
    try:
        _SHAPE_CACHES.move_to_end(key)
    except KeyError:                       # evicted between the read and here
        pass


def _edge_topo(part: Part) -> dict:
    """The topology an edge tool asks for over and over — every edge, which
    faces share each edge, which edges bound each face, and the two ends of
    every edge (the tangent chain's walk) — enumerated ONCE per built body and
    kept beside it (_cached; a rebuild is a new Part, so nothing goes stale).
    build123d's faces() / edges() are not memoised: on esp32-remote (254 faces,
    609 edges) faces() costs 33 ms and a face's edges() 11 ms, and one plan on
    a 48-edge selection paid for them again for EVERY stored edge — 33 s per
    click (profiled 2026-09-08; probes/feature_edges_probe.py --big)."""
    return _cached(part, "edges", lambda: _build_edge_topo(part))


def _build_edge_topo(part: Part) -> dict:
    edge_faces, face_edges = {}, {}
    for f in part.faces():
        es = list(f.edges())
        face_edges[_shape_key(f)] = es
        for e in es:
            edge_faces.setdefault(_shape_key(e), []).append(f)
    edges = list(part.edges())
    # vertex -> the edges ending there, each with its tangent AT that end; and
    # per edge its two (vertex, tangent) ends — so the chain walk is lookups
    # and dot products (evaluating tangents in the walk was 0.7 s a click)
    ends, edge_ends = {}, {}
    for e in edges:
        mine = []
        for t in (0.0, 1.0):
            try:
                p, tan = e @ t, e % t
            except Exception:
                continue                   # an edge the kernel will not place joins no chain
            vkey = (round(p.X, 4), round(p.Y, 4), round(p.Z, 4))
            ends.setdefault(vkey, []).append((e, tan))
            mine.append((vkey, tan))
        edge_ends[_shape_key(e)] = mine
    return {"edges": edges, "edge_faces": edge_faces, "face_edges": face_edges,
            "ends": ends, "edge_ends": edge_ends}


def _edge_faces(part: Part) -> dict:
    """edge key -> the faces that share it, for the whole part (cached: _edge_topo)."""
    return _edge_topo(part)["edge_faces"]


def _face_edges(part: Part, face) -> list:
    """the edges bounding a face of `part` (cached: _edge_topo)"""
    es = _edge_topo(part)["face_edges"].get(_shape_key(face))
    return es if es is not None else list(face.edges())


def edge_ref(part: Part, edge, faces_by_edge: dict | None = None) -> dict:
    """The STORED form of a picked edge: midpoint, direction, curve type and the
    two faces it separates (centre + normal each)."""
    faces_by_edge = faces_by_edge or _edge_faces(part)
    faces = []
    for f in faces_by_edge.get(_shape_key(edge), [])[:2]:
        c = f.center()
        try:
            n = f.normal_at(c)
        except Exception:
            n = f.normal_at()
        faces.append({"center": _v3(c), "normal": _v3(n)})
    d = edge % 0.5
    # a stored direction has ONE sign: an edge comes out of a face with the
    # face's orientation, out of the part with its own — identity ignores sign
    if next((c for c in (d.X, d.Y, d.Z) if abs(c) > 1e-9), 1.0) < 0:
        d = -d
    return {"mid": _v3(edge @ 0.5), "dir": _v3(d), "type": _gtype(edge),
            "faces": faces}


def _nearest_edge(edges, ref: dict):
    mx, my, mz = (float(v) for v in ref["mid"])
    d = ref.get("dir")
    gt = ref.get("type")

    def score(e):
        m = e @ 0.5
        s = (m.X - mx) ** 2 + (m.Y - my) ** 2 + (m.Z - mz) ** 2
        if d:
            t = e % 0.5
            s += (1.0 - abs(t.X * d[0] + t.Y * d[1] + t.Z * d[2])) * 25.0
        if gt and _gtype(e) != gt:
            s += 100.0
        return s

    return min(edges, key=score)


def _poly_mid(points) -> list[float]:
    """The point half-way along a polyline's length — the viewport sends an
    edge's drawn points untouched (R1: no maths in JS); for a 2-point line this
    is the exact midpoint, for a 24-step circle it is within 0.1% of it."""
    pts = [tuple(float(c) for c in p) for p in points]
    if len(pts) == 1:
        return list(pts[0])
    seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    half, run = sum(seg) / 2, 0.0
    for (a, b), L in zip(zip(pts, pts[1:]), seg):
        if run + L >= half and L > 0:
            t = (half - run) / L
            return [a[i] + (b[i] - a[i]) * t for i in range(3)]
        run += L
    return list(pts[-1])


def _edge_distance(edge, pt) -> float:
    """Distance from a point to the edge ITSELF — bounded by its ends, never the
    infinite line (probes/edge_point_distance_probe.py: 75 us a pair)."""
    ad = BRepAdaptor_Curve(edge.wrapped)
    g = gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2]))
    best = min(ad.Value(ad.FirstParameter()).Distance(g),
               ad.Value(ad.LastParameter()).Distance(g))
    ext = Extrema_ExtPC(g, ad)
    if ext.IsDone():
        for i in range(1, ext.NbExt() + 1):
            best = min(best, ext.SquareDistance(i) ** 0.5)
    return best


PICK_ON_EDGE_TOL = 0.05     # mm; the drawn points are the mesh's own nodes, to 1e-4


def _edge_under(part: Part, points, gtype: str | None = None):
    """The edge of `part` a drawn line lies ON — its two ends and its middle all
    within PICK_ON_EDGE_TOL of the edge — or None when it lies on none."""
    pts = [tuple(float(c) for c in p) for p in points]
    samples = (pts[0], pts[len(pts) // 2], pts[-1])
    best, best_d = None, None
    for e in _edge_topo(part)["edges"]:
        if gtype and _gtype(e) != gtype:
            continue
        d = 0.0
        for q in samples:
            d = max(d, _edge_distance(e, q))
            if d > PICK_ON_EDGE_TOL:
                break
        if d <= PICK_ON_EDGE_TOL and (best_d is None or d < best_d):
            best, best_d = e, d
    return best


def resolve_edge(part: Part, ref: dict):
    """The edge of `part` a stored pick means — by the two faces it separates
    when the pick recorded them, else by the nearest midpoint (+ direction).
    Raises the sentence the feature shows when the edge is gone.

    A RAW viewport pick carries the drawn `points` of a line on screen instead:
    an edge of this body — or of the PREVIEW body a round is being tried on,
    whose unchanged and TRIMMED edges lie exactly on their parents while the
    round's own new rims lie on none. So the identity is "lies on", never
    "nearest midpoint": nearest answered a click on a new rim with the edge it
    replaced, and the click silently un-picked it."""
    if ref.get("mid") is None and ref.get("points"):
        e = _edge_under(part, ref["points"], ref.get("type"))
        if e is None:
            x, y, z = _poly_mid(ref["points"])
            raise ValueError(
                f"the line clicked at ({x:g}, {y:g}, {z:g}) is not an edge of this "
                f"body — it is a rim the round or bevel being previewed has made. "
                f"Click an edge of the body itself; the gold lines are the ones picked so far.")
        return e
    faces = ref.get("faces") or []
    if len(faces) == 2:
        fa, fb = (resolve_face(part, f["center"], f.get("normal")) for f in faces)
        # resolve_face is a NEAREST match — it always returns something. When
        # one of the two stored faces is gone, both can land on the SAME face,
        # whose edges all "share" it: without this check the refusal below is
        # skipped and the feature quietly rounds a different edge.
        shared = []
        if _shape_key(fa) != _shape_key(fb):
            kb = {_shape_key(e) for e in _face_edges(part, fb)}
            shared = [e for e in _face_edges(part, fa) if _shape_key(e) in kb]
        if not shared:
            x, y, z = ref.get("mid", [0, 0, 0])
            raise ValueError(
                f"the picked edge at ({x:g}, {y:g}, {z:g}) is no longer on the "
                f"body — an upstream change removed it (the two faces it sat "
                f"between no longer meet). Re-pick the edges of this feature.")
        return shared[0] if len(shared) == 1 else _nearest_edge(shared, ref)
    if len(faces) == 1:                         # a SEAM of a round face touches one face
        fa = resolve_face(part, faces[0]["center"], faces[0].get("normal"))
        return _nearest_edge(_face_edges(part, fa), ref)
    if ref.get("mid") is None:
        raise ValueError("a picked edge needs its midpoint ('mid': [x, y, z]) — "
                         "pick it in the viewport")
    return _nearest_edge(_edge_topo(part)["edges"], ref)


def tangent_chain(part: Part, edge, tol: float = 0.99) -> list:
    """`edge` plus every edge smoothly connected to it (Fusion's tangent chain):
    walk shared vertices while the tangents agree. A rounded rim is one chain;
    a sharp box edge is a chain of one (probed 2026-09-04). The vertex table is
    the body's, built once (_edge_topo): rebuilding it here cost 265 ms per
    picked edge on esp32-remote."""
    topo = _edge_topo(part)
    ends, own = topo["ends"], topo["edge_ends"]
    seen = {_shape_key(edge)}
    out, todo = [edge], [edge]
    while todo:
        e = todo.pop()
        for vkey, tan in own.get(_shape_key(e), []):
            for other, otan in ends.get(vkey, []):
                if _shape_key(other) in seen:
                    continue
                if abs(tan.dot(otan)) > tol:
                    seen.add(_shape_key(other))
                    out.append(other)
                    todo.append(other)
    return out


def _pick_edges(part: Part, which: str):
    edges = part.edges()
    if which == "all":
        return edges
    if which == "top":
        return edges.group_by(Axis.Z)[-1]
    if which == "bottom":
        return edges.group_by(Axis.Z)[0]
    if which == "vertical":
        # edges parallel to Z — the 4 corner edges of a box (round-the-corners)
        picked = edges.filter_by(Axis.Z)
        if not picked:
            raise ValueError('no "vertical" edges (none run parallel to Z)')
        return picked
    if which == "horizontal":
        # edges lying flat (parallel to X or Y) — top+bottom rims
        picked = edges.filter_by(Axis.X) + edges.filter_by(Axis.Y)
        if not picked:
            raise ValueError('no "horizontal" edges (none parallel to X or Y)')
        return picked
    raise ValueError(f'edges must be one of {", ".join(_EDGE_RULES)}, or a list '
                     f"of picked edges")


def edges_for(part: Part, edges) -> list:
    """The edges an `edges` param names: a group name, or a list of picked
    edges (dicts from edge_ref, or bare [x, y, z] midpoints)."""
    if isinstance(edges, str):
        return list(_pick_edges(part, edges))
    if isinstance(edges, (list, tuple)):
        if not edges:
            raise ValueError("no edges picked — click at least one edge of the body")
        out, seen = [], set()
        for r in edges:
            e = resolve_edge(part, r if isinstance(r, dict) else {"mid": list(r)})
            if _shape_key(e) not in seen:
                seen.add(_shape_key(e))
                out.append(e)
        return out
    raise ValueError(f'edges must be one of {", ".join(_EDGE_RULES)}, or a list '
                     f"of picked edges")


# OCCT's own vocabulary. A user-facing sentence never carries it (the same
# rule tests/gauntlet.py enforces), so a failure wearing it is named plainly.
_KERNEL_WORDS = ("TopoDS", "NCollection", "Standard_", "BRep", "StdFail",
                 "Geom_", "gp_", "TColStd", "BOPAlgo")


def _plain_cause(e: Exception) -> str:
    """The REAL reason a build failed, in words a user can act on.

    build123d's own refusal is already plain; a raw OCP error is jargon, so it
    is named without its internals; anything else (a TypeError — our own bug)
    says what it is instead of being dressed up as a geometry problem. Never
    invent a diagnosis: before 2026-09-04 every failure here was reported as
    \"a face beside them is too small\", which was a guess for all but one of them."""
    msg = (str(e) or "").strip()
    if re.match(r"Failed creating a (fillet|chamfer)", msg):
        return "the kernel could not build it there"
    if not msg or any(w in msg or w in type(e).__name__ for w in _KERNEL_WORDS):
        return "the geometry kernel rejected the shape it would produce"
    if isinstance(e, ValueError):
        return msg
    return f"{type(e).__name__}: {msg}"


def _finish(name: str, part: Part, edges, value: float, unit: str, build):
    """Shared by fillet_edges / chamfer_edges: the value guard, the kernel call,
    the health check, and a refusal that says the TRUE reason.

    NOTHING here is speculative: the kernel is called ONCE, with the value the
    user asked for. A bisection for "the largest that would fit" used to run
    here — 10 more builds on every rebuild of a failing feature — and probing
    radii nobody typed is not merely slow: on the user's esp32-remote design
    (254 faces) a refused radius 4 made it try 2.0, and OCCT SEGFAULTED, taking
    the server and every unsaved tab with it (reproduced 2026-09-04, exit 139).

    The health check is the CHEAP one — Document.rebuild's own per-feature
    policy. OCCT's validity analysis is ~270 ms on a large solid, and the RESULT
    gets it anyway in the deep-check pass after the rebuild loop. It still
    catches the second banned failure: a round larger than the round beside it
    comes back as a solid the kernel ACCEPTS, and it is not watertight
    (measured 2026-09-04 — the manifold check sees it, validity adds nothing)."""
    if value is None or not value > 0:
        raise ValueError(f"{name}: {unit} must be positive (got "
                         f"{'nothing' if value is None else format(value, 'g')}) — "
                         f"drag the handle or type a value")
    picked = edges_for(part, edges)
    n = len(picked)
    on = f"{n} edge{'s' if n != 1 else ''}"
    low = unit.lower()
    try:
        out = build(picked, value)
    except Exception as e:                      # OCP errors are Exception, not RuntimeError
        raise ValueError(f"{name}: {low} {value:g} mm does not fit on {on} — "
                         f"{_plain_cause(e)}. Try a smaller {low}, or pick "
                         f"different edges.") from e
    # measured OUTSIDE that try on purpose: a health check that throws is our
    # own problem, and must never be reported as a value that "does not fit"
    problems = inspector.health(out, check_valid=False)
    if not problems:
        return out
    raise ValueError(f"{name}: {low} {value:g} mm leaves a broken solid on {on} — "
                     f"{problems[0]}. It runs into a neighbouring face or round; "
                     f"try a smaller {low}.")


def fillet_edges(part: Part, radius: float, edges="all") -> Part:
    """Round edges with a radius. `edges`: "all", "top", "bottom", "vertical"
    (the 4 upright corner edges — for rounding the corners of a box/enclosure),
    "horizontal" (the flat top+bottom rims), or a LIST of picked edges (see
    edge_ref). The radius must be smaller than the neighbouring faces allow;
    the refusal names the largest that fits."""
    return _finish("fillet", part, edges, radius, "radius",
                   lambda es, v: _b3d_fillet(es, radius=v))


def chamfer_edges(part: Part, length: float, edges="all") -> Part:
    """Cut a flat 45-degree bevel on edges. `edges` as for fillet_edges."""
    return _finish("chamfer", part, edges, length, "distance",
                   lambda es, v: _b3d_chamfer(es, length=v))


def shell_out(part: Part, thickness: float, open_face: str = "top") -> Part:
    """Hollow a part into walls of `thickness`. open_face "top"/"bottom" removes
    that face (an open container, e.g. a cup); "none" keeps it fully closed."""
    if thickness <= 0:
        raise ValueError("shell: thickness must be positive")
    if open_face == "none":
        return _b3d_offset(part, amount=-thickness)
    if open_face in ("top", "bottom"):
        idx = -1 if open_face == "top" else 0
        face = part.faces().sort_by(Axis.Z)[idx]
        return _b3d_offset(part, amount=-thickness, openings=face)
    raise ValueError('shell: open_face must be "top", "bottom" or "none"')


# ---------------------------------------------------------------------------
# Mesh import (STL from outside sources)
# ---------------------------------------------------------------------------

IMPORTS_DIR = Path(__file__).parent / "imports"   # UI uploads land here
MAX_STL_TRIANGLES = 20_000                        # keeps rebuild + display usable


def _stl_triangles(data: bytes) -> tuple[str, int]:
    """('ascii'|'binary', triangle count) without a full parse. ASCII is
    detected by content, not just the 'solid' prefix — some binary exporters
    put 'solid' in the 80-byte header too, so the size formula decides."""
    head = data[:80].lstrip()
    if head.startswith(b"solid") and b"facet" in data:
        return "ascii", data.count(b"facet normal")
    if len(data) >= 84:
        (n,) = struct.unpack_from("<I", data, 80)
        if len(data) >= 84 + 50 * n:
            return "binary", n
    if head.startswith(b"solid"):
        return "ascii", 0
    raise ValueError("import_stl: not an STL file (neither binary nor ascii STL)")


def _ascii_stl_to_binary(data: bytes) -> bytes:
    """lib3mf's STL reader only accepts BINARY STL — ascii files fail with a
    cryptic 'Reading from a stream was not possible'. Convert up front."""
    verts = re.findall(
        rb"vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", data)
    if not verts or len(verts) % 3:
        raise ValueError("import_stl: malformed ascii STL "
                         "(vertex count is not a multiple of 3)")
    out = bytearray(b"\0" * 80)
    out += struct.pack("<I", len(verts) // 3)
    for i in range(0, len(verts), 3):
        out += struct.pack("<3f", 0.0, 0.0, 0.0)   # normals recomputed on read
        for v in verts[i:i + 3]:
            out += struct.pack("<3f", float(v[0]), float(v[1]), float(v[2]))
        out += struct.pack("<H", 0)
    return bytes(out)


def _stl_bytes_to_solids(data: bytes) -> tuple[list, int]:
    """One binary STL through lib3mf into closed Solids. Returns
    (solids, open_shell_count). A shape that is already a valid positive
    Solid is taken AS-IS — exploding it per shell would split a hollow part
    into an outer solid plus a phantom cavity solid."""
    tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        try:
            shapes = Mesher().read(tmp.name)
        except Exception as e:   # lib3mf errors do NOT derive from RuntimeError
            raise ValueError(f"import_stl: could not read the STL ({e})") from e
    finally:
        tmp.close()
        os.unlink(tmp.name)

    solids, open_shells = [], 0
    for shp in shapes:
        try:
            if isinstance(shp, Solid) and shp.volume > 0 and shp.is_valid():
                solids.append(shp)
                continue
        except Exception:
            pass
        for sh in shp.shells():
            if not BRep_Tool.IsClosed_s(sh.wrapped):
                open_shells += 1
                continue
            sol = Solid(BRepBuilderAPI_MakeSolid(sh.wrapped).Solid())
            if sol.volume < 0:               # inverted winding — flip it
                sol = Solid(sol.wrapped.Reversed())
            solids.append(sol)
    return solids, open_shells


@functools.lru_cache(maxsize=8)
def _read_stl_solids(path_str: str, mtime_ns: int, size: int) -> tuple:
    """Read (+ auto-repair) an STL into (tuple of closed Solids, report dict).
    Cached on (path, mtime, size): Document.rebuild() re-evaluates every
    feature on every edit, and re-parsing a big mesh each time would crawl.
    Downstream ops never mutate OCCT shapes, so sharing the cached Solids
    across rebuilds is safe.

    Clean meshes under MAX_STL_TRIANGLES go straight to the kernel. Anything
    dirty (duplicated interface walls, pinched edges, too dense) goes through
    meshrepair's heal/split/remesh/decimate pipeline first — feeding a broken
    mesh straight to OCCT produced a 6-minute read returning an EMPTY invalid
    solid (probed on a real Fusion assembly export)."""
    import meshrepair

    data = Path(path_str).read_bytes()
    fmt, ntri = _stl_triangles(data)
    if ntri == 0:
        raise ValueError("import_stl: the file contains no triangles")
    if ntri > meshrepair.MAX_INPUT_TRIANGLES:
        raise ValueError(
            f"import_stl: mesh has {ntri:,} triangles — beyond the "
            f"{meshrepair.MAX_INPUT_TRIANGLES:,} import limit even for "
            "auto-repair. Decimate it in a mesh tool (Blender/MeshLab) "
            "and re-export.")
    if fmt == "ascii":
        data = _ascii_stl_to_binary(data)

    verts, faces = meshrepair.parse_binary_stl(data)
    boundary, overshared = meshrepair.edge_counts(faces)
    dupes = bool(meshrepair.duplicate_triangles(faces).any())
    report = {"input_triangles": ntri, "output_triangles": ntri,
              "healed_wall_triangles": 0, "remeshed_bodies": 0,
              "repaired": False}

    if ntri <= MAX_STL_TRIANGLES and not (boundary or overshared or dupes):
        pieces = [data]
    else:
        try:
            pieces, rep = meshrepair.repair_stl_mesh(data)
        except ValueError as e:
            raise ValueError(f"import_stl: {e}") from e
        report.update(rep)
        report["repaired"] = True

    solids, open_shells = [], 0
    for piece in pieces:
        s, o = _stl_bytes_to_solids(piece)
        solids.extend(s)
        open_shells += o
    if open_shells:
        raise ValueError(
            f"import_stl: the mesh is not watertight ({open_shells} open "
            f"shell(s), {len(solids)} closed) — a solid needs a fully closed "
            "surface. Repair it in a mesh tool and re-export.")
    if not solids:
        raise ValueError("import_stl: no solid found in the mesh")
    report["bodies"] = len(solids)
    return tuple(solids), report


def _resolve_stl_path(file: str) -> Path:
    if not isinstance(file, str) or not file.strip():
        raise ValueError("import_stl: file must be a filename or path")
    path = Path(file)
    if not path.is_absolute():
        path = IMPORTS_DIR / file
    if not path.is_file():
        raise ValueError(f"import_stl: file not found: {path}")
    return path


def import_stl(file: str, scale: float = 1.0) -> Part:
    """Import an external STL mesh file as a solid body. `file` is an absolute
    path, or the name of a file in the imports/ folder (where UI uploads
    land). The triangles become a faceted solid; broken meshes (duplicated
    interface walls, pinched edges, too dense) are auto-repaired via
    meshrepair — meshes with actual holes are refused. STL units are read as
    mm; `scale` resizes on import (e.g. 25.4 for a file modeled in inches)."""
    if not isinstance(scale, (int, float)) or scale <= 0:
        raise ValueError("import_stl: scale must be a positive number")
    path = _resolve_stl_path(file)
    st = path.stat()
    solids, _report = _read_stl_solids(str(path), st.st_mtime_ns, st.st_size)
    # NOTE: Part(solid.wrapped) reports volume 0 (probed) — never wrap that
    # way. Multi-body imports become a Compound, NOT a fuse: assembly exports
    # overlap/touch, and fusing two 10k-triangle meshes can hang the kernel.
    part = solids[0] if len(solids) == 1 else Compound(children=list(solids))
    if scale != 1.0:
        part = _b3d_scale(part, by=float(scale))
    return part


def _resolve_step_path(file: str) -> Path:
    if not isinstance(file, str) or not file.strip():
        raise ValueError("import_step: file must be a filename or path")
    path = Path(file)
    if not path.is_absolute():
        path = IMPORTS_DIR / file
    if not path.is_file():
        raise ValueError(f"import_step: file not found: {path}")
    if path.suffix.lower() not in (".step", ".stp"):
        raise ValueError(f"import_step: {path.name} is not a STEP file "
                         "(.step / .stp)")
    return path


def import_step(file: str, scale: float = 1.0) -> Part:
    """Import a STEP file (.step/.stp) as exact BREP solid bodies. `file` is an
    absolute path, or the name of a file in the imports/ folder.

    Unlike STL there is no faceting and nothing to repair: the geometry comes
    back as real curves and surfaces, so cylinders stay round and a design
    exported from HERE re-imports losslessly (the user's round-trip case,
    2026-08-31). Multi-solid files become a Compound, NOT a fuse — assemblies
    overlap or touch, and merging them is not this op's decision. STEP files
    carry their own units (read as mm); `scale` resizes on import."""
    if not isinstance(scale, (int, float)) or scale <= 0:
        raise ValueError("import_step: scale must be a positive number")
    path = _resolve_step_path(file)
    try:
        shape = b3d_import_step(str(path))
    except Exception as e:      # OCP read errors are Exception, not RuntimeError
        raise ValueError(f"import_step: could not read the STEP ({e})") from e
    solids = shape.solids()
    if not solids:
        raise ValueError("import_step: the file contains no solid bodies — "
                         "surfaces or curves alone cannot be used here")
    # NOTE: never Part(solid.wrapped) — that reports volume 0 (probed).
    part = solids[0] if len(solids) == 1 else Compound(children=list(solids))
    try:
        vol = float(part.volume)
    except Exception:
        vol = 0.0
    if vol <= 0:
        raise ValueError("import_step: the imported geometry has no volume")
    if scale != 1.0:
        part = _b3d_scale(part, by=float(scale))
    return part


def import_stl_report(file: str) -> dict:
    """The repair/import report for an STL (free: served from the same cache
    as import_stl). Keys: input_triangles, output_triangles, bodies,
    healed_wall_triangles, remeshed_bodies, repaired."""
    path = _resolve_stl_path(file)
    st = path.stat()
    return _read_stl_solids(str(path), st.st_mtime_ns, st.st_size)[1]


# ---------------------------------------------------------------------------
# Registry — the exact names exposed to the LLM's script namespace
# ---------------------------------------------------------------------------

EXPORTS = {
    "plate": plate,
    "disc": disc,
    "ball": ball,
    "cone": cone,
    "tube": tube,
    "polygon_plate": polygon_plate,
    "hex_plate": hex_plate,
    "revolve_profile": revolve_profile,
    "curved_blade": curved_blade,
    "with_center_hole": with_center_hole,
    "with_bolt_circle": with_bolt_circle,
    "polar_pattern": polar_pattern,
    "rotate": rotate,
    "mirror": mirror_copy,
    "scale": scale_uniform,
    "linear_pattern": linear_pattern,
    "fillet": fillet_edges,
    "chamfer": chamfer_edges,
    "shell": shell_out,
    "import_stl": import_stl,
    "import_step": import_step,
}


def api_summary() -> str:
    """A compact, copy-pasteable list of the blocks, for the system prompt."""
    return "\n".join(
        f"  {name}{_signature(fn)}" for name, fn in EXPORTS.items())


def _signature(fn) -> str:
    import inspect
    return str(inspect.signature(fn))


# ---------------------------------------------------------------------------
# Self-test — build every block and validate it with the inspector. No LLM.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import inspector
    from build123d import export_stl as _export_stl

    # import_stl needs a real file: round-trip a box through STL
    _selftest_stl = Path(tempfile.gettempdir()) / "_blocks_selftest.stl"
    _export_stl(Box(20, 10, 5), str(_selftest_stl))

    _selftest_step = Path(tempfile.gettempdir()) / "_blocks_selftest.step"
    import build123d as _b3d_mod
    _b3d_mod.export_step(Box(20, 10, 5), str(_selftest_step))

    cases = {
        "import_stl (box roundtrip)": import_stl(str(_selftest_stl)),
        "import_step (box roundtrip)": import_step(str(_selftest_step)),
        "plate":        plate(40, 30, 5),
        "disc":         disc(20, 8),
        "ball":         ball(15),
        "cone":         cone(20, 8, 25),
        "tube":         tube(20, 12, 6),
        "polygon_plate": polygon_plate(5, 25, 8),
        "hex_plate":    hex_plate(across_flats=30, thickness=8),
        "revolve_profile (pulley)":
            revolve_profile([(0, 0), (30, 0), (30, 6), (18, 12),
                             (18, 20), (0, 20)]),
        "curved_blade (backswept)":
            curved_blade(inner_radius=10, outer_radius=40,
                         inlet_angle_deg=25, exit_angle_deg=55,
                         height=20, thickness=2.5),
        "with_center_hole": with_center_hole(disc(20, 8), 6),
        "with_bolt_circle (6)":
            with_bolt_circle(disc(50, 10), count=6, bolt_radius=4,
                             pitch_circle_dia=76),
        "polar_pattern (blades x8)":
            polar_pattern(Pos(20, 0, 0) * Box(24, 3, 10), count=8),
    }

    print("=== block library self-test (validated by inspector.health) ===")
    all_ok = True
    for name, part in cases.items():
        problems = inspector.health(part)
        status = "OK   " if not problems else "FAIL "
        if problems:
            all_ok = False
        vol = round(part.volume, 1)
        sym = inspector.rotational_symmetry_order(part)
        extra = f"vol={vol:<10} sym={sym}"
        print(f"  {status}{name:28} {extra}  {problems if problems else ''}")

    print("\nALL BLOCKS HEALTHY" if all_ok else "\nSOME BLOCKS FAILED — fix before use")

    print("\n=== api_summary (goes into the LLM system prompt) ===")
    print(api_summary())
