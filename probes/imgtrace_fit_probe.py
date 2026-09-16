"""probes/imgtrace_fit_probe.py - REVIEW-QUEUE section 9, scale and fit.

1. artwork_aspect reads the RAW mask; image_to_entities traces the mask
   AFTER speckle removal. One stray dark pixel therefore decides the fit
   height and the 90-degree auto-rotate from a DIFFERENT shape than the one
   that gets traced.
2. the fit box is the face BBOX, so art fitted to a round or L-shaped face
   can hang over the material.
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="imgtrace_fit_")
os.environ["TEXTCAD_HISTORY_ROOT"] = _TMP

import imgtrace  # noqa: E402
import document as dm  # noqa: E402
import studio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

studio.DESIGNS = _TMP


def png(c):
    ok, b = cv2.imencode(".png", c)
    return b.tobytes()


def wide_art(speck=False, size=(600, 1200)):
    img = np.zeros((size[0], size[1], 4), np.uint8)
    cv2.rectangle(img, (100, 280), (1100, 320), (0, 0, 0, 255), -1)  # 1000x40
    if speck:
        cv2.rectangle(img, (4, 4), (6, 6), (0, 0, 0, 255), -1)       # 3x3 dot
    return png(img)


def part1():
    print("=== 1. one stray pixel vs the fit ===")
    for speck in (False, True):
        data = wide_art(speck)
        a = imgtrace.artwork_aspect(data)
        ents, info = imgtrace.image_to_entities(data, height_mm=20)
        real = info["width_mm"] / info["height_mm"]
        print(f"  speckle={speck}: artwork_aspect={a:.3f}  traced aspect={real:.3f}"
              f"  info={info}")
    print("  -> the fit picks its height and its rotate from artwork_aspect")
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("plate")
    doc.add("base", "plate", {"width": 100, "depth": 40, "thickness": 10}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    c = TestClient(studio.app)
    for speck in (False, True):
        b64 = base64.b64encode(wide_art(speck)).decode()
        d = c.post("/api/trace-png", json={
            "png_base64": b64, "entities_only": True,
            "fit_box": [100, 40, 0, 0]}).json()
        if d.get("error"):
            print(f"  speckle={speck}: ERROR {d['error']}")
            continue
        e = d["entities"]
        xs = [q["x"] + p[0] for q in e for p in q["points"]]
        ys = [q["y"] + p[1] for q in e for p in q["points"]]
        print(f"  speckle={speck}: fitted {max(xs) - min(xs):.2f} x "
              f"{max(ys) - min(ys):.2f} mm on a 100x40 face, "
              f"rotated={d['trace_info']['rotated']}, "
              f"info={d['trace_info']}")


def part2():
    print("=== 2. the fit box is the face BBOX ===")
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("disc")
    doc.add("base", "disc", {"radius": 30, "thickness": 8}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    c = TestClient(studio.app)
    sq = np.zeros((400, 400, 4), np.uint8)
    cv2.rectangle(sq, (20, 20), (380, 380), (0, 0, 0, 255), -1)
    b64 = base64.b64encode(png(sq)).decode()
    d = c.post("/api/trace-png", json={
        "png_base64": b64, "feature_id": "logo",
        "face_center": [0, 0, 4], "face_normal": [0, 0, 1],
        "body_feature_id": "base"}).json()
    if d.get("error"):
        print("  ERROR", d["error"])
        return
    ft = next(f for f in d["features"] if f["id"] == "logo")
    pts = [(e["x"] + p[0], e["y"] + p[1])
           for e in ft["params"]["entities"] for p in e["points"]]
    out = [q for q in pts if np.hypot(*q) > 30.0]
    print(f"  square art on a R30 disc face: {len(pts)} points, "
          f"{len(out)} of them OUTSIDE the disc "
          f"(max radius {max(np.hypot(*q) for q in pts):.2f} vs 30.00)")
    print("  trace_info", d["trace_info"])
    print("  feature status", ft["status"], ft.get("problems"))


if __name__ == "__main__":
    part1()
    part2()
