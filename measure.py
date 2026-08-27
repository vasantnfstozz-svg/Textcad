"""measure.py — the measurement kernel: how far, how wide, how thick.

Picking already produced rich geometry (studio.py's _tagged_mesh tags every
face with center/normal/area and every edge with type/length), but nothing let
the user ask the two questions a machinist actually asks: *what is this
diameter* and *how far is A from B*.

Deterministic and read-only. It never mutates the document and never raises for
geometry — a measurement it cannot make comes back as {"error": ...} so the UI
can say so honestly (Fusion parity rule 7: failures speak).

Two probed facts this module is built on (2026-08-27, measured not assumed):

  * `edge.center()` is a point ON a circle, NOT its centre — for a r=5 circle
    centred at (0,0,5) it returns (-5,0,5). `arc_center` is the only correct
    source. The same trap exists on cylindrical faces, where `center()` lies on
    the surface and `axis_of_rotation` gives the true axis. Using the wrong one
    is a silent one-radius error in every hole position.

  * Solid face normals are reliably OUTWARD, which makes the thickness/gap
    distinction purely geometric: with d = n1 · (c2 - c1), the faces point AWAY
    from each other when d < 0 (solid material between them — a THICKNESS) and
    TOWARD each other when d > 0 (empty space between them — a GAP). Probed on
    a box (top/bottom -> thickness 10), a slot (walls -> gap 10) and a blind
    pocket (floor to underside -> thickness 6, the remaining floor).

That second rule is why "how much material is left under this pocket" is a
first-class measurement here: on a vacuum-held part, cutting through is the
expensive mistake.
"""

from __future__ import annotations

import math

from OCP.BRepExtrema import BRepExtrema_DistShapeShape

import provenance

# |1 - |n1·n2|| below this counts as parallel. Face normals come from OCCT at
# double precision but a fused/tapered wall can wobble in the last digits.
PARALLEL_TOL = 1e-6
# below this a distance is "touching" rather than a gap
TOUCH_TOL = 1e-7

MM = "mm"


# ---------------------------------------------------------------------------
# small vector helpers (plain tuples — no numpy in this project)

def _xyz(v) -> list[float]:
    """build123d Vector / OCCT gp_Pnt / gp_Dir -> [x, y, z]."""
    for getter in ("X", "x"):
        if hasattr(v, getter):
            a = getattr(v, getter)
            if callable(a):          # gp_Pnt.X() is a method
                return [float(v.X()), float(v.Y()), float(v.Z())]
            return [float(v.X), float(v.Y), float(v.Z)]
    return [float(v[0]), float(v[1]), float(v[2])]


def _sub(a, b): return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
def _add(a, b): return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
def _scale(a, k): return [a[0] * k, a[1] * k, a[2] * k]
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _norm(a): return math.sqrt(_dot(a, a))


def _r(x, n=3):
    """Round for display, and turn -0.0 into 0.0 (a readout showing '-0.00 mm'
    reads as a bug)."""
    v = round(float(x), n)
    return 0.0 if v == 0 else v


def _r3(v, n=3):
    return [_r(c, n) for c in v]


def _fmt(x, unit=MM):
    return f"{float(x):.2f} {unit}"


# ---------------------------------------------------------------------------
# resolving a selection to real geometry

def _body_part(doc, body_id):
    """The Part a selection refers to, mirroring provenance.attribute_face:
    an explicit body wins, otherwise the design's result solid."""
    part = doc._parts.get(body_id) if body_id else None
    if part is not None:
        return body_id, part
    part = doc.result()
    rf = doc._result_feature()
    return (rf.id if rf else None), part


def resolve(doc, sel: dict):
    """One viewport selection -> (shape, body_id).

    Face and edge ids are the tagged mesh's indices, so faces come from
    provenance.picked_faces (the SAME part.faces() order _tagged_mesh used, and
    already cached per rebuild) and edges from part.edges().
    """
    if not isinstance(sel, dict):
        raise ValueError("a selection must be an object")
    kind = str(sel.get("kind") or "face").lower()
    body, part = _body_part(doc, sel.get("body"))
    if part is None:
        raise ValueError("nothing is built — rebuild the design first")
    if sel.get("id") is None:
        raise ValueError("that selection carries no id")
    idx = int(sel["id"])

    if kind == "face":
        faces = provenance.picked_faces(doc, body, part)
        if not 0 <= idx < len(faces):
            raise ValueError(
                f"face {idx} is not on this body any more — click it again")
        return faces[idx], body
    if kind == "edge":
        edges = part.edges()
        if not 0 <= idx < len(edges):
            raise ValueError(
                f"edge {idx} is not on this body any more — click it again")
        return edges[idx], body
    raise ValueError(f"cannot measure a {kind!r}")


