"""LAUNCH-PLAN s10 P1: the trace fit measures the aspect at 50 mm and then
traces at the height that aspect produced.

`studio._trace_fitted` calls `imgtrace.artwork_aspect(data)` with NO height,
so the speckle floor that decides which pieces exist runs at the DEFAULT
50 mm, while `image_to_entities` then runs it at the fitted height. The floor
is physical (0.25 mm at the final scale), so a smaller height drops more
pieces - and the aspect the fit was computed from is the aspect of artwork
that never gets traced.

Run:  C:\\Python314\\python.exe probes/imgtrace_fit_height_probe.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                          # noqa: E402


def _png(canvas):
    ok, buf = cv2.imencode(".png", canvas)
    assert ok
    return buf.tobytes()


def bar_with_ornaments(dot_r=3, dot_x=500):
    """A tall bar plus two small round ornaments far to its right.

    The ornaments are ~28 px: above the 0.25 mm floor at 50 mm tall
    (min_area 9) and under it at ~13 mm tall (min_area ~31), so the same
    picture is 'wide' at one size and 'tall and narrow' at the other."""
    img = np.zeros((400, 600, 4), np.uint8)
    cv2.rectangle(img, (100, 50), (199, 349), (0, 0, 0, 255), -1)
    cv2.circle(img, (dot_x, 120), dot_r, (0, 0, 0, 255), -1)
    cv2.circle(img, (dot_x, 280), dot_r, (0, 0, 0, 255), -1)
    return _png(img)


def pieces_at(data, h_mm):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    solid, min_area = imgtrace._traceable(imgtrace._mask_from_image(img), h_mm)
    n, _lab = cv2.connectedComponents(solid, 8)
    ys, xs = np.where(solid)
    return (n - 1, min_area,
            int(xs.max()) - int(xs.min()) + 1,
            int(ys.max()) - int(ys.min()) + 1)


def fit(aspect, fw, fh, margin=0.9):
    """studio._trace_fitted's height/rotate choice, verbatim."""
    h0 = margin * min(fh, fw / aspect)
    h90 = margin * min(fw, fh / aspect)
    rotated = h90 > h0 * 1.001
    return max(1.0, min(1000.0, h90 if rotated else h0)), rotated


def main():
    data = bar_with_ornaments()
    print("pieces / min_area / bbox px, by the height the floor runs at")
    for h in (50.0, 30.0, 20.0, 16.0, 13.5, 12.0, 8.0):
        n, ma, w, px_h = pieces_at(data, h)
        print(f"  {h:6.2f} mm -> {n} pieces, min_area {ma:8.2f} px, "
              f"bbox {w}x{px_h} px, aspect {w / px_h:.4f}")

    for fw, fh in ((20.0, 20.0), (60.0, 60.0), (40.0, 14.0)):
        print(f"\nface box {fw} x {fh} mm, margin 0.9")
        a50 = imgtrace.artwork_aspect(data)                 # what ships
        h, rot = fit(a50, fw, fh)
        print(f"  SHIPPED : aspect@50 {a50:.4f} -> trace at {h:.3f} mm, "
              f"rotated {rot}")
        ents, info = imgtrace.image_to_entities(data, h)
        print(f"            traced {info['width_mm']} x {info['height_mm']} mm"
              f", {info['contours']} pieces")
        # the honest loop: measure the aspect AT the height we will trace at
        seen, cur = [], h
        for _ in range(6):
            a = imgtrace.artwork_aspect(data, cur)
            nxt, rot2 = fit(a, fw, fh)
            seen.append((cur, a, nxt, rot2))
            if abs(nxt - cur) <= 1e-6 * max(1.0, cur):
                break
            cur = nxt
        for c, a, nxt, r in seen:
            print(f"  iterate : aspect@{c:.3f} {a:.4f} -> {nxt:.3f} mm "
                  f"rotated {r}")
        ents, info = imgtrace.image_to_entities(data, cur)
        print(f"  FIXED   : trace at {cur:.3f} mm -> "
              f"{info['width_mm']} x {info['height_mm']} mm, "
              f"{info['contours']} pieces")

    sweep(data)


def measured_fit(data, fw, fh, margin=0.9, rounds=5):
    """The rule this probe recommends: measure the aspect AT every height
    that is tried, and keep the BIGGEST tried height whose own measured
    artwork fits the box. A finite set, so it terminates even when the
    iteration cycles."""
    m_w, m_h = margin * fw, margin * fh
    tried, height = [], 50.0
    for _ in range(rounds):
        try:
            a = imgtrace.artwork_aspect(data, height)
        except ValueError:
            break
        tried.append((height, a))
        h0 = min(m_h, m_w / a)
        h90 = min(m_w, m_h / a)
        nxt = max(1.0, min(1000.0, h90 if h90 > h0 * 1.001 else h0))
        if any(abs(nxt - h) <= 1e-6 * h for h, _ in tried):
            break
        height = nxt
    best = None
    for h, a in tried:
        tol = 1.0 + 1e-9
        rot = (False if h <= m_h * tol and h * a <= m_w * tol else
               True if h <= m_w * tol and h * a <= m_h * tol else None)
        if rot is not None and (best is None or h > best[0]):
            best = (h, rot)
    if best is None:
        h, a = min(tried, key=lambda t: t[0])
        best = (h, min(m_w, m_h / a) > min(m_h, m_w / a) * 1.001)
    return best[0], best[1], len(tried)


def sweep(data):
    print("\nbox sweep: shipped vs measured-at-its-own-height")
    print(f"{'face box':>14s} {'shipped h':>10s} {'rot':>5s} "
          f"{'art w x h':>16s} | {'fixed h':>8s} {'rot':>5s} "
          f"{'art w x h':>16s} {'calls':>5s}")
    for fw in (12.0, 20.0, 40.0, 60.0):
        for fh in (14.0, 15.0, 20.0, 60.0):
            a50 = imgtrace.artwork_aspect(data)
            hs, rs = fit(a50, fw, fh)
            _e, i_s = imgtrace.image_to_entities(data, hs)
            ws, hh_s = ((i_s["height_mm"], i_s["width_mm"]) if rs else
                        (i_s["width_mm"], i_s["height_mm"]))
            hf, rf, n = measured_fit(data, fw, fh)
            _e, i_f = imgtrace.image_to_entities(data, hf)
            wf, hh_f = ((i_f["height_mm"], i_f["width_mm"]) if rf else
                        (i_f["width_mm"], i_f["height_mm"]))
            flag = "  <-- BIGGER" if hf > hs * 1.01 else ""
            print(f"{fw:6.1f}x{fh:<6.1f} {hs:10.3f} {str(rs):>5s} "
                  f"{ws:7.2f} x{hh_s:7.2f} | {hf:8.3f} {str(rf):>5s} "
                  f"{wf:7.2f} x{hh_f:7.2f} {n:5d}{flag}")


if __name__ == "__main__":
    main()
