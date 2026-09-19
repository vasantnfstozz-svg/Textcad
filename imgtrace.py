"""trace.py — raster image -> sketch polygon entities ("Trace PNG").

Turns a silhouette image (PNG with transparency, or dark-on-light art) into
the SAME polygon entities the sketcher already understands, so the result is
a normal `sketch` feature the user can Extrude / Revolve / Cut like anything
drawn by hand. No new geometry kinds, no new ops.

Pipeline (battle-proven on the rocky-keychain design series, 2026-08):
    decode -> binary mask (alpha channel if real, else Otsu on luminance,
    polarity chosen so the BACKGROUND is the side that fills the picture's
    border, read past a THIN border shell — a scan edge or a printed frame)
 -> fill pieces solid + BRIDGE disjoint pieces (art is often split by
    highlight streaks; connect globally-closest pairs until one blob set)
 -> optional CHANNEL ABSORB: morphological open of the background at final
    mm scale — pre-fills recesses narrower than the user's end mill so the
    traced sketch is millable by construction
 -> outer contours + holes (RETR_CCOMP)
 -> Douglas-Peucker simplify (tol in mm) + one Chaikin smoothing round
 -> scale to mm, centre the whole artwork on the sketch origin
 -> polygon entities: outers mode "add", holes mode "subtract", points
    counter-clockwise and bbox-centred (align-safe, fuse-safe).
"""
from __future__ import annotations

import math

import cv2
import numpy as np


def _round_pts(pts):
    out, last = [], None
    for x, y in pts:
        p = (round(float(x), 3), round(float(y), 3))
        if p != last:
            out.append(p)
            last = p
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _area2(pts) -> float:
    n = len(pts)
    return sum(pts[i][0] * pts[(i + 1) % n][1]
               - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))


def _first_crossing(pts, tol=1e-9):
    """The first pair of non-adjacent edges that cross or TOUCH, as
    (i, j, point) — or None. One vectorised pass per edge, so a few hundred
    points cost milliseconds.

    `tol` widens the test past the segment ends by a billionth of their own
    length, because a touch decided in the last bits is not settled geometry:
    an outline this read as clean came out of `_poly_entity` — the same
    polygon, moved by its own bbox centre — as one that CROSSES, and the
    solid was invalid (rand76 in probes/imgtrace_r2_sweep.py, measured
    2026-09-17, round two). A pair of edges within a billionth of touching
    is a zero-width sliver whichever coordinates it is written in."""
    n = len(pts)
    if n < 4:
        return None
    a = np.asarray(pts, dtype=float)
    r = np.roll(a, -1, axis=0) - a
    for i in range(n - 2):
        lo, hi = i + 2, (n if i else n - 1)       # edge 0 and edge n-1 touch
        if lo >= hi:
            continue
        den = r[i, 0] * r[lo:hi, 1] - r[i, 1] * r[lo:hi, 0]
        safe = np.where(np.abs(den) > 1e-15, den, 1.0)
        d = a[lo:hi] - a[i]
        t = (d[:, 0] * r[lo:hi, 1] - d[:, 1] * r[lo:hi, 0]) / safe
        u = (d[:, 0] * r[i, 1] - d[:, 1] * r[i, 0]) / safe
        hit = ((np.abs(den) > 1e-15) & (t >= -tol) & (t <= 1.0 + tol)
               & (u >= -tol) & (u <= 1.0 + tol))
        if hit.any():
            k = int(np.argmax(hit))
            return i, lo + k, (float(a[i, 0] + t[k] * r[i, 0]),
                               float(a[i, 1] + t[k] * r[i, 1]))
    return None


def _uncross(pts):
    """Split a traced outline into SIMPLE polygons at its self-crossings, and
    return every one of them.

    OpenCV walks out and back along a one-pixel whisker, so the raw contour
    of ordinary anti-aliased art already touches itself; Douglas-Peucker then
    moves a point by up to `eps` and turns the touch into a crossing. Measured
    2026-09-17 (REVIEW-QUEUE section 9): a comb of 1 px teeth came out of the
    tracer with 26 self-crossings in ONE outline, and on random artwork one
    trace in sixty built a body OpenCASCADE calls invalid.

    Round one cut the SMALLER loop off and kept ONE polygon. That is right for
    a whisker — its fold-back turns the OTHER way and is `eps` wide — and
    wrong for a PINCH, where both loops are artwork: two discs joined by a
    one-pixel bar came back as one disc, 1237.16 mm2 of a true 2498.45,
    healthy and green with nothing said (measured 2026-09-17, round two). A
    loop that turns the same way as the piece it was cut from is material the
    picture really carries, so it is kept as a polygon of its own."""
    loops, work = [], [list(pts)]
    for _ in range(256):
        if not work:
            break
        cur = work.pop()
        hit = _first_crossing(cur)
        if hit is None:
            if len(cur) >= 3:
                loops.append(cur)
            continue
        i, j, x = hit
        a = _round_pts([x] + list(cur[i + 1:j + 1]))
        b = _round_pts(list(cur[:i + 1]) + [x] + list(cur[j + 1:]))
        aa, ab = _area2(a), _area2(b)
        if len(a) < 3 or len(b) < 3 or (aa > 0) != (ab > 0):
            keep = a if abs(aa) >= abs(ab) else b      # a whisker's fold-back
            if len(keep) >= 3:
                work.append(keep)
        else:
            work += [a, b]                             # a pinch: both are art
    else:                                              # pathological outline
        loops += [w for w in work
                  if len(w) >= 3 and _first_crossing(w) is None]
    return loops


_HAIR_MM = 0.01          # thinner than this, a wall is not geometry


