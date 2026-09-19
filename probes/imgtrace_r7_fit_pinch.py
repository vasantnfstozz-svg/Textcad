"""ROUND SEVEN — the fit's rescale, end to end through /api/trace-png.

`probes/imgtrace_r7_fit_shrink.py` measures `s` at the door: on a 5 x 5 mm
face the picture tests/test_trace_fit.py already uses for "the aspect never
settles" is traced at 50 mm and then SHRUNK by s = 0.0902 — and one of its
eleven polygons comes back crossing itself.

This runs the same thing through the HTTP door the sketcher uses and puts the
entities the browser is handed to the kernel.

Run:  C:/Python314/python.exe probes/imgtrace_r7_fit_pinch.py
"""
from __future__ import annotations

import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402
from imgtrace_r7_fit_shrink import ladder                   # noqa: E402
from imgtrace_r7_rescale import closest, crosses            # noqa: E402


def client():
    from fastapi.testclient import TestClient
    import document as dm
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("plate")
    doc.add("base", "plate", {"width": 40, "depth": 40, "thickness": 6}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def build(ents):
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:70]}", None
    bad = inspector.health(solid)
    return (bad[0] if bad else None), float(solid.volume)


def main():
    cl = client()
    for spokes, box in ((6, (5.0, 5.0, 0.0, 0.0)), (14, (5.0, 5.0, 0.0, 0.0)),
                        (6, (6.0, 6.0, 0.0, 0.0)), (6, (4.0, 4.0, 0.0, 0.0))):
        data = ladder(spokes=spokes)
        d = cl.post("/api/trace-png", json={
            "png_base64": base64.b64encode(data).decode(),
            "entities_only": True, "fit_box": list(box)}).json()
        if d.get("error"):
            print(f"  {spokes} spokes into {box[0]:g} x {box[1]:g} mm: "
                  f"REFUSED {d['error']}")
            continue
        ents = d["entities"]
        x = crosses(ents)
        g = closest(ents) if len(ents) > 1 else float("nan")
        bad, vol = build(ents)
        print(f"  {spokes} spokes into {box[0]:g} x {box[1]:g} mm: "
              f"{len(ents)} polygons, {x} of them CROSS THEMSELVES, "
              f"closest pair {g:.9f} mm -> {bad or 'healthy'} vol {vol}")
        print(f"      trace_info {d['trace_info']}")
        # ...and the same art traced WITHOUT the fit, for comparison
        h = d["trace_info"]["height_mm"]
        ents2, _i = imgtrace.image_to_entities(data, height_mm=max(1.0, h))
        bad2, vol2 = build(ents2)
        print(f"      the same art traced at {max(1.0, h):.2f} mm with no "
              f"fit: {crosses(ents2)} crossing -> {bad2 or 'healthy'} "
              f"vol {vol2}")


if __name__ == "__main__":
    main()
