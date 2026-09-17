"""Does the inscribed fit box land art IN a hole?

`_inscribed_box` rasterises the OUTER wire only — "HOLES are deliberately
ignored: art crossing a bolt hole is ordinary". Measure what that means on a
washer face (a big central hole) and on a plate with a big central pocket,
against a plate with four small bolt holes (the case the rule is defending).

Run: C:/Python314/python.exe probes/imgtrace_fitbox_hole_probe.py
"""
import base64
import sys
import os

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import document as dm            # noqa: E402
import studio                    # noqa: E402


def _png(mask):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _square_png(size=400, pad=30):
    m = np.zeros((size, size), np.uint8)
    m[pad:size - pad, pad:size - pad] = 1
    return _png(m)


def _tab(doc):
    from fastapi.testclient import TestClient
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def washer(outer=30.0, inner=20.0, thick=8.0):
    doc = dm.Document("washer")
    doc.add("base", "tube", {"outer_radius": outer, "inner_radius": inner,
                             "height": thick}, [])
    return _tab(doc)


def pocket_plate(w=120.0, d=80.0, t=12.0, pw=90.0, pd=55.0):
    doc = dm.Document("pocket")
    doc.add("base", "plate", {"width": w, "depth": d, "thickness": t}, [])
    doc.add("cut_tool", "plate", {"width": pw, "depth": pd,
                                  "thickness": t * 3}, [])
    doc.add("plate_pocket", "cut", {}, ["base", "cut_tool"])
    return _tab(doc)


def bolted_plate(w=120.0, d=80.0, t=12.0, r=2.5):
    doc = dm.Document("bolted")
    doc.add("base", "plate", {"width": w, "depth": d, "thickness": t}, [])
    prev = "base"
    for k, (bx, by) in enumerate([(-50, -30), (50, -30), (-50, 30), (50, 30)]):
        doc.add(f"bolt{k}", "disc", {"radius": r, "thickness": t * 3}, [])
        doc.add(f"bolt{k}_at", "move", {"x": bx, "y": by, "z": 0},
                [f"bolt{k}"])
        doc.add(f"drill{k}", "cut", {}, [prev, f"bolt{k}_at"])
        prev = f"drill{k}"
    return _tab(doc)


def inscribed_with_holes(outer, holes):
    """What `_inscribed_box` would answer if the face's HOLES were punched out
    of the grid it rasterises — the same algorithm, two extra fillPoly calls."""
    xs = [float(p[0]) for p in outer]
    ys = [float(p[1]) for p in outer]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = x1 - x0, y1 - y0
    cell = max(bw, bh) / float(studio._FIT_CELLS)

    def grid_pts(ring):
        return np.array([[[round((float(p[0]) - x0) / cell),
                           round((float(p[1]) - y0) / cell)]
                          for p in ring]], np.int32)

    grid = np.zeros((max(1, round(bh / cell)) + 1,
                     max(1, round(bw / cell)) + 1), np.uint8)
    cv2.fillPoly(grid, grid_pts(list(zip(xs, ys))), 1)
    for hole in holes:
        cv2.fillPoly(grid, grid_pts(hole), 0)
    inside = cv2.erode(grid, np.ones((3, 3), np.uint8),
                       borderType=cv2.BORDER_CONSTANT, borderValue=0)
    area, i0, i1, j0, j1 = studio._biggest_all_true_block(inside.astype(bool))
    if area <= 0:
        return None
    ax0, ax1 = x0 + i0 * cell, x0 + i1 * cell
    ay0, ay1 = y0 + j0 * cell, y0 + j1 * cell
    return [round(ax1 - ax0, 2), round(ay1 - ay0, 2),
            round((ax0 + ax1) / 2, 2), round((ay0 + ay1) / 2, 2)]


