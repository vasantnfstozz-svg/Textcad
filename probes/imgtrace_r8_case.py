"""ROUND EIGHT — a DETERMINISTIC picture the shipped refusal turns away for
an overlap, so the finding can be locked in by a test rather than a seed.

`probes/imgtrace_r8_meet.py` finds these on random artwork. A test needs one
that is the same every run, so this sweeps the deterministic ladder of
`probes/imgtrace_r7_fit_shrink.py` (the picture `tests/test_trace_fit.py`
already uses for the case where NO tried height fits) over face boxes, and
prints what every refusal really is.

MEASURED 2026-09-19 at 37eb290: the ladder is refused on NONE of the 110
fits, so the test case had to be built by hand instead (see
tests/test_imgtrace_loops.py, the wedge on the wall).

What the sweep did turn up is a SEPARATE, PRE-EXISTING quality defect in
`studio._trace_fit_height`, which this range does not touch and which is
therefore reported, not fixed:

    10 spokes on 1.5x1.5 mm: ok 1.0 x 1.35 mm, 11 entities   <- the whole logo
    10 spokes on 2x2   mm: ok 1.8 x 0.07 mm,  1 entity       <- a hairline
    10 spokes on 8x1.5 mm: ok 7.2 x 0.29 mm,  1 entity       <- a hairline
    10 spokes on 6x2   mm: ok 5.4 x 0.22 mm,  1 entity
    10 spokes on 2x6   mm: ok 0.22 x 5.4 mm,  1 entity

A BIGGER face gives LESS art. The winner is "the biggest tried height whose
own measured artwork really fits the box", and the candidate set is the
iteration's own trajectory — 50 -> 1.82 -> 0.30 on the 8 x 1.5 box. The one
height that draws all eleven pieces, 1.35, is never tried, so the fit lays a
bar 0.29 mm tall on the face and throws ten of the eleven pieces away, green
and silent.

Run:  C:/Python314/python.exe probes/imgtrace_r8_case.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import studio                                               # noqa: E402
from imgtrace_r7_fit_shrink import ladder                   # noqa: E402
from imgtrace_r8_meet import zero_pairs                     # noqa: E402

BOXES = ((5.0, 5.0), (4.0, 4.0), (3.0, 3.0), (2.5, 2.5), (2.0, 2.0),
         (1.5, 1.5), (1.0, 1.0), (6.0, 2.0), (2.0, 6.0), (8.0, 1.5))


def classify(ents):
    flat = [imgtrace._round_pts([(float(e["x"] + px), float(e["y"] + py))
                                 for px, py in e["points"]]) for e in ents]
    split = []
    for pts in flat:
        split += [p for p in imgtrace._uncross(pts)
                  if len(p) >= 3 and abs(imgtrace._area2(p)) > 1e-9]
    st: list = []
    apart = imgtrace._pull_apart(split, report=st)
    hits = zero_pairs(apart, st)
    return len(hits), sorted({h[3] for h in hits})


def main():
    for spokes in range(0, 22, 2):
        data = ladder(spokes=spokes)
        for fw, fh in BOXES:
            req = studio.TracePngReq(png_base64="",
                                     fit_box=[fw, fh, 0.0, 0.0])
            tag = f"  {spokes:2d} spokes on {fw:g}x{fh:g}"
            try:
                ents, info = studio._trace_fitted(data, req,
                                                  (fw, fh, 0.0, 0.0))
            except ValueError as exc:
                if "meet at a point" not in str(exc):
                    print(f"{tag}: OTHER REFUSAL {str(exc)[:56]}")
                    continue
                real = imgtrace._MEET_MM
                try:
                    imgtrace._MEET_MM = -1.0
                    e2, _i2 = studio._trace_fitted(data, req,
                                                   (fw, fh, 0.0, 0.0))
                finally:
                    imgtrace._MEET_MM = real
                n, kinds = classify(e2)
                print(f"{tag}: MEET — {n} zero pair(s) {kinds or ['-']}, "
                      f"{len(e2)} entities")
                continue
            except Exception as exc:                        # noqa: BLE001
                print(f"{tag}: {type(exc).__name__} {str(exc)[:56]}")
                continue
            print(f"{tag}: ok {info['width_mm']}x{info['height_mm']} "
                  f"{len(ents)} ents")


if __name__ == "__main__":
    main()
