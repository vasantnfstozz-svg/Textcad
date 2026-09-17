"""REVIEW-QUEUE section 9 ROUND FOUR — the section's "input limits" finding
class, swept once for the closing round: a sentence, not a stack trace.

`_border_bright` reads the picture's border, erodes it and runs a distance
transform, all of which have degenerate cases the corpora cannot reach (a one
pixel row, a picture that is one tone, a shell that swallows the picture).
And the decode path hands whatever `cv2.imdecode(..., IMREAD_UNCHANGED)`
returns straight to `cv2.threshold(..., THRESH_OTSU)`, which is 8-bit only.

Anything that comes back as ValueError is a sentence the UI shows; anything
else is a traceback in the user's face.

Run:  C:\\Python314\\python.exe probes/imgtrace_r4_inputs.py
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


def enc(img, ext=".png"):
    ok, b = cv2.imencode(ext, img)
    assert ok, ext
    return b.tobytes()


def art8(h=300, w=300):
    im = np.full((h, w, 3), 255, np.uint8)
    cv2.circle(im, (w // 2, h // 2), min(h, w) // 3, (0, 0, 0), -1)
    return im


def cases():
    yield "1x1 white", enc(np.full((1, 1, 3), 255, np.uint8))
    yield "2x2 checker", enc(np.array([[[0, 0, 0], [255, 255, 255]],
                                       [[255, 255, 255], [0, 0, 0]]],
                                      np.uint8))
    yield "1 x 400 row", enc(np.tile(np.array([[0], [255]], np.uint8).T,
                                     (1, 200)).reshape(1, 400, 1)
                             .repeat(3, axis=2))
    yield "400 x 1 column", enc(np.tile(np.array([[0], [255]], np.uint8),
                                        (200, 1)).reshape(400, 1, 1)
                                .repeat(3, axis=2))
    yield "all white", enc(np.full((200, 200, 3), 255, np.uint8))
    yield "all black", enc(np.zeros((200, 200, 3), np.uint8))
    yield "one grey tone", enc(np.full((200, 200, 3), 128, np.uint8))
    yield "grayscale 2-D", enc(cv2.cvtColor(art8(), cv2.COLOR_BGR2GRAY))
    yield "opaque alpha (min 255)", enc(
        np.dstack([art8(), np.full((300, 300), 255, np.uint8)]))
    yield "alpha only, no colour", enc(
        np.dstack([np.zeros((300, 300, 3), np.uint8),
                   (art8()[:, :, 0] < 128).astype(np.uint8) * 255]))
    yield "JPG with no dark pixels", enc(
        np.full((200, 200, 3), 250, np.uint8), ".jpg")
    yield "16-bit PNG", enc((art8().astype(np.uint16) * 257))
    yield "not an image at all", b"this is not a picture"
    big = np.full((4000, 4000, 3), 255, np.uint8)
    cv2.circle(big, (2000, 2000), 1200, (0, 0, 0), -1)
    yield "4000 x 4000", enc(big)


def main():
    worst = 0
    for name, data in cases():
        for fn, tag in ((imgtrace.image_to_entities, "trace"),
                        (imgtrace.artwork_aspect, "aspect")):
            try:
                r = fn(data)
                out = (f"ok  {r[1]}" if tag == "trace" else f"ok  {r:.4f}")
            except ValueError as exc:
                out = f"sentence: {str(exc)[:58]}"
            except Exception as exc:                        # noqa: BLE001
                out = f"!! {type(exc).__name__}: {str(exc)[:58]}"
                worst += 1
            print(f"  {name:24s} {tag:6s} {out}")
    print(f"\ninputs answered with something other than a sentence: {worst}")


if __name__ == "__main__":
    main()
