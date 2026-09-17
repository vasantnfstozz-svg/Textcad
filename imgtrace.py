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
    ground. A thin shell of PAPER is left alone: that is a margin."""
    if img is None:
        raise ValueError("could not decode the image — is it a PNG/JPG?")
    if img.ndim == 3 and img.shape[2] == 4 and int(img[:, :, 3].min()) < 250:
        return (img[:, :, 3] > 128).astype(np.uint8)
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


def artwork_aspect(data: bytes, height_mm: float = 50.0) -> float:
    """width/height of the image's traceable artwork bbox — from the SAME mask
    (same polarity rules, same speckle floor) image_to_entities traces, so a
    fit computed from it matches what the trace will actually produce. Needed
    to pick the trace height BEFORE tracing when fitting art onto a face.

    It read the RAW mask until 2026-09-17, and this number picks both the fit
    height and the 90-degree auto-rotate: two 3-pixel specks in the corners of
    a 1200px picture — specks image_to_entities then threw away, tracing
    identical art — moved it from 0.20 to 1.00, and the logo landed on a
    120x40 face at 7.2 x 36.0 mm standing up instead of 107.9 x 21.6 mm lying
    along it (REVIEW-QUEUE section 9)."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    solid, _ = _traceable(_mask_from_image(img), height_mm)
    ys, xs = np.where(solid)
    w = int(xs.max()) - int(xs.min()) + 1
    h = int(ys.max()) - int(ys.min()) + 1
    return w / h


def _bridge_pieces(solid: np.ndarray, thickness: int) -> np.ndarray:
    """Connect disjoint art pieces (highlight-streak splits) by drawing a
    thick line between the globally closest pair until one piece remains."""
    for _ in range(16):
        pieces, _h = cv2.findContours(solid, cv2.RETR_EXTERNAL,
                                      cv2.CHAIN_APPROX_NONE)
        if len(pieces) <= 1:
            break
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
    return solid


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
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    mask = _mask_from_image(img)

    # drop only true speckles, KEEPING small ornaments and interior holes
    # (shared with artwork_aspect so the fit matches the trace)
    solid, min_area = _traceable(mask, height_mm)

    ys, xs = np.where(solid)
    x, y = int(xs.min()), int(ys.min())
    w, h = int(xs.max()) - x + 1, int(ys.max()) - y + 1
    mm_px = float(height_mm) / h
    if connect_pieces:
        solid = _bridge_pieces(solid, max(3, int(0.6 / mm_px)))

    if min_channel_mm and min_channel_mm > 0:
        k = int(min_channel_mm / mm_px) | 1
        field = 1 - solid
        field = cv2.morphologyEx(
            field, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        solid = (1 - field).astype(np.uint8)

    # final geometry: outer rings + their holes. Fidelity knobs are in SOURCE
    # PIXELS with hard caps — the sketch must look like the artwork at any
    # target size (resize later with the sketch Scale tool if needed).
    cnts, hier = cv2.findContours(solid, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    x, y, w, h = cv2.boundingRect(np.vstack([c for c in cnts]))
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

    ents, n_holes = [], 0
    hier = hier[0] if hier is not None else []
    order = sorted(range(len(cnts)),
                   key=lambda i: cv2.contourArea(cnts[i]), reverse=True)
    for i in order:
        if cv2.contourArea(cnts[i]) < min_area:
            continue
        outer = hier[i][3] < 0            # no parent -> outer ring
        for pts in to_mm(cnts[i]):
            if outer:
                ents.append(_poly_entity(pts, "add"))
            else:
                ents.append(_poly_entity(pts, "subtract"))
                n_holes += 1
    if not ents or ents[0]["mode"] != "add":
        raise ValueError("tracing produced no usable outline")

    info = {"width_mm": round(w * mm_px, 2), "height_mm": round(h * mm_px, 2),
            "contours": len(ents) - n_holes, "holes": n_holes,
            "points": sum(len(e["points"]) for e in ents)}
    return ents, info
