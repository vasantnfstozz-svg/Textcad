"""
sketch_trim.py — geometry for the sketch TRIM tool (the last P1 item).

Fusion's Trim: hover a curve, the piece between its nearest intersections
with other curves highlights red, click deletes it. Adapted to TextCAD's
closed-entity sketch model:

  * Every entity outline is split at its intersections with the OTHER
    entities' outlines into PIECES.
  * A piece of an entity that intersects nothing is the WHOLE outline —
    clicking it deletes the entity (Fusion deletes crossing-free curves too).
  * Clicking a real piece merges the two regions it separates. Material
    always wins (trim never removes material), so:
      - both sides material  -> the piece was an internal seam: dissolve it,
      - one side empty       -> that empty region is filled into the profile.
    The connected CLUSTER of overlapping entities is then rebuilt from the
    exact OCCT boundary as `path` entities (full circles are preserved as
    parametric circle entities). Entities outside the cluster stay untouched.
  * The true outer boundary cannot be trimmed — that would leave the
    profile open; the error says so instead of producing garbage.

Pure functions (no HTTP):  trim_pieces(entities)  and
trim_apply(entities, piece_id).  Both are stateless — the frontend sends the
current entity list every time, so a stale id is detected, never mis-applied.
"""

from __future__ import annotations
import math
import numpy as np
import build123d as b3d
import sketch as sk

TOL = 0.05      # mm — intersection merge tolerance
EPS = 0.15      # mm — flank probe offset from a piece's midpoint
SLIVER = 0.01   # mm^2 — boolean leftovers below this are noise


# ---------------------------------------------------------------------------
# entity outlines (sampled, exact enough for picking & point classification)
# ---------------------------------------------------------------------------

def _entity_face(e: dict, idx: int):
    try:
        return sk._entity(e).faces()[0]
    except Exception as ex:
        raise ValueError(f"trim: entity {idx} ({e.get('kind')}) does not "
                         f"build: {ex}") from ex


def _outline(e: dict, idx: int) -> dict:
    """Sample an entity's outer boundary into a closed polyline.
    Returns {pts (n,2), seglen (n,), cum (n+1,), L} — cum[k] is the
    arc-length at sample k, the loop closes from pts[-1] back to pts[0]."""
    wire = _entity_face(e, idx).outer_wire()
    n = int(min(max(wire.length / 0.8, 96), 384))
    pts = np.empty((n, 2))
    for i in range(n):
        p = wire.position_at(i / n)          # LENGTH mode: fraction of perimeter
        pts[i] = (p.X, p.Y)
    seg = np.roll(pts, -1, axis=0) - pts
    seglen = np.hypot(seg[:, 0], seg[:, 1])
    cum = np.concatenate(([0.0], np.cumsum(seglen)))
    return {"pts": pts, "seglen": seglen, "cum": cum, "L": float(cum[-1])}


def _inside(outline: dict, x: float, y: float) -> bool:
    """Even-odd point-in-polygon on the sampled outline."""
    pts = outline["pts"]
    xi, yi = pts[:, 0], pts[:, 1]
    xj, yj = np.roll(xi, 1), np.roll(yi, 1)
    crossing = ((yi > y) != (yj > y)) & \
               (x < (xj - xi) * (y - yi) / np.where(yj != yi, yj - yi, 1e-30) + xi)
    return bool(np.count_nonzero(crossing) % 2)


def _material_at(entities: list, outlines: list, idxs: list, x, y) -> bool:
    """Replay the sketch's add/subtract composition at one point.

    `idxs` must already be in the BUILDER's composition order (`_cluster`
    returns it that way) — the last entity that covers the point decides, so
    the order IS the answer. Replaying the drawing order instead was half of
    the P1 this module was carrying: on `[boss, bar, pocket]` it reported no
    material at (0, ±4), where the builder leaves 22.3648 mm2 of boss.
    """
    m = False
    for i in idxs:
        if _inside(outlines[i], x, y):
            m = entities[i].get("mode", "add") != "subtract"
    return m


# ---------------------------------------------------------------------------
# outline-outline intersections (vectorized segment pairs)
# ---------------------------------------------------------------------------

