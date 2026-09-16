"""probes/imgtrace_rotate_probe.py - REVIEW-QUEUE section 9.

The 90-degree auto-rotate is decided from artwork_aspect, which reads the
RAW mask. One speck of dirt that image_to_entities then throws away can
flip that decision - putting the logo back in the "vertical position, its
no use" the rotate exists to prevent.
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="imgtrace_rot_")
os.environ["TEXTCAD_HISTORY_ROOT"] = _TMP

import imgtrace  # noqa: E402
import document as dm  # noqa: E402
import studio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

studio.DESIGNS = _TMP


def tall_art(speck):
    """TALL art (1:12) in a wide canvas; optional 3px speck bottom-right"""
    img = np.zeros((1200, 1200, 4), np.uint8)
    cv2.rectangle(img, (580, 100), (620, 1100), (0, 0, 0, 255), -1)
    cv2.rectangle(img, (500, 100), (700, 200), (0, 0, 0, 255), -1)   # a T bar
    if speck:
        cv2.rectangle(img, (20, 1170), (23, 1173), (0, 0, 0, 255), -1)
        cv2.rectangle(img, (1170, 20), (1173, 23), (0, 0, 0, 255), -1)
    ok, b = cv2.imencode(".png", img)
    return b.tobytes()


def main():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("plate")
    doc.add("base", "plate", {"width": 120, "depth": 40, "thickness": 10}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    c = TestClient(studio.app)
    for speck in (False, True):
        data = tall_art(speck)
        print(f"speck={speck}: artwork_aspect="
              f"{imgtrace.artwork_aspect(data):.4f}  "
              f"(the art itself is {imgtrace.image_to_entities(data, 50)[1]})")
        d = c.post("/api/trace-png", json={
            "png_base64": base64.b64encode(data).decode(),
            "entities_only": True, "fit_box": [120, 40, 0, 0]}).json()
        if d.get("error"):
            print("   ERROR", d["error"])
            continue
        e = d["entities"]
        xs = [q["x"] + p[0] for q in e for p in q["points"]]
        ys = [q["y"] + p[1] for q in e for p in q["points"]]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        print(f"   on a 120x40 face -> rotated={d['trace_info']['rotated']}, "
              f"{max(xs) - min(xs):.2f} x {max(ys) - min(ys):.2f} mm "
              f"(bbox {area:.0f} mm2)")


if __name__ == "__main__":
    main()
