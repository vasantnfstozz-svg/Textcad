"""Does the new server `fit_box` reach the button the user presses?

cdd98e5 put the inscribed box on `/api/face-outline` as `fit_box` and used it
in `_trace_face_fit` (the FEATURE path, `/api/trace-png` with a face_center —
dialogs.js: "stays for scripts and the MCP tools").

The user's own Trace Image button is `traceIntoSketch` in static/js/sketcher.js
and takes the OTHER path: `entities_only: true` with a `fit_box` the browser
computes itself from the face outline's min/max (sketcher.js:417-421), which
is the face only when the face is a rectangle. `faceRef` is rebuilt at
sketcher.js:300 and :341 as `{outer, holes}`, so the server's `fit_box` is
dropped on the floor.

This probe replays both requests against a 30 mm disc and counts how many
traced points land off the material each way.

Run:  C:/Python314/python.exe probes/imgtrace_fitbox_unused.py
"""
import base64
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import document as dm            # noqa: E402
import studio                    # noqa: E402


def _square_png(size=400, pad=30):
    img = np.zeros((size, size, 4), np.uint8)
    cv2.rectangle(img, (pad, pad), (size - pad, size - pad),
                  (10, 10, 10, 255), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _disc_tab(radius=30.0, thick=10.0):
    from fastapi.testclient import TestClient
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("disc")
    doc.add("base", "disc", {"radius": radius, "thickness": thick}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def off_disc(ents, radius):
    pts = [(e["x"] + p[0], e["y"] + p[1]) for e in ents for p in e["points"]]
    far = [(x * x + y * y) ** 0.5 for x, y in pts]
    return sum(1 for d in far if d > radius), len(pts), max(far)


def main():
    radius = 30.0
    client = _disc_tab(radius)
    png = base64.b64encode(_square_png()).decode()
    out = client.post("/api/face-outline", json={
        "face_center": [0, 0, 5], "face_normal": [0, 0, 1]}).json()
    xs = [p[0] for p in out["outer"]]
    ys = [p[1] for p in out["outer"]]
    browser_box = [max(xs) - min(xs), max(ys) - min(ys),
                   (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2]
    print(f"server  fit_box (unused by the UI) : {out.get('fit_box')}")
    print(f"browser fit_box (sketcher.js:417)  : "
          f"{[round(v, 3) for v in browser_box]}")

    d = client.post("/api/trace-png", json={
        "png_base64": png, "entities_only": True,
        "fit_box": browser_box}).json()
    n, tot, worst = off_disc(d["entities"], radius)
    print(f"\nTrace Image button  (entities_only + the BROWSER's box):")
    print(f"  {n} of {tot} traced points are off the {radius:g} mm disc, "
          f"the furthest {worst:.2f} mm from the centre")

    d2 = client.post("/api/trace-png", json={
        "png_base64": png, "entities_only": True,
        "fit_box": out["fit_box"]}).json()
    n2, tot2, worst2 = off_disc(d2["entities"], radius)
    print(f"same button if it sent the SERVER's box:")
    print(f"  {n2} of {tot2} traced points are off the disc, "
          f"the furthest {worst2:.2f} mm from the centre")


if __name__ == "__main__":
    main()
