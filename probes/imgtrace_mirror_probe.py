"""probes/imgtrace_mirror_probe.py - REVIEW-QUEUE section 9, orientation.

Traces a CHIRAL glyph (an F) onto the TOP and the BOTTOM face of the same
plate through the real /api/trace-png path and measures where the long top
arm ends up in WORLD coordinates. If both land at the same world +X, the
art on the underside reads MIRRORED when that face is looked at from
outside it.

TEXTCAD_HISTORY_ROOT + studio.DESIGNS are redirected to a temp folder:
this probe must never touch designs/.
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="imgtrace_probe_")
os.environ["TEXTCAD_HISTORY_ROOT"] = _TMP

import document as dm  # noqa: E402
import studio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

studio.DESIGNS = _TMP


def f_png():
    """an F: stem on the LEFT, arms to the RIGHT, top arm the longer one"""
    img = np.zeros((400, 300, 4), np.uint8)
    cv2.rectangle(img, (60, 40), (110, 360), (0, 0, 0, 255), -1)
    cv2.rectangle(img, (60, 40), (250, 90), (0, 0, 0, 255), -1)
    cv2.rectangle(img, (60, 170), (200, 220), (0, 0, 0, 255), -1)
    ok, b = cv2.imencode(".png", img)
    return base64.b64encode(b.tobytes()).decode()


def main():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("plate")
    doc.add("base", "plate", {"width": 80, "depth": 40, "thickness": 10}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    c = TestClient(studio.app)
    b64 = f_png()
    for name, ctr, nrm in (("TOP  (+Z)", [0, 0, 5], [0, 0, 1]),
                           ("BOTTOM (-Z)", [0, 0, -5], [0, 0, -1])):
        d = c.post("/api/trace-png", json={
            "png_base64": b64, "feature_id": name.split()[0].lower(),
            "face_center": ctr, "face_normal": nrm,
            "body_feature_id": "base"}).json()
        if d.get("error"):
            print(name, "ERROR", d["error"])
            continue
        ft = next(f for f in d["features"]
                  if f["id"] == name.split()[0].lower())
        ents = ft["params"]["entities"]
        pts = [(e["x"] + p[0], e["y"] + p[1]) for e in ents for p in e["points"]]
        ys = [q[1] for q in pts]
        top_reach = max(q[0] for q in pts if q[1] > max(ys) - 2)
        bot_reach = max(q[0] for q in pts if q[1] < min(ys) + 2)
        print(f"{name}: frame x {min(q[0] for q in pts):7.2f}..{max(q[0] for q in pts):7.2f}"
              f"  top-arm reach {top_reach:7.2f}  bottom-arm reach {bot_reach:7.2f}")
        print(f"          -> the long arm points "
              f"{'+X' if top_reach > 0 else '-X'} in the SKETCH FRAME")


if __name__ == "__main__":
    main()