def _poly_intersections(a: dict, b: dict):
    """All crossings between two closed polylines -> (paramsA, paramsB) in
    arc-length along each. Collinear overlaps are skipped (tangent contact)."""
    A0 = a["pts"]; A1 = np.roll(A0, -1, axis=0)
    B0 = b["pts"]; B1 = np.roll(B0, -1, axis=0)
    r = A1 - A0                                   # (n,2)
    s = B1 - B0                                   # (m,2)
    denom = np.multiply.outer(r[:, 0], s[:, 1]) - \
            np.multiply.outer(r[:, 1], s[:, 0])   # (n,m)
    qp = B0[None, :, :] - A0[:, None, :]          # (n,m,2)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (qp[:, :, 0] * s[None, :, 1] - qp[:, :, 1] * s[None, :, 0]) / denom
        u = (qp[:, :, 0] * r[:, None, 1] - qp[:, :, 1] * r[:, None, 0]) / denom
    hit = (np.abs(denom) > 1e-12) & \
          (t >= -1e-9) & (t <= 1 + 1e-9) & (u >= -1e-9) & (u <= 1 + 1e-9)
    ii, jj = np.nonzero(hit)
    pa = a["cum"][ii] + np.clip(t[ii, jj], 0, 1) * a["seglen"][ii]
    pb = b["cum"][jj] + np.clip(u[ii, jj], 0, 1) * b["seglen"][jj]
    return pa.tolist(), pb.tolist()


def _merge_params(params: list, L: float) -> list:
    """Sort and merge split params closer than TOL along the loop (incl. the
    wrap between last and first)."""
    if not params:
        return []
    ps = sorted(p % L for p in params)
    merged = [ps[0]]
    for p in ps[1:]:
        if p - merged[-1] > TOL:
            merged.append(p)
    if len(merged) > 1 and (merged[0] + L) - merged[-1] <= TOL:
        merged.pop()                              # wraps onto the first point
    return merged


def _slice_pts(o: dict, p0: float, p1: float) -> np.ndarray:
    """Polyline of the outline between arc-length params p0 -> p1 (wrapping)."""
    L = o["L"]
    if p1 <= p0:
        p1 += L

    def at(p):
        p %= L
        k = int(np.searchsorted(o["cum"], p, side="right")) - 1
        k = min(max(k, 0), len(o["pts"]) - 1)
        f = (p - o["cum"][k]) / max(o["seglen"][k], 1e-12)
        nxt = o["pts"][(k + 1) % len(o["pts"])]
        return o["pts"][k] + np.clip(f, 0, 1) * (nxt - o["pts"][k])

    pts = [at(p0)]
    n = len(o["pts"])
    # every sample point whose arc-length falls strictly inside (p0, p1),
    # unrolled once past L so wrapping pieces walk through the loop start
    base = np.concatenate([o["cum"][:-1], o["cum"][:-1] + L])
    sel = (base > p0 + 1e-9) & (base < p1 - 1e-9)
    idxs = np.nonzero(sel)[0] % n
    pts.extend(o["pts"][i] for i in idxs)
    pts.append(at(p1))
    return np.array(pts)


# ---------------------------------------------------------------------------
# pieces
# ---------------------------------------------------------------------------

def _pieces_raw(entities: list):
    if not entities:
        raise ValueError("trim: the sketch has no entities")
    outlines = [_outline(e, i) for i, e in enumerate(entities)]
    params = [[] for _ in entities]
    crossing = set()                              # {(i,j)} outline intersections
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            a, b = outlines[i], outlines[j]
            if (a["pts"].min(0) > b["pts"].max(0) + TOL).any() or \
               (b["pts"].min(0) > a["pts"].max(0) + TOL).any():
                continue                          # bounding boxes don't touch
            pa, pb = _poly_intersections(a, b)
            if pa:
                crossing.add((i, j))
                params[i] += pa
                params[j] += pb
    pieces = []
    for i, o in enumerate(outlines):
        ps = _merge_params(params[i], o["L"])
        if not ps:
            pieces.append({"id": f"{i}:0", "ent": i, "whole": True,
                           "_pts": np.vstack([o["pts"], o["pts"][:1]])})
            continue
        for k in range(len(ps)):
            p0, p1 = ps[k], ps[(k + 1) % len(ps)]
            if len(ps) == 1:
                p1 = p0 + o["L"]                  # single tangency: one big piece
            pieces.append({"id": f"{i}:{k}", "ent": i, "whole": False,
                           "_pts": _slice_pts(o, p0, p1)})
    return pieces, outlines, crossing


