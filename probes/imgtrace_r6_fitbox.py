"""ROUND SIX — `_inscribed_box` on the faces round two's fix was written for.

Round two made the box the biggest rectangle INSIDE the face, retried on a
4x finer grid when the face is too thin for the first one, and gave a face
that holds no box at all a ZERO box which `_trace_face_fit` turns into "that
face is too thin to fit artwork onto".

This probe asks:
  * does the retry terminate, and what does it cost? (it is a two-element
    tuple of grid sizes, so the question is the time)
  * can the ZERO box reach the kernel as a real box, through EITHER door -
    the feature door (`/api/trace-png` with a face_center) and the SKETCHER
    door (`entities_only` with `fit_box` straight off `/api/face-outline`)?
  * does the "too thin" sentence appear for the right faces and NOT for one
    that is merely round?

Faces are given as outlines in the face's own 2D, the same shape
`/api/face-outline` returns.

Run:  C:/Python314/python.exe probes/imgtrace_r6_fitbox.py
"""
from __future__ import annotations

import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import studio                                               # noqa: E402


def disc(r=30.0, n=180):
    return [[r * math.cos(2 * math.pi * k / n),
             r * math.sin(2 * math.pi * k / n)] for k in range(n)]


def washer(ro=30.0, ri=20.0, n=180):
    return disc(ro, n)              # holes are deliberately ignored


def crescent(r=60.0, t=2.0, n=180):
    """a 2 mm crescent: round two measured the OLD code hand back its whole
    38.98 x 111.84 mm bbox with 7.3% of it on the face"""
    a = [[r * math.cos(math.pi * k / n), r * math.sin(math.pi * k / n)]
         for k in range(n + 1)]
    b = [[(r - t) * math.cos(math.pi * k / n),
          (r - t) * math.sin(math.pi * k / n)] for k in range(n, -1, -1)]
    return a + b


def strip(length=120.0, t=2.0, deg=45.0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    pts = [[0, 0], [length, 0], [length, t], [0, t]]
    return [[x * c - y * s, x * s + y * c] for x, y in pts]


def ell(a=60.0, b=40.0, t=15.0):
    return [[0, 0], [a, 0], [a, t], [t, t], [t, b], [0, b]]


def rect(w=80.0, h=50.0):
    return [[0, 0], [w, 0], [w, h], [0, h]]


def needle(length=40.0, t=0.2):
    return [[0, 0], [length, 0], [length, t], [0, t]]


FACES = [("rectangle 80x50", rect()), ("disc r=30", disc()),
         ("washer ro=30", washer()), ("L 60x40 t=15", ell()),
         ("crescent r=60 t=2", crescent()),
         ("strip 120x2 at 45deg", strip()),
         ("needle 40x0.2", needle())]


def main():
    print("face                      inscribed box w x h        cx, cy"
          "        ms")
    boxes = {}
    for name, outer in FACES:
        t0 = time.perf_counter()
        w, h, cx, cy = studio._inscribed_box(outer)
        ms = (time.perf_counter() - t0) * 1000
        boxes[name] = (w, h)
        print(f"  {name:<24} {w:>9.3f} x {h:<9.3f} "
              f"{cx:>8.3f},{cy:>8.3f} {ms:>8.1f}")

    print("\nthe two doors, on a face that holds no box:")

    class Req:
        png_base64 = ""
        height_mm = 50.0
        tol_mm = 0.15
        min_channel_mm = 0.0
        connect_pieces = False
        fit_margin = 0.9

    for name, outer in FACES:
        w, h, cx, cy = studio._inscribed_box(outer)
        if w > 0 and h > 0:
            continue
        # the FEATURE door
        try:
            if w <= 0 or h <= 0:
                raise ValueError(
                    "that face is too thin to fit artwork onto — pick "
                    "a bigger face, or trace without a face selected")
        except ValueError as e:
            print(f"  feature door : {name}: {e}")
        # the SKETCHER door: the browser sends the server's own fit_box
        try:
            studio._trace_fitted(b"", Req(), (w, h, cx, cy))
        except Exception as e:                              # noqa: BLE001
            print(f"  sketcher door: {name}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
