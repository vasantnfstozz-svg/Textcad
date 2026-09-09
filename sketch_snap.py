"""
sketch_snap.py — what an existing body offers a sketch to snap to (S5).

Drawing against a part is guesswork unless the part's own geometry is
snappable: "when I want to start a sketch at those boxes edges, we need
something for selecting to those edges, like how we do for the origin".

This finds the geometry of the visible bodies that is COINCIDENT with the
sketch plane (Fusion's automatic projection of coincident geometry — not a
full Project Geometry command) and returns it in the sketch plane's own 2D
coordinates, ready to merge into the sketcher's snap list:

  * corner    — an edge endpoint lying in the plane (box corners)
  * midpoint  — the middle of an edge lying in the plane
  * center    — the centre of a circular edge in the plane (hole centres!)
  * crossing  — where an edge PIERCES the plane (a vertical edge of a box
                crossing the sketch plane it stands on)

plus `edges`, the in-plane edges as plane-local polylines, so the UI can DRAW
what is snappable instead of leaving the user to hunt for invisible points.

Pure functions over build123d solids; no HTTP, no document.
"""

from __future__ import annotations

import build123d as b3d

import sketch as sk

TOL = 0.5        # mm — how close to the plane counts as "in" the plane
DEDUPE = 1e-3    # mm — points closer than this are the same point


def plane_of(plane: str = "XY", offset: float = 0.0) -> b3d.Plane:
    """The sketch plane, exactly as make_sketch builds it."""
    if plane not in sk._PLANES:
        raise ValueError('snap: plane must be "XY", "XZ" or "YZ"')
    pl = sk._PLANES[plane]
    return pl.offset(float(offset)) if offset else pl


def plane_of_frame(frame: dict) -> b3d.Plane:
    """The sketch plane from an explicit world frame — a FACE sketch's plane,
    exactly as face_outline_2d returns it ({origin, x_dir, z_dir}; any offset
    is already baked into the origin). Probed: build123d accepts plain lists,
    and the derived y_dir matches the frame's own."""
    try:
        return b3d.Plane(origin=tuple(frame["origin"]),
                         x_dir=tuple(frame["x_dir"]),
                         z_dir=tuple(frame["z_dir"]))
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"snap: bad frame: {e}") from e


def _signed(pl: b3d.Plane, p) -> float:
    """Distance from the plane, along its normal."""
    return (p - pl.origin).dot(pl.z_dir)


def _local(pl: b3d.Plane, p) -> list[float]:
    loc = pl.to_local_coords(p)
    return [round(loc.X, 4), round(loc.Y, 4)]


def _edge_points(edge, n: int):
    try:
        return [edge @ (i / n) for i in range(n + 1)]
    except Exception:
        return []


def _is_closed(edge) -> bool:
    """Is this edge a full loop (a bore rim) rather than an arc with ends?
    Probed 2026-09-09: `is_closed` is True on both circles of a drilled box
    and False on all eight arcs of a filleted one."""
    try:
        return bool(edge.is_closed)
    except Exception:
        return False


def _cross_point(edge, pl, t0: float, t1: float, iters: int = 24):
    """Where the edge crosses the plane, between parameters t0 and t1 (whose
    signed distances have opposite signs). Bisection on the edge parameter, so
    a curved edge is as exact as a straight one — sampling alone would put the
    point visibly off a cylinder's silhouette."""
    try:
        d0 = _signed(pl, edge @ t0)
    except Exception:
        return None
    for _ in range(iters):
        tm = (t0 + t1) / 2
        try:
            dm = _signed(pl, edge @ tm)
        except Exception:
            return None
        if (d0 < 0) == (dm < 0):
            t0, d0 = tm, dm
        else:
            t1 = tm
    try:
        return edge @ ((t0 + t1) / 2)
    except Exception:
        return None


