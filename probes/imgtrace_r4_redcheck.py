"""REVIEW-QUEUE section 9 ROUND FOUR — would each of round three's 5 new
test cases go RED if ITS OWN half of the fix were reverted?

Round three made TWO independent changes inside `_border_bright`:

    L  "only a DARK shell is read past"       (was: either side)
    F  the floor inside the shell is 64 px    (was: max(64, 1% of the picture))

so a test only earns its place if it is red with ITS half reverted, not merely
with both. Four modules are scored: the shipped rule, L-reverted, F-reverted,
and round two whole (both reverted).

Run:  C:\\Python314\\python.exe probes/imgtrace_r4_redcheck.py
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
import sketch as sk                                         # noqa: E402


def _png(img):
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes()


# --- the four border rules, as `_border_bright` replacements ---------------
SHIPPED = imgtrace._border_bright


def bb_shipped(m):
    return SHIPPED(m)


def _generic(m, dark_only, floor_pct):
    valid = np.ones(m.shape, np.uint8)
    ring = imgtrace._ring_mean(m, valid)
    if dark_only:
        if ring > 0.4:
            return ring
        side = 0
    else:
        if 0.4 <= ring <= 0.6:
            return ring
        side = 1 if ring > 0.5 else 0
    shell = imgtrace._edge_shell(m, side, valid)
    if shell is None:
        return ring
    if float(cv2.distanceTransform(shell, cv2.DIST_L2, 3).max()) > \
            0.05 * min(m.shape):
        return ring
    rest = (1 - shell).astype(np.uint8)
    inside = m[rest.astype(bool)]
    lit = int(inside.sum())
    if min(lit, int(inside.size) - lit) < max(64.0, floor_pct * inside.size):
        return ring
    return imgtrace._ring_mean(m, rest)


def bb_L_reverted(m):        # round two's "either side", round three's floor
    return _generic(m, dark_only=False, floor_pct=0.0)


def bb_F_reverted(m):        # round three's dark-only, round two's 1% floor
    return _generic(m, dark_only=True, floor_pct=0.01)


def bb_r2(m):                # round two whole
    return _generic(m, dark_only=False, floor_pct=0.01)


MODULES = [("shipped", bb_shipped), ("L-reverted", bb_L_reverted),
           ("F-reverted", bb_F_reverted), ("r2 (both)", bb_r2)]


# --- the pictures the two tests use, copied from tests/test_trace.py ------
def padded_plate(size, pad, n=3):
    img = np.full((size, size, 3), 255, np.uint8)
    cv2.rectangle(img, (pad, pad), (size - 1 - pad, size - 1 - pad),
                  (0, 0, 0), -1)
    step = (size - 2 * pad) // (n + 1)
    for i in range(n):
        for j in range(n):
            cv2.circle(img, (pad + (i + 1) * step, pad + (j + 1) * step),
                       size // 12, (255, 255, 255), -1)
    return img


def scan_sheet(size, band, logo_frac):
    img = np.full((size, size, 3), 255, np.uint8)
    r = int(np.sqrt(logo_frac * size * size / np.pi))
    cv2.circle(img, (size // 2, size // 2), r, (0, 0, 0), -1)
    img[:band] = img[-band:] = 0
    img[:, :band] = img[:, -band:] = 0
    return img


def check_plate(size, pad):
    ents, info = imgtrace.image_to_entities(_png(padded_plate(size, pad)),
                                            height_mm=40)
    area = sk.make_sketch("XY", 0, ents).area
    ok = info["contours"] == 1 and info["holes"] == 9 and area > 1000
    return ok, f"{info['contours']}c/{info['holes']}h {area:8.1f} mm2"


def check_scan(frac):
    ents, info = imgtrace.image_to_entities(_png(scan_sheet(800, 12, frac)),
                                            height_mm=40)
    area = sk.make_sketch("XY", 0, ents).area
    ok = area < 400 and info["holes"] <= 1
    return ok, f"{info['contours']}c/{info['holes']}h {area:8.1f} mm2"


CASES = [
    ("light_pad 400/8  (fix L)", lambda: check_plate(400, 8)),
    ("light_pad 1200/20 (fix L)", lambda: check_plate(1200, 20)),
    ("light_pad 2400/50 (fix L)", lambda: check_plate(2400, 50)),
    ("small_logo 0.5%  (fix F)", lambda: check_scan(0.005)),
    ("small_logo 0.2%  (fix F)", lambda: check_scan(0.002)),
]


def main():
    orig = imgtrace._border_bright
    print(f"{'test case':28s} " + " ".join(f"{n:11s}" for n, _ in MODULES))
    print("-" * 90)
    rows = []
    for name, fn in CASES:
        cells = []
        for _mn, bb in MODULES:
            imgtrace._border_bright = bb
            try:
                ok, detail = fn()
            except Exception as exc:                        # noqa: BLE001
                ok, detail = False, f"RAISED {type(exc).__name__}"
            cells.append((ok, detail))
        imgtrace._border_bright = orig
        rows.append((name, cells))
        print(f"{name:28s} "
              + " ".join(f"{'GREEN' if ok else 'RED':11s}" for ok, _ in cells))
        print(f"{'':28s} " + " ".join(f"{d:11s}" for _, d in cells))
    print("-" * 90)
    for name, cells in rows:
        verdict = []
        if not cells[0][0]:
            verdict.append("!! GREEN TEST IS RED ON THE SHIPPED MODULE")
        half = 1 if "fix L" in name else 2
        verdict.append("own half reverted -> "
                       + ("RED (earns its place)" if not cells[half][0]
                          else "STILL GREEN (does not lock its fix)"))
        verdict.append("r2 -> " + ("RED" if not cells[3][0] else "GREEN"))
        print(f"{name:28s} " + "; ".join(verdict))


if __name__ == "__main__":
    main()
