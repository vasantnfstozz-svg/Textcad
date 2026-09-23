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
        if idx < 0:
            # An imported STL is tagged with ONE mesh pseudo-face (id -1),
            # because 21552 triangles are not 21552 pickable faces. Every
            # click on such a body used to answer "face -1 is not on this body
            # any more — click it again", which is untrue and is a loop with
            # no way out: clicking again gives -1 again (section 6 review,
            # 2026-09-10, measured on imports/liquid-piston-2-v1.stl).
            raise ValueError(
                "this is an imported mesh body — its surface is one triangle "
                "mesh rather than separate faces, so there is nothing here to "
                "measure")
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


def _full_circles(shape) -> list[float]:
    """The radii of this face's FULL circular boundary edges, largest first.

    Full circles only: an annular face's rims, a hole's mouth on a floor.
    Corner-fillet arcs are partial circles and excluded — someone asking
    "what is this bore" does not mean the corner radius. Never raises."""
    radii: list[float] = []
    try:
        for ed in shape.edges():
            if _geom(ed) != "CIRCLE":
                continue
            r = float(ed.radius)
            if abs(float(ed.length) - 2 * math.pi * r) > max(1e-6, 1e-4 * r):
                continue                       # an arc, not a full circle
            if not any(abs(r - q) < 1e-6 for q in radii):
                radii.append(r)
    except Exception:
        return []
    return sorted(radii, reverse=True)


# ---------------------------------------------------------------------------
# single-selection measurements

def _measure_one(shape) -> dict:
    circ = _circle(shape)
    if circ:
        centre, radius, axis = circ
        dia = radius * 2
        shown = centre
        if axis:
            # axis_of_rotation.position is an ARBITRARY point along the axis:
            # for a 5 mm pocket in a 12 mm plate it came back at the mouth
            # (z=6) while the bore's middle is z=3.5, so x and y were right
            # and z was a guess presented as a fact (section 6 review,
            # 2026-09-10 — the pick panel calls the same number "axis_at").
            # Pin it to the face's own middle; the module docstring makes
            # exactly this point about center().
            try:
                bb = shape.bounding_box()
                mid = _scale(_add(_xyz(bb.min), _xyz(bb.max)), 0.5)
                shown = _closest_on_axis(centre, axis, mid)
            except Exception:
                shown = centre
        rows = [["radius", _fmt(radius)], ["centre", ", ".join(
            f"{c:.2f}" for c in _r3(shown, 2))]]
        if axis:
            rows.append(["axis", ", ".join(f"{c:.3f}" for c in _r3(axis, 3))])
        return {"kind": "diameter", "value": _r(dia), "unit": MM,
                "label": f"⌀{dia:.2f} {MM}", "rows": rows,
                "centre": _r3(shown)}

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

    # a planar (or any) face on its own: its ⌀s first, then area + extents.
    # A washer-like face IS its outer and inner diameters to the person
    # clicking it (user request 2026-08-31) — the area is the footnote.
    rows = []
    holes = _full_circles(shape)
    if len(holes) == 1:
        rows.append(["⌀", _fmt(holes[0] * 2)])
    elif len(holes) >= 2:
        rows.append(["outer ⌀", _fmt(holes[0] * 2)])
        rows.append(["inner ⌀", _fmt(holes[-1] * 2)])
        for r_mid in holes[1:-1]:            # a floor with several bores
            rows.append(["also ⌀", _fmt(r_mid * 2)])
    rows.append(["type", _geom(shape)])
    try:
        rows.append(["area", f"{shape.area:.2f} mm²"])
    except Exception:
        pass
    pl = _plane(shape)
    # IN THE FACE'S OWN FRAME. The world bounding box of a TILTED face lies
    # — the third extent is only ~0 when the face is axis aligned, and
    # dropping it then throws away real width. Measured (section 6 review,
    # 2026-09-10): a 6 mm 45° chamfer read "60.00 × 6.00" where its true
    # width is 6√2 = 8.49, which is what the PICK panel shows for the same
    # face. _tagged_mesh already projected into the plane frame; this did not.
    dims = None
    if pl is not None:
        try:
            import sketch as sketchlib
            frame = sketchlib.face_plane(shape)
            if frame is not None:
                s = frame.to_local_coords(shape).bounding_box().size
                dims = sorted((_r(s.X, 2), _r(s.Y, 2)), reverse=True)
        except Exception:
            dims = None
    if dims is None:
        # its OWN try: sharing one with the projection above made this
        # unreachable on the single path that needs it, so a face whose frame
        # projection threw lost its extents row altogether (round two of the
        # section 6 review, 2026-09-10)
        try:
            size = _xyz(shape.bounding_box().size)
            dims = sorted((_r(size[0], 2), _r(size[1], 2), _r(size[2], 2)),
                          reverse=True)
        except Exception:
            dims = None
    if dims is not None:
        rows.append(["extents", f"{dims[0]:.2f} × {dims[1]:.2f} {MM}"])
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

    # -- two round things: SURFACE to surface, centres as the footnote -------
    # (user report 2026-08-31: "its measuring from center to center, i do not
    # want like this, it should measure from the surface to surface"). The
    # drawn line runs between the actual walls; the machinist's hole-spacing
    # number stays one row below.
    if ca and cb:
        (centre_a, ra, axis_a), (centre_b, rb, axis_b) = ca, cb
        # cylinders: pin each arbitrary axis position to the comparable point
        if axis_a:
            centre_a = _closest_on_axis(centre_a, axis_a, centre_b)
        if axis_b:
            centre_b = _closest_on_axis(centre_b, axis_b, centre_a)
        delta = _sub(centre_b, centre_a)
        dist = _norm(delta)
        rows = [["centre-to-centre", _fmt(dist)],
                ["Δx", _fmt(delta[0])], ["Δy", _fmt(delta[1])],
                ["Δz", _fmt(delta[2])],
                ["⌀ A", _fmt(ra * 2)], ["⌀ B", _fmt(rb * 2)]]
        if md and md[0] > TOUCH_TOL:
            return {"kind": "clearance", "value": _r(md[0]), "unit": MM,
                    "label": f"{md[0]:.2f} {MM} surface-to-surface",
                    "rows": rows, "from": _r3(md[1]), "to": _r3(md[2])}
        # touching or overlapping: there is no surface gap to report, so the
        # centre distance is the honest headline again
        rows = rows[1:]
        if md:
            rows.insert(0, ["surfaces", "touching / overlapping"])
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
                # Say what this is NOT, because it is the pair a user picks by
                # accident: from any one view the two faces that FACE each
                # other are never both visible, so the natural two clicks land
                # on two faces pointing the same way — giving the far side of
                # the feature instead of the clearance in front of it. (User
                # report 2026-08-27: "i tried to move the box … still it was
                # not moving" — they had measured, and moved, the far wall.)
                kind = "step"
                rows = [["faces", "both point the same way"],
                        ["note", "a step, not a clearance — orbit and pick "
                                 "the facing wall for the gap"]]
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
            tuple(p.get("face_center") or ()), tuple(p.get("face_normal") or ()),
            p.get("face_area"))


