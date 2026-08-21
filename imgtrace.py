"""trace.py — raster image -> sketch polygon entities ("Trace PNG").

Turns a silhouette image (PNG with transparency, or dark-on-light art) into
the SAME polygon entities the sketcher already understands, so the result is
a normal `sketch` feature the user can Extrude / Revolve / Cut like anything
drawn by hand. No new geometry kinds, no new ops.

Pipeline (battle-proven on the rocky-keychain design series, 2026-08):
    decode -> binary mask (alpha channel if real, else Otsu on luminance,
    polarity chosen so the ART is the minority of pixels)
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


def _poly_entity(pts, mode="add"):
    """CCW-normalised, bbox-centred polygon entity (see sketch.py polygon)."""
    n = len(pts)
    signed2 = sum(pts[i][0] * pts[(i + 1) % n][1]
                  - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if signed2 < 0:
        pts = list(reversed(pts))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    return {"kind": "polygon", "mode": mode,
            "x": round(cx, 3), "y": round(cy, 3),
            "points": [[round(x - cx, 3), round(y - cy, 3)] for x, y in pts]}


def _mask_from_image(img) -> np.ndarray:
    """Foreground mask: real alpha channel wins; otherwise Otsu on luminance
    with polarity chosen so the artwork is the MINORITY of pixels."""
    if img is None:
        raise ValueError("could not decode the image — is it a PNG/JPG?")
    if img.ndim == 3 and img.shape[2] == 4 and int(img[:, :, 3].min()) < 250:
        return (img[:, :, 3] > 128).astype(np.uint8)
    gray = (cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
            if img.ndim == 3 else img)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if int(m.sum()) > m.size // 2:          # foreground must be the art
        m = 1 - m
    return m.astype(np.uint8)


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

    # drop only true speckles, KEEPING small ornaments and interior holes:
    # the floor is a physical ~0.25mm at the final scale, not a fraction of
    # the biggest piece (that used to silently eat dots and thin ornaments)
    n_comp, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n_comp < 2:
        raise ValueError("no artwork found in the image")
    comp_areas = stats[1:, 4]
    biggest = int(comp_areas.max())
    if biggest < 64:
        raise ValueError("artwork too small to trace")
    ys, xs = np.where(mask)
    h_all = int(ys.max()) - int(ys.min()) + 1
    mm_px = float(height_mm) / h_all
    min_area = max(9.0, (0.25 / mm_px) ** 2)
    keep = {i + 1 for i, a in enumerate(comp_areas) if a >= min_area}
    solid = np.isin(labels, list(keep)).astype(np.uint8)

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
            return None
        ap = _chaikin(ap, cut_px=cut_px)
        pts = [((px - cx_px) * mm_px, (cy_px - py) * mm_px) for px, py in ap]
        pts = _round_pts(pts)
        return pts if len(pts) >= 3 else None

    ents, n_holes = [], 0
    hier = hier[0] if hier is not None else []
    order = sorted(range(len(cnts)),
                   key=lambda i: cv2.contourArea(cnts[i]), reverse=True)
    for i in order:
        if cv2.contourArea(cnts[i]) < min_area:
            continue
        outer = hier[i][3] < 0            # no parent -> outer ring
        pts = to_mm(cnts[i])
        if pts is None:
            continue
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
