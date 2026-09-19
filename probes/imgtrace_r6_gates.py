"""ROUND SIX — are the fit's gate and the trace's gate really IDENTICAL?

Round five made `artwork_aspect` drop sub-`min_area` CONTOURS, matching the
trace, after a 620 px hairline read aspect 2.15 for art really drawn at 0.50.
The rule it wrote down is the one that matters: the two must be the same
question in every parameter, or the same bug comes back through the next
difference.

`image_to_entities` runs two more passes on the mask before it takes contours:

    if connect_pieces:  solid, welded = _bridge_pieces(solid, ...)
    if min_channel_mm:  solid = 1 - open(1 - solid, ellipse(k))

`artwork_aspect` runs neither, and `studio._trace_fit_height` calls it with
the height alone — never with `req.min_channel_mm` or `req.connect_pieces`.
Both passes can only ADD material, so the traced artwork can be WIDER or
TALLER than the aspect the fit was chosen from, and that number sets the
90-degree rotate as well as the height.

This probe measures the two aspects side by side on art built for each pass.

Run:  C:/Python314/python.exe probes/imgtrace_r6_gates.py
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
from imgtrace_r5_mirror import png                          # noqa: E402


def split_bar():
    """a TALL bar broken into pieces, with the pieces spread sideways: as
    traced it is tall and narrow, and `connect_pieces` bridges it into
    something wide"""
    m = np.zeros((600, 600), np.uint8)
    cv2.rectangle(m, (270, 40), (330, 560), 1, -1)     # the tall bar
    for x in (60, 120, 480, 540):                      # the outriggers
        cv2.rectangle(m, (x, 280), (x + 40, 320), 1, -1)
    return m


def combed_pad():
    """a pad with a comb of narrow recesses cut into one side — the recesses
    are what `min_channel_mm` fills back in"""
    m = np.zeros((600, 600), np.uint8)
    cv2.rectangle(m, (150, 60), (450, 540), 1, -1)
    for y in range(80, 530, 24):
        cv2.rectangle(m, (150, y), (360, y + 10), 0, -1)
    return m


def blob_and_hairlines():
    """a solid blob with loose HAIRLINES beside it: each hairline is hundreds
    of pixels and encloses nothing, so the contour gate drops it — until
    `connect_pieces` bridges them all into ONE contour that encloses plenty"""
    m = np.zeros((600, 900), np.uint8)
    cv2.circle(m, (200, 300), 130, 1, -1)
    for x in (420, 520, 620, 720, 820):
        cv2.line(m, (x, 120), (x, 480), 1, 1)
    return m


def traced_aspect(data, height, **kw):
    ents, info = imgtrace.image_to_entities(data, height, **kw)
    xs = [e["x"] + p[0] for e in ents for p in e["points"]]
    ys = [e["y"] + p[1] for e in ents for p in e["points"]]
    return (max(xs) - min(xs)) / (max(ys) - min(ys)), info


def main():
    for name, gen, kw in (("connect_pieces", split_bar,
                           dict(connect_pieces=True)),
                          ("min_channel_mm", combed_pad,
                           dict(min_channel_mm=1.5)),
                          ("connect_pieces over hairlines", blob_and_hairlines,
                           dict(connect_pieces=True))):
        data = png(gen())
        print(f"\n=== {name} = {list(kw.values())[0]}")
        for h in (20.0, 40.0):
            a_fit = imgtrace.artwork_aspect(data, h)
            a_fit2 = imgtrace.artwork_aspect(data, h, **kw)
            a_plain, i0 = traced_aspect(data, h)
            a_real, i1 = traced_aspect(data, h, **kw)
            print(f"  at {h:g} mm: the fit asked artwork_aspect -> "
                  f"{a_fit:.4f}  (with the knobs: {a_fit2:.4f})")
            print(f"             the trace WITHOUT the knob   -> "
                  f"{a_plain:.4f}  ({i0['width_mm']}x{i0['height_mm']})")
            print(f"             the trace the user asked for -> "
                  f"{a_real:.4f}  ({i1['width_mm']}x{i1['height_mm']})")
        # and what the fit does with it on a face the choice matters on
        for box in ((20.0, 60.0), (60.0, 20.0)):
            h, rot = studio._trace_fit_height(data, 0.9 * box[0],
                                              0.9 * box[1], **kw)
            a_real, i1 = traced_aspect(data, h, **kw)
            w, hh = ((i1["height_mm"], i1["width_mm"]) if rot
                     else (i1["width_mm"], i1["height_mm"]))
            s = min(1.0, 0.9 * box[0] / w, 0.9 * box[1] / hh)
            print(f"  on a {box[0]:g}x{box[1]:g} mm face: height {h:.3f}, "
                  f"rotated {rot} -> {w * s:.2f} x {hh * s:.2f} mm "
                  f"(area {w * s * hh * s:.1f} mm2, rescaled by {s:.3f})")


if __name__ == "__main__":
    main()