def _geom(shape) -> str:
    try:
        return str(shape.geom_type).replace("GeomType.", "")
    except Exception:
        return "UNKNOWN"


def _circle(shape):
    """(centre, radius, axis|None) for anything round, else None.

    arc_center / axis_of_rotation ONLY — see the module docstring for why
    center() is wrong here."""
    g = _geom(shape)
    if g == "CIRCLE":
        try:
            return _xyz(shape.arc_center), float(shape.radius), None
        except Exception:
            return None
    if g == "CYLINDER":
        try:
            ax = shape.axis_of_rotation
            return _xyz(ax.position), float(shape.radius), _xyz(ax.direction)
        except Exception:
            return None
    return None


def _plane(shape):
    """(centre, unit normal) for a planar FACE, else None."""
    try:
        if shape.__class__.__name__ != "Face":
            return None
        c = shape.center()
        n = shape.normal_at(c)
        n = _xyz(n)
        ln = _norm(n)
        if ln < 1e-9:
            return None
        # planar is geometric, not by surface type: a taper/loft wall can be
        # dead flat yet typed BSPLINE (same rule _tagged_mesh uses)
        if _geom(shape) != "PLANE":
            import sketch as sketchlib
            if sketchlib.face_plane(shape) is None:
                return None
        return _xyz(c), _scale(n, 1.0 / ln)
    except Exception:
        return None


def _min_distance(a, b):
    """True minimum distance plus the two witness points, via OCCT."""
    try:
        d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
        if not d.IsDone() or d.NbSolution() < 1:
            return None
        return (float(d.Value()),
                _xyz(d.PointOnShape1(1)), _xyz(d.PointOnShape2(1)))
    except Exception:              # OCP errors are Exception, not RuntimeError
        return None


def _closest_on_axis(pos, direction, target):
    """The point on the line (pos, direction) nearest `target`.

    For a cylindrical face the axis POSITION is arbitrary along the axis, so
    comparing two raw axis positions would fold in a meaningless slide. Taking
    the nearest point to the other feature's centre gives the perpendicular
    distance between parallel holes, which is what hole spacing means."""
    d = _norm(direction)
    if d < 1e-9:
        return pos
    u = _scale(direction, 1.0 / d)
    return _add(pos, _scale(u, _dot(_sub(target, pos), u)))


# ---------------------------------------------------------------------------
# single-selection measurements

def _measure_one(shape) -> dict:
    circ = _circle(shape)
    if circ:
        centre, radius, axis = circ
        dia = radius * 2
        rows = [["radius", _fmt(radius)], ["centre", ", ".join(
            f"{c:.2f}" for c in _r3(centre, 2))]]
        if axis:
            rows.append(["axis", ", ".join(f"{c:.3f}" for c in _r3(axis, 3))])
        return {"kind": "diameter", "value": _r(dia), "unit": MM,
                "label": f"⌀{dia:.2f} {MM}", "rows": rows,
                "centre": _r3(centre)}

    if shape.__class__.__name__ == "Edge":
        length = float(shape.length)
        rows = [["type", _geom(shape)]]
        try:
            p0, p1 = _xyz(shape @ 0), _xyz(shape @ 1)
            rows.append(["from", ", ".join(f"{c:.2f}" for c in _r3(p0, 2))])
            rows.append(["to", ", ".join(f"{c:.2f}" for c in _r3(p1, 2))])
            return {"kind": "length", "value": _r(length), "unit": MM,
                    "label": _fmt(length), "rows": rows,
                    "from": _r3(p0), "to": _r3(p1)}
        except Exception:
            pass
        return {"kind": "length", "value": _r(length), "unit": MM,
                "label": _fmt(length), "rows": rows}

    # a planar (or any) face on its own: area + how big it is
    rows = [["type", _geom(shape)]]
    try:
        rows.append(["area", f"{shape.area:.2f} mm²"])
    except Exception:
        pass
    pl = _plane(shape)
    try:
        bb = shape.bounding_box()
        size = _xyz(bb.size)
        # the two in-plane extents are what "how big is this face" means; the
        # third is ~0 for a planar face and noise is not worth showing
        dims = sorted((_r(size[0], 2), _r(size[1], 2), _r(size[2], 2)),
                      reverse=True)
        rows.append(["extents", f"{dims[0]:.2f} × {dims[1]:.2f} {MM}"])
    except Exception:
        pass
    if pl:
        c, n = pl
        rows.append(["centre", ", ".join(f"{v:.2f}" for v in _r3(c, 2))])
        rows.append(["normal", ", ".join(f"{v:.3f}" for v in _r3(n, 3))])
    try:
        area = float(shape.area)
    except Exception:
        area = 0.0
    return {"kind": "area", "value": _r(area, 2), "unit": "mm²",
            "label": f"{area:.2f} mm²", "rows": rows}