def _plane_base(doc, feat):
    """The built part a sketch's plane is derived FROM — the body under a face
    sketch, or the CONSTRUCTION PLANE it names in `plane`.

    `_plane_sig` reads the sketch's own params, and those do not change when
    the plane row under it moves ("p1" stays "p1"), so without this the cached
    entry answered the plane's OLD position after an edit. A rebuild puts a new
    Part object in `_parts` for anything whose signature moved, so identity is
    the freshness test — the same one a face sketch's body already uses."""
    import sketch as sk
    if feat.inputs:
        return doc._parts.get(feat.inputs[0])
    name = str((feat.params or {}).get("plane") or "XY")
    return None if name in sk.PRINCIPAL_PLANES else doc._parts.get(name)


def _sketch_plane(doc, feat):
    """The Plane a sketch feature's entity coordinates live in — the same plane
    sketch.make_sketch / sketch_on_face place them on.

    Derived from the CURRENT geometry, never stored on the feature: under the
    offset method a sketch plane is stated as a depth from a face, so it moves
    when the base changes. The cache above keys on that base, so it follows."""
    base = _plane_base(doc, feat)
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
            # Document.plane_of, not sk._PLANES: the name is a principal plane
            # OR an `offset_plane` feature's id, and only the document knows the
            # second. Reading the dict alone answered None for every sketch on a
            # construction plane, so Measure silently had no dimension to drive
            # (user report 2026-09-23). A name it cannot place raises, and the
            # except below turns that into the same None as before.
            pl = doc.plane_of(p.get("plane") or "XY")
        elif feat.op == "sketch_on_face":
            if base is None:
                return None
            if p.get("face"):
                picked = sk.named_face(base, p["face"])
            elif p.get("face_center") is not None:
                picked = sk.resolve_face(base, p["face_center"],
                                         p.get("face_normal"),
                                         p.get("face_area"))
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


# a `hole` feature's own params, by what each one makes round (specs/hole.md)
_HOLE_BORES = (("diameter", "⌀"), ("cbore_diameter", "counterbore ⌀"),
               ("csink_diameter", "countersink ⌀"))


def _hole_driver(doc, att: dict, radius: float):
    """A bore drilled by the `hole` op is driven by that feature's own
    `diameter` — no sketch circle exists to find (the op eats its body), and
    without this every hole made with the Hole tool answered "read-only … no
    sketch circle drives this bore (a primitive, or an imported body)", which
    is untrue and loses measure-and-drive on every hole in a design.

    provenance names the feature that CREATED the face (probed 2026-09-06,
    probes/hole_review_probe.py §3: both the ⌀6 bore and its ⌀12 counterbore
    seat came back origin='h', origin_op='hole'), and the radius says which of
    the three round params it is."""
    origin = att.get("origin")
    if not origin or att.get("origin_op") != "hole":
        return None
    try:
        feat = doc.get(origin)
    except KeyError:
        return None
    for key, what in _HOLE_BORES:
        cur = float(feat.params.get(key) or 0.0)
        if cur > 0 and abs(cur / 2.0 - radius) <= MATCH_TOL:
            return {"feature": feat.id, "path": [key], "current": cur,
                    "transform": "value",      # a hole stores the DIAMETER itself
                    "label": f"{feat.id} · {what}", "drives": "diameter"}
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
    hit = _hole_driver(doc, att, radius)
    if hit:
        return hit
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


# ---------------------------------------------------------------------------
# P2 — DERIVED distances: moving one side instead of writing one param
#
# The user's own example: "distanse bewteen a pillar to wall is 10, and i am
# changine the it 8, the pillar should move to wall". That 10 is stored nowhere
# — it is the subtraction of two independent sketches' literals — so there is no
# param to overwrite. What CAN be done is move one side, and the only honest way
# is to be explicit about which one.

# how close a wall's centre must lie to an entity's 2D boundary to belong to it
BOUNDARY_TOL = 1e-3


