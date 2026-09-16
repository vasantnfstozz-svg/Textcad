"""REVIEW-QUEUE section 9 ROUND TWO — can _uncross() throw real artwork away?

Round one added `_uncross`: at every self-crossing it splits the outline into
two loops and keeps the BIGGER one, claiming "the loop thrown away is the
width of `eps` — under a tenth of a millimetre of artwork". That claim was
measured on a comb of one-pixel whiskers. This puts it to shapes where a loop
is LEGITIMATE: an hourglass pinched to a thin neck, two blobs touching at one
pixel, a spiral, a nearly-closed C, and the letters e, g, 8, &.

For each: the true artwork area (pixels x mm/px squared), the area traced with
_uncross as shipped, and the area traced with _uncross disabled.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_uncross.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                                    # noqa: E402
import sketch as sk                                                # noqa: E402

H_MM = 40.0


def _png(img):
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def _rgba(mask):
    """black-on-transparent so the alpha path is used and polarity is moot"""
    h, w = mask.shape
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    return img


def _true_mm2(mask):
    ys, _ = np.where(mask)
    h_all = int(ys.max()) - int(ys.min()) + 1
    return float((mask > 0).sum()) * (H_MM / h_all) ** 2


def _trace(data, uncross):
    saved = imgtrace._uncross
    if not uncross:
        imgtrace._uncross = lambda p: [p]      # no splitting at all
    try:
        ents, info = imgtrace.image_to_entities(data, height_mm=H_MM)
        try:
            area = sk.make_sketch("XY", 0, ents).area
        except Exception as e:                                # noqa: BLE001
            area = f"sketch: {type(e).__name__}"
        return area, f"{info['contours']}c/{info['holes']}h"
    except Exception as e:                                    # noqa: BLE001
        return f"refused: {type(e).__name__}", "-"
    finally:
        imgtrace._uncross = saved


SH = []


def shape(fn):
    SH.append(fn)
    return fn


@shape
def hourglass_neck_2px():
    """two 300x300 lobes joined by a 2 px neck — a legitimate figure eight"""
    m = np.zeros((700, 400), np.uint8)
    cv2.rectangle(m, (50, 20), (350, 320), 1, -1)
    cv2.rectangle(m, (50, 380), (350, 680), 1, -1)
    m[320:380, 199:201] = 1
    return m, "two lobes joined by a 2 px neck"


@shape
def hourglass_touch_1px():
    """two lobes touching at ONE pixel corner-to-corner (8-connectivity
    makes them one component, so the contour walks a true figure eight)"""
    m = np.zeros((700, 700), np.uint8)
    cv2.rectangle(m, (20, 20), (349, 349), 1, -1)
    cv2.rectangle(m, (350, 350), (679, 679), 1, -1)
    return m, "two squares touching at one corner pixel"


@shape
def spiral():
    m = np.zeros((600, 600), np.uint8)
    pts = []
    for i in range(900):
        t = i / 900 * 5.5 * np.pi
        r = 20 + t * 14
        pts.append((int(300 + r * np.cos(t)), int(300 + r * np.sin(t))))
    cv2.polylines(m, [np.array(pts)], False, 1, 9)
    return m, "a 2.7-turn spiral, 9 px wide"


@shape
def thin_c_nearly_closed():
    m = np.zeros((500, 500), np.uint8)
    cv2.circle(m, (250, 250), 200, 1, 14)
    cv2.ellipse(m, (250, 250), (200, 200), 0, -4, 4, 0, 16)
    return m, "a 14 px ring with a 28 px gap (a thin C)"


def _glyph(ch, scale=14, thick=26):
    m = np.zeros((520, 520), np.uint8)
    cv2.putText(m, ch, (60, 430), cv2.FONT_HERSHEY_SIMPLEX, scale, 1, thick)
    return m


@shape
def letter_e():
    return _glyph("e"), "the letter e"


@shape
def letter_g():
    return _glyph("g"), "the letter g"


@shape
def letter_8():
    return _glyph("8"), "the figure 8"


@shape
def letter_amp():
    return _glyph("&"), "an ampersand"


@shape
def dumbbell_4px():
    """two discs joined by a 4 px bar — a barbell logo"""
    m = np.zeros((400, 800), np.uint8)
    cv2.circle(m, (150, 200), 130, 1, -1)
    cv2.circle(m, (650, 200), 130, 1, -1)
    m[198:202, 150:650] = 1
    return m, "two discs joined by a 4 px bar"


def main():
    print(f"{'shape':24s} {'true mm2':>10s} {'shipped':>12s} {'sig':>7s} "
          f"{'_uncross off':>14s} {'sig':>7s}  lost%")
    print("-" * 100)
    for fn in SH:
        m, desc = fn()
        data = _png(_rgba(m))
        want = _true_mm2(m)
        a_on, s_on = _trace(data, True)
        a_off, s_off = _trace(data, False)
        lost = ""
        if isinstance(a_on, float) and isinstance(a_off, float) and a_off:
            lost = f"{100.0 * (a_off - a_on) / a_off:6.2f}"
        f = (lambda v: f"{v:12.2f}" if isinstance(v, float) else f"{v:>12s}")
        g = (lambda v: f"{v:14.2f}" if isinstance(v, float) else f"{v:>14s}")
        print(f"{fn.__name__:24s} {want:10.2f} {f(a_on)} {s_on:>7s} "
              f"{g(a_off)} {s_off:>7s} {lost:>7s}   {desc}")
    print("-" * 100)


if __name__ == "__main__":
    main()