# ---------------------------------------------------------------------------
# two-selection measurements

def _measure_two(a, b) -> dict:
    ca, cb = _circle(a), _circle(b)
    pa, pb = _plane(a), _plane(b)
    md = _min_distance(a, b)

    # -- two round things: centre-to-centre, the machinist's hole spacing ----
    if ca and cb:
        (centre_a, ra, axis_a), (centre_b, rb, axis_b) = ca, cb
        # cylinders: pin each arbitrary axis position to the comparable point
        if axis_a:
            centre_a = _closest_on_axis(centre_a, axis_a, centre_b)
        if axis_b:
            centre_b = _closest_on_axis(centre_b, axis_b, centre_a)
        delta = _sub(centre_b, centre_a)
        dist = _norm(delta)
        rows = [["Δx", _fmt(delta[0])], ["Δy", _fmt(delta[1])],
                ["Δz", _fmt(delta[2])],
                ["⌀ A", _fmt(ra * 2)], ["⌀ B", _fmt(rb * 2)]]
        if md:
            rows.append(["clearance", _fmt(md[0])])
        return {"kind": "centres", "value": _r(dist), "unit": MM,
                "label": f"{dist:.2f} {MM} centre-to-centre", "rows": rows,
                "from": _r3(centre_a), "to": _r3(centre_b)}

    # -- two planar faces ---------------------------------------------------
    if pa and pb:
        (centre_a, na), (centre_b, nb) = pa, pb
        cos = _dot(na, nb)
        if abs(abs(cos) - 1.0) <= PARALLEL_TOL:          # parallel
            delta = _sub(centre_b, centre_a)
            along = _dot(na, delta)
            dist = abs(along)
            if cos < 0:
                # OPPOSED outward normals. Pointing away from each other means
                # solid between them (a wall/floor THICKNESS); pointing at each
                # other means empty space (a GAP). Probed, see the docstring.
                solid_between = along < 0
                kind = "thickness" if solid_between else "gap"
                rows = [["between",
                         "material" if solid_between else "open space"]]
                label = (f"{dist:.2f} {MM} "
                         + ("thick" if solid_between else "apart"))
            else:
                # CO-DIRECTIONAL normals: both faces look the same way, so one
                # is a step above the other (a pocket floor under its rim is
                # the common case, where this distance is the pocket DEPTH).
                # Neither "thick" nor "apart" is true here — claiming material
                # between two up-facing faces would be a confident lie.
                kind = "step"
                rows = [["faces", "both point the same way — a step"]]
                label = f"{dist:.2f} {MM} step"
            if md and abs(md[0] - dist) > 1e-6:
                # faces that do not overlap in plan: the nearest points are at
                # the rims, so the plane separation and the true gap differ and
                # showing only one of them would be a half-truth
                rows.append(["closest points", _fmt(md[0])])
            rows.append(["normal", ", ".join(f"{v:.3f}" for v in _r3(na, 3))])
            # Anchor the drawn line on the SMALLER face's centre, projected on
            # to the other plane. A pocket floor measured against the whole top
            # face is the common case, and anchoring on the big face put the
            # line out at the plate's centroid — metres of daylight from the
            # pocket the user actually clicked (seen in UI verification).
            try:
                small_is_b = float(b.area) < float(a.area)
            except Exception:
                small_is_b = False
            if small_is_b:
                frm = centre_b
                to = _add(centre_b, _scale(nb, _dot(nb, _sub(centre_a, centre_b))))
            else:
                frm = centre_a
                to = _add(centre_a, _scale(na, along))
            return {"kind": kind, "value": _r(dist), "unit": MM,
                    "label": label, "rows": rows,
                    "from": _r3(frm), "to": _r3(to)}
        # not parallel: the angle is the headline, distance the footnote
        ang = math.degrees(math.acos(max(-1.0, min(1.0, abs(cos)))))
        rows = []
        if md:
            rows.append(["closest points", _fmt(md[0])])
        rows.append(["dihedral", f"{180 - ang:.2f}°"])
        out = {"kind": "angle", "value": _r(ang, 2), "unit": "°",
               "label": f"{ang:.2f}°", "rows": rows}
        if md:
            out["from"], out["to"] = _r3(md[1]), _r3(md[2])
        return out

    # -- anything else: honest minimum distance -----------------------------
    if md:
        dist, p1, p2 = md
        rows = [["from", ", ".join(f"{c:.2f}" for c in _r3(p1, 2))],
                ["to", ", ".join(f"{c:.2f}" for c in _r3(p2, 2))]]
        if dist <= TOUCH_TOL:
            rows.insert(0, ["note", "these touch"])
        return {"kind": "distance", "value": _r(dist), "unit": MM,
                "label": _fmt(dist), "rows": rows,
                "from": _r3(p1), "to": _r3(p2)}
    raise ValueError("could not measure between those two selections")