def _face_role(doc, shape, sel: dict, body):
    """What this flat face IS, relative to the sketch that made it.

      {"kind": "wall", feature, entity, plane}  — a side of an entity's
          profile. Its position across the plane is the entity's x/y, so it
          CAN be moved by editing those.
      {"kind": "cap", feature, plane}           — the top or bottom face of an
          extruded profile. Its position is the extrude depth / plane offset,
          NOT the entity's x/y, so sliding the profile sideways would not move
          it at all. Distinguishing this is what lets the tool say "change the
          depth" instead of the misleading "nothing here can move".
      None                                       — no sketch behind it (a
          primitive, an imported body).

    Wall vs cap is decided by the face normal against the sketch plane normal:
    a cap looks along it, a wall lies in it.

    A rectangle entity makes four walls, so "which entity" is not answerable
    from the face alone. It IS answerable in the sketch's own plane: rebuild
    each entity's 2D face with sketch._entity (which applies its rotation and
    position) and the wall belongs to the entity whose boundary passes through
    the wall's projected centre. Probed 2026-08-27 — the four walls of a 20x20
    boss and a round boss's wall each resolved to their own entity at distance
    0.0, while the host plate's own walls sat 20-40 mm from every entity and
    correctly resolved to none."""
    from build123d import Vector, Vertex
    import sketch as sk
    pl = _plane(shape)
    if not pl or str(sel.get("kind")) != "face" or sel.get("id") is None:
        return None
    centre, normal = pl
    att = provenance.attribute_face(doc, body_id=body,
                                    face_index=int(sel["id"]))
    sid = att.get("sketch")
    if not sid:
        return None
    try:
        feat = doc.get(sid)
    except KeyError:
        return None
    plane = _sketch_plane(doc, feat)
    if plane is None:
        return None
    pn = _xyz(plane.z_dir)
    if abs(abs(_dot(normal, pn)) - 1.0) <= 1e-6:
        return {"kind": "cap", "feature": feat, "plane": plane}
    try:
        loc = plane.to_local_coords(Vector(*centre))
    except Exception:
        return None
    probe = Vertex(loc.X, loc.Y, 0)
    best, best_d = None, None
    for i, e in enumerate((feat.params or {}).get("entities") or []):
        if not isinstance(e, dict):
            continue
        try:
            face2d = sk._entity(e)
        except Exception:
            continue                      # an entity that will not build alone
        d = None
        for ed in face2d.edges():
            got = _min_distance(probe, ed)
            if got and (d is None or got[0] < d):
                d = got[0]
        if d is not None and (best_d is None or d < best_d):
            best, best_d = i, d
    if best is None or best_d > BOUNDARY_TOL:
        return None
    return {"kind": "wall", "feature": feat, "entity": best, "plane": plane}


DEPTH_ADVICE = ("this distance runs along the sketch's depth, not across its "
                "plane — change the extrude distance or the sketch offset "
                "instead of moving the profile")


# ---------------------------------------------------------------------------
# two faces of ONE entity: the distance IS one of its dimensions
#
# User report (2026-08-27, round 2): "i can measure the distance between two
# seleted face, but the moving option is not working". They had picked the two
# OPPOSITE WALLS of one box. Both walls belong to the same rectangle entity, so
# the move path translated the whole box sideways — the box stayed 10 wide, the
# verification failed, the edit reverted, and the tool read as broken. Moving
# can never change a distance both of whose ends ride the same entity.
#
# But that distance IS a driven dimension: opposite walls of a rectangle are
# exactly its `w` (or `h`). So this pair gets an exact edit box, like a
# diameter, not a move.

# which dimension key spans a given LOCAL direction, per entity kind. Only
# kinds whose opposed flat walls correspond to one stored dimension belong
# here — a polygon/path wall has no such single number.
_DIM_BY_AXIS = {
    "rectangle": {"x": ("w", "width"), "y": ("h", "height")},
    # a slot's flat sides span its height; its ends are arcs, never planar
    "slot": {"y": ("height", "height")},
}


def _entity_dim_for_direction(feat, ent_idx, plane, normal):
    """(param key, display name) of the entity dimension spanning `normal`
    (a world unit vector), or None.

    The normal is mapped into the sketch plane and then UN-ROTATED by the
    entity's own rotation, because sketch._entity rotates the shape about its
    centre before placing it — a 90-degree rectangle's `w` runs along local Y.
    Probed 2026-08-27: all eight walls of a straight and a rotated rectangle
    map to the correct dimension."""
    from build123d import Vector
    try:
        e = (feat.params or {})["entities"][ent_idx]
    except (KeyError, IndexError, TypeError):
        return None
    table = _DIM_BY_AXIS.get(e.get("kind"))
    if not table:
        return None
    try:
        o = plane.to_local_coords(Vector(0, 0, 0))
        v = plane.to_local_coords(Vector(*normal))
    except Exception:
        return None
    lx, ly = v.X - o.X, v.Y - o.Y
    r = math.radians(float(e.get("rotation", 0) or 0))
    ux = lx * math.cos(r) + ly * math.sin(r)
    uy = -lx * math.sin(r) + ly * math.cos(r)
    axis = "x" if abs(abs(ux) - 1) < 1e-3 else \
           "y" if abs(abs(uy) - 1) < 1e-3 else None
    got = table.get(axis) if axis else None
    if not got:
        return None
    key, name = got
    if not isinstance(e.get(key), (int, float)):
        return None
    return key, name