def _pull_apart(loops, gap=_HAIR_MM, report=None):
    """Open a `gap` between loops of ONE sketch that come within a hair of
    each other. Returns the loops, the small ones moved.

    `_uncross` guarantees no ONE polygon crosses itself. Nothing guaranteed
    that two DIFFERENT polygons of the same sketch stay apart, and two hole
    loops that meet at a POINT pinch the face: measured 2026-09-17, round
    three's fuzz cases f73 at 90 mm and f122 at 12 mm build a solid OCCT calls
    `is_valid` True, with the right volume, that `inspector.health` calls "not
    manifold/watertight (open shell)" — 2 of 450 traces
    (probes/imgtrace_r3_pinch.py).

    It is a SLIVER, not a coincidence: before any rounding those two loops
    pass 0.000209 mm and 0.000346 mm apart, and the 0.001 mm coordinate grid
    then puts them on the same point exactly — the same argument
    `_first_crossing`'s `tol` makes for one polygon. A wall a fifth of a
    micron thick is not something the picture carries.

    So the SMALLER loop gives way: each of its vertices inside the hair is
    pushed straight out to `gap` from the vertex it is nearest. 0.01 mm is ten
    times the coordinate grid (so rounding cannot close it again), five times
    the 0.002 mm that measures healthy in
    probes/imgtrace_touching_loops_probe.py, and a quarter of the thinnest
    wall the corpus really carries (f122's next-closest pair, 0.0373 mm). A
    vertex is left alone if the push is more than a quarter of its own
    shorter edge, so a loop cannot be turned inside out to save a sliver.

    That last guard used to REFUSE instead of moving, and refusing is how a
    pinch got through it: the shared vertex `_uncross` inserts at a crossing
    sits on a sub-hair edge, so the push was always bigger than a quarter of
    it. Measured 2026-09-17 (probes/imgtrace_pull_apart_audit.py): 1 of 700
    ring traces — radius 130, spokes at 3.034032, 0.032646, 3.425228, traced
    12 mm tall — still handed sketch.py two hole loops at 0.000000000 mm and
    built 84.472 mm3 that `is_valid` calls True and `health` calls an open
    shell. So a vertex with no room of its own now moves TOGETHER WITH the
    neighbours joined to it by edges too short to absorb the push
    (`_hair_cluster`): below that length the points are one point at any
    scale the picture carries, the nudge is rigid so their shape is exact,
    and the edges either side of the cluster are still four times the move —
    which is the inside-out guard, kept.

    It measured ONE direction — the smaller loop's vertices against the bigger
    loop's outline — and the closest approach of two outlines sits on a vertex
    of either one, so a vertex of the BIGGER loop on the middle of a smaller
    loop's edge walked straight through it. Measured 2026-09-17 (round five,
    probes/imgtrace_r5_mirror.py): 1 of 16 800 ring traces — radius 131,
    spokes at 5.825232830 (1 px) and 4.621843815 (2 px), traced 9.5 mm tall —
    handed sketch.py two hole loops at 0.000000000 mm while this test read
    0.025739602 mm of clearance, and built 47.933 mm3 that `is_valid` calls
    True and `health` calls an open shell. `_split_at_feet` now asks the
    mirror question first and splits the smaller loop's edge at the contact,
    so the push below has a vertex to move.

    Those two are the only ways two polygons can TOUCH without their interiors
    overlapping: two straight segments at zero distance either cross
    transversally — which is an overlap, and an overlap is a union the kernel
    is happy with — or they meet at a point that is an endpoint of one of
    them, i.e. a vertex of one against the other's outline. Asked in both
    directions, the test is complete for a PAIR (round six; the ground truth
    is segment-to-segment in probes/imgtrace_r6_truth.py). What it never asked
    is whether a loop meets ITSELF after the push — `_walks_through_itself`
    — and what it never said is when it gave up; `report` collects that, and
    `_worst_residual` reads it back off the final coordinates."""
    if len(loops) < 2:
        return loops
    arr = [np.asarray(p, dtype=float) for p in loops]
    size = np.array([abs(_area2(p)) for p in loops])
    # only pairs whose (widened) boxes overlap can possibly be within a hair,
    # and the test is done for all pairs at once: detailed art is legitimately
    # hundreds of pieces, and a per-pair python test costs more than the
    # geometry does (392 entities: 1.25 s, against 0.02 s this way)
    lo = np.array([a.min(axis=0) for a in arr]) - gap
    hi = np.array([a.max(axis=0) for a in arr]) + gap
    box = ((lo[:, None, :] <= hi[None, :, :]).all(axis=2)
           & (lo[None, :, :] <= hi[:, None, :]).all(axis=2))
    pairs = [(int(i), int(j))
             for i in np.argsort(size, kind="stable")   # smallest gives way
             for j in np.flatnonzero(box[i] & (size >= size[i])) if i != j]
    stuck: list = []
    moved = False
    for _ in range(4):
        moved = False
        stuck = []
        for i, j in pairs:
            d, foot = _nearest_on_ring(arr[i], arr[j])
            # ...and the mirror question, when it can possibly matter. If a
            # vertex B of the bigger loop sits within `gap` of an edge (P, Q)
            # of this one, then P is within |PQ| + gap of the bigger loop, so
            # a one-way reading further than the longest edge plus the hair
            # proves there is nothing to find — and the second pass over the
            # points, which costs what the first one does, is not made.
            reach = float(np.hypot(*(np.roll(arr[i], -1, axis=0)
                                     - arr[i]).T).max())
            if float(d.min()) - reach <= gap:
                grown = _split_at_feet(arr[i], arr[j], gap)
                if len(grown) != len(arr[i]):
                    arr[i] = grown
                    d, foot = _nearest_on_ring(arr[i], arr[j])
            near = np.where(d < gap)[0]
            if not len(near):
                continue
            cij = arr[i].mean(axis=0) - arr[j].mean(axis=0)
            # plain floats from here down: this runs once per vertex inside
            # the hair, and on the pathological art (200 loops of 400 points,
            # every one touching its neighbours) a two-element numpy call per
            # step costs more than the whole pair scan — 169 s against 86 s
            # before the arithmetic came out (probes/imgtrace_r6_cost.py)
            cx, cy = float(cij[0]), float(cij[1])
            cn = math.hypot(cx, cy)
            for v in near:
                hx, hy = float(arr[i][v][0]), float(arr[i][v][1])
                fx, fy = float(foot[v][0]), float(foot[v][1])
                ax, ay = hx - fx, hy - fy
                n = math.hypot(ax, ay)
                if n < 1e-9:                  # exactly on the other outline
                    ax, ay, n = cx, cy, cn
                    if n < 1e-9:
                        stuck.append((i, j, float(d[v])))
                        continue
                ux, uy = ax / n, ay / n
                dx, dy = fx + ux * gap - hx, fy + uy * gap - hy
                # ...ON the 0.001 mm grid the sketch is written on. Every
                # point is on that grid by the time the push runs, so a move
                # that is a whole number of grid steps keeps it there and the
                # final `_round_pts` cannot eat any of the clearance the
                # guard just opened. Un-snapped it did: with the art-centring
                # shift put on the grid, round five's own ring case came out
                # at 0.009837 mm where the push had measured 0.010000
                # (measured 2026-09-17, round six). Step out until the
                # SNAPPED point really clears the hair.
                sx = sy = 0.0
                for _ in range(4):
                    sx, sy = round(dx, 3), round(dy, 3)
                    if math.hypot(hx + sx - fx, hy + sy - fy) >= gap:
                        break
                    dx, dy = dx + ux * 0.0008, dy + uy * 0.0008
                span = 4.0 * math.hypot(sx, sy)        # the old room test,
                if span < 1e-12:                       # read the other way
                    stuck.append((i, j, float(d[v])))
                    continue
                block = _hair_cluster(arr[i], int(v), span)
                if block is None:             # the whole loop is sub-hair
                    stuck.append((i, j, float(d[v])))
                    continue                  # — leave it as traced
                delta = np.array((sx, sy))
                if _walks_through_itself(arr[i], block, delta):
                    stuck.append((i, j, float(d[v])))
                    continue                  # the loop's OWN far wall
                arr[i][block] += delta
                moved = True
        if not moved:
            break
    if report is not None:
        # In the round that moved NOTHING, every pair still inside the hair
        # was one this pass gave up on, so `stuck` IS the residual and costs
        # no extra pass. Only when the four rounds run out does it have to be
        # measured, which is the rare case.
        if moved:
            stuck = []
            for i, j in pairs:
                d, _f = _nearest_on_ring(arr[i], arr[j])
                if float(d.min()) < gap:
                    stuck.append((i, j, float(d.min())))
        report.extend(stuck)
    return [[(float(x), float(y)) for x, y in a] for a in arr]