# ---------------------------------------------------------------------------
# P1 — which PARAM drives the number we just measured?
#
# A measured value falls into one of two kinds, and conflating them is the
# whole risk of this feature (see MEASURE-PLAN.md):
#
#   DRIVEN   the number IS one param in the tree (a hole's diameter is the `r`
#            of a circle entity). Editing it is exact and reversible.
#   DERIVED  the number is a CONSEQUENCE of two independent literals (a pillar-
#            to-wall gap). There is no single param to write, so P1 offers no
#            edit box at all rather than guessing which side should move.
#
# No driver => read-only. A missing edit box is a small disappointment; an edit
# box that silently moves the wrong wall is the failure this project exists to
# prevent.

# how close an entity must be, in its own sketch plane, to claim a picked face
MATCH_TOL = 1e-3


def _plane_cache(doc) -> dict:
    """One sketch-plane cache per Document, alive across clicks.

    Freshness is per ENTRY: each remembers the base Part it was derived from
    and the params that shaped it, and is rebuilt when either changes — which
    is exactly what a rebuild does (_mark_stale clears _parts, rebuild puts NEW
    Part objects in). Same design as provenance._cache, for the same reason:
    without it, resolving a driver cost 660 ms per click at 24 sketches
    (measured), because every sketch_on_face re-resolved its named face over
    the whole base solid."""
    cache = getattr(doc, "_measure_planes", None)
    if cache is None:
        cache = {}
        try:
            doc._measure_planes = cache
        except Exception:
            return {}                  # uncacheable doc: correct, just slower
    return cache


def _plane_sig(feat) -> tuple:
    """Everything about a sketch feature that changes where its plane sits."""
    p = feat.params or {}
    return (feat.op, p.get("plane"), p.get("offset"), p.get("face"),
            tuple(p.get("face_center") or ()), tuple(p.get("face_normal") or ()))


def _sketch_plane(doc, feat):
    """The Plane a sketch feature's entity coordinates live in — the same plane
    sketch.make_sketch / sketch_on_face place them on.

    Derived from the CURRENT geometry, never stored on the feature: under the
    offset method a sketch plane is stated as a depth from a face, so it moves
    when the base changes. The cache above keys on that base, so it follows."""
    base = doc._parts.get(feat.inputs[0]) if feat.inputs else None
    sig = _plane_sig(feat)
    cache = _plane_cache(doc)
    hit = cache.get(feat.id)
    if hit is not None and hit[0] is base and hit[1] == sig:
        return hit[2]
    plane = _build_plane(doc, feat, base)
    cache[feat.id] = (base, sig, plane)
    return plane