def resolve_pair_driver(doc, a_shape, b_shape, a_sel, b_sel, body_a, body_b,
                        measured):
    """When two parallel faces are opposite walls of ONE entity, the distance
    between them is that entity's dimension — return it as a driver.

    Returns {"driver": {...}} when the pair maps to a dimension,
    {"blocked": reason} when the pair is same-entity but has no such dimension
    (moving it would be a no-op, so the move path must not be offered either),
    or None when the faces belong to different things (the move path applies).
    """
    pa, pb = _plane(a_shape), _plane(b_shape)
    if not pa or not pb:
        return None
    (_ca, na), (_cb, nb) = pa, pb
    if _dot(na, nb) > -1.0 + PARALLEL_TOL:
        return None            # not opposed: not a width-like pair
    ra = _face_role(doc, a_shape, a_sel, body_a)
    rb = _face_role(doc, b_shape, b_sel, body_b)
    if (not ra or not rb or ra["kind"] != "wall" or rb["kind"] != "wall"
            or ra["feature"].id != rb["feature"].id
            or ra["entity"] != rb["entity"]):
        return None            # different owners: moving one side works
    feat, idx, plane = ra["feature"], ra["entity"], ra["plane"]
    got = _entity_dim_for_direction(feat, idx, plane, na)
    kind = (feat.params or {})["entities"][idx].get("kind")
    blocked = {"blocked":
               f"both faces belong to the same {kind or 'sketch entity'} "
               f"({feat.id} · #{idx}) — moving it slides both walls together, "
               "so this distance cannot be changed that way; edit the entity "
               "in the feature tree"}
    if not got:
        return blocked
    key, name = got
    current = float(feat.params["entities"][idx][key])
    # sanity: opposite walls of the entity must actually measure its dimension;
    # if they do not (a fragment of a wall after some cut), offering the edit
    # would land somewhere other than what the user sees
    if measured is not None and abs(current - float(measured)) > 1e-2:
        return blocked
    return {"driver": {
        "feature": feat.id,
        "path": ["entities", idx, key],
        "current": current,
        "transform": "value",          # the distance IS the stored number
        "label": f"{feat.id} · {kind} #{idx} {key}",
        "drives": name,
    }}


def _tree_order(doc) -> dict:
    return {f.id: i for i, f in enumerate(doc.features)}


def resolve_move(doc, a_shape, b_shape, a_sel, b_sel, body_a, body_b,
                 side: str = "auto"):
    """How to change a two-face distance by MOVING one side.

    Parallel planar faces only, because only then is "the distance" a single
    number with a single direction.

    Which side moves: by default the one whose sketch is LATER in the tree. The
    earlier feature is almost always stock or a datum — in esp32-remote
    `outline_sketch` is feature #1 and the pillar islands come far later, so
    "the pillar moves, the wall stays" falls out of tree order rather than from
    a guess. `side` overrides it with the user's explicit choice.

    Returns a description, or {"error": reason} — never a silent None, because
    "why can't I type here?" deserves an answer (rule 7)."""
    pa, pb = _plane(a_shape), _plane(b_shape)
    if not pa or not pb:
        return {"error": "moving a side needs two FLAT faces"}
    (centre_a, na), (centre_b, nb) = pa, pb
    if abs(abs(_dot(na, nb)) - 1.0) > PARALLEL_TOL:
        return {"error": "those faces are not parallel, so there is no single "
                         "distance to set — measure a parallel pair"}
    roles = {"a": _face_role(doc, a_shape, a_sel, body_a),
             "b": _face_role(doc, b_shape, b_sel, body_b)}
    walls = {k: v for k, v in roles.items() if v and v["kind"] == "wall"}
    # BACKSTOP: both walls on ONE entity means translating it moves both ends
    # of the tape measure together — the distance can never change. This pair
    # belongs to resolve_pair_driver (an exact dimension edit); reaching here
    # means it had no such dimension, so refuse rather than no-op.
    if (len(walls) == 2
            and walls["a"]["feature"].id == walls["b"]["feature"].id
            and walls["a"]["entity"] == walls["b"]["entity"]):
        return {"error": "both faces belong to the same sketch entity — "
                         "moving it slides both walls together; edit the "
                         "entity's dimensions in the feature tree instead"}
    if not walls:
        # A cap's position is its depth, not its profile's x/y, so name the
        # edit that WOULD work rather than reporting nothing movable.
        if any(v and v["kind"] == "cap" for v in roles.values()):
            return {"error": DEPTH_ADVICE}
        return {"error": "neither face traces back to a sketch entity that "
                         "could be moved (a primitive or an imported body) — "
                         "ask the AI designer to move it instead"}
    if side not in ("auto", "a", "b"):
        side = "auto"
    if side == "auto":
        order = _tree_order(doc)
        # LATER in the tree moves: the earlier feature is the datum
        side = max(walls.items(),
                   key=lambda kv: order.get(kv[1]["feature"].id, -1))[0]
    if side not in walls:
        other = "b" if side == "a" else "a"
        if roles[side] and roles[side]["kind"] == "cap":
            return {"error": DEPTH_ADVICE}
        return {"error": f"face {side.upper()} does not come from a movable "
                         f"sketch entity — try moving {other.upper()} instead"}
    feat = walls[side]["feature"]
    idx = walls[side]["entity"]
    plane = walls[side]["plane"]
    # signed separation along A's normal, which is what "the distance" is
    along = _dot(na, _sub(centre_b, centre_a))
    return {"side": side, "feature": feat.id, "entity": idx,
            "plane": plane, "normal": na, "along": along,
            "label": f"{feat.id} · entity #{idx}",
            "movable": sorted(walls)}


