"""ROUND SEVEN — how small the fit's residual rescale really gets.

`probes/imgtrace_r7_rescale.py` shows what a rescale costs: 129 of 288 traces
end pinched (a pair at exactly 0.000000000 mm) or self-crossing once their
points are multiplied by `s` and re-rounded onto the 0.001 mm grid. That only
matters if `s` really gets small at the door, so this measures `s` itself.

`studio._trace_fitted` computes it with exactly this arithmetic, and the
comment calls it a residual — "the traced bbox can differ a hair from the mask
bbox after speckle removal / smoothing". `_trace_fit_height`'s own docstring
says otherwise for the case where nothing tried fits: "one of them has to be
traced and then SHRUNK by `_trace_fitted`'s residual rescale".

So: the ring/plate/comb/rings corpus against a spread of face boxes, and the
`s` that comes out.

Run:  C:/Python314/python.exe probes/imgtrace_r7_fit_shrink.py [n] [seed]
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import studio                                               # noqa: E402
from imgtrace_r5_mirror import GENS, png                    # noqa: E402
from imgtrace_r7_rescale import closest, crosses, rescale   # noqa: E402

BOXES = ((60.0, 40.0), (20.0, 60.0), (12.0, 14.0), (8.0, 30.0), (40.0, 3.0),
         (5.0, 5.0), (100.0, 2.5))
MARGIN = 0.9


def fit(data, fw, fh):
    """studio._trace_fitted's own arithmetic, `s` included"""
    height, rotated = studio._trace_fit_height(data, MARGIN * fw, MARGIN * fh)
    ents, info = imgtrace.image_to_entities(data, height, 0.15, 0.0, False)
    w, h = info["width_mm"], info["height_mm"]
    if rotated:
        w, h = h, w
    s = min([1.0]
            + ([MARGIN * fw / w] if w > MARGIN * fw else [])
            + ([MARGIN * fh / h] if h > MARGIN * fh else []))
    return ents, s, height


def ladder(radii=(30, 24, 20, 17, 14, 12, 10, 8, 7, 6), gap=130,
           bar_w=1000, bar_t=40, spokes=0):
    """tests/test_trace_fit.py's own picture for the case where NO tried
    height fits: a wide bar with a ladder of dots above it, each smaller than
    the one below. With `spokes` it also carries hair-wide walls."""
    import cv2
    h = bar_t + gap * (len(radii) + 1) + 80
    img = np.zeros((h, bar_w + 200, 4), np.uint8)
    y0 = h - 60
    cv2.rectangle(img, (100, y0 - bar_t), (100 + bar_w, y0), (0, 0, 0, 255), -1)
    for k, r in enumerate(radii):
        cv2.circle(img, (600, y0 - bar_t - gap * (k + 1)), int(r),
                   (0, 0, 0, 255), -1)
    for k in range(spokes):
        x = 200 + k * 37
        cv2.rectangle(img, (x, y0 - bar_t), (x + 1, y0 - 4), (0, 0, 0, 0), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def never_settles():
    print("THE PICTURE WHOSE ASPECT NEVER SETTLES "
          "(tests/test_trace_fit.py's own _ladder)\n")
    for spokes in (0, 6, 14):
        data = ladder(spokes=spokes)
        for fw, fh in ((12.0, 14.0), (12.0, 10.0), (12.0, 18.0), (8.0, 30.0),
                       (5.0, 5.0), (40.0, 3.0)):
            try:
                ents, s, height = fit(data, fw, fh)
            except ValueError as exc:
                print(f"  {spokes:2d} spokes on {fw:g} x {fh:g}: "
                      f"REFUSED {exc}")
                continue
            g0 = closest(ents) if len(ents) > 1 else float("nan")
            sc = rescale(ents, s)
            g = closest(sc) if len(ents) > 1 else float("nan")
            x = crosses(sc)
            print(f"  {spokes:2d} spokes on {fw:g} x {fh:g} mm: traced "
                  f"{height:.3f} mm, s={s:.4f}, {len(ents)} polygons, "
                  f"closest {g0:.6f} -> {g:.9f} mm, "
                  f"{x} now cross themselves"
                  + ("   <- PINCHED" if g <= 0.0 else "")
                  + ("   <- CROSSES" if x else ""))
    print()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--ladder" in sys.argv:
        return never_settles()
    n = int(args[0]) if args else 8
    seed = int(args[1]) if len(args) > 1 else 7_2026
    rng = np.random.default_rng(seed)
    ss: list = []
    pinched = crossed = fits = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for fw, fh in BOXES:
                try:
                    ents, s, height = fit(data, fw, fh)
                except ValueError:
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k} {fw}x{fh}: "
                          f"{type(exc).__name__}: {str(exc)[:70]}")
                    continue
                fits += 1
                ss.append(s)
                if s >= 1.0 or len(ents) < 2:
                    continue
                g0, sc = closest(ents), rescale(ents, s)
                g, x = closest(sc), crosses(sc)
                if g <= 0.0:
                    pinched += 1
                if x:
                    crossed += 1
                if g <= 0.0 or x:
                    print(f"  {gname}{k} on a {fw:g} x {fh:g} mm box: traced "
                          f"{height:.3f} mm tall then shrunk s={s:.4f} -> "
                          f"closest {g0:.6f} -> {g:.9f} mm, {x} of "
                          f"{len(ents)} polygons now cross themselves")
    ss.sort()
    print(f"\n{fits} fits")
    print(f"  s == 1.000 (no rescale)  : {sum(1 for v in ss if v >= 1.0)}")
    print(f"  s <  1.000               : {sum(1 for v in ss if v < 1.0)}")
    if ss:
        print(f"  smallest s               : {ss[0]:.6f}")
        print(f"  s below 0.9 / 0.5 / 0.1  : "
              f"{sum(1 for v in ss if v < 0.9)} / "
              f"{sum(1 for v in ss if v < 0.5)} / "
              f"{sum(1 for v in ss if v < 0.1)}")
    print(f"  fits ending PINCHED      : {pinched}")
    print(f"  fits ending self-crossing: {crossed}")


if __name__ == "__main__":
    main()