def _worst_residual(loops, stuck):
    """How close the closest pair `_pull_apart` could NOT open really comes,
    measured BOTH ways on the rounded coordinates `sketch.py` is handed.
    `None` when it opened them all.

    The guard gives way rather than turn a loop inside out, and when it does
    it used to say nothing at all. A sliver squeezed between two bigger loops
    is a fixed point for it: measured 2026-09-17 (round five), 2 of 960 ring
    traces end still inside the hair by the guard's own test, the worst at
    0.000259 mm, and running the pass eight more times does not improve them.
    They build healthy today — and 0.000259 mm is exactly the pre-condition
    that produced the pinch of round one. Reading it back off the FINAL
    coordinates is the honest number: whatever the push measured, this is
    what the sketch carries."""
    if not stuck:
        return None
    rings: dict = {}
    worst = None
    for i, j, _d in stuck:
        for k in (i, j):
            if k not in rings:
                p = _round_pts(loops[k])
                rings[k] = np.asarray(p, float) if len(p) >= 3 else None
        a, b = rings[i], rings[j]
        if a is None or b is None:
            continue
        d1, _f = _nearest_on_ring(a, b)
        d2, _f = _nearest_on_ring(b, a)
        g = min(float(d1.min()), float(d2.min()))
        worst = g if worst is None else min(worst, g)
    return worst


def _walks_through_itself(pts, block, delta) -> bool:
    """True when nudging the run `block` of `pts` by `delta` would make the
    loop meet its OWN outline — the half of the room test `_hair_cluster`
    cannot ask.

    `_hair_cluster` walks the loop's INDEX order: it proves the two edges
    joined to the moved run are four times the move, so the run cannot be
    turned inside out locally. A part of the same outline that lies a few
    microns away with half the loop in between is invisible to it, and a
    ribbon folded back on itself is exactly that — its two runs are
    non-adjacent edges. Measured 2026-09-17 (round six,
    probes/imgtrace_r6_self.py): a ribbon 0.005 mm thick with a bigger loop
    0.0045 mm under it had its bottom edge pushed 0.0055 mm UP, straight
    through its own far wall, and the 2 mm extrusion went from healthy to
    "OpenCASCADE reports the solid is invalid". `_uncross` proves every loop
    simple BEFORE the push; nothing re-asked after it.

    Only the edges the move CHANGES can make a new crossing, so the test is
    those edges against the rest of the outline — the same maths and the same
    tolerance as `_first_crossing`, at O(n) a move instead of O(n**2) a loop.
    A push that would do this is not made: a pair left a hair apart beats a
    polygon that crosses itself."""
    m = len(pts)
    edges = sorted({(b - 1) % m for b in block} | {b % m for b in block})
    cand = pts.copy()
    cand[block] += delta
    # only a crossing the MOVE makes counts. An outline can arrive here
    # already touching itself — `_split_at_feet` rounds its inserted point
    # onto the 0.001 mm grid, which is up to 0.0007 mm off the edge it split
    # — and refusing then would block a push that is needed and fixes
    # nothing.
    return _edges_hit(cand, edges) and not _edges_hit(pts, edges)


def _edges_hit(pts, edges) -> bool:
    """True when one of the edges `edges` of the closed polyline `pts` crosses
    or touches a NON-adjacent edge of it — `_first_crossing`'s maths and
    `_first_crossing`'s tolerance, asked about a few edges instead of all."""
    m = len(pts)
    r = np.roll(pts, -1, axis=0) - pts
    idx = np.arange(m)
    tol = 1e-9
    for i in edges:
        adj = (np.abs(idx - i) <= 1) | (np.abs(idx - i) >= m - 1)
        den = r[i, 0] * r[:, 1] - r[i, 1] * r[:, 0]
        safe = np.where(np.abs(den) > 1e-15, den, 1.0)
        d = pts - pts[i]
        t = (d[:, 0] * r[:, 1] - d[:, 1] * r[:, 0]) / safe
        u = (d[:, 0] * r[i, 1] - d[:, 1] * r[i, 0]) / safe
        if ((np.abs(den) > 1e-15) & ~adj & (t >= -tol) & (t <= 1.0 + tol)
                & (u >= -tol) & (u <= 1.0 + tol)).any():
            return True
    return False