def plan_move(doc, mv: dict, current: float, target: float) -> dict:
    """Turn a resolve_move() description into the x/y writes that land it.

    One formula covers all three parallel cases. With
    `along` = nA·(cB - cA) the measured distance is |along|, and shifting the
    chosen side by s along nA gives |along + s| = target when

        s = sign(along) · (target - current)

    Checked on all three: a gap (along > 0) shrinks by moving B toward A, a
    thickness (along < 0) thins by moving B the other way, and a step follows
    the same rule. Moving A instead of B reverses the sense."""
    from build123d import Vector
    if current <= 0:
        return {"error": "that distance is zero — nothing to move relative to"}
    sign = 1.0 if mv["along"] >= 0 else -1.0
    s = sign * (target - current)
    if mv["side"] == "a":
        s = -s
    shift = _scale(mv["normal"], s)

    plane = mv["plane"]
    # The move must lie IN the sketch plane. When it does not, the distance is
    # controlled by DEPTH (an extrude amount or a plane offset), not by where
    # the entity sits — a different edit. Pretending otherwise would slide the
    # profile sideways and leave the measurement unchanged.
    try:
        origin = plane.to_local_coords(Vector(0, 0, 0))
        moved = plane.to_local_coords(Vector(*shift))
        dx, dy = moved.X - origin.X, moved.Y - origin.Y
        dz = moved.Z - origin.Z
    except Exception:
        return {"error": "could not map that move into the sketch's plane"}
    if abs(dz) > 1e-6:
        return {"error": DEPTH_ADVICE}
    try:
        feat = doc.get(mv["feature"])
        ent = (feat.params or {})["entities"][mv["entity"]]
    except (KeyError, IndexError, TypeError):
        return {"error": "the entity behind that face is gone — click it again"}
    x0, y0 = float(ent.get("x", 0) or 0), float(ent.get("y", 0) or 0)
    return {
        "writes": [(["entities", mv["entity"], "x"], _r(x0 + dx, 6)),
                   (["entities", mv["entity"], "y"], _r(y0 + dy, 6))],
        "feature": mv["feature"],
        "moved": mv["label"],
        "by": [_r(dx, 4), _r(dy, 4)],
        "side": mv["side"],
    }


# ---------------------------------------------------------------------------
# after a write: finding the SAME pick again
#
# Face and edge ids are array positions, and a rebuild renumbers them. The
# verification below a write used to re-read the pick's old index, so whenever
# OCCT reordered the faces it compared the requested value against some other
# piece of geometry and reverted a CORRECT edit. Measured in the section 6
# review (2026-09-10) on the user's own x-frame: asking a ⌀8 pad hole for 8.5
# really made it 8.5 (volume 116961.184 -> 116896.394) and the tool answered
# "asked for 8.5 mm but the model came out at 8 mm — nothing was changed".
# Seven of the 81 editable diameters across eight saved designs lost a correct
# edit that way, and the derived MOVE path lost them too (the picked wall had
# moved by exactly the 1.0 mm asked for, at a new index).
#
# So a pick is re-found by its GEOMETRY, the way sketch.resolve_face already
# survives a rebuild. What stays constant is:
#
#   a round face/edge   its AXIS LINE   (changing a diameter leaves it alone)
#   a flat face         its NORMAL, and its position ACROSS that normal
#
# Both a move and a width edit slide a wall along its own normal and nowhere
# else (plan_move's shift is `normal * s` by construction), so ignoring the
# along-normal component is exactly right. A match must be UNIQUE: two
# candidates within tolerance mean we cannot claim to have found the same
# pick, and the stored index is kept rather than guessed at.

# how close a candidate must sit to the pick's own line/plane to BE that pick
RELOCATE_TOL = 1e-3


def _signature(shape):
    """Index-free identity of a pick, captured BEFORE the write."""
    circ = _circle(shape)
    if circ:
        centre, radius, axis = circ
        if axis:
            return {"kind": "axis", "at": centre, "dir": axis, "r": radius}
        return {"kind": "ring", "at": centre, "r": radius}
    pl = _plane(shape)
    if pl:
        centre, normal = pl
        return {"kind": "plane", "at": centre, "dir": normal}
    return None


def _sig_distance(sig, shape):
    """How far this shape is from BEING the pick `sig` described, or None when
    it is not the same kind of thing at all."""
    kind = sig["kind"]
    if kind in ("axis", "ring"):
        circ = _circle(shape)
        if not circ:
            return None
        centre, _radius, axis = circ
        if kind == "ring":
            return None if axis else _norm(_sub(centre, sig["at"]))
        if not axis or abs(abs(_dot(axis, sig["dir"])) - 1.0) > PARALLEL_TOL:
            return None
        # perpendicular distance between the two axis LINES: where the pick
        # sits along its own axis is arbitrary, and a radius change moves it
        return _axis_offset(sig["at"], centre, axis)
    pl = _plane(shape)
    if not pl:
        return None
    centre, normal = pl
    if _dot(normal, sig["dir"]) < 1.0 - PARALLEL_TOL:
        return None                       # a wall keeps facing the same way
    d = _sub(centre, sig["at"])
    return _norm(_sub(d, _scale(sig["dir"], _dot(d, sig["dir"]))))


