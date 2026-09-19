"""ROUND SEVEN — studio.py's own side of the tracer: the values the request
model accepts and nothing checks.

`TracePngReq` validates nothing but what pydantic can: `height_mm` is checked
inside imgtrace (1..1000), and `fit_margin`, `tol_mm` and `fit_box` are taken
as given. The rules of engagement call a degenerate value that reaches
build123d unchecked a finding, so each one is put to the door.

Also here: the questions round seven was asked to ask of studio.py — what a
trace does when the face outline arrives empty, and what two traces landing in
one sketch do to each other.

Run:  C:/Python314/python.exe probes/imgtrace_r7_doors.py
"""
from __future__ import annotations

import base64
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402


def png():
    m = np.zeros((300, 400, 4), np.uint8)
    cv2.circle(m, (200, 150), 90, (0, 0, 0, 255), -1)
    cv2.circle(m, (200, 150), 30, (0, 0, 0, 0), -1)
    ok, buf = cv2.imencode(".png", m)
    assert ok
    return buf.tobytes()


def client():
    from fastapi.testclient import TestClient
    import document as dm
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("plate")
    doc.add("base", "plate", {"width": 60, "depth": 40, "thickness": 8}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def ask(cl, name, **extra):
    d = cl.post("/api/trace-png", json={
        "png_base64": base64.b64encode(png()).decode(),
        "entities_only": True, **extra})
    body = d.json()
    if body.get("error"):
        print(f"  {name:<40} REFUSED  {body['error'][:100]}")
        return None
    ents = body["entities"]
    xs = [e["x"] + p[0] for e in ents for p in e["points"]]
    ys = [e["y"] + p[1] for e in ents for p in e["points"]]
    span = (max(xs) - min(xs), max(ys) - min(ys)) if xs else (0.0, 0.0)
    print(f"  {name:<40} ok  {len(ents)} polygons, "
          f"{span[0]:.3f} x {span[1]:.3f} mm, info {body['trace_info']}")
    return ents


def main():
    cl = client()
    print("A. fit_margin — the fraction of the box the art fills")
    for m in (0.9, 0.5, 0.05, 0.0, -0.5, 2.0, 1e9):
        ask(cl, f"fit_margin = {m:g}", fit_box=[30.0, 20.0, 0.0, 0.0],
            fit_margin=m)

    print("\nB. fit_box — the browser sends the server's own inscribed box")
    for box in ([30.0, 20.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0],
                [-30.0, 20.0, 0.0, 0.0], [1e-6, 1e-6, 0.0, 0.0],
                [1e9, 1e9, 0.0, 0.0]):
        ask(cl, f"fit_box = {box}", fit_box=box)
    d = cl.post("/api/trace-png", json={
        "png_base64": base64.b64encode(png()).decode(),
        "entities_only": True, "fit_box": [30.0]}).json()
    print(f"  {'fit_box with one number':<40} "
          f"{'REFUSED  ' + d['error'][:80] if d.get('error') else 'ok'}")

    print("\nC. tol_mm — the fidelity knob")
    for t in (0.15, 0.0, -1.0, 1e9):
        ask(cl, f"tol_mm = {t:g}", tol_mm=t)

    print("\nD. a face pick whose outline the server cannot read")
    for name, body in (("no face at all", {}),
                       ("a face_center off the body",
                        {"face_center": [500.0, 500.0, 500.0],
                         "face_normal": [0.0, 0.0, 1.0]}),
                       ("a zero normal",
                        {"face_center": [0.0, 0.0, 8.0],
                         "face_normal": [0.0, 0.0, 0.0]}),
                       ("a curved face's centre",
                        {"face_center": [0.0, 0.0, 4.0],
                         "face_normal": [1.0, 0.0, 0.0],
                         "face_area": 1e9})):
        r = cl.post("/api/trace-png", json={
            "png_base64": base64.b64encode(png()).decode(),
            "feature_id": f"logo-{name.replace(' ', '-')}", **body})
        j = r.json()
        msg = j.get("error") or "ok"
        print(f"  {name:<40} {r.status_code}  {str(msg)[:110]}")

    print("\nE. two traces landing in ONE sketch")
    a = ask(cl, "trace 1 into a 30 x 20 box", fit_box=[30.0, 20.0, 0.0, 0.0])
    b = ask(cl, "trace 2 into the SAME box", fit_box=[30.0, 20.0, 0.0, 0.0])
    if a and b:
        rings = [np.asarray([[e["x"] + x, e["y"] + y] for x, y in e["points"]],
                            float) for e in list(a) + list(b)]
        worst = min(min(float(imgtrace._nearest_on_ring(rings[i],
                                                        rings[j])[0].min()),
                        float(imgtrace._nearest_on_ring(rings[j],
                                                        rings[i])[0].min()))
                    for i in range(len(a))
                    for j in range(len(a), len(rings)))
        print(f"      the two traces' loops come {worst:.9f} mm apart in the "
              f"sketch they share")


if __name__ == "__main__":
    main()