def _build_plane(doc, feat, base):
    import sketch as sk
    p = feat.params or {}
    try:
        if feat.op == "sketch":
            pl = sk._PLANES.get(p.get("plane", "XY"))
        elif feat.op == "sketch_on_face":
            if base is None:
                return None
            if p.get("face"):
                picked = sk.named_face(base, p["face"])
            elif p.get("face_center") is not None:
                picked = sk.resolve_face(base, p["face_center"],
                                         p.get("face_normal"))
            else:
                return None
            pl = sk.face_sketch_plane(picked)
        else:
            return None
        if pl is None:
            return None
        off = float(p.get("offset") or 0.0)
        return pl.offset(off) if off else pl
    except Exception:          # a sketch whose base failed to build
        return None


def _round_entities(feat):
    """(index, entity, radius-key) for each entity dimensioned by a radius."""
    import sketch as sk
    for i, e in enumerate((feat.params or {}).get("entities") or []):
        if not isinstance(e, dict):
            continue
        key = sk.ENTITY_DIAMETER.get(e.get("kind"))
        if key is not None and isinstance(e.get(key), (int, float)):
            yield i, e, key


def _axis_offset(p, pos, direction) -> float:
    """Perpendicular distance from point `p` to the line (pos, direction)."""
    d = _sub(p, pos)
    n = _norm(direction)
    if n < 1e-9:
        return _norm(d)
    u = _scale(direction, 1.0 / n)
    return _norm(_sub(d, _scale(u, _dot(d, u))))


def _face_index_for(doc, shape, sel, body):
    """Which tagged-mesh face index this pick should be attributed through.

    A face pick is its own index. A circular EDGE borrows the bore wall it
    bounds, so clicking the rim of a hole resolves the same driver as clicking
    its wall — the user should not have to know which of the two the tool
    prefers."""
    if str(sel.get("kind")) == "face" and sel.get("id") is not None:
        return int(sel["id"])
    circ = _circle(shape)
    if not circ:
        return None
    centre, radius, _ = circ
    part = doc._parts.get(body) if body else None
    if part is None:
        part = doc.result()
    if part is None:
        return None
    for i, f in enumerate(provenance.picked_faces(doc, body, part)):
        fc = _circle(f)
        if not fc:
            continue
        c2, r2, ax = fc
        if abs(r2 - radius) > MATCH_TOL or not ax:
            continue
        if _axis_offset(centre, c2, ax) <= MATCH_TOL:
            return i
    return None


def _diameter_driver(doc, shape, sel, body):
    """The sketch entity whose radius drives this round face/edge, or None.

    Which sketch to look in comes from provenance.attribute_face — the same
    "which feature made this face" walk the pick panel already runs. That
    matters for speed as much as for correctness: scanning every sketch instead
    cost 660 ms per click at 24 sketches, because each sketch_on_face had to
    re-resolve its named face over the whole base solid. Asking provenance
    resolves exactly ONE plane.

    Within that sketch the entity is matched in the sketch's OWN plane: its
    (x, y) must coincide with the pick's centre projected into that plane, and
    the radii must agree. Local Z is deliberately ignored, so a pocket's mouth
    rim, its bottom rim and its bore wall all resolve to the same entity
    (probed 2026-08-27).

    Returns None unless the match is UNIQUE. Six identical holes at six
    different positions still resolve, because position tells them apart; two
    genuinely coincident entities do not, and read-only is then the honest
    answer."""
    from build123d import Vector
    circ = _circle(shape)
    if not circ:
        return None
    centre, radius, _axis = circ
    fi = _face_index_for(doc, shape, sel, body)
    if fi is None:
        return None
    att = provenance.attribute_face(doc, body_id=body, face_index=fi)
    sid = att.get("sketch")
    if not sid:
        return None                    # e.g. a hole from a block op, not a sketch
    try:
        feat = doc.get(sid)
    except KeyError:
        return None
    plane = _sketch_plane(doc, feat)
    if plane is None:
        return None
    try:
        loc = plane.to_local_coords(Vector(*centre))
    except Exception:
        return None
    def hit(i, e, key):
        return {
            "feature": feat.id,
            "path": ["entities", i, key],
            "current": float(e[key]),
            "transform": "half",       # a diameter is twice the stored radius
            "label": f"{feat.id} · {e.get('kind')} #{i} {key}",
            "drives": "diameter",
        }

    by_radius, by_position = [], []
    for i, e, key in _round_entities(feat):
        if abs(float(e[key]) - radius) > MATCH_TOL:
            continue
        by_radius.append(hit(i, e, key))
        if (abs(float(e.get("x", 0) or 0) - loc.X) <= MATCH_TOL
                and abs(float(e.get("y", 0) or 0) - loc.Y) <= MATCH_TOL):
            by_position.append(hit(i, e, key))
    if len(by_position) == 1:
        return by_position[0]
    # PATTERNED COPIES land nowhere near their seed entity, so position finds
    # nothing — 5 of the 6 bores in a polar pattern were read-only while the
    # seed alone was editable (probed 2026-08-27). But provenance has already
    # proved this face came from THIS sketch, so if the sketch holds exactly one
    # circle of this radius it is unambiguously the driver, wherever the copy
    # sits. Editing it moves the whole pattern, which is what the seed means.
    if len(by_radius) == 1:
        return by_radius[0]
    return None


