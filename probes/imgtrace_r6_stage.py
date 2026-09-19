"""ROUND SIX — WHICH pass puts a crossing back into an outline `_uncross`
has just cleaned?

`probes/imgtrace_r6_reach.py` finds a real picture — a disc with hair-thin
spokes, traced 10 mm tall — whose traced sketch hands `sketch.py` a polygon
that crosses itself, and whose 2 mm extrusion OpenCASCADE calls invalid. The
push is not the cause: the same picture crosses with `_pull_apart` turned off.

Between `_uncross` and `sketch.py` there are three more passes, and this probe
runs `_first_crossing` after each:

  1. `_uncross`                     — promises None
  2. the art-centring translation   — dx, dy = (max + min) / 2 of the DRAWN
                                      points, which is a half-grid number
                                      whenever max + min is an odd multiple of
                                      0.001 mm
  3. `_pull_apart`
  4. `_round_pts` back onto the 0.001 mm grid
  5. `_poly_entity` (its own centre is rounded onto the grid on purpose)

Run:  C:/Python314/python.exe probes/imgtrace_r6_stage.py [png ...]
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
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402


def stages(data, height_mm):
    """re-run `image_to_entities`' tail by hand, checking after each pass"""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    solid, min_area = imgtrace._traceable(imgtrace._mask_from_image(img),
                                          height_mm)
    cnts, hier = cv2.findContours(solid, cv2.RETR_CCOMP,
                                  cv2.CHAIN_APPROX_SIMPLE)
    hier = hier[0] if hier is not None else []
    order = sorted(range(len(cnts)),
                   key=lambda i: cv2.contourArea(cnts[i]), reverse=True)
    keep = [i for i in order if cv2.contourArea(cnts[i]) >= min_area]
    x, y, w, h = cv2.boundingRect(np.vstack([cnts[i] for i in keep or order]))
    mm_px = float(height_mm) / h
    cx_px, cy_px = x + w / 2.0, y + h / 2.0
    eps = max(1.0, min(3.0, 0.15 / mm_px))
    cut_px = max(0.8, min(2.0, 0.4 / mm_px))

    drawn = []
    for i in keep:
        ap = cv2.approxPolyDP(cnts[i], eps, True).reshape(-1, 2).astype(float)
        if len(ap) < 3:
            continue
        ap = imgtrace._chaikin(ap, cut_px=cut_px)
        pts = [((px - cx_px) * mm_px, (cy_px - py) * mm_px) for px, py in ap]
        loops = [p for p in imgtrace._uncross(imgtrace._round_pts(pts))
                 if len(p) >= 3]
        if not loops:
            continue
        loops.sort(key=lambda p: abs(imgtrace._area2(p)), reverse=True)
        floor = 2.0 * min_area * mm_px * mm_px
        loops = loops[:1] + [p for p in loops[1:]
                             if abs(imgtrace._area2(p)) >= floor]
        drawn += [(hier[i][3] < 0, p) for p in loops]

    def bad(ls):
        return [n for n, p in enumerate(ls)
                if imgtrace._first_crossing(list(p)) is not None]

    step1 = [p for _o, p in drawn]
    print(f"  mm/px {mm_px:.6f}  eps {eps:g} px  loops {len(step1)}")
    print(f"  1 after _uncross                : crossing {bad(step1)}")
    ax = [p[0] for p in sum(step1, [])]
    ay = [p[1] for p in sum(step1, [])]
    dx, dy = (max(ax) + min(ax)) / 2.0, (max(ay) + min(ay)) / 2.0
    print(f"    dx {dx!r}  dy {dy!r}")
    print(f"    dx on the 0.001 grid? {abs(dx * 1000 - round(dx * 1000)) < 1e-9}"
          f"   dy? {abs(dy * 1000 - round(dy * 1000)) < 1e-9}")
    step2 = [[(px - dx, py - dy) for px, py in p] for p in step1]
    print(f"  2 after the art-centring shift  : crossing {bad(step2)}")
    step2r = [imgtrace._round_pts(p) for p in step2]
    print(f"  2b ...and back on the grid      : crossing {bad(step2r)}")
    step3 = imgtrace._pull_apart(step2)
    print(f"  3 after _pull_apart             : crossing {bad(step3)}")
    step4 = [imgtrace._round_pts(p) for p in step3]
    print(f"  4 after _round_pts              : crossing {bad(step4)}")
    ents = [imgtrace._poly_entity(p, "add" if o else "subtract")
            for (o, _raw), p in zip(drawn, step4) if len(p) >= 3]
    step5 = [[tuple(q) for q in e["points"]] for e in ents]
    print(f"  5 after _poly_entity            : crossing {bad(step5)}")
    try:
        sol = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
        bd = inspector.health(sol)
        print(f"  kernel: {bd[0] if bd else 'healthy'}  volume {sol.volume}")
    except Exception as exc:                                # noqa: BLE001
        print(f"  kernel: SKETCH FAIL {type(exc).__name__}: {str(exc)[:70]}")


def main():
    files = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not files:
        files = [os.path.join(HERE, "_r6_cross_spikes2.png")]
    for f in files:
        data = open(f, "rb").read()
        for h in (10.0, 8.0, 13.0):
            print(f"\n=== {os.path.basename(f)} at {h:g} mm")
            stages(data, h)


if __name__ == "__main__":
    main()
