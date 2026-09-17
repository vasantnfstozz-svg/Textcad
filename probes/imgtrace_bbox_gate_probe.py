"""LAUNCH-PLAN s10 P3: the traced bounding box counts contours the `min_area`
gate then drops, so the art is scaled and centred on a box holding a piece
that was never drawn.

`_traceable` drops connected components by PIXEL COUNT; `image_to_entities`
then drops contours by `cv2.contourArea`, which is the area the OUTLINE
encloses. A 1 px hairline has a big pixel count and no enclosed area at all,
so it passes the first gate, fails the second — and is still in the box every
surviving piece is scaled and centred on.

Run:  C:\\Python314\\python.exe probes/imgtrace_bbox_gate_probe.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                             # noqa: E402


def png(m):
    img = np.zeros(m.shape + (4,), np.uint8)
    img[:, :, 3] = (m > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def square_and_hairline(tail=140, thick=1, detached=True):
    """A 400 x 400 px square and a separate `thick` px hairline to its right.

    The hairline is a big connected COMPONENT (a few hundred pixels), so
    `_traceable`'s pixel-count floor keeps it; its contour ENCLOSES nothing,
    so `cv2.contourArea` is ~0 and the entity loop drops it."""
    m = np.zeros((500, 700), np.uint8)
    cv2.rectangle(m, (40, 40), (439, 439), 1, -1)
    if tail:
        x0 = 440 + (20 if detached else 0)
        m[239:239 + thick, x0:x0 + tail] = 1
    return m


def drawn_extent(ents):
    xs = [e["x"] + p[0] for e in ents for p in e["points"]]
    ys = [e["y"] + p[1] for e in ents for p in e["points"]]
    return max(xs) - min(xs), max(ys) - min(ys), \
        (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2


def main():
    print(f"{'picture':34s} {'info w x h':>18s} {'DRAWN w x h':>18s} "
          f"{'drawn centre':>18s}")
    for tail, thick, det in ((0, 1, True), (140, 1, True), (200, 1, True),
                             (140, 2, True), (260, 1, False)):
        m = square_and_hairline(tail, thick, det)
        ents, info = imgtrace.image_to_entities(png(m), height_mm=40.0)
        w, h, cx, cy = drawn_extent(ents)
        name = (f"square + {tail}x{thick} px "
                f"{'loose' if det else 'attached'} tail" if tail
                else "square alone")
        print(f"{name:34s} {info['width_mm']:8.2f} x{info['height_mm']:8.2f} "
              f"{w:8.2f} x{h:8.2f} {cx:8.2f} ,{cy:7.2f}   "
              f"({info['contours']} pieces, {info['points']} points)")


if __name__ == "__main__":
    main()