def _split_at_feet(pts, ring, gap):
    """`pts` with a vertex inserted wherever a vertex of `ring` comes within
    `gap` of it — at the point OF `pts` nearest that vertex, which lies on
    the edge it splits, so not one shape changes. It only gives the push
    something to move.

    The push walks the pairs (small, big) and asks `_nearest_on_ring(small,
    big)`: how far is every VERTEX of the smaller loop from the bigger loop's
    outline. That is half the question. The closest approach of two polylines
    sits on a vertex of ONE OR OF THE OTHER, and a vertex of the bigger loop
    landing on the MIDDLE of a long edge of the smaller one is invisible to
    it: measured 2026-09-17 (round five), a 20 mm bar under a plate with a
    needle whose tip touches the middle of its top edge reads 4.000 mm of
    clearance where the truth is 0.000 mm, and as two holes of one sketch it
    builds 3516.800 mm3 that `is_valid` calls True and `inspector.health`
    calls an open shell — the same banned failure round four fixed through
    the other door. Round four measured 49 of 50 residual pairs within
    0.002 mm to be invisible this way and left the direction open.

    Splitting rather than pushing the edge's ENDS: an endpoint of a long edge
    is metres from the contact, so moving it would swing the whole edge for a
    contact at one point of it. The inserted vertex is exactly on the edge,
    and the existing push then opens the hair at the place that is actually
    close."""
    d, foot = _nearest_on_ring(ring, pts)
    near = np.flatnonzero(d < gap)
    if not len(near):
        return pts
    ab = np.roll(pts, -1, axis=0) - pts
    den = (ab * ab).sum(axis=1)
    safe = np.where(den > 1e-18, den, 1.0)
    add: dict = {}
    for v in near:
        f = foot[v]
        t = np.clip(((f - pts) * ab).sum(axis=1) / safe, 0.0, 1.0)
        proj = pts + t[:, None] * ab
        k = int(np.hypot(proj[:, 0] - f[0], proj[:, 1] - f[1]).argmin())
        run = float(np.sqrt(den[k]))
        if min(float(t[k]), 1.0 - float(t[k])) * run <= 1e-9:
            continue              # the foot IS an end of the edge — already
        add.setdefault(k, []).append((float(t[k]),               # measured
                                      np.round(proj[k], 3)))
    if not add:
        return pts
    out = []
    for k in range(len(pts)):
        out.append(pts[k])
        out += [p for _t, p in sorted(add.get(k, []), key=lambda z: z[0])]
    return np.array(out, dtype=float)


def _hair_cluster(pts, v, span):
    """`v` plus every neighbour reachable from it along edges SHORTER than
    `span` — the run of points that is one point at that scale, and so the
    smallest piece of the outline that can be nudged rigidly without changing
    any shape the picture carries.

    `None` when the run is the whole loop: a ring with no edge long enough to
    absorb the push is a sliver, and the caller leaves it as traced rather
    than turn it inside out."""
    m = len(pts)
    # the edge lengths once, as plain floats: this walks per VERTEX inside the
    # hair, and a two-element numpy call per STEP was four fifths of the
    # guard's time on the pathological art once the push's grid snap made the
    # span — and so the walk — longer (probes/imgtrace_r6_cost.py, round six)
    e = np.hypot(*(np.roll(pts, -1, axis=0) - pts).T).tolist()
    lo = hi = int(v)
    for _ in range(m):
        prev = (lo - 1) % m
        if e[prev] >= span:
            break
        lo = prev
    else:
        return None
    for _ in range(m):
        if e[hi] >= span:
            break
        hi = (hi + 1) % m
    else:
        return None
    n = (hi - lo) % m + 1
    if n >= m:
        return None
    return [(lo + k) % m for k in range(n)]


def _nearest_on_ring(pts, ring, chunk=128):
    """For every point of `pts`, its distance to the closed polyline `ring`
    and the point ON that ring it is nearest — the honest "how close do these
    two outlines come", where vertex-to-vertex alone misses a vertex sitting
    on the middle of an edge. Chunked so a 3000-point trace cannot build a
    3000 x 3000 x 2 array."""
    a = ring
    ab = np.roll(ring, -1, axis=0) - a
    den = (ab * ab).sum(axis=1)
    safe = np.where(den > 1e-18, den, 1.0)
    dist = np.empty(len(pts))
    foot = np.empty((len(pts), 2))
    for s in range(0, len(pts), chunk):
        p = pts[s:s + chunk]
        t = ((p[:, None, :] - a[None]) * ab[None]).sum(axis=2) / safe
        t = np.clip(np.where(den > 1e-18, t, 0.0), 0.0, 1.0)
        proj = a[None] + t[:, :, None] * ab[None]
        d = np.hypot(proj[:, :, 0] - p[:, None, 0],
                     proj[:, :, 1] - p[:, None, 1])
        k = d.argmin(axis=1)
        rows = np.arange(len(p))
        dist[s:s + chunk] = d[rows, k]
        foot[s:s + chunk] = proj[rows, k]
    return dist, foot


