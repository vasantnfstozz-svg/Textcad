"""probes/imgtrace_min_cross_probe.py - a SMALL, deterministic image whose
traced outline crosses itself (so the test does not depend on a fuzz seed).
A 1-pixel whisker makes OpenCV's contour walk out and back along the same
pixels; Douglas-Peucker then shortcuts one side past the other.
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imgtrace  # noqa: E402
import inspector  # noqa: E402
import sketch as sk  # noqa: E402
from imgtrace_fuzz_probe import crossings  # noqa: E402

from OCP.BRepCheck import BRepCheck_Analyzer  # noqa: E402


def png(c):
    ok, b = cv2.imencode(".png", c)
    return b.tobytes()


def report(name, img, h=30.0):
    try:
        ents, info = imgtrace.image_to_entities(png(img), height_mm=h)
    except Exception as e:                        # noqa: BLE001
        print(f"  {name}: {type(e).__name__}: {e}")
        return
    x = sum(len(crossings([tuple(p) for p in e["points"]])) for e in ents)
    face = sk.make_sketch("XY", 0, ents)
    valid = BRepCheck_Analyzer(face.wrapped).IsValid()
    solid = sk.extrude_sketch(face, 2.0)
    # what the artwork really covers, in mm2, straight from the pixels
    mask = imgtrace._mask_from_image(
        cv2.imdecode(np.frombuffer(png(img), np.uint8), cv2.IMREAD_UNCHANGED))
    ys, xs = np.where(mask)
    mm_px = h / (int(ys.max()) - int(ys.min()) + 1)
    truth = float(mask.sum()) * mm_px * mm_px
    print(f"  {name}: {info['contours']}c/{info['holes']}h "
          f"{info['points']}pts, {x} self-crossings, face valid={valid}, "
          f"health={inspector.health(solid)}\n"
          f"      area {face.area:9.3f} mm2 vs {truth:9.3f} from the pixels "
          f"({100 * face.area / truth:6.1f}%)")


def main():
    # a) a blob with a one-pixel whisker sticking out
    img = np.zeros((300, 300, 4), np.uint8)
    cv2.rectangle(img, (60, 60), (240, 240), (0, 0, 0, 255), -1)
    for k in range(40):
        img[60 - k, 150] = (0, 0, 0, 255)          # 1px vertical whisker
    report("1px whisker", img)

    # b) two blobs joined at a single diagonal pixel (8-connectivity)
    img = np.zeros((300, 300, 4), np.uint8)
    cv2.rectangle(img, (40, 40), (140, 140), (0, 0, 0, 255), -1)
    cv2.rectangle(img, (141, 141), (250, 250), (0, 0, 0, 255), -1)
    report("diagonal join", img)

    # c) a comb of 1px teeth
    img = np.zeros((300, 300, 4), np.uint8)
    cv2.rectangle(img, (40, 150), (260, 250), (0, 0, 0, 255), -1)
    for i in range(20):
        img[60:150, 50 + i * 10] = (0, 0, 0, 255)
    report("1px comb teeth", img)

    # d) a staircase of single pixels (the classic anti-aliased edge)
    img = np.zeros((300, 300, 4), np.uint8)
    cv2.rectangle(img, (60, 60), (240, 240), (0, 0, 0, 255), -1)
    for k in range(60):
        img[60 - (k // 2), 100 + k] = (0, 0, 0, 255)
    report("1px staircase", img)

    # e) a spike drawn as a zero-width line out of a body
    img = np.zeros((300, 300, 4), np.uint8)
    cv2.rectangle(img, (60, 120), (240, 240), (0, 0, 0, 255), -1)
    cv2.line(img, (150, 120), (150, 30), (0, 0, 0, 255), 1)
    cv2.line(img, (150, 120), (90, 30), (0, 0, 0, 255), 1)
    report("two hairlines", img)


if __name__ == "__main__":
    main()
