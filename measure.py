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
