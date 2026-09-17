"""REVIEW-QUEUE section 9 ROUND FIVE — the fit still measures a piece that
is never drawn.

Round four closed this inside `image_to_entities`: the box the art is scaled
and centred on now holds only the contours that pass the `min_area` gate, so
a loose 1 px hairline no longer stretches it (probes/imgtrace_bbox_gate_probe.py).

`artwork_aspect` was NOT changed, and that is the number the FIT door uses:
`studio._trace_fit_height` asks it for the artwork's width/height, and that
one number picks BOTH the trace height and the 90 degree auto-rotate. It
still measures `_traceable`'s mask — the PIXEL-COUNT gate — so the hairline
is still in it.

This probe prints, for one picture family, the aspect the fit is computed
from against the aspect of the art that is actually drawn, and then what the
fit door does with it on a real face.

Run:  C:/Python314/python.exe probes/imgtrace_r5_aspect_gate.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import studio                                               # noqa: E402


def png(m):
    img = np.zeros(m.shape + (4,), np.uint8)
    img[:, :, 3] = (m > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def square_and_hairline(tail=140, thick=1):
    m = np.zeros((500, 900), np.uint8)
    cv2.rectangle(m, (40, 40), (439, 439), 1, -1)
    if tail:
        m[239:239 + thick, 460:460 + tail] = 1
    return m


def tall_bar_and_hairline(tail=0, thick=1):
    """A TALL piece of art (aspect 0.5) with a loose 1 px horizontal hairline
    beside it — a scan streak, a stray rule, the tail of a signature."""
    m = np.zeros((520, 980), np.uint8)
    cv2.rectangle(m, (40, 60), (239, 459), 1, -1)
    if tail:
        m[259:259 + thick, 280:280 + tail] = 1
    return m


def drawn_extent(ents):
    xs = [e["x"] + p[0] for e in ents for p in e["points"]]
    ys = [e["y"] + p[1] for e in ents for p in e["points"]]
    return max(xs) - min(xs), max(ys) - min(ys)


class Req:
    def __init__(self, **kw):
        self.height_mm = 40.0
        self.tol_mm = 0.15
        self.min_channel_mm = 0.0
        self.connect_pieces = False
        self.fit_margin = 0.9
        for k, v in kw.items():
            setattr(self, k, v)


def row(name, data, fw, fh):
    asp = imgtrace.artwork_aspect(data, 40.0)
    ents, _i = imgtrace.image_to_entities(data, height_mm=40.0)
    w, h = drawn_extent(ents)
    height, rot = studio._trace_fit_height(data, 0.9 * fw, 0.9 * fh)
    _e2, i2 = studio._trace_fitted(data, Req(), (fw, fh, 0.0, 0.0))
    print(f"{name:32s} {asp:10.4f} {w / h:10.4f} "
          f"  h={height:6.2f} rot={str(rot):5s} "
          f"-> {i2['width_mm']:6.2f} x{i2['height_mm']:6.2f} mm "
          f"= {i2['width_mm'] * i2['height_mm']:8.1f} mm2")


def main():
    print(f"{'picture':32s} {'fit door':>10s} {'drawn':>10s}"
          f"   ---- on a 60 x 20 mm face ----")
    for tail in (0, 140, 260, 400):
        name = f"square + {tail} px hairline" if tail else "square alone"
        row(name, png(square_and_hairline(tail)), 60.0, 20.0)
    print(f"\n{'picture':32s} {'fit door':>10s} {'drawn':>10s}"
          f"   ---- on a 20 x 60 mm face ----")
    for tail in (0, 200, 400, 620):
        name = f"tall bar + {tail} px hairline" if tail else "tall bar alone"
        row(name, png(tall_bar_and_hairline(tail)), 20.0, 60.0)


if __name__ == "__main__":
    main()
