"""LAUNCH-PLAN s10 P2: the trace auto-fit box is the face BBOX, so square art
on a round or L-shaped face lands OFF the face.

Measures, through the real API, how far the traced points sit outside the
face they were "auto-fitted to", on a disc and on an L-shaped plate — before
and after `studio._inscribed_box`.

Run:  C:\\Python314\\python.exe probes/imgtrace_inscribed_box_probe.py
"""
from __future__ import annotations

import base64
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import document as dm                                    # noqa: E402
import studio                                            # noqa: E402


def square_png(size=400, pad=30):
    img = np.zeros((size, size, 4), np.uint8)
    cv2.rectangle(img, (pad, pad), (size - pad, size - pad),
                  (10, 10, 10, 255), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _tab(doc):
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(doc)
    studio._rebuild_and_mesh()


def disc_doc(radius=30.0, thick=10.0):
    doc = dm.Document("disc")
    doc.add("base", "disc", {"radius": radius, "thickness": thick}, [])
    return doc, [0.0, 0.0, thick / 2]


def ell_doc(a=60.0, b=60.0, bite=30.0, thick=10.0):
    """An L: a x b plate with a bite x bite corner cut away."""
    doc = dm.Document("ell")
    doc.add("base", "plate", {"width": a, "depth": b, "thickness": thick}, [])
    doc.add("bite", "plate",
            {"width": bite, "depth": bite, "thickness": thick * 3}, [])
    doc.add("bite_at", "move",
            {"x": (a - bite) / 2, "y": (b - bite) / 2, "z": 0}, ["bite"])
    doc.add("ell", "cut", {}, ["base", "bite_at"])
    return doc, [0.0, 0.0, thick / 2]


def trace_on(doc, centre, radius=None, poly=None):
    from fastapi.testclient import TestClient
    _tab(doc)
    client = TestClient(studio.app)
    d = client.post("/api/trace-png", json={
        "png_base64": base64.b64encode(square_png()).decode(),
        "face_center": centre, "face_normal": [0, 0, 1],
        "feature_id": "art"}).json()
    assert not d.get("error"), d.get("error")
    info = d["trace_info"]
    doc2 = studio._doc()
    ents = [f for f in doc2.features if f.id == info["feature_id"]][0]
    pts = [(e["x"] + p[0], e["y"] + p[1])
           for e in ents.params["entities"] for p in e["points"]]
    if radius is not None:
        out = [p for p in pts if (p[0] ** 2 + p[1] ** 2) ** 0.5 > radius]
        worst = max((p[0] ** 2 + p[1] ** 2) ** 0.5 for p in pts)
    else:
        out = [p for p in pts if cv2.pointPolygonTest(
            np.array(poly, np.float32), (float(p[0]), float(p[1])),
            False) < 0]
        worst = -min(cv2.pointPolygonTest(
            np.array(poly, np.float32), (float(p[0]), float(p[1])), True)
            for p in pts)
    return info, len(pts), len(out), worst


def main():
    print("== disc face, radius 30.0, square art ==")
    doc, c = disc_doc()
    info, n, out, worst = trace_on(doc, c, radius=30.0)
    print(f"   chat says 'auto-fitted to the "
          f"{info['face_mm'][0]}x{info['face_mm'][1]}mm face'")
    print(f"   art {info['width_mm']} x {info['height_mm']} mm, {n} points, "
          f"{out} OUTSIDE the disc, furthest {worst:.2f} mm from centre "
          f"(face radius 30.00)")

    print("\n== L face, 60 x 60 with a 30 x 30 bite, square art ==")
    doc, c = ell_doc()
    ell = [(-30, -30), (30, -30), (30, 0), (0, 0), (0, 30), (-30, 30)]
    info, n, out, worst = trace_on(doc, c, poly=ell)
    print(f"   chat says 'auto-fitted to the "
          f"{info['face_mm'][0]}x{info['face_mm'][1]}mm face'")
    print(f"   art {info['width_mm']} x {info['height_mm']} mm, {n} points, "
          f"{out} OUTSIDE the face, furthest {worst:.2f} mm off it")


if __name__ == "__main__":
    main()