def _poly_entity(pts, mode="add"):
    """CCW-normalised, bbox-centred polygon entity (see sketch.py polygon)."""
    n = len(pts)
    signed2 = sum(pts[i][0] * pts[(i + 1) % n][1]
                  - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if signed2 < 0:
        pts = list(reversed(pts))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    # the centre is put ON the same 0.001 grid the points are: centring by a
    # half-sum that is not on the grid re-rounds every point onto a shifted
    # one, which merged two distinct points into a pinch and put a crossing
    # back into an outline _uncross had just cleaned (measured 2026-09-17)
    cx = round((min(xs) + max(xs)) / 2.0, 3)
    cy = round((min(ys) + max(ys)) / 2.0, 3)
    return {"kind": "polygon", "mode": mode,
            "x": round(cx, 3), "y": round(cy, 3),
            "points": [[round(x - cx, 3), round(y - cy, 3)] for x, y in pts]}


_K3 = np.ones((3, 3), np.uint8)


def _inner(valid):
    """`valid` minus its outermost layer (outside the picture counts as out)"""
    return cv2.erode(valid, _K3, borderType=cv2.BORDER_CONSTANT, borderValue=0)


def _ring_mean(m, valid) -> float:
    """mean of `m` over the outermost layer of the region `valid`"""
    edge = valid - _inner(valid)
    n = int(edge.sum())
    return float((m * edge).sum()) / n if n else 0.5


def _edge_shell(m, side, valid):
    """the pieces of `side` that reach the outer layer of `valid`, or None"""
    sel = ((m == side) & valid.astype(bool)).astype(np.uint8)
    n, labels = cv2.connectedComponents(sel, 8)
    if n < 2:
        return None
    ids = [int(i)
           for i in np.unique(labels[(valid - _inner(valid)).astype(bool)])
           if i]
    return np.isin(labels, ids).astype(np.uint8) if ids else None


def _border_bright(m) -> float:
    """How much of the picture's border is BRIGHT — read PAST a thin shell of
    INK at the edge.

    Round one read the outermost ONE pixel. A scan's dark platen edge, a
    printed rule box, even the 1 px frame an exporter leaves behind all fill
    that pixel, so the paper was called the artwork and the tracer produced
    its NEGATIVE: five letters inside a 12 px dark edge came back as ONE
    contour with five letter-shaped holes, 1435.4 mm2, status ok and nothing
    said (measured 2026-09-17, REVIEW-QUEUE section 9 round two) — the same
    P0 round one had just fixed, through the other door.

    Only a DARK shell is read past. Round two read past a thin shell of
    EITHER side, and a thin LIGHT shell is not an artefact — it is the margin
    every exported logo has. Strip it and the art's own outer boundary is all
    ink, so the rule says "the ground is dark" and returns the negative: a
    2400 px plate silhouette with nine bolt holes and a 50 px pad traced
    440.1 mm2 of a true 1258.0, as ten pieces with one hole, valid and green
    (measured 2026-09-17, round three). A bright border needs no reading past
    — it already says what it means.

    A dark shell counts as a frame when it is THIN (under 5% of the picture,
    by distance transform) and there are 64 px of both sides left inside it.
    A genuinely dark ground is fat — a white disc filling all but 10 px of
    its picture still leaves a 93 px thick corner — so inverse-video art is
    untouched. The floor inside used to be 1% of the picture as well, which
    left round two's own P0 open for small art: an 800 px sheet with a 12 px
    platen edge and a logo at 0.5% of it traced 1587.8 mm2 of a true 102.1,
    the paper as a slab with a logo-shaped hole (measured, round three)."""
    valid = np.ones(m.shape, np.uint8)
    ring = _ring_mean(m, valid)
    if ring > 0.4:                             # a light border is a MARGIN
        return ring
    shell = _edge_shell(m, 0, valid)
    if shell is None:
        return ring
    if float(cv2.distanceTransform(shell, cv2.DIST_L2, 3).max()) > \
            0.05 * min(m.shape):
        return ring                            # a real ground, not a frame
    rest = (1 - shell).astype(np.uint8)
    inside = m[rest.astype(bool)]
    lit = int(inside.sum())
    if min(lit, int(inside.size) - lit) < 64:
        return ring                            # nothing inside it to read
    return _ring_mean(m, rest)


def _mask_from_image(img) -> np.ndarray:
    """Foreground mask: real alpha channel wins; otherwise Otsu on luminance
    with the BACKGROUND taken to be whichever side fills the picture's outer
    border.

    It used to be "the artwork is the MINORITY of pixels", which is only true
    while the art has room around it. Crop a logo to its own ink — what an
    image editor's Trim does, and what designs/cam-cover-plaque.py and
    designs/autonomiq-panel-profile.py do with `img.crop(...getbbox())` — and
    the ink is the majority: a 40 mm disc cropped to its bounding box traced
    its four CORNERS, 343.5 mm2 of a true 1256.6, status ok and nothing said
    (measured 2026-09-17, REVIEW-QUEUE section 9). Inverse-video art (white
    on black) failed the same way.

    A border split down the middle says nothing, so there the old minority
    rule still decides. Art that runs off all four edges of its own picture
    with a hollow middle — a picture-frame shape cropped to zero margin — is
    genuinely ambiguous either way, and this rule reads it as the middle.

    `_border_bright` reads that border PAST a thin shell of INK, because a
    scan's platen edge or a printed rule box fills it without being the
    ground. A thin shell of PAPER is left alone: that is a margin.

    An alpha channel only wins when it really CUTS the picture in two. The
    test used to be `min(alpha) < 250` alone, and one flat opacity passes it:
    a picture saved at 95% has alpha 242 everywhere, every pixel then reads
    "foreground", and the tracer drew the picture's own frame and threw the
    art away — a 90 px disc traced as a 26.60 x 19.93 mm rectangle where the
    logo is 19.86 mm across, one piece, status ok, nothing said. Read from
    the other end, 15% opacity put every pixel under the 128 cut and the
    trace refused "no artwork found in the image" for a picture that plainly
    has a logo in it (measured 2026-09-17, round seven). A channel with
    nothing on one side of the cut carries no silhouette; the luminance does.
    """
    if img is None:
        raise ValueError("could not decode the image — is it a PNG/JPG?")
    if img.ndim == 3 and img.shape[2] == 4 and int(img[:, :, 3].min()) < 250:
        cut = (img[:, :, 3] > 128).astype(np.uint8)
        if 0 < int(cut.sum()) < cut.size:
            return cut
    gray = (cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
            if img.ndim == 3 else img)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright_edge = _border_bright(m)
    if bright_edge > 0.6:                   # light border -> the art is dark
        m = 1 - m
    elif bright_edge >= 0.4:                # border split: the old rule
        if int(m.sum()) > m.size // 2:
            m = 1 - m
    return m.astype(np.uint8)


def _traceable(mask: np.ndarray, height_mm: float):
    """The mask with true SPECKLES dropped — the one step between "what is
    dark" and "what gets traced" — plus the pixel area floor that step used.

    The floor is a physical ~0.25 mm at the final scale, not a fraction of
    the biggest piece (that used to silently eat dots and thin ornaments).
    Shared so that `artwork_aspect` measures the artwork `image_to_entities`
    will actually trace, which its docstring has always claimed."""
    n_comp, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n_comp < 2:
        raise ValueError("no artwork found in the image")
    comp_areas = stats[1:, 4]
    if int(comp_areas.max()) < 64:
        raise ValueError("artwork too small to trace")
    # The floor is physical, so it needs the scale, and the scale is
    # height_mm / the artwork's own pixel height. That height must NOT be
    # measured on the raw mask: one 2x2 speck in a corner stretched it, and
    # the floor with it, dropping the dot of an i at 1.66 mm and REFUSING
    # five pieces 9.7 mm across (measured 2026-09-17, section 9 round two).
    # So start from the pieces above the absolute 9 px floor and shrink to a
    # fixed point — each round can only drop pieces, so it terminates.
    keep = [i + 1 for i, a in enumerate(comp_areas) if a >= 9]
    min_area = 9.0
    for _ in range(8):
        ys, _xs = np.where(np.isin(labels, keep))
        h_all = int(ys.max()) - int(ys.min()) + 1
        min_area = max(9.0, (0.25 * h_all / float(height_mm)) ** 2)
        smaller = [i for i in keep if comp_areas[i - 1] >= min_area]
        if not smaller:
            raise ValueError(
                f"every piece of this artwork would be under 0.25 mm at "
                f"{float(height_mm):g} mm tall — trace it bigger and scale "
                f"the sketch down")
        if smaller == keep:
            break
        keep = smaller
    return np.isin(labels, keep).astype(np.uint8), min_area


def _traced_mask(data: bytes, height_mm: float, min_channel_mm: float = 0.0,
                 connect_pieces: bool = False):
    """The mask the contours are taken from — decode, polarity, speckle floor,
    optional BRIDGES and optional CHANNEL ABSORB. -> (solid, min_area, mm_px,
    welded).

    Shared so `artwork_aspect` and `image_to_entities` cannot ask different
    questions. Round five made them share `_traceable`, after a 620 px
    hairline read aspect 2.15 for art really drawn at 0.50 — and left the two
    passes BELOW it unshared. Both only ADD material, and adding material
    changes which contours clear the area gate: measured 2026-09-17 (round
    six, probes/imgtrace_r6_gates.py) a disc beside five loose 1 px hairlines
    read aspect 1.0000 for art `connect_pieces` really draws at 2.1144, and
    on a 20 x 60 mm face the fit laid it down at 18.00 x 8.50 mm — 153 mm2
    where standing it up gives 684.

    `min_channel_mm` is the one knob with no bound on it, and the browser
    never sends it — only the HTTP door and a script do. Unbounded it fails
    both ways at once (measured 2026-09-17, round seven,
    probes/imgtrace_r7_channel.py): the open erases the space AROUND the art
    as readily as the recesses IN it, so a 30 mm channel on artwork 19.9 mm
    across traced the picture's own 24.98 x 19.98 mm rectangle, one piece, no
    holes, status ok and nothing said; and the cost is k**2 a pixel, so the
    same knob at 60 mm on a 1500 x 1200 picture took 119.56 SECONDS for one
    trace. So a channel that cannot be a recess in this artwork is refused
    before the morphology runs, and a fill that spilled past the artwork's
    own boundary is refused after it."""
    try:
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    except cv2.error:
        # an empty or unreadable buffer makes OpenCV ASSERT, and its assertion
        # is not a ValueError: a zero-byte file dragged into Trace Image put
        # "OpenCV(5.0.0) ... (-215:Assertion failed) !buf.empty()" straight
        # into the user's chat (measured 2026-09-17, round seven). The
        # browser's own reader hands a 0-byte .png through as
        # "data:image/png;base64," with nothing after the comma.
        img = None
    solid, min_area = _traceable(_mask_from_image(img), height_mm)
    ys, xs = np.where(solid)
    mm_px = float(height_mm) / (int(ys.max()) - int(ys.min()) + 1)
    welded = None
    if connect_pieces:
        solid, welded = _bridge_pieces(solid, max(3, int(0.6 / mm_px)))
    if min_channel_mm and min_channel_mm > 0:
        box = _art_box(solid)
        wide = min(box[1] - box[0] + 1, box[3] - box[2] + 1) * mm_px
        if float(min_channel_mm) >= wide:
            raise ValueError(
                f"a {float(min_channel_mm):g} mm channel is as wide as this "
                f"artwork, which measures {wide:.1f} mm across at "
                f"{float(height_mm):g} mm tall — filling it would leave a "
                f"plain rectangle. Set the channel to your end-mill diameter")
        k = int(min_channel_mm / mm_px) | 1
        field = 1 - solid
        field = cv2.morphologyEx(
            field, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        solid = (1 - field).astype(np.uint8)
        grew = _art_box(solid)
        if (grew[0] < box[0] - 2 or grew[1] > box[1] + 2
                or grew[2] < box[2] - 2 or grew[3] > box[3] + 2):
            raise ValueError(
                f"filling channels narrower than {float(min_channel_mm):g} mm "
                f"swallowed the space AROUND this artwork, not just the "
                f"recesses in it — the trace would come back as a plain "
                f"rectangle. Use a smaller channel, or trace it bigger")
    return solid, min_area, mm_px, welded


def _art_box(solid):
    """(y0, y1, x0, x1) of the set pixels — the artwork's own bounding box"""
    ys, xs = np.where(solid)
    if not len(ys):
        raise ValueError("no artwork found in the image")
    return int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())


def artwork_aspect(data: bytes, height_mm: float = 50.0,
                   min_channel_mm: float = 0.0,
                   connect_pieces: bool = False) -> float:
    """width/height of the image's traceable artwork bbox — from the SAME mask
    (same polarity rules, same speckle floor) image_to_entities traces, so a
    fit computed from it matches what the trace will actually produce. Needed
    to pick the trace height BEFORE tracing when fitting art onto a face.

    It read the RAW mask until 2026-09-17, and this number picks both the fit
    height and the 90-degree auto-rotate: two 3-pixel specks in the corners of
    a 1200px picture — specks image_to_entities then threw away, tracing
    identical art — moved it from 0.20 to 1.00, and the logo landed on a
    120x40 face at 7.2 x 36.0 mm standing up instead of 107.9 x 21.6 mm lying
    along it (REVIEW-QUEUE section 9).

    The speckle floor is not the last gate either, and reading the mask alone
    left this promise half kept. `image_to_entities` drops a CONTOUR whose
    outline encloses less than `min_area`, which is a different question from
    the pixel count: a 1 px hairline is hundreds of pixels and encloses
    nothing, so it survives the mask and is never drawn. Measured 2026-09-17
    (probes/imgtrace_r5_aspect_gate.py): a tall bar with a loose 620 px
    hairline beside it read aspect 2.15 for art really drawn at 0.50, and on
    a 20 x 60 mm face the fit ROTATED that art and laid it down at
    17.95 x 8.96 mm instead of standing it up at 17.91 x 35.91 — a quarter of
    the area, over a hairline that is not in the sketch at all."""
    solid, min_area, _mm, _w = _traced_mask(data, height_mm, min_channel_mm,
                                            connect_pieces)
    cnts, _h = cv2.findContours(solid, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    keep = [c for c in cnts if cv2.contourArea(c) >= min_area]
    _x, _y, w, h = cv2.boundingRect(np.vstack(keep or list(cnts)))
    return w / h


def _bridge_pieces(solid: np.ndarray, thickness: int, rounds: int = 16):
    """Connect disjoint art pieces (highlight-streak splits) by drawing a
    thick line between the globally closest pair until one piece remains.
    -> (mask, welded)

    `welded` is False when the rounds ran out with the art still in pieces.
    It used to return quietly, so a caller that asked for ONE piece was handed
    seventeen and told nothing (LAUNCH-PLAN section 10)."""
    for _ in range(rounds):
        pieces, _h = cv2.findContours(solid, cv2.RETR_EXTERNAL,
                                      cv2.CHAIN_APPROX_NONE)
        if len(pieces) <= 1:
            return solid, True
        best = None
        for a in range(len(pieces)):
            for b in range(a + 1, len(pieces)):
                pa = pieces[a].reshape(-1, 2)[::5]
                pb = pieces[b].reshape(-1, 2)[::5]
                d = ((pa[:, None, :] - pb[None, :, :]) ** 2).sum(axis=2)
                i, j = np.unravel_index(d.argmin(), d.shape)
                if best is None or d[i, j] < best[0]:
                    best = (d[i, j], tuple(int(v) for v in pa[i]),
                            tuple(int(v) for v in pb[j]))
        cv2.line(solid, best[1], best[2], 1, thickness)
    left, _h = cv2.findContours(solid, cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_NONE)
    return solid, len(left) <= 1


def _chaikin(pts: np.ndarray, cut_px: float) -> np.ndarray:
    """Corner-cut smoothing with an ABSOLUTE cut length: softens pixel
    facets without butchering long straight edges (a plain 0.25/0.75
    Chaikin turns a simplified square into an octagon)."""
    out, n = [], len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        edge = q - p
        t = min(0.25, cut_px / max(float(np.hypot(*edge)), 1e-9))
        out.append(p + t * edge)
        out.append(q - t * edge)
    return np.array(out)


def image_to_entities(data: bytes, height_mm: float = 50.0,
                      tol_mm: float = 0.15, min_channel_mm: float = 0.0,
                      connect_pieces: bool = False):
    """bytes of a PNG/JPG -> (sketch polygon entities, info dict).

    height_mm       : traced artwork is scaled to this overall height.
    tol_mm          : simplification fidelity (smaller = more points).
                      Internally CAPPED at ~3 source pixels: tracing a
                      high-res image to a small target must not bulldoze
                      its detail (the user can rescale the sketch later).
    min_channel_mm  : pre-fill background recesses narrower than this
                      (set to the end-mill diameter + margin; 0 = off).
    connect_pieces  : weld disjoint pieces with straight bridges (for
                      single-piece pendants). Default OFF — detailed art
                      is legitimately many separate pieces, and a sketch
                      handles that fine.
    """
    if not (1.0 <= float(height_mm) <= 1000.0):
        raise ValueError("height_mm must be between 1 and 1000")
    # drop only true speckles, KEEPING small ornaments and interior holes;
    # then the bridges and the channel absorb. All of it shared with
    # `artwork_aspect`, so the fit measures the artwork the trace draws.
    solid, min_area, mm_px, welded = _traced_mask(data, height_mm,
                                                  min_channel_mm,
                                                  connect_pieces)

    # final geometry: outer rings + their holes. Fidelity knobs are in SOURCE
    # PIXELS with hard caps — the sketch must look like the artwork at any
    # target size (resize later with the sketch Scale tool if needed).
    cnts, hier = cv2.findContours(solid, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    hier = hier[0] if hier is not None else []
    order = sorted(range(len(cnts)),
                   key=lambda i: cv2.contourArea(cnts[i]), reverse=True)
    # The box the art is scaled and centred on holds only what will BE drawn.
    # `_traceable` drops components by PIXEL COUNT and the loop below drops
    # contours by the area they ENCLOSE, which are different questions: a 1 px
    # hairline is hundreds of pixels and encloses nothing, so it passed the
    # first gate, failed the second, and still stretched the box every
    # surviving piece was measured against. Measured 2026-09-17: a 40 mm
    # square beside a loose 140 px hairline reported width_mm 56.00 for
    # 39.90 mm of drawn art and put that art 8.05 mm off the sketch origin
    # (probes/imgtrace_bbox_gate_probe.py).
    keep = [i for i in order if cv2.contourArea(cnts[i]) >= min_area]
    x, y, w, h = cv2.boundingRect(np.vstack([cnts[i] for i in keep or order]))
    mm_px = float(height_mm) / h
    cx_px, cy_px = x + w / 2.0, y + h / 2.0
    eps = max(1.0, min(3.0, tol_mm / mm_px))
    cut_px = max(0.8, min(2.0, 0.4 / mm_px))

    def to_mm(cnt):
        ap = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2).astype(float)
        if len(ap) < 3:
            return []
        ap = _chaikin(ap, cut_px=cut_px)
        pts = [((px - cx_px) * mm_px, (cy_px - py) * mm_px) for px, py in ap]
        # _uncross AFTER the scale to mm: sketch.py must never be handed a
        # polygon that crosses itself (REVIEW-QUEUE section 9). One contour
        # can come back as SEVERAL loops — a pinched piece is several pieces.
        loops = [p for p in _uncross(_round_pts(pts)) if len(p) >= 3]
        if not loops:
            return []
        # the biggest loop is the piece; the rest have to be worth drawing,
        # or sketch.py refuses the whole sketch ("encloses no area") over a
        # sliver (measured 2026-09-17 round two)
        loops.sort(key=lambda p: abs(_area2(p)), reverse=True)
        floor = 2.0 * min_area * mm_px * mm_px
        return loops[:1] + [p for p in loops[1:] if abs(_area2(p)) >= floor]

    drawn = []
    for i in keep:
        outer = hier[i][3] < 0            # no parent -> outer ring
        drawn += [(outer, pts) for pts in to_mm(cnts[i])]
    # …and the sketch is centred on what was drawn, for the same reason: the
    # contour gate is not the last word, `_uncross` and the sliver floor also
    # drop loops, and a dropped loop used to pull the whole sketch off the
    # origin by up to 12.90 mm of a 40 mm piece. A translation only — the
    # fidelity knobs ran at `mm_px` and must not be re-scaled under them.
    if drawn:
        ax = [p[0] for _o, pts in drawn for p in pts]
        ay = [p[1] for _o, pts in drawn for p in pts]
        # ON the 0.001 mm grid, for the reason `_poly_entity` spells out: the
        # points are on that grid when `_uncross` proves them simple, and a
        # half-sum is on the HALF grid whenever max + min is an odd multiple
        # of 0.001. Shifting by it and rounding again re-rounds every point
        # onto a shifted grid, and two points 0.001 mm apart can land on the
        # same one — which puts a crossing back into an outline `_uncross`
        # had just cleaned. Measured 2026-09-17, round six
        # (probes/imgtrace_r6_stage.py): a 1600 px disc with eleven 1 px
        # spokes traced 8 mm tall (0.005 mm/px) centred by dx = -0.0025 and
        # handed sketch.py TWO self-crossing hole loops, building 20.023 mm3
        # that OpenCASCADE calls INVALID, with the feature green. Rounding
        # the shift moves the art by at most half a micron and leaves every
        # unmoved point exactly where `_uncross` measured it.
        dx = round((max(ax) + min(ax)) / 2.0, 3)
        dy = round((max(ay) + min(ay)) / 2.0, 3)
        drawn = [(o, [(round(px - dx, 3), round(py - dy, 3))
                      for px, py in pts]) for o, pts in drawn]
    # no two loops of ONE sketch may meet: a pair that does pinches the face
    # into an open shell, valid and the right volume (REVIEW-QUEUE section 9)
    stuck: list = []
    apart = _pull_apart([pts for _outer, pts in drawn], report=stuck)
    ents, n_holes = [], 0
    for (outer, _raw), pts in zip(drawn, apart):
        pts = _round_pts(pts)
        if len(pts) < 3:
            continue
        if outer:
            ents.append(_poly_entity(pts, "add"))
        else:
            ents.append(_poly_entity(pts, "subtract"))
            n_holes += 1
    if not ents or ents[0]["mode"] != "add":
        raise ValueError("tracing produced no usable outline")

    # the size reported is the size of what was DRAWN, read back off the
    # entities themselves — a loop `_uncross` or the sliver floor dropped is
    # no more part of the artwork than a contour the min_area gate dropped
    xs = [e["x"] + p[0] for e in ents for p in e["points"]]
    ys = [e["y"] + p[1] for e in ents for p in e["points"]]
    info = {"width_mm": round(max(xs) - min(xs), 2),
            "height_mm": round(max(ys) - min(ys), 2),
            "contours": len(ents) - n_holes, "holes": n_holes,
            "points": sum(len(e["points"]) for e in ents)}
    # ...and when the guard could NOT open a pair, it says so instead of
    # handing the sketch over as if it had. A pair that still MEETS is the
    # banned failure — a pinched face that builds "successfully" as an open
    # shell — so that one is refused; a pair merely inside the hair builds
    # today and is reported, not refused.
    tight = _worst_residual(apart, stuck)
    if tight is not None and tight < _HAIR_MM:
        if tight <= 0.0:
            raise ValueError(
                "two parts of this artwork meet at a point and the tracer "
                "could not pull them apart — extruding it would make a "
                "pinched, unusable solid. Trace it taller, or open the gap "
                "in the picture where the two shapes touch")
        info["tight_mm"] = round(tight, 6)
        info["note"] = (
            f"two parts of this artwork pass {tight * 1000:.2f} microns "
            f"apart — thinner than the tracer can open. The sketch builds, "
            f"but trace it taller if the extrude ever refuses."
            + (" " + info["note"] if info.get("note") else ""))
    if welded is not None:
        # asked to weld the art into one piece, and it did not: say so rather
        # than hand back several pieces as if it had (LAUNCH-PLAN section 10)
        info["welded"] = bool(welded and info["contours"] == 1)
        if not info["welded"]:
            info["note"] = (info.get("note", "") and info["note"] + " ") + (
                f"the artwork is still {info['contours']} separate pieces — "
                f"16 bridges were not enough to join it. Extrude it as it is, "
                f"or close the gaps in the picture and trace it again.")
    return ents, info
