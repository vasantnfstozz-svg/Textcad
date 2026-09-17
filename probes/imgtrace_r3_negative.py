"""REVIEW-QUEUE section 9 round THREE — does round two's border rule still
hand the user the NEGATIVE of their artwork?  Measured, not read.

Two doors found by the round-three corpus:

  A. a THIN LIGHT PAD round rectangular art that has light regions INSIDE it
     (a plate with bolt holes, a rectangular ring, a box outline).  Round
     two reads past any thin shell — a light one too — and a light pad is
     not an artefact, it is the ordinary margin of an exported logo.  Once
     it is stripped, the art's own outer boundary is all ink, so the rule
     says "the ground is dark" and the tracer returns the negative.

  B. round two's OWN headline P0 (a scan's dark platen edge) with artwork
     under 1% of the sheet: its "is there anything inside to read" floor is
     `max(64, 1% of the picture)`, and a small logo does not clear the 1%.

Both are reported here as TRACED GEOMETRY: area in mm2 against the picture's
own ink, contour count and hole count.

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_negative.py
"""
from __future__ import annotations

import io
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import sketch as sk                                         # noqa: E402
import _imgtrace_old as OLD                                 # noqa: E402
import _imgtrace_r1 as R1                                   # noqa: E402
from imgtrace_r3_corpus import cand_mask                    # noqa: E402

MODS = [("old", OLD), ("r1", R1), ("r2", imgtrace)]


def png(img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return io.BytesIO(buf).getvalue()


def ink_mm2(img, h_mm):
    """what the DARK ink of the picture is worth once scaled to h_mm tall"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = (1 - m).astype(np.uint8)
    ys, _ = np.where(dark)
    mm_px = h_mm / (int(ys.max()) - int(ys.min()) + 1)
    return float(dark.sum()) * mm_px * mm_px


def trace(mod, data, h_mm, mask_fn=None):
    """(area, contours, holes) or ('refused', reason)"""
    try:
        if mask_fn is None:
            ents, info = mod.image_to_entities(data, height_mm=h_mm)
        else:
            old = mod._mask_from_image
            mod._mask_from_image = mask_fn
            try:
                ents, info = mod.image_to_entities(data, height_mm=h_mm)
            finally:
                mod._mask_from_image = old
        area = sk.make_sketch("XY", 0, ents).area
        return area, info["contours"], info["holes"]
    except Exception as exc:                                # noqa: BLE001
        return None, type(exc).__name__, str(exc)[:60]


def plate_with_holes(size, pad, n=3):
    """a rectangular part silhouette with round holes and a uniform pad"""
    im = np.full((size, size, 3), 255, np.uint8)
    cv2.rectangle(im, (pad, pad), (size - 1 - pad, size - 1 - pad),
                  (0, 0, 0), -1)
    r = size // 12
    step = (size - 2 * pad) // (n + 1)
    for i in range(n):
        for j in range(n):
            cv2.circle(im, (pad + (i + 1) * step, pad + (j + 1) * step),
                       r, (255, 255, 255), -1)
    return im


def scan_sheet(size, band, logo_frac):
    """paper with a dark platen edge and a logo of the given area fraction"""
    im = np.full((size, size, 3), 255, np.uint8)
    r = int(np.sqrt(logo_frac * size * size / np.pi))
    cv2.circle(im, (size // 2, size // 2), r, (0, 0, 0), -1)
    im[:band] = im[-band:] = 0
    im[:, :band] = im[:, -band:] = 0
    return im


def row(label, img, h_mm=40.0):
    data = png(img)
    want = ink_mm2(img, h_mm)
    out = []
    for name, mod in MODS:
        a, c, h = trace(mod, data, h_mm)
        out.append((name, a, c, h))
    a, c, h = trace(imgtrace, data, h_mm, mask_fn=cand_mask)
    out.append(("cand", a, c, h))
    print(f"{label:38s} ink {want:9.1f} mm2")
    for name, a, c, h in out:
        if a is None:
            print(f"    {name:5s} REFUSED {c}: {h}")
        else:
            tag = "  <-- NEGATIVE" if a > want * 1.5 else ""
            print(f"    {name:5s} {a:9.1f} mm2  {c} contours  {h} holes"
                  f"  ({a / want * 100:6.1f}% of the ink){tag}")


def main():
    print("A. a rectangular part silhouette with a UNIFORM LIGHT PAD")
    print("   (5% of the picture = the pad width at which r2's rule turns)")
    for size in (400, 1200, 2400):
        for pad in (4, 8, 20, 50, 100):
            if pad * 2 >= size // 2:
                continue
            thick = pad * np.sqrt(2.0)
            mark = "thin" if thick <= 0.05 * size else "fat "
            row(f"plate {size}px, {pad}px pad ({mark} to r2)",
                plate_with_holes(size, pad))
        print()

    print("\nB. round two's own P0 with SMALL artwork "
          "(its floor is max(64, 1% of the sheet))")
    for frac in (0.02, 0.01, 0.005, 0.002):
        row(f"scan sheet 800px, 12px edge, logo {frac * 100:.1f}% of it",
            scan_sheet(800, 12, frac))


if __name__ == "__main__":
    main()
