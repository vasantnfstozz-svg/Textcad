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
                  tol: float = TOL) -> dict:
    """`parts` maps body id -> solid. Returns
    {"points": [{"x","y","kind","body"}], "edges": [{"body","pts"}]}
    in the sketch plane's local 2D frame."""
    pl = plane_of(plane, offset)
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
                n = 2 if edge.geom_type == b3d.GeomType.LINE else 16
            except Exception:
                continue
            pts = _edge_points(edge, n)
            if not pts:
                continue
            dist = [_signed(pl, p) for p in pts]

            if all(abs(d) <= tol for d in dist):          # edge IS in the plane
                add(pts[0], "corner", body)
                add(pts[-1], "corner", body)
                mid = len(pts) // 2
                add(pts[mid], "midpoint", body)
                if circle:
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

    return {"points": points, "edges": edges}