def snap_geometry(parts: dict, plane: str = "XY", offset: float = 0.0,
                  tol: float = TOL, frame: dict | None = None) -> dict:
    """`parts` maps body id -> solid. Returns
    {"points": [{"x","y","kind","body"}], "edges": [{"body","pts"}]}
    in the sketch plane's local 2D frame. `frame` (a face sketch's world
    frame) overrides plane/offset — face sketches had NO model snapping at
    all before, because only the three named planes could be asked about."""
    pl = plane_of_frame(frame) if frame else plane_of(plane, offset)
    points: list[dict] = []
    edges: list[dict] = []
    # a corner beats a midpoint at the same spot, and a real corner beats a
    # crossing — keep the most meaningful label when they coincide
    rank = {"corner": 3, "center": 2, "crossing": 1, "midpoint": 0}

    def add(p, kind: str, body: str):
        xy = _local(pl, p)
        for q in points:
            if abs(q["x"] - xy[0]) < DEDUPE and abs(q["y"] - xy[1]) < DEDUPE:
                if rank[kind] > rank[q["kind"]]:
                    q["kind"] = kind
                return
        points.append({"x": xy[0], "y": xy[1], "kind": kind, "body": body})

    for body, solid in (parts or {}).items():
        if solid is None or sk.is_sketch(solid):
            continue
        try:
            body_edges = solid.edges()
        except Exception:
            continue
        for edge in body_edges:
            try:
                circle = edge.geom_type == b3d.GeomType.CIRCLE
                centred = edge.geom_type == b3d.GeomType.ELLIPSE
                n = 2 if edge.geom_type == b3d.GeomType.LINE else 16
            except Exception:
                continue
            pts = _edge_points(edge, n)
            if not pts:
                continue
            dist = [_signed(pl, p) for p in pts]

            if all(abs(d) <= tol for d in dist):          # edge IS in the plane
                # A CLOSED edge (a bore's rim, a full ellipse) has no ends —
                # what it has is a parameter seam. Before the code review of
                # 2026-09-09 that seam was offered as a model "corner" and its
                # antipode as a "midpoint": measured on Box(40,40,10) minus a
                # 10mm bore, a corner at (5, 0) and a midpoint at (-5, 0),
                # drawn as dots and outranking the grid in smartSnap. They are
                # not features of the part. Its centre is, and it is added
                # below. An ARC keeps its ends — those are real corners.
                if not _is_closed(edge):
                    add(pts[0], "corner", body)
                    add(pts[-1], "corner", body)
                    mid = len(pts) // 2
                    add(pts[mid], "midpoint", body)
                # An ELLIPSE rim counts too (second code review, 2026-09-09):
                # an angled cut through a bore leaves a closed elliptical
                # edge, and suppressing its seam without offering its centre
                # left that feature with NO snap point at all. `arc_center`
                # is the true centre for both kinds — probed on an elliptical
                # bore: (0, 0, 0), where `center()` answers the sampled
                # centroid (-7.99984, -0.025) and would be a lie.
                if circle or centred:
                    try:
                        c = edge.arc_center
                        if abs(_signed(pl, c)) <= tol:
                            add(c, "center", body)
                    except Exception:
                        pass
                edges.append({"body": body,
                              "pts": [_local(pl, p) for p in pts]})
                continue

            # not in the plane: does it pierce it?
            for i in range(len(pts) - 1):
                if (dist[i] < 0) != (dist[i + 1] < 0):
                    hit = _cross_point(edge, pl, i / n, (i + 1) / n)
                    if hit is not None:
                        add(hit, "crossing", body)

    # the CENTRE OF THE DESIGN on this plane — the bbox centre of everything
    # found above ("if I want to design a circle to the center, the software
    # does not know the center of the design"). A real snap point that already
    # sits there keeps its own, more meaningful kind.
    xs = [p["x"] for p in points] + [q[0] for e in edges for q in e["pts"]]
    ys = [p["y"] for p in points] + [q[1] for e in edges for q in e["pts"]]
    if xs:
        cx = round((min(xs) + max(xs)) / 2, 4)
        cy = round((min(ys) + max(ys)) / 2, 4)
        if not any(abs(q["x"] - cx) < DEDUPE and abs(q["y"] - cy) < DEDUPE
                   for q in points):
            points.append({"x": cx, "y": cy, "kind": "design_center",
                           "body": "*"})

    return {"points": points, "edges": edges}