def trim_pieces(entities: list) -> list:
    """Public: pieces for hover-highlighting, decimated for transport."""
    pieces, _, _ = _pieces_raw(entities)
    out = []
    for p in pieces:
        pts = p["_pts"]
        step = max(1, len(pts) // 80)
        thin = np.vstack([pts[::step], pts[-1:]])
        out.append({"id": p["id"], "ent": p["ent"], "whole": p["whole"],
                    "pts": [[round(float(x), 3), round(float(y), 3)]
                            for x, y in thin]})
    return out


# ---------------------------------------------------------------------------
# cluster of overlapping entities (rebuilt together on a trim)
# ---------------------------------------------------------------------------

def _cluster(entities, outlines, crossing, seed: int) -> list:
    """The connected group of entities the seed is tangled with, IN THE
    BUILDER'S COMPOSITION ORDER.

    The order is asked of `sketch.py` (R1: never re-derive a backend fact).
    Asking the cluster alone is the same answer as asking the whole sketch and
    striking out the rest: the cluster is closed under "overlaps or contains",
    so no ordering edge can cross its border, and `_order_from` breaks ties by
    the drawing order either way.
    """
    def overlaps(i, j):
        if (i, j) in crossing or (j, i) in crossing:
            return True
        # containment without boundary crossing (a hole fully inside a plate)
        return _inside(outlines[j], *outlines[i]["pts"][0]) or \
               _inside(outlines[i], *outlines[j]["pts"][0])
    seen, todo = {seed}, [seed]
    while todo:
        i = todo.pop()
        for j in range(len(entities)):
            if j not in seen and overlaps(i, j):
                seen.add(j)
                todo.append(j)
    members = sorted(seen)
    try:
        order = sk.compose_order([entities[i] for i in members])
    except Exception as ex:                       # noqa: BLE001
        raise ValueError(f"trim: these shapes cannot be ordered: {ex}") from ex
    return [members[k] for k in order]


def _compose_faces(entities, idxs):
    """The composed profile of just these entities — the BUILDER's answer.

    This used to be twenty lines of its own composition rule, in drawing
    order, and it disagreed with `sketch.py` (LAUNCH-PLAN section 10 P1,
    measured 2026-09-11): on `[boss, bar, pocket]` the builder composes
    22.3648 mm2 and this composed 0.0, so EVERY Trim click on that cluster
    died with "the result would have no area left". There is one rule now and
    it lives in `sketch.py`; `note=False` keeps a hover's arithmetic out of
    the next rebuild's warnings.
    """
    try:
        return sk.compose([entities[i] for i in idxs], note=False)
    except Exception as ex:                       # noqa: BLE001
        raise ValueError(f"trim: these shapes do not compose: {ex}") from ex


def _union_faces(entities, idxs):
    u = None
    for i in idxs:
        f = _entity_face(entities[i], i)
        u = f if u is None else u + f
    return u


def _pick_face(shape, q):
    """The face of a boolean result containing point q — or a clear error."""
    faces = [] if shape is None else \
        [f for f in shape.faces() if f.area > SLIVER]
    hit = next((f for f in faces if _face_contains(f, *q)), None)
    if hit is None:
        raise ValueError(
            "trim: couldn't resolve the region behind that segment — the "
            "shapes may only touch tangentially; move one slightly and retry")
    return hit


def _face_contains(face, x, y) -> bool:
    """Point inside an OCCT face (2D): inside its outer wire, outside holes."""
    def wire_pip(w):
        n = int(min(max(w.length / 0.8, 64), 384))
        pts = np.empty((n, 2))
        for i in range(n):
            p = w.position_at(i / n)
            pts[i] = (p.X, p.Y)
        return _inside({"pts": pts}, x, y)
    ow = face.outer_wire()
    if not wire_pip(ow):
        return False
    return not any(wire_pip(w) for w in face.wires() if not w.is_same(ow))


# ---------------------------------------------------------------------------
# exact boundary -> entities (paths with true lines/arcs; circles stay circles)
# ---------------------------------------------------------------------------

def _xy(v):
    return [round(float(v.X), 4), round(float(v.Y), 4)]


def _straightish(edge) -> bool:
    try:
        p0, pm, p1 = edge @ 0, edge @ 0.5, edge @ 1
    except Exception:
        return False
    chord = (p1 - p0).length
    if chord < 1e-9:
        return False
    return ((pm - p0).cross(p1 - p0)).length / chord < 1e-4


def _wire_entity(wire, mode: str) -> dict:
    edges = wire.order_edges()
    if len(edges) == 1 and edges[0].geom_type == b3d.GeomType.CIRCLE \
            and edges[0].is_closed:
        c = edges[0].arc_center                   # an untouched circle survives
        return {"kind": "circle", "mode": mode,   # as a parametric circle
                "x": round(float(c.X), 4), "y": round(float(c.Y), 4),
                "r": round(float(edges[0].radius), 4)}
    segs, cur, start = [], None, None
    for e in edges:
        p0, p1 = e @ 0, e @ 1
        flipped = cur is not None and \
            (cur - p0).length > (cur - p1).length
        pt = (lambda t, e=e: e @ (1 - t)) if flipped else (lambda t, e=e: e @ t)
        if start is None:
            start = pt(0)
        gt = e.geom_type
        if gt == b3d.GeomType.LINE or _straightish(e):
            segs.append({"type": "line", "to": _xy(pt(1))})
        elif gt == b3d.GeomType.CIRCLE:
            if e.is_closed:                       # full circle inside a chain
                segs.append({"type": "arc", "via": _xy(pt(0.25)),
                             "to": _xy(pt(0.5))})
                segs.append({"type": "arc", "via": _xy(pt(0.75)),
                             "to": _xy(pt(1))})
            else:
                segs.append({"type": "arc", "via": _xy(pt(0.5)),
                             "to": _xy(pt(1))})
        else:                                     # ellipse/spline: short arcs
            n = min(16, max(2, int(e.length / 4) + 1))
            for k in range(n):
                pa, pm, pb = pt(k / n), pt((k + 0.5) / n), pt((k + 1) / n)
                chord = (pb - pa).length
                bow = ((pm - pa).cross(pb - pa)).length / max(chord, 1e-9)
                if bow < 1e-3:
                    segs.append({"type": "line", "to": _xy(pb)})
                else:
                    segs.append({"type": "arc", "via": _xy(pm), "to": _xy(pb)})
        cur = pt(1)
    s0 = _xy(start)
    if segs and math.hypot(segs[-1]["to"][0] - s0[0],
                           segs[-1]["to"][1] - s0[1]) < 1e-3:
        segs[-1]["to"] = s0                       # close exactly, no micro-edge
    return {"kind": "path", "mode": mode, "x": 0, "y": 0,
            "start": s0, "segments": segs}


def _shape_to_entities(shape) -> list:
    faces = [f for f in shape.faces() if f.area > SLIVER]
    if not faces:
        raise ValueError("trim: the result would have no area left")
    ents = []
    for f in faces:                               # outers first: adds
        ents.append(_wire_entity(f.outer_wire(), "add"))
    for f in faces:                               # then every hole: cuts
        ow = f.outer_wire()
        for w in f.wires():
            if not w.is_same(ow):
                ents.append(_wire_entity(w, "subtract"))
    return ents


# ---------------------------------------------------------------------------
# the trim itself
# ---------------------------------------------------------------------------

def _refuse_if_the_trim_broke_it(before: list, after: list) -> None:
    """Let the trim through unless it is what stopped the sketch building.

    The two guards this replaces asked a question of their own — "does the
    list now START with a cut?" — which the builder has not cared about since
    it learned to order by geometry. They refused work it accepts: deleting
    one bar from `[pocket cut, bar, bar, bar]` builds 144.0 mm2, and Trim
    answered "delete the cut shapes first" (measured 2026-09-11, LAUNCH-PLAN
    section 10 P1). The honest question is whether the builder can still
    compose the result, and a sketch that was already broken before the click
    must not be blamed on the click — that would trap the user in it.
    """
    try:
        sk.compose(after, note=False)
        return
    except Exception as ex:                       # noqa: BLE001
        complaint = str(ex)
    try:
        sk.compose(before, note=False)
    except Exception:                             # noqa: BLE001
        return                                    # broken before the click too
    raise ValueError(f"trim: that would leave a sketch the builder cannot "
                     f"make — {complaint}")


def trim_apply(entities: list, piece_id: str) -> dict:
    """Delete one piece. Returns {"entities": [...], "message": str}."""
    entities = [dict(e) for e in entities]
    pieces, outlines, crossing = _pieces_raw(entities)
    piece = next((p for p in pieces if p["id"] == piece_id), None)
    if piece is None:
        raise ValueError("trim: that segment is stale — the sketch changed; "
                         "hover again")
    i = piece["ent"]

    if piece["whole"]:                            # crossing-free entity: delete
        kind = entities[i].get("kind", "shape")
        new = entities[:i] + entities[i + 1:]
        if new:
            _refuse_if_the_trim_broke_it(entities, new)
        return {"entities": new,
                "message": f"Trim: removed the {kind} (it crossed nothing)."}

    pts = piece["_pts"]
    m = len(pts) // 2
    a, b = pts[max(m - 1, 0)], pts[min(m + 1, len(pts) - 1)]
    t = b - a
    tl = float(np.hypot(*t))
    if tl < 1e-9:
        raise ValueError("trim: segment too short to resolve — zoom in")
    nx, ny = -t[1] / tl, t[0] / tl
    mid = pts[m]
    cl = _cluster(entities, outlines, crossing, i)
    q1 = (mid[0] + EPS * nx, mid[1] + EPS * ny)
    q2 = (mid[0] - EPS * nx, mid[1] - EPS * ny)
    m1 = _material_at(entities, outlines, cl, *q1)
    m2 = _material_at(entities, outlines, cl, *q2)

    if m1 == m2:                                  # internal seam: dissolve it
        result = _compose_faces(entities, cl)
        note = "dissolved the seam"
    else:
        q = q1 if not m1 else q2                  # the empty side gets filled
        if not any(_inside(outlines[j], *q) for j in cl):
            raise ValueError(
                "trim: that is the outer boundary — removing it would leave "
                "the profile open. Select the shape and press Delete to "
                "remove it entirely.")
        material = _compose_faces(entities, cl)
        gaps = _union_faces(entities, cl) - material
        cell = _pick_face(gaps, q)
        # refine to the exact arrangement cell around q: a U-M component can
        # span several cells (a cut circle biting a rect edge is ONE disk in
        # U-M, but only its inside-the-rect half may be filled) — clip by
        # every cluster entity until only q's cell remains
        for j in cl:
            fj = _entity_face(entities[j], j)
            clipped = (cell & fj) if _inside(outlines[j], *q) else (cell - fj)
            cell = _pick_face(clipped, q)
        result = material + cell
        note = "filled the enclosed region"

    rebuilt = _shape_to_entities(result)
    cl_set = set(cl)
    # `cl` is in COMPOSITION order now, not index order, so the split point is
    # its SMALLEST member: the rebuilt block lands where the user drew the
    # first shape of the cluster, exactly as it did before.
    first = min(cl)
    keep_before = [e for k, e in enumerate(entities) if k < first
                   and k not in cl_set]
    keep_after = [e for k, e in enumerate(entities) if k > first
                  and k not in cl_set]
    new = keep_before + rebuilt + keep_after
    _refuse_if_the_trim_broke_it(entities, new)
    return {"entities": new,
            "message": f"Trim: {note}; {len(cl)} shape(s) rebuilt as "
                       f"{len(rebuilt)} profile(s)."}
