"""
sketch_corner.py — what a path arc's RADIUS means, and how to change it.

User report (2026-08-31): "if I want to edit this curve dia to smaller or
bigger, how to do that ... it should be there in the tree, wherever we have
a curve." Curves in a path are stored as 3-POINT ARCS (via + to) — there is
no radius number anywhere, so the tree had nothing to offer. This module
gives every path arc an editable radius:

  * a CORNER arc — an arc whose neighbouring edges are straight lines that
    meet at a corner — is re-solved like a fillet: the new arc stays tangent
    to both lines, and the tangent points slide along them. Only three
    stored values change (the previous edge's end, the arc's via and to),
    so the surrounding geometry is untouched.
  * any other arc (a free bulge) keeps its two ENDPOINTS and moves `via`
    along the chord's perpendicular bisector until the radius matches,
    preserving which side it bulges to and whether it is the minor or
    major arc.

Stateless pure functions over the entity-list JSON, same contract as
sketch_trim: the UI sends the entities it is showing, gets rewritten
entities back, and applies them through the normal /api/edit path (so undo
and rebuild come for free).
"""

from __future__ import annotations

import math

EPS = 1e-9
TANGENT_MARGIN = 1e-6   # tangent length may not consume a full segment


# ---------------------------------------------------------------------------
# small 2D helpers
# ---------------------------------------------------------------------------

def _v(p):
    return (float(p[0]), float(p[1]))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, k):
    return (a[0] * k, a[1] * k)


def _norm(a):
    return math.hypot(a[0], a[1])


def _unit(a):
    n = _norm(a)
    if n < EPS:
        raise ValueError("degenerate (zero-length) edge in path")
    return (a[0] / n, a[1] / n)


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def circumradius(a, b, c) -> float:
    """Radius of the circle through three points (inf for collinear)."""
    a, b, c = _v(a), _v(b), _v(c)
    d = 2 * abs(_cross(_sub(b, a), _sub(c, a)))
    if d < EPS:
        return float("inf")
    la, lb, lc = _norm(_sub(b, c)), _norm(_sub(a, c)), _norm(_sub(a, b))
    return la * lb * lc / d


# ---------------------------------------------------------------------------
# the path as a chain
# ---------------------------------------------------------------------------

def _pt(label: str, value) -> tuple:
    """One [x, y], or a sentence naming what is wrong with it."""
    try:
        x, y = (float(v) for v in value or ())
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be two numbers, [x, y]") from None
    return (x, y)


def _chain(ent: dict):
    """-> (points, segs, closed_explicitly). points[i] is where segment i
    STARTS; points[n] is the last segment's end. The path closes back to
    points[0] — either because the last segment already ends there
    (explicitly closed) or via the implicit auto-close line _path_face adds."""
    segs = ent.get("segments") or []
    if not segs:
        raise ValueError("path has no segments")
    # NOT the origin when there is no start (fourth code review, 2026-09-09).
    # `set_arc_radius` writes this point back into the entity (line 240
    # below), so a radius edit on a start-less path SAVED a vertex at the
    # origin that the user never drew — and the sketch, which the backend
    # refuses precisely because the editor cannot show it, then turned green.
    if not ent.get("start"):
        raise ValueError(
            "path entity has no start point — the editor shows no profile "
            "for it at all; redraw it")
    pts = [_pt("the path entity's start point", ent["start"])]
    for i, s in enumerate(segs, start=1):
        if not s.get("to"):
            raise ValueError(
                f"path segment {i} has no end point — a segment needs the "
                f"point it ends at, written as [x, y]")
        pts.append(_pt(f"path segment {i}'s end point", s["to"]))
        # `via` is read raw further down (path_arcs l.149, set_arc_radius
        # l.180), and an IndexError from there is not in studio.py's catch
        # list: `/api/sketch/path-arcs` 500s and EVERY radius row in the
        # sketch disappears (fourth review follow-up, 2026-09-09).
        if s.get("type") == "arc":
            _pt(f"path segment {i}'s middle point", s.get("via"))
    closed = _norm(_sub(pts[-1], pts[0])) < 1e-6
    return pts, segs, closed


def _neighbour(segs, pts, closed, i, direction):
    """The edge before (-1) / after (+1) segment i, walking around the loop.
    -> (kind, far_point, writers) where kind is 'line'/'arc'/'close',
    far_point is the edge's far endpoint, and writers names which JSON slots
    move when the shared point with segment i moves."""
    n = len(segs)
    if direction < 0:
        j = i - 1
        if j < 0:
            if closed:                       # the LAST segment is the edge in
                return (segs[n - 1].get("type", "line"), pts[n - 1],
                        ["start", ("to", n - 1)])
            return ("close", pts[n], ["start"])   # implicit line pts[n]->start
    else:
        j = i + 1
        if j >= n:
            if closed:                       # the FIRST segment is the edge out
                return (segs[0].get("type", "line"), pts[1],
                        [("to", i), "start"])
            return ("close", pts[0], [("to", i)])  # implicit line ->start
    far = pts[j] if direction < 0 else pts[j + 1]
    writers = [("to", j)] if direction < 0 else [("to", i)]
    return (segs[j].get("type", "line"), far, writers)


def path_arcs(ent: dict) -> list[dict]:
    """Every arc in the path, with its current radius and whether a radius
    edit will re-fillet a corner or re-bulge a free arc.
    -> [{"segment": i, "kind": "corner"|"arc", "r": current}]"""
    pts, segs, closed = _chain(ent)
    out = []
    for i, s in enumerate(segs):
        if s.get("type") != "arc":
            continue
        r = circumradius(pts[i], s["via"], pts[i + 1])
        kind_in, _, _ = _neighbour(segs, pts, closed, i, -1)
        kind_out, _, _ = _neighbour(segs, pts, closed, i, +1)
        corner = kind_in in ("line", "close") and kind_out in ("line", "close")
        out.append({"segment": i, "kind": "corner" if corner else "arc",
                    "r": round(r, 4) if math.isfinite(r) else None})
    return out