def report(name, client, centre):
    d = client.post("/api/face-outline", json={
        "face_center": list(centre), "face_normal": [0, 0, 1]}).json()
    if not d.get("planar"):
        print(f"{name}: not planar -> {d.get('error')}")
        return
    box = d.get("fit_box")
    holes = [np.array(h, np.float32) for h in d.get("holes") or []]
    print(f"\n=== {name} ===")
    print(f"  outer bbox : "
          f"{max(p[0] for p in d['outer']) - min(p[0] for p in d['outer']):.2f}"
          f" x "
          f"{max(p[1] for p in d['outer']) - min(p[1] for p in d['outer']):.2f}")
    print(f"  fit_box    : {box}   (holes ignored)")
    print(f"  holes punched out: "
          f"{inscribed_with_holes(d['outer'], d.get('holes') or [])}")
    if box and holes:
        w, h, cx, cy = box
        corners = [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
                   (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2),
                   (cx, cy)]
        for hi, hole in enumerate(holes):
            ins = [cv2.pointPolygonTest(hole, (float(x), float(y)), True)
                   for x, y in corners]
            if max(ins) > 0:
                print(f"  hole {hi}: {sum(1 for v in ins if v > 0)} of 5 fit-box"
                      f" reference points are INSIDE it "
                      f"(deepest {max(ins):.2f} mm in)")
    # now trace real art onto the face and measure how much of it is over air
    t = client.post("/api/trace-png", json={
        "png_base64": base64.b64encode(_square_png()).decode(),
        "face_center": list(centre), "face_normal": [0, 0, 1],
        "feature_id": f"art-{name}"}).json()
    if t.get("error"):
        print(f"  trace refused: {t['error']}")
        return
    feat = [f for f in studio._doc().features
            if f.id == t["trace_info"]["feature_id"]][0]
    pts = [(e["x"] + p[0], e["y"] + p[1])
           for e in feat.params["entities"] for p in e["points"]]
    outer = np.array(d["outer"], np.float32)
    off_face = sum(1 for x, y in pts
                   if cv2.pointPolygonTest(outer, (float(x), float(y)),
                                           False) < 0)
    in_hole = 0
    for x, y in pts:
        for hole in holes:
            if cv2.pointPolygonTest(hole, (float(x), float(y)), False) > 0:
                in_hole += 1
                break
    print(f"  traced art : {t['trace_info']['width_mm']} x "
          f"{t['trace_info']['height_mm']} mm, {len(pts)} points")
    print(f"  off the outline : {off_face} of {len(pts)}")
    print(f"  INSIDE a hole   : {in_hole} of {len(pts)}")
    # how much of the ART's AREA sits over material? sample its own bbox
    art = np.array(pts, np.float32)
    lo, hi = art.min(axis=0), art.max(axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 120),
                         np.linspace(lo[1], hi[1], 120))
    on_art = on_mat = 0
    for x, y in zip(gx.ravel(), gy.ravel()):
        if cv2.pointPolygonTest(art, (float(x), float(y)), False) < 0:
            continue
        on_art += 1
        if cv2.pointPolygonTest(outer, (float(x), float(y)), False) < 0:
            continue
        if any(cv2.pointPolygonTest(h, (float(x), float(y)), False) > 0
               for h in holes):
            continue
        on_mat += 1
    if on_art:
        print(f"  art area over MATERIAL: {100.0 * on_mat / on_art:.1f}% "
              f"(over air: {100.0 * (on_art - on_mat) / on_art:.1f}%)")
    # and what the user gets when they extrude it as a boss
    try:
        studio._doc().add("boss", "extrude",
                          {"amount": 3.0},
                          [t["trace_info"]["feature_id"]])
        studio._rebuild_and_mesh()
        part = studio._doc().result()
        errs = [(f.id, f.status, f.problems, f.pieces)
                for f in studio._doc().features if f.status != "ok"]
        print(f"  extruded boss -> {len(part.solids())} solid(s), "
              f"{part.volume:.2f} mm3   errors={errs}")
    except Exception as exc:                                # noqa: BLE001
        print(f"  extrude failed: {type(exc).__name__}: {str(exc)[:90]}")


def hole_grid(w=120.0, d=80.0, t=12.0, r=2.5, nx=6, ny=4):
    """the nightmare for a hole-aware box: a face peppered with holes."""
    doc = dm.Document("grid")
    doc.add("base", "plate", {"width": w, "depth": d, "thickness": t}, [])
    prev = "base"
    k = 0
    for i in range(nx):
        for j in range(ny):
            bx = -w / 2 + w * (i + 0.5) / nx
            by = -d / 2 + d * (j + 0.5) / ny
            doc.add(f"h{k}", "disc", {"radius": r, "thickness": t * 3}, [])
            doc.add(f"h{k}_at", "move", {"x": bx, "y": by, "z": 0}, [f"h{k}"])
            doc.add(f"d{k}", "cut", {}, [prev, f"h{k}_at"])
            prev = f"d{k}"
            k += 1
    return _tab(doc)


def timing():
    import time
    client = washer()
    d = client.post("/api/face-outline", json={
        "face_center": [0, 0, 8], "face_normal": [0, 0, 1]}).json()
    t0 = time.perf_counter()
    for _ in range(20):
        studio._inscribed_box(d["outer"])
    t1 = time.perf_counter()
    for _ in range(20):
        inscribed_with_holes(d["outer"], d["holes"])
    t2 = time.perf_counter()
    print(f"\n_inscribed_box   {1000 * (t1 - t0) / 20:.2f} ms/call")
    print(f"holes punched    {1000 * (t2 - t1) / 20:.2f} ms/call")


if __name__ == "__main__":
    report("washer 60 od / 40 id", washer(), (0, 0, 8))
    report("plate with a 90x55 pocket", pocket_plate(), (0, 0, 12))
    report("plate with 4 bolt holes", bolted_plate(), (0, 0, 12))
    report("plate peppered with 24 holes", hole_grid(), (0, 0, 12))
    timing()