def _relocate(doc, sel, sig, want_r=None):
    """`sel` with its id updated to where that geometry sits NOW.

    Unchanged when there is no signature, no unique match, or nothing built —
    in which case the caller simply verifies the way it always did.

    `want_r` is the radius the pick is EXPECTED to have afterwards, and it is
    what separates a bore from the counterbore it sits inside: those two are
    coaxial, so the axis test alone calls them both a match (x-frame's pad
    holes are ⌀8 bores inside ⌀36 recesses). Without it two of the design's
    seventeen editable diameters stayed unfindable."""
    if not sig or not isinstance(sel, dict):
        return sel
    body = sel.get("body")
    part = doc._parts.get(body) if body else None
    if part is None:
        part = doc.result()
    if part is None:
        return sel
    try:
        shapes = (part.edges() if str(sel.get("kind")) == "edge"
                  else provenance.picked_faces(doc, body, part))
    except Exception:
        return sel
    hits = []
    for i, shape in enumerate(shapes):
        d = _sig_distance(sig, shape)
        if d is not None and d <= RELOCATE_TOL:
            hits.append(i)
    if not hits:
        return sel
    if len(hits) == 1:
        return {**sel, "id": hits[0]}
    target = want_r if want_r is not None else sig.get("r")
    if target is None:
        return sel                        # ambiguous: never guess (see above)
    ranked = []
    for i in hits:
        circ = _circle(shapes[i])
        if circ:
            ranked.append((abs(circ[1] - target), i))
    ranked.sort()
    if not ranked:
        return sel
    if len(ranked) > 1 and ranked[1][0] - ranked[0][0] <= RELOCATE_TOL:
        return sel                        # a genuine tie: still never guess
    return {**sel, "id": ranked[0][1]}


def remeasure(doc, plan: dict, a: dict, b: dict | None = None) -> dict:
    """Measure the same PICKS again after a write — wherever they moved to.

    Returns the measurement with a "picks" key naming the ids the selections
    now carry, so the caller (and the panel) can go on talking about the same
    two faces instead of two array positions."""
    sigs = (plan or {}).get("signatures") or {}
    want_r = None
    if plan.get("kind") == "diameter":
        try:
            want_r = float(plan["requested"]) / 2.0
        except (KeyError, TypeError, ValueError):
            want_r = None
    a2 = _relocate(doc, a, sigs.get("a"), want_r)
    b2 = _relocate(doc, b, sigs.get("b"), want_r) if b else None
    out = measure(doc, a2, b2)
    out["picks"] = {"a": a2, "b": b2}
    return out


def _to_param(transform: str, value: float, current: float) -> float:
    """The stored param that produces `value` on screen."""
    if transform == "half":
        return value / 2.0
    if transform == "signed":       # magnitude shown, sign preserved
        return -abs(value) if current < 0 else abs(value)
    return value


def plan_set(doc, a: dict, b: dict | None, value: float,
             side: str = "auto") -> dict:
    """Work out WHAT to write and to what — without writing anything.

    Split from the write so the caller can snapshot for undo first, and so a
    request that cannot be honoured changes nothing at all.

    `side` ("auto" | "a" | "b") picks which face moves when the distance is
    derived rather than driven — see resolve_move."""
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
    # the index-free identity of each pick, so the write can be VERIFIED
    # against the same geometry even after a rebuild renumbers the faces
    sigs = {"a": _signature(shape_a)}
    driver = resolve_driver(doc, shape_a, base, a, body_a)
    if driver:
        new_param = _to_param(driver["transform"], value, driver["current"])
        if new_param <= 0:
            # sketch._validate_dims would reject it at rebuild anyway; refusing
            # here means the document is never even touched
            return {"error": f"a {driver['drives']} of {value:g} mm would need "
                             f"{new_param:g} mm — dimensions must be positive"}
        return {"driver": driver, "requested": _r(value),
                "param": _r(new_param, 6), "was": _r(driver["current"], 6),
                "kind": base.get("kind"), "signatures": sigs,
                "writes": [(driver["path"], _r(new_param, 6))]}

    # Not driven by one param. If it is a distance between two parallel faces,
    # it can still be changed by MOVING one side — but only with the side named
    # (P2). Everything else is honestly read-only.
    if b is None:
        return {"error": "this measurement is not driven by a single "
                         "parameter, so it cannot be typed into — see the "
                         "feature tree, or ask the AI designer to change it"}
    try:
        shape_b, body_b = resolve(doc, b)
    except ValueError as e:
        return {"error": str(e)}
    sigs["b"] = _signature(shape_b)
    # opposite walls of ONE entity: an exact dimension edit, never a move
    pd = resolve_pair_driver(doc, shape_a, shape_b, a, b, body_a, body_b,
                             base.get("value"))
    if pd and "driver" in pd:
        driver = pd["driver"]
        new_param = _to_param(driver["transform"], value, driver["current"])
        if new_param <= 0:
            return {"error": f"a {driver['drives']} of {value:g} mm would "
                             f"need {new_param:g} mm — dimensions must be "
                             "positive"}
        return {"driver": driver, "requested": _r(value),
                "param": _r(new_param, 6), "was": _r(driver["current"], 6),
                "kind": base.get("kind"), "signatures": sigs,
                "writes": [(driver["path"], _r(new_param, 6))]}
    if pd and "blocked" in pd:
        return {"error": pd["blocked"]}
    mv = resolve_move(doc, shape_a, shape_b, a, b, body_a, body_b, side)
    if "error" in mv:
        return mv
    plan = plan_move(doc, mv, float(base.get("value") or 0), value)
    if "error" in plan:
        return plan
    return {"move": {"side": plan["side"], "feature": plan["feature"],
                     "label": plan["moved"], "by": plan["by"],
                     "movable": mv["movable"]},
            "requested": _r(value), "was": _r(base.get("value") or 0, 6),
            "kind": base.get("kind"), "signatures": sigs,
            "writes": plan["writes"]}


