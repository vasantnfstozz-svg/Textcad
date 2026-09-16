"""REVIEW-QUEUE section 9 ROUND TWO — what the border rule DOES to a picture
with a dark edge, measured end to end (traced mm2 vs the true artwork mm2).

Round one's rule reads the picture's outermost ONE-PIXEL ring. A scan's dark
platen edge, a printed rule box, even a 1 px frame an exporter added, all fill
that ring — so the rule calls the paper the artwork and the tracer produces
the NEGATIVE of the art: the same P0 round one fixed, through the other door.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_frame.py
"""
from __future__ import annotations

import importlib.util
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import imgtrace                                                    # noqa: E402
import sketch as sk                                                # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "imgtrace_old", os.path.join(HERE, "_imgtrace_old.py"))
imgtrace_old = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(imgtrace_old)


def _png(img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _area(mod, data, h_mm):
    try:
        ents, info = mod.image_to_entities(data, height_mm=h_mm)
    except Exception as e:                                    # noqa: BLE001
        return None, f"refused: {e}"
    try:
        return sk.make_sketch("XY", 0, ents).area, (
            f"{info['contours']}c/{info['holes']}h/{info['points']}p")
    except Exception as e:                                    # noqa: BLE001
        return None, f"sketch failed: {e}"


def _ink_mm2(ink_px, img, h_mm):
    """true artwork area in mm2 at the trace's own scale"""
    ys, xs = np.where(ink_px)
    h_all = int(ys.max()) - int(ys.min()) + 1
    return float(ink_px.sum()) * (h_mm / h_all) ** 2


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def scan_dark_frame():
    im = np.full((400, 400, 3), 255, np.uint8)
    for i in range(5):
        cv2.rectangle(im, (60 + i * 60, 160), (95 + i * 60, 240), (0, 0, 0), -1)
    ink = (im[:, :, 0] == 0).astype(np.uint8)
    cv2.rectangle(im, (0, 0), (399, 399), (0, 0, 0), 12)
    return im, ink, "five letters on paper, 12 px dark scan edge"


@case
def one_pixel_frame():
    im = np.full((400, 400, 3), 255, np.uint8)
    for i in range(5):
        cv2.rectangle(im, (60 + i * 60, 160), (95 + i * 60, 240), (0, 0, 0), -1)
    ink = (im[:, :, 0] == 0).astype(np.uint8)
    cv2.rectangle(im, (0, 0), (399, 399), (0, 0, 0), 1)
    return im, ink, "the same art with a ONE-pixel frame"


@case
def printed_border():
    im = np.full((400, 400, 3), 255, np.uint8)
    cv2.circle(im, (200, 200), 110, (0, 0, 0), -1)
    ink = (im[:, :, 0] == 0).astype(np.uint8)
    cv2.rectangle(im, (2, 2), (397, 397), (0, 0, 0), 5)
    return im, ink, "a disc inside a 5 px printed rule box"


@case
def vignette():
    im = np.full((400, 400, 3), 255, np.uint8)
    cv2.circle(im, (200, 200), 100, (0, 0, 0), -1)
    ink = (im[:, :, 0] == 0).astype(np.uint8)
    yy, xx = np.mgrid[0:400, 0:400].astype(float)
    r = np.hypot(yy - 199.5, xx - 199.5) / 199.5
    fall = np.clip(1.0 - 1.15 * np.clip(r - 0.45, 0, None) ** 1.4, 0, 1)
    return (im.astype(float) * fall[:, :, None]).astype(np.uint8), ink, \
        "a disc on paper under a heavy photo vignette"


@case
def tight_crop_disc():
    im = np.full((400, 400, 3), 255, np.uint8)
    cv2.circle(im, (200, 200), 199, (0, 0, 0), -1)
    return im, (im[:, :, 0] == 0).astype(np.uint8), \
        "a disc trimmed to its ink (round one's P0)"


def main():
    print(f"{'case':22s} {'true mm2':>9s} {'OLD rule':>10s} "
          f"{'NEW rule':>10s}   note")
    print("-" * 96)
    for fn in CASES:
        im, ink, desc = fn()
        data = _png(im)
        want = _ink_mm2(ink, im, 40.0)
        ao, io = _area(imgtrace_old, data, 40.0)
        an, inn = _area(imgtrace, data, 40.0)
        print(f"{fn.__name__:22s} {want:9.1f} "
              f"{(f'{ao:10.1f}' if ao is not None else f'{io:>10s}')} "
              f"{(f'{an:10.1f}' if an is not None else f'{inn:>10s}')}"
              f"   {desc}")
        print(f"{'':22s} {'':>9s} {io:>10s} {inn:>10s}")
    print("-" * 96)


if __name__ == "__main__":
    main()
