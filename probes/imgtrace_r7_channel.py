"""ROUND SEVEN — `min_channel_mm`, the knob only the API and a script can set.

The channel absorb pre-fills background recesses narrower than the user's end
mill, so the traced sketch is millable by construction. Nothing bounds it. Two
things happen when it is set too big for the picture:

  * the open erases the background ENTIRELY, so the "artwork" the tracer
    returns is the picture's own rectangle — the section's signature failure,
    green and silent;
  * the cost is O(k**2) a pixel, and `k` is `min_channel_mm / mm_px`, so a
    single trace can take a minute with the request holding a server thread.

This measures both: the traced size and the wall time against the channel, on
two picture sizes, plus where the art actually disappears.

Run:  C:/Python314/python.exe probes/imgtrace_r7_channel.py
"""
from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402


def enc(img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def comb(w, h):
    """a bar with narrow slots cut into it — art the absorb is FOR"""
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (w // 8, h // 4), (w - w // 8, h - h // 4), 255, -1)
    step = max(4, w // 20)
    for x in range(w // 6, w - w // 6, step):
        cv2.rectangle(m, (x, h // 4), (x + max(1, step // 4), h // 2), 0, -1)
    return m


def main():
    for w, h, height_mm in ((400, 300, 20.0), (1500, 1200, 20.0)):
        data = enc(comb(w, h))
        base = imgtrace.image_to_entities(data, height_mm)[1]
        print(f"\n{w} x {h} px, traced {height_mm:g} mm tall — "
              f"art {base['width_mm']} x {base['height_mm']} mm, "
              f"{base['contours']} pieces, {base['holes']} holes")
        art_short = min(base["width_mm"], base["height_mm"])
        print(f"  the artwork's short side is {art_short:.2f} mm")
        for ch in (0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 12.0, 16.0, 20.0, 30.0,
                   60.0):
            t0 = time.time()
            try:
                _e, info = imgtrace.image_to_entities(data, height_mm, 0.15,
                                                      ch, False)
                dt = time.time() - t0
                gone = (info["width_mm"] >= base["width_mm"] * 1.02
                        and info["holes"] == 0 and base["holes"] > 0)
                print(f"    channel {ch:5.1f} mm -> {info['width_mm']:7.2f} x "
                      f"{info['height_mm']:6.2f} mm, {info['contours']} "
                      f"pieces, {info['holes']} holes, {dt:6.2f}s"
                      f"{'   <- THE ART IS GONE' if gone else ''}")
            except ValueError as exc:
                print(f"    channel {ch:5.1f} mm -> REFUSED "
                      f"({time.time() - t0:.2f}s) {exc}")
            if time.time() - t0 > 90:
                print("      (stopping: one trace already over 90 s)")
                break


if __name__ == "__main__":
    main()
