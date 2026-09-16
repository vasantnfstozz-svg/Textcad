"""REVIEW-QUEUE section 9 ROUND TWO — is _traceable() really the set the
trace traces, and can its new refusal fire on art that would trace fine?

Round one's P1 was "a speck of dirt decided the fit and the auto-rotate", and
the fix was one shared `_traceable()`. This asks the same question one level
down, of _traceable's OWN numbers:

  A. `h_all` is the bbox of the RAW mask, specks included, and it sets
     mm_px, which sets the 0.25 mm floor. So a speck still decides WHICH
     PIECES get traced — and can make the whole thing refuse.
  B. the trace applies the floor a SECOND time as cv2.contourArea(), which
     is not the component's pixel area at all, so pieces that count in the
     aspect are still dropped from the trace.
  C. studio._trace_fitted calls artwork_aspect(data) with the DEFAULT 50 mm
     and then traces at the FITTED height, so the two floors differ anyway.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_traceable.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import imgtrace                                                    # noqa: E402


def _png(mask):
    h, w = mask.shape
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


def _report(tag, data, h_mm):
    try:
        ents, info = imgtrace.image_to_entities(data, height_mm=h_mm)
        got = (f"{info['contours']}c/{info['holes']}h  "
               f"{info['width_mm']} x {info['height_mm']} mm")
    except Exception as e:                                    # noqa: BLE001
        got = f"REFUSED: {e}"
    try:
        asp = f"{imgtrace.artwork_aspect(data, h_mm):.4f}"
    except Exception as e:                                    # noqa: BLE001
        asp = f"REFUSED: {type(e).__name__}"
    print(f"   {tag:34s} aspect {asp:>10s}   trace {got}")


def case_a_speck_sets_the_floor():
    """`h_all` is the bbox of the RAW mask, so one 2x2 speck far from the art
    stretches it — and the 0.25 mm floor is (0.25 / (height_mm/h_all))^2."""
    print("A1. a 2x2 speck REFUSES art whose pieces are 9.7 mm across")
    for speck in (False, True):
        m = np.zeros((3000, 1200), np.uint8)
        for i in range(5):                       # five 30 px dots in a row
            cv2.rectangle(m, (200 + i * 180, 1400), (230 + i * 180, 1430),
                          1, -1)
        if speck:
            m[40:42, 40:42] = 1
        _report(f"{'with' if speck else 'without'} the speck, 10 mm tall",
                _png(m), 10.0)
    print()
    print("A2. a 2x2 speck drops the dot of an i from otherwise normal art")
    for speck in (False, True):
        m = np.zeros((3000, 1200), np.uint8)
        cv2.rectangle(m, (200, 1400), (230, 1560), 1, -1)     # the stem
        cv2.rectangle(m, (208, 1350), (215, 1357), 1, -1)     # the dot
        cv2.rectangle(m, (300, 1400), (330, 1560), 1, -1)     # a second stem
        if speck:
            m[40:42, 40:42] = 1
        _report(f"{'with' if speck else 'without'} the speck, 50 mm tall",
                _png(m), 50.0)
    print()


def case_b_thin_stroke():
    """A blob plus a 1 px hairline: the hairline is 600 pixels of ink, well
    over the component floor, so it counts in the ASPECT — but its contour
    encloses nothing, so the trace drops it. The two are out of step again."""
    print("B. a 1 px stroke counts in the aspect and is dropped by the trace")
    for stroke in (False, True):
        m = np.zeros((800, 800), np.uint8)
        cv2.circle(m, (200, 400), 120, 1, -1)
        if stroke:
            m[100:700, 700] = 1
        _report(f"{'with' if stroke else 'without'} the hairline, 40 mm",
                _png(m), 40.0)
    print()


def case_c_aspect_height_differs():
    """studio._trace_fitted computes the aspect at the DEFAULT 50 mm and then
    traces at the height that fit produced. Same picture, two floors."""
    print("C. the aspect's floor (50 mm) vs the trace's floor (fitted)")
    m = np.zeros((1600, 1600), np.uint8)
    cv2.rectangle(m, (600, 200), (1000, 1400), 1, -1)       # the body
    for i in range(3):                                       # three ornaments
        cv2.circle(m, (300, 400 + i * 400), 11, 1, -1)
    data = _png(m)
    for h in (50.0, 20.0, 12.0, 8.0):
        try:
            a = f"{imgtrace.artwork_aspect(data, h):.4f}"
        except Exception as e:                                # noqa: BLE001
            a = f"REFUSED {type(e).__name__}"
        try:
            _, info = imgtrace.image_to_entities(data, height_mm=h)
            t = f"{info['contours']}c  {info['width_mm']}x{info['height_mm']}"
        except Exception as e:                                # noqa: BLE001
            t = f"REFUSED {e}"
        print(f"   height {h:5.1f} mm   aspect {a:>10s}   trace {t}")
    print("   (studio always asks for the aspect at 50 mm, whatever it then "
          "traces at)")
    print()


if __name__ == "__main__":
    case_a_speck_sets_the_floor()
    case_b_thin_stroke()
    case_c_aspect_height_differs()