def write(doc, plan: dict) -> None:
    """Apply a plan_set() result to the document. Caller rebuilds.

    Every plan carries a `writes` list of (path, value), so a one-param edit
    (a diameter) and a two-param edit (moving an entity in x AND y) go through
    the same code — one of them being half-applied is not a state this should
    be able to reach."""
    fid = (plan.get("driver") or plan.get("move") or {})["feature"]
    feat = doc.get(fid)
    for path, value in plan["writes"]:
        target = feat.params
        for k in path[:-1]:
            target = target[k]
        target[path[-1]] = value


# ---------------------------------------------------------------------------
# probing: slide the measurement along the geometry
#
# User request (2026-08-31): "the measurement always measure from the center,
# but i dont know the closest distance and longest distance … if i can able to
# [move] the line, i can see the live value in the box, same this works for the
# circle and a box". The witness pair is one sample; between a slanted wall and
# a boss — or around a cylinder — the distance varies along the geometry, so
# the dimension line is draggable and each drag position asks the KERNEL for
# the local distance, not the mesh.

def probe(doc, a: dict, b: dict | None, point, on: str = "a") -> dict:
    """Distance from a dragged point (riding selection `on`) to the OTHER
    selection — the live value under a dimension-line drag.

    The point comes from a raycast on the picked face, so it is already ON the
    source shape; the answer is the exact minimum distance from that point to
    the other shape, with the witness point so the line can follow the drag.
    Read-only and never raises."""
    from build123d import Vertex, Vector
    try:
        if not doc.features:
            return {"error": "the design is empty"}
        if b is None:
            return {"error": "probing needs two selections"}
        shape_a, _ = resolve(doc, a)
        shape_b, _ = resolve(doc, b)
    except ValueError as e:
        return {"error": str(e)}
    try:
        p = [float(point[0]), float(point[1]), float(point[2])]
        v = Vertex(*p)
    except Exception:
        return {"error": "that probe point is not a valid position"}
    source = shape_b if str(on) == "b" else shape_a
    target = shape_a if str(on) == "b" else shape_b

    # TWO ROUND SURFACES (two pillars, two bores): the CALIPER model. The drag
    # has two degrees of freedom — ALONG the axis (station) and SIDEWAYS
    # (lateral offset t). The measuring line stays parallel to the gap and
    # shifts sideways as one piece, so BOTH dots slide to the same side around
    # their own curves together, and the length grows because both surfaces
    # curve away:  value(t) = D − sqrt(rA²−t²) − sqrt(rB²−t²)  — the facing
    # minimum at t=0, extending on both sides, limit at the smaller flank.
    # (User report 2026-09-01: "one point is stactic and fixed and one point
    # is moving … the line or both ponts has to move parrlry in the curve side
    # and the line should exted in the curve on the both side". The previous
    # cut swung only the near dot and measured nearest-from-it: the far dot
    # hugged one spot.)
    cs, ct = _circle(source), _circle(target)
    if cs and ct and cs[2] and ct[2]:
        (pos_s, r_s, dir_s), (pos_t, r_t, dir_t) = cs, ct
        ua = _scale(dir_s, 1.0 / max(_norm(dir_s), 1e-12))
        station = _add(pos_s, _scale(ua, _dot(_sub(p, pos_s), ua)))
        other = _closest_on_axis(pos_t, dir_t, station)
        gap_v = _sub(other, station)
        gap_d = _norm(gap_v)
        if gap_d > 1e-9 and gap_d - r_s - r_t > TOUCH_TOL:
            u = _scale(gap_v, 1.0 / gap_d)          # across the gap
            va = [ua[1]*u[2] - ua[2]*u[1],          # sideways = axis × u
                  ua[2]*u[0] - ua[0]*u[2],
                  ua[0]*u[1] - ua[1]*u[0]]
            vn = _norm(va)
            if vn > 1e-9:
                va = _scale(va, 1.0 / vn)
                t = _dot(_sub(p, station), va)
                # the line needs a wall point on BOTH circles at this offset:
                # clamp at the smaller flank — that is the natural limit
                t_max = min(r_s, r_t)
                t = max(-t_max, min(t_max, t))
                ha = (max(r_s * r_s - t * t, 0.0)) ** 0.5
                hb = (max(r_t * r_t - t * t, 0.0)) ** 0.5
                frm = _add(_add(station, _scale(va, t)), _scale(u, ha))
                to = _sub(_add(other, _scale(va, t)), _scale(u, hb))
                val = gap_d - ha - hb
                return {"kind": "probe", "mode": "across", "value": _r(val),
                        "unit": MM, "label": _fmt(val),
                        "from": _r3(frm), "to": _r3(to)}
        # coaxial or overlapping at this station: fall through to nearest

    # FLAT + ROUND (a pillar beside a wall): the same caliper, one side
    # straightened out. The flat dot may only travel the band between the
    # pillar's two FLANK points (user report 2026-09-01: "the flat side moves
    # to over cross. it should move only till the pillar curve two points,
    # becuase those are hightest point") — near the tangent the old across-ray
    # grazed and its hit point skated away along the wall. At lateral offset t
    # (clamped to ±r) the curve dot sits sqrt(r²−t²) from the axis toward the
    # wall and the flat dot at the perpendicular foot at the SAME offset:
    #     value(t) = d0 − sqrt(r²−t²)
    # — the facing minimum, growing to d0 at the flanks, both dots moving in
    # parallel and holding at the flanks together. Applies when the axis runs
    # (near-)parallel to the wall; a tilted pair keeps the generic ray.
    pl_s, pl_t = _plane(source), _plane(target)
    round_s, round_t = _circle(source), _circle(target)
    flat_round = None
    if pl_s and round_t and round_t[2]:
        flat_round = (pl_s, round_t)
    elif pl_t and round_s and round_s[2]:
        flat_round = (pl_t, round_s)
    if flat_round:
        (pc, n), (pos_r, r_r, dir_r) = flat_round
        ua = _scale(dir_r, 1.0 / max(_norm(dir_r), 1e-12))
        if abs(_dot(ua, n)) < 0.2:              # axis parallel-ish to the wall
            axp = _add(pos_r, _scale(ua, _dot(_sub(p, pos_r), ua)))
            dsign = _dot(_sub(axp, pc), n)
            d0 = abs(dsign)
            if d0 - r_r > TOUCH_TOL:
                nh = _scale(n, 1.0 if dsign >= 0 else -1.0)  # wall -> axis
                va = [ua[1]*nh[2] - ua[2]*nh[1],
                      ua[2]*nh[0] - ua[0]*nh[2],
                      ua[0]*nh[1] - ua[1]*nh[0]]
                vn = _norm(va)
                if vn > 1e-9:
                    va = _scale(va, 1.0 / vn)
                    t = max(-r_r, min(r_r, _dot(_sub(p, axp), va)))
                    h = (max(r_r * r_r - t * t, 0.0)) ** 0.5
                    curve_dot = _sub(_add(axp, _scale(va, t)), _scale(nh, h))
                    flat_dot = _sub(_add(axp, _scale(va, t)), _scale(nh, d0))
                    val = d0 - h
                    src_is_flat = flat_round[0] is pl_s
                    frm = flat_dot if src_is_flat else curve_dot
                    to = curve_dot if src_is_flat else flat_dot
                    out = {"kind": "probe", "mode": "across",
                           "value": _r(val), "unit": MM, "label": _fmt(val),
                           "from": _r3(frm), "to": _r3(to)}
                    # the closest-anywhere footnote — one glance tells the
                    # user how far off the facing minimum this station sits
                    mdn = _min_distance(Vertex(*frm), target)
                    if mdn is not None and mdn[0] < val - 5e-3:
                        out["nearest"] = _r(mdn[0])
                    return out

    md = _min_distance(v, target)
    if md is None:
        return {"error": "could not measure from there"}
    d, _p1, p2 = md

    # ACROSS, not just nearest (user request 2026-08-31: "the line should move
    # according to the surface"). Nearest-point pivots the line toward one spot
    # on the other shape; what a machinist dragging along a wall expects is the
    # gap AT this point — a ray from here along the surface normal, stretched
    # until it meets the other shape. Probed: sliding along a wall past a
    # cylinder reads 25.0 / 26.0 / 29.0 mm as the circle curves away, and
    # cleanly misses beyond it (where nearest takes over again).
    across = None
    try:
        n = source.normal_at(Vector(*p))
        nv = [float(n.X), float(n.Y), float(n.Z)]
        ln = _norm(nv)
        if ln > 1e-9 and d > TOUCH_TOL:
            nv = _scale(nv, 1.0 / ln)
            if _dot(nv, _sub(p2, p)) < 0:
                nv = _scale(nv, -1.0)        # the normal must look AT the target
            from OCP.gp import gp_Lin, gp_Pnt, gp_Dir
            from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
            inter = BRepIntCurveSurface_Inter()
            inter.Init(target.wrapped, gp_Lin(gp_Pnt(*p), gp_Dir(*nv)), 1e-6)
            best = None
            while inter.More():
                w = float(inter.W())
                if w > 1e-7 and (best is None or w < best[0]):
                    q = inter.Pnt()
                    best = (w, [float(q.X()), float(q.Y()), float(q.Z())])
                inter.Next()
            if best is not None:
                across = best
    except Exception:
        across = None                        # curved-source oddity: fall back

    if across is not None:
        w, hit = across
        return {"kind": "probe", "mode": "across", "value": _r(w), "unit": MM,
                "label": _fmt(w), "from": _r3(p), "to": _r3(hit),
                "nearest": _r(d)}
    return {"kind": "probe", "mode": "nearest", "value": _r(d), "unit": MM,
            "label": _fmt(d), "from": _r3(p), "to": _r3(p2)}


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
        out["driver"] = None
        if out.get("kind") in ("gap", "thickness", "step"):
            # Opposite walls of ONE entity first: that distance IS the entity's
            # dimension (a box's width), so it gets an exact edit box. Moving
            # is meaningless there — it slides both walls together.
            try:
                pd = resolve_pair_driver(doc, shape_a, shape_b, a, b,
                                         body_a, body_b, out.get("value"))
            except Exception:
                pd = None
            if pd and "driver" in pd:
                out["driver"] = pd["driver"]
                return out
            if pd and "blocked" in pd:
                out["move"] = {"error": pd["blocked"]}
                return out
            # Different owners: a derived distance, changeable by MOVING one
            # side (P2). Report which sides could move and which is the
            # default, so the panel offers the choice instead of picking.
            try:
                mv = resolve_move(doc, shape_a, shape_b, a, b, body_a, body_b)
            except Exception as e:
                mv = {"error": f"could not work out what to move ({e!r})"}
            out["move"] = ({"error": mv["error"]} if "error" in mv else
                           {"side": mv["side"], "label": mv["label"],
                            "feature": mv["feature"],
                            "movable": mv["movable"]})
        return out
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:          # OCP errors are Exception, not RuntimeError
        return {"error": f"measurement failed: {e!r}"}
