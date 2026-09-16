"""REVIEW-QUEUE section 9 ROUND TWO — what _uncross costs, and two input
shapes the new code has never been put to.

Section 8 round four's finding was a COST one (a guard that was linear in the
container's faces), so the same question is asked here: _first_crossing is a
Python loop of numpy slices per edge and _uncross calls it up to 64 times per
contour. Timed on detailed art at the resolution a user actually uploads.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_cost.py
"""
from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                                    # noqa: E402


def _png_rgba(mask):
    h, w = mask.shape
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def detailed(n_px, seed=3):
    rng = np.random.default_rng(seed)
    m = np.zeros((n_px, n_px), np.uint8)
    for _ in range(140):
        p = tuple(int(v) for v in rng.integers(0, n_px, 2))
        q = tuple(int(v) for v in rng.integers(0, n_px, 2))
        cv2.line(m, p, q, 1, int(rng.integers(1, 6)))
    for _ in range(40):
        p = tuple(int(v) for v in rng.integers(0, n_px, 2))
        cv2.circle(m, p, int(rng.integers(10, n_px // 10)), 1, -1)
    return m


def timed(data, h_mm, uncross):
    saved = imgtrace._uncross
    if not uncross:
        imgtrace._uncross = lambda p: [p]      # no splitting at all
    try:
        t0 = time.perf_counter()
        _, info = imgtrace.image_to_entities(data, height_mm=h_mm)
        return time.perf_counter() - t0, info["points"]
    except Exception as e:                                    # noqa: BLE001
        return None, f"{type(e).__name__}"
    finally:
        imgtrace._uncross = saved


def main():
    print("cost of _uncross on detailed art (one trace each)")
    print(f"{'pixels':>9s} {'height':>7s} {'with':>9s} {'without':>9s} "
          f"{'x slower':>9s} {'points':>8s}")
    for n in (600, 1200, 2400, 4000):
        data = _png_rgba(detailed(n))
        for h in (50.0,):
            a, pa = timed(data, h, True)
            b, pb = timed(data, h, False)
            if a is None or b is None:
                print(f"{n:9d} {h:7.1f}   {pa} / {pb}")
                continue
            print(f"{n:9d} {h:7.1f} {a:9.3f} {b:9.3f} {a / b:9.2f} "
                  f"{pa:8d}")
    print()
    print("input shapes the new code has never been put to:")
    # a grey+alpha (LA) PNG, which PIL writes and OpenCV cannot encode
    import io as _io

    from PIL import Image
    la = Image.new("LA", (200, 200), (40, 0))
    la.paste((255, 255), (50, 50, 150, 150))
    buf = _io.BytesIO()
    la.save(buf, format="PNG")
    dec = cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8),
                       cv2.IMREAD_UNCHANGED)
    print(f"   LA (grey+alpha) PNG decodes to shape "
          f"{None if dec is None else dec.shape}")
    try:
        _, info = imgtrace.image_to_entities(buf.getvalue(), height_mm=20)
        print(f"   traced fine: {info}")
    except ValueError as e:
        print(f"   ValueError (a sentence): {e}")
    except Exception as e:                                    # noqa: BLE001
        print(f"   {type(e).__name__} reaches the user: {str(e)[:150]}")
    # a fully opaque RGBA png: the alpha branch must not fire
    a4 = np.zeros((200, 200, 4), np.uint8)
    a4[:, :, 3] = 255
    a4[50:150, 50:150, :3] = 255
    ok, b4 = cv2.imencode(".png", a4)
    try:
        _, info = imgtrace.image_to_entities(b4.tobytes(), height_mm=20)
        print(f"   opaque RGBA (white square on black): {info}")
    except Exception as e:                                    # noqa: BLE001
        print(f"   opaque RGBA: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