# ---------------------------------------------------------------------------
# the edit
# ---------------------------------------------------------------------------

def set_arc_radius(entities: list, entity: int, segment: int,
                   radius: float) -> list:
    """Rewrite one arc of one path entity to the given radius. Returns a NEW
    entity list; the input is not touched. Raises ValueError with a human
    reason when the radius cannot be honoured."""
    r = float(radius)
    if not math.isfinite(r) or r <= 0:
        raise ValueError("radius must be a positive number")
    if not (0 <= entity < len(entities)):
        raise ValueError(f"no entity #{entity}")
    ent = entities[entity]
    if ent.get("kind") != "path":
        raise ValueError(f"entity #{entity} is a {ent.get('kind')}, not a path")
    pts, segs, closed = _chain(ent)
    if not (0 <= segment < len(segs)) or segs[segment].get("type") != "arc":
        raise ValueError(f"segment #{segment} is not an arc")

    new_ent = {**ent, "segments": [dict(s) for s in segs]}
    S, E, via = pts[segment], pts[segment + 1], _v(segs[segment]["via"])

    kind_in, far_in, wr_in = _neighbour(segs, pts, closed, segment, -1)
    kind_out, far_out, wr_out = _neighbour(segs, pts, closed, segment, +1)

    if (kind_in in ("line", "close") and kind_out in ("line", "close")
            and _corner_solve(new_ent, segment, S, E, via,
                              far_in, wr_in, far_out, wr_out, r)):
        return _replace(entities, entity, new_ent)

    # free arc: endpoints stay, via moves along the perpendicular bisector
    chord = _sub(E, S)
    h = _norm(chord) / 2
    if h < EPS:
        raise ValueError("this arc's ends coincide — edit it in the sketch")
    if r < h - 1e-9:
        raise ValueError(f"radius must be at least {round(h, 4)} "
                         "(half the distance between the arc's ends)")
    r = max(r, h)
    m = _mul(_add(S, E), 0.5)
    n_ = _unit((-chord[1], chord[0]))
    side = 1.0 if _cross(chord, _sub(via, S)) >= 0 else -1.0
    k = math.sqrt(max(r * r - h * h, 0.0))
    r_old = circumradius(S, via, E)
    s_old = abs(_dot(_sub(via, m), n_))
    major = math.isfinite(r_old) and s_old > r_old   # sagitta > r <=> major arc
    sag = r + k if major else r - k
    new_ent["segments"][segment]["via"] = _round(_add(m, _mul(n_, side * sag)))
    return _replace(entities, entity, new_ent)


def _corner_solve(new_ent, i, S, E, via, far_in, wr_in, far_out, wr_out, r):
    """Try to re-fillet the corner around arc i. Returns False when the two
    neighbouring edges do not actually form a corner (parallel/collinear) so
    the caller falls back to the free-arc edit. Raises when the corner is
    real but the radius does not fit."""
    d1 = _sub(S, far_in)         # along the incoming line, toward the corner
    d2 = _sub(far_out, E)        # along the outgoing line, away from it
    denom = _cross(d1, d2)
    if abs(denom) < EPS * max(_norm(d1) * _norm(d2), 1.0):
        return False             # parallel edges: no corner point exists
    # corner point P: far_in + t1*d1  ==  far_out - t2*d2
    t1 = _cross(_sub(far_out, far_in), d2) / denom
    P = _add(far_in, _mul(d1, t1))
    u1, u2 = _unit(d1), _unit(d2)
    ray1, ray2 = _mul(u1, -1), u2          # the two line rays leaving P
    cosphi = max(-1.0, min(1.0, _dot(ray1, ray2)))
    phi = math.acos(cosphi)
    if phi < 1e-6 or math.pi - phi < 1e-6:
        return False             # straight through / doubled back: no corner
    t = r / math.tan(phi / 2)
    lim_in = _norm(_sub(P, far_in))
    lim_out = _norm(_sub(far_out, P))
    if t > lim_in - TANGENT_MARGIN or t > lim_out - TANGENT_MARGIN:
        biggest = min(lim_in, lim_out) * math.tan(phi / 2)
        raise ValueError(
            f"radius {round(r, 4)} does not fit this corner — the round "
            f"would eat past a neighbouring edge (max here ≈ "
            f"{round(biggest * 0.999, 2)})")
    T1 = _add(P, _mul(ray1, t))            # tangent point, incoming line
    T2 = _add(P, _mul(ray2, t))            # tangent point, outgoing line
    bis = _unit(_add(ray1, ray2))
    C = _add(P, _mul(bis, r / math.sin(phi / 2)))
    mid = _sub(C, _mul(bis, r))            # arc midpoint, nearest the corner
    _write(new_ent, wr_in, T1)
    new_ent["segments"][i]["via"] = _round(mid)
    _write(new_ent, wr_out, T2)
    return True


def _write(ent, writers, p):
    for w in writers:
        if w == "start":
            ent["start"] = _round(p)
        else:
            ent["segments"][w[1]]["to"] = _round(p)


def _round(p):
    return [round(p[0], 4), round(p[1], 4)]


def _replace(entities, i, new_ent):
    out = [dict(e) for e in entities]
    out[i] = new_ent
    return out