def resolve_driver(doc, shape_a, result: dict, sel_a: dict | None = None,
                   body: str | None = None):
    """The param behind a measurement, or None when it is derived/unmatched."""
    try:
        if result.get("kind") == "diameter":
            return _diameter_driver(doc, shape_a, sel_a or {}, body)
    except Exception:      # attribution/geometry trouble must not break a read
        return None
    return None


def _to_param(transform: str, value: float, current: float) -> float:
    """The stored param that produces `value` on screen."""
    if transform == "half":
        return value / 2.0
    if transform == "signed":       # magnitude shown, sign preserved
        return -abs(value) if current < 0 else abs(value)
    return value


def plan_set(doc, a: dict, b: dict | None, value: float) -> dict:
    """Work out WHICH param to write and to what — without writing anything.

    Split from the write so the caller can snapshot for undo first, and so a
    request that cannot be honoured changes nothing at all."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return {"error": f"{value!r} is not a number"}
    base = measure(doc, a, b)
    if "error" in base:
        return base
    try:
        shape_a, body_a = resolve(doc, a)
    except ValueError as e:
        return {"error": str(e)}
    driver = resolve_driver(doc, shape_a, base, a, body_a)
    if not driver:
        return {"error": "this measurement is not driven by a single "
                         "parameter, so it cannot be typed into — see the "
                         "feature tree, or ask the AI designer to move it"}
    new_param = _to_param(driver["transform"], value, driver["current"])
    if new_param <= 0:
        # sketch._validate_dims would reject it at rebuild anyway; refusing
        # here means the document is never even touched
        return {"error": f"a {driver['drives']} of {value:g} mm would need "
                         f"{new_param:g} mm — dimensions must be positive"}
    return {"driver": driver, "requested": _r(value),
            "param": _r(new_param, 6), "was": _r(driver["current"], 6)}


def write(doc, plan: dict) -> None:
    """Apply a plan_set() result to the document. Caller rebuilds."""
    feat = doc.get(plan["driver"]["feature"])
    target = feat.params
    path = plan["driver"]["path"]
    for k in path[:-1]:
        target = target[k]
    target[path[-1]] = plan["param"]


# ---------------------------------------------------------------------------
# the entry point

def measure(doc, a: dict, b: dict | None = None) -> dict:
    """Measure one selection, or between two.

    Returns {kind, value, unit, label, rows, from?, to?} — `from`/`to` are the
    witness points so the viewport can draw the line it actually measured —
    or {"error": reason}. Never raises."""
    try:
        if not doc.features:
            return {"error": "the design is empty"}
        shape_a, body_a = resolve(doc, a)
        if b is None:
            out = _measure_one(shape_a)
            out["a"] = {"body": body_a, "kind": a.get("kind"), "id": a.get("id")}
            # is this number editable? (None => the readout stays read-only)
            out["driver"] = resolve_driver(doc, shape_a, out, a, body_a)
            return out
        shape_b, body_b = resolve(doc, b)
        if (body_a == body_b and str(a.get("kind")) == str(b.get("kind"))
                and a.get("id") == b.get("id")):
            return {"error": "those are the same thing — pick two"}
        out = _measure_two(shape_a, shape_b)
        out["a"] = {"body": body_a, "kind": a.get("kind"), "id": a.get("id")}
        out["b"] = {"body": body_b, "kind": b.get("kind"), "id": b.get("id")}
        return out
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:          # OCP errors are Exception, not RuntimeError
        return {"error": f"measurement failed: {e!r}"}
