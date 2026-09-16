"""probes/imgtrace_polarity_probe.py - REVIEW-QUEUE section 9 fix pass.

Scores the OLD polarity rule ("the art is the minority of pixels") against
the NEW one ("the background is what fills the picture's border") over a
corpus with a KNOWN answer: for each picture, the traced area is compared
with the ink the picture really carries.
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import imgtrace  # noqa: E402
import sketch as sk  # noqa: E402


def png(c):
    ok, b = cv2.imencode(".png", c)
    return b.tobytes()


def old_mask(img):
    """the rule as it stood before 2026-09-17"""
    if img.ndim == 3 and img.shape[2] == 4 and int(img[:, :, 3].min()) < 250:
        return (img[:, :, 3] > 128).astype(np.uint8)
    gray = (cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
            if img.ndim == 3 else img)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if int(m.sum()) > m.size // 2:
        m = 1 - m
    return m.astype(np.uint8)


def corpus():
    out = []

    def blank(dark=False):
        return (np.zeros((400, 400, 3), np.uint8) if dark
                else np.full((400, 400, 3), 255, np.uint8))

    ink = (0, 0, 0)
    lit = (255, 255, 255)

    img = blank(); cv2.circle(img, (200, 200), 110, ink, -1)
    out.append(("disc, roomy margin", img, "dark"))

    img = blank(); cv2.circle(img, (200, 200), 199, ink, -1)
    out.append(("disc, cropped to its ink", img, "dark"))

    img = blank(); cv2.rectangle(img, (0, 0), (399, 399), ink, -1)
    cv2.rectangle(img, (40, 40), (359, 359), lit, -1)
    out.append(("frame, zero margin (ambiguous)", img, "dark"))

    img = blank()
    cv2.putText(img, "AQ", (20, 300), cv2.FONT_HERSHEY_SIMPLEX, 9, ink, 30)
    out.append(("bold text on white", img, "dark"))

    img = blank(dark=True); cv2.circle(img, (200, 200), 110, lit, -1)
    out.append(("inverse video, roomy", img, "light"))

    img = blank(dark=True); cv2.circle(img, (200, 200), 199, lit, -1)
    out.append(("inverse video, cropped", img, "light"))

    img = blank(dark=True)
    cv2.putText(img, "AQ", (20, 300), cv2.FONT_HERSHEY_SIMPLEX, 9, lit, 30)
    out.append(("inverse video text", img, "light"))

    img = blank()
    cv2.rectangle(img, (30, 150), (370, 250), ink, -1)      # wide bar, 22%
    out.append(("wide bar on white", img, "dark"))

    img = blank()
    cv2.rectangle(img, (0, 120), (399, 280), ink, -1)       # bleeds L-R, 40%
    out.append(("bar bleeding off two sides", img, "dark"))

    img = blank()
    cv2.circle(img, (200, 200), 190, ink, -1)
    cv2.circle(img, (200, 200), 70, lit, -1)                # ring, 63% ink
    out.append(("thick ring, tight crop", img, "dark"))
    return out


def area_of(mask, mm_px):
    return float(mask.sum()) * mm_px * mm_px


def main():
    print(f"{'picture':34s} {'want':>9s} {'OLD':>9s} {'NEW':>9s}")
    old_ok = new_ok = 0
    for name, img, art_is in corpus():
        data = png(img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        truth = ((gray < 128) if art_is == "dark" else (gray > 128))
        truth = truth.astype(np.uint8)
        ys, xs = np.where(truth)
        mm_px = 40.0 / (int(ys.max()) - int(ys.min()) + 1)
        want = area_of(truth, mm_px)
        got = {}
        for label, fn in (("OLD", old_mask), ("NEW", imgtrace._mask_from_image)):
            saved = imgtrace._mask_from_image
            imgtrace._mask_from_image = fn
            try:
                ents, _ = imgtrace.image_to_entities(data, height_mm=40)
                got[label] = sk.make_sketch("XY", 0, ents).area
            except Exception as e:                    # noqa: BLE001
                got[label] = f"{type(e).__name__}"
            finally:
                imgtrace._mask_from_image = saved
        def mark(v):
            return ("OK " if isinstance(v, float) and abs(v - want) < 0.08 * want
                    else "BAD")
        old_ok += mark(got["OLD"]) == "OK "
        new_ok += mark(got["NEW"]) == "OK "
        f = lambda v: f"{v:9.1f}" if isinstance(v, float) else f"{v:>9s}"  # noqa: E731
        print(f"{name:34s} {want:9.1f} {f(got['OLD'])}{mark(got['OLD'])} "
              f"{f(got['NEW'])}{mark(got['NEW'])}")
    print(f"\nOLD rule right on {old_ok}/10, NEW rule right on {new_ok}/10")


if __name__ == "__main__":
    main()
