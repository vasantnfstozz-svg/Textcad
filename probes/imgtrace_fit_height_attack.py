"""Can `_trace_fit_height` be defeated?

The rule: measure the artwork's aspect at every height it tries, stop on the
first repeat, keep the biggest TRIED height whose own measured artwork fits.
Two questions the shipped comment does not answer:

  1. what happens to a picture whose aspect never repeats — five distinct
     heights, none of which fits?  The fallback then takes `min(tried)`, the
     SMALLEST height tried;
  2. is the art it lands on ever smaller than the old one-shot rule's?

The picture built here is a wide bar with a ladder of dots above it, each
smaller than the one below, so every drop in the trace height loses the
topmost dot, shortens the artwork and RAISES its aspect. That is exactly the
input on which the iteration walks downhill without ever repeating.

Run:  C:/Python314/python.exe probes/imgtrace_fit_height_attack.py
"""
from __future__ import annotations

import base64
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                             # noqa: E402
import studio                                               # noqa: E402


def ladder(radii=(26, 19, 14, 10, 7), gap=200, bar_w=1000, bar_t=40):
    """a wide bar with `len(radii)` dots stacked above it, smallest on top"""
    h = bar_t + gap * (len(radii) + 1) + 80
    img = np.zeros((h, bar_w + 200, 4), np.uint8)
    y0 = h - 60
    cv2.rectangle(img, (100, y0 - bar_t), (100 + bar_w, y0),
                  (0, 0, 0, 255), -1)
    for k, r in enumerate(radii):
        cv2.circle(img, (600, y0 - bar_t - gap * (k + 1)), int(r),
                   (0, 0, 0, 255), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def aspect_curve(data, lo=4.0, hi=60.0, n=29):
    print("  height_mm : aspect")
    for m in np.linspace(lo, hi, n):
        try:
            print(f"   {m:7.2f} : {imgtrace.artwork_aspect(data, float(m)):.4f}")
        except ValueError as e:
            print(f"   {m:7.2f} : refused ({str(e)[:40]})")


def _client():
    from fastapi.testclient import TestClient
    import document as dm
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("plate")
    doc.add("base", "plate", {"width": 200, "depth": 120, "thickness": 10}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def fitted(client, data, box):
    d = client.post("/api/trace-png", json={
        "png_base64": base64.b64encode(data).decode(),
        "entities_only": True, "fit_box": list(box)}).json()
    if d.get("error"):
        return None
    xs = [e["x"] + p[0] for e in d["entities"] for p in e["points"]]
    ys = [e["y"] + p[1] for e in d["entities"] for p in e["points"]]
    return (max(xs) - min(xs), max(ys) - min(ys), d["trace_info"])


def old_rule(data, m_w, m_h):
    """the pre-0a08578 one-shot rule, for the 'never smaller' claim"""
    aspect = imgtrace.artwork_aspect(data)
    h0 = min(m_h, m_w / aspect)
    h90 = min(m_w, m_h / aspect)
    rot = h90 > h0 * 1.001
    return max(1.0, min(1000.0, h90 if rot else h0)), rot


_ASPECT_CACHE: dict = {}
_REAL_ASPECT = imgtrace.artwork_aspect


def cached_aspect(data, height_mm=50.0):
    """`artwork_aspect` is the whole cost of a sweep and it is a pure
    function of (picture, height) — memoise it so 1200 boxes are affordable."""
    key = round(float(height_mm), 6)
    if key not in _ASPECT_CACHE:
        _ASPECT_CACHE[key] = _REAL_ASPECT(data, key)
    return _ASPECT_CACHE[key]


def picks(data, m_w, m_h):
    """run `_trace_fit_height` and report what it tried, plus whether its
    'biggest tried height that fits' found anything (the fallback fires when
    it does not)."""
    tried = []
    real = imgtrace.artwork_aspect

    def spy(d, height_mm=50.0, _t=tried):
        a = cached_aspect(d, height_mm)
        _t.append((round(height_mm, 4), round(a, 4)))
        return a

    studio.imgtrace.artwork_aspect = spy
    try:
        h, rot = studio._trace_fit_height(data, m_w, m_h)
    finally:
        studio.imgtrace.artwork_aspect = real
    tol = 1.0 + 1e-9
    any_fit = any(
        (h0 <= m_h * tol and h0 * a <= m_w * tol)
        or (h0 <= m_w * tol and h0 * a <= m_h * tol) for h0, a in tried)
    return h, rot, tried, any_fit


def sweep():
    """hunt for boxes where NOTHING tried fits, so the fallback decides"""
    data = ladder(radii=(30, 24, 20, 17, 14, 12, 10, 8, 7, 6), gap=130)
    print("=== aspect against the height it is measured at ===")
    aspect_curve(data, 4.0, 40.0, 37)
    client = _client()
    print("\n=== boxes where NOTHING tried fits (the fallback decides) ===")
    print(f"{'face':>14} {'tried heights':<52} {'pick':>8} {'rot':>5} "
          f"{'final art':>18} {'old rule':>18}")
    def final_size(data, h, rot, m_w, m_h):
        """what `_trace_fitted` ends up with, without tracing: the art at `h`,
        rotated or not, shrunk by the residual rescale"""
        a = cached_aspect(data, h)
        w, hh = (h, h * a) if rot else (h * a, h)
        s = min(1.0, m_w / w, m_h / hh)
        return w * s, hh * s

    worse = 0
    n_fallback = shown = 0
    for fw10 in range(120, 600, 4):
        fw = fw10 / 10.0
        for fh10 in range(100, 600, 4):
            fh = fh10 / 10.0
            m_w, m_h = 0.9 * fw, 0.9 * fh
            h, rot, tried, any_fit = picks(data, m_w, m_h)
            if any_fit:
                continue
            n_fallback += 1
            nw, nh = final_size(data, h, rot, m_w, m_h)
            oh, orot = old_rule(data, m_w, m_h)
            ow, ohh = final_size(data, oh, orot, m_w, m_h)
            if nw * nh < ow * ohh * 0.999:
                worse += 1
                if worse <= 8:
                    print(f"  SMALLER than the one-shot rule at "
                          f"{fw:.1f}x{fh:.1f}: {nw:.2f}x{nh:.2f} vs "
                          f"{ow:.2f}x{ohh:.2f}")
            if shown >= 25:
                continue
            shown += 1
            got = fitted(client, data, (fw, fh, 0, 0))
            oh, orot = old_rule(data, m_w, m_h)
            try:
                _oe, oinfo = imgtrace.image_to_entities(data, oh)
                ow, ohh = oinfo["width_mm"], oinfo["height_mm"]
                if orot:
                    ow, ohh = ohh, ow
                s = min([1.0] + ([m_w / ow] if ow > m_w else [])
                        + ([m_h / ohh] if ohh > m_h else []))
                old_txt = f"{ow * s:7.2f} x {ohh * s:6.2f}"
            except ValueError:
                old_txt = "        refused   "
            heights = " ".join(f"{t[0]:g}/{t[1]:g}" for t in tried)
            print(f"{fw:6.1f}x{fh:<6.1f} {heights:<52} {h:8.3f} {str(rot):>5} "
                  f"{got[0]:8.2f} x {got[1]:6.2f}   {old_txt}")
    print(f"\n{n_fallback} boxes fell back (nothing tried fits); "
          f"{worse} of them come out SMALLER in area than the one-shot rule")


def main():
    data = ladder()
    print("=== aspect against the height it is measured at ===")
    aspect_curve(data)

    client = _client()
    print("\n=== the fit, box by box ===")
    print(f"{'face':>14} {'tried heights':<42} {'pick':>8} {'rot':>5} "
          f"{'final art':>18} {'old rule':>18}")
    for fw, fh in [(60.0, 40.0), (80.0, 30.0), (100.0, 25.0), (120.0, 20.0),
                   (60.0, 60.0), (40.0, 40.0), (160.0, 30.0), (200.0, 40.0),
                   (30.0, 90.0), (25.0, 60.0)]:
        m_w, m_h = 0.9 * fw, 0.9 * fh
        tried = []
        real = imgtrace.artwork_aspect

        def spy(d, height_mm=50.0, _real=real, _t=tried):
            a = _real(d, height_mm)
            _t.append((round(height_mm, 3), round(a, 4)))
            return a

        studio.imgtrace.artwork_aspect = spy
        try:
            h, rot = studio._trace_fit_height(data, m_w, m_h)
        finally:
            studio.imgtrace.artwork_aspect = real
        got = fitted(client, data, (fw, fh, 0, 0))
        oh, orot = old_rule(data, m_w, m_h)
        try:
            oents, oinfo = imgtrace.image_to_entities(data, oh)
            ow, ohh = oinfo["width_mm"], oinfo["height_mm"]
            if orot:
                ow, ohh = ohh, ow
            s = min([1.0] + ([m_w / ow] if ow > m_w else [])
                    + ([m_h / ohh] if ohh > m_h else []))
            old_txt = f"{ow * s:7.2f} x {ohh * s:6.2f}"
        except ValueError:
            old_txt = "        refused   "
        heights = " ".join(f"{t[0]:g}/{t[1]:g}" for t in tried)
        print(f"{fw:6.0f}x{fh:<6.0f} {heights:<42} {h:8.3f} {str(rot):>5} "
              f"{got[0]:8.2f} x {got[1]:6.2f}   {old_txt}")


if __name__ == "__main__":
    if "--sweep" in sys.argv:
        sweep()
    else:
        main()
