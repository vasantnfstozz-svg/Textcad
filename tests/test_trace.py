"""imgtrace: raster image -> sketch polygon entities, end to end.

Covers the four failure classes the rocky-keychain designs actually hit:
alpha vs luminance masks, holes, split pieces needing bridges, and the
channel absorb for tool-width recesses — plus the full path into a real
extruded, healthy solid.
"""
import cv2
import numpy as np
import pytest

import imgtrace
import inspector
import sketch as sk


def _png(canvas):
    ok, buf = cv2.imencode(".png", canvas)
    assert ok
    return buf.tobytes()


def _donut_rgba(size=400):
    """Filled circle with a hole, on a transparent background."""
    img = np.zeros((size, size, 4), np.uint8)
    cv2.circle(img, (200, 200), 150, (10, 10, 10, 255), -1)
    cv2.circle(img, (200, 200), 60, (0, 0, 0, 0), -1)
    return img


def test_donut_alpha_scaled_with_hole():
    ents, info = imgtrace.image_to_entities(_png(_donut_rgba()), height_mm=50)
    assert ents[0]["mode"] == "add"
    assert any(e["mode"] == "subtract" for e in ents)
    assert info["holes"] == 1 and info["contours"] == 1
    # scaled to the requested height (circle -> 50mm across)
    assert abs(info["height_mm"] - 50) < 0.5
    assert abs(info["width_mm"] - 50) < 0.5


def test_luminance_polarity_black_on_white():
    """No alpha: dark art on white must come out as the foreground."""
    img = np.full((300, 300, 3), 255, np.uint8)
    cv2.rectangle(img, (100, 50), (200, 250), (0, 0, 0), -1)
    ents, info = imgtrace.image_to_entities(_png(img), height_mm=40)
    assert info["contours"] == 1 and info["holes"] == 0
    assert abs(info["height_mm"] - 40) < 0.5
    assert abs(info["width_mm"] - 20) < 0.5          # 100x200px -> 20x40mm


def test_split_pieces_stay_separate_unless_asked():
    """Detailed art is legitimately many pieces: default keeps them apart;
    connect_pieces=True welds them for single-piece pendants."""
    img = np.zeros((300, 300, 4), np.uint8)
    cv2.circle(img, (150, 100), 60, (0, 0, 0, 255), -1)
    cv2.circle(img, (150, 230), 60, (0, 0, 0, 255), -1)   # 10px gap
    ents, info = imgtrace.image_to_entities(_png(img), height_mm=50)
    assert info["contours"] == 2
    ents, info = imgtrace.image_to_entities(_png(img), height_mm=50,
                                            connect_pieces=True)
    assert info["contours"] == 1


def test_high_res_traced_small_keeps_detail():
    """Reported 2026-08-21 (idol trace 'broken so much'): simplification used
    to scale with the TARGET size, so a 2000px image traced to 20mm was
    simplified at ~15px and detail died. Fidelity is now resolution-bound."""
    img = np.zeros((2000, 1200, 4), np.uint8)
    # a comb: body + 12 teeth 30px wide with 30px gaps — fine detail
    cv2.rectangle(img, (100, 100), (1100, 800), (0, 0, 0, 255), -1)
    for i in range(12):
        x0 = 120 + i * 80
        cv2.rectangle(img, (x0, 800), (x0 + 30, 1800), (0, 0, 0, 255), -1)
    ents, info = imgtrace.image_to_entities(_png(img), height_mm=20)
    assert info["contours"] == 1
    # every tooth survives: the outline must weave 12 teeth -> lots of
    # near-vertical excursions; a bulldozed trace has far fewer points
    pts = ents[0]["points"]
    ys = [p[1] for p in pts]
    deep = sum(1 for p in pts if p[1] < min(ys) + 1.0)
    assert deep >= 24, f"teeth lost: only {deep} deep points, {len(pts)} total"
    # and tiny separate ornaments survive too (a 14px dot = 0.14mm at 20mm)
    img2 = np.zeros((2000, 1200, 4), np.uint8)
    cv2.circle(img2, (600, 1000), 500, (10, 10, 10, 255), -1)
    cv2.circle(img2, (600, 200), 40, (10, 10, 10, 255), -1)   # 0.8mm ornament
    ents2, info2 = imgtrace.image_to_entities(_png(img2), height_mm=20)
    assert info2["contours"] == 2, "small ornament was dropped"


def test_channel_absorb_fills_narrow_recess():
    """A slot narrower than the tool disappears when min_channel_mm is set."""
    img = np.zeros((400, 400, 4), np.uint8)
    cv2.rectangle(img, (100, 100), (300, 300), (0, 0, 0, 255), -1)
    cv2.rectangle(img, (195, 100), (205, 200), (0, 0, 0, 0), -1)  # 10px slot
    # artwork bbox is the 200px square -> 50mm; slot 10px = 2.5mm;
    # absorb anything under 3mm -> slot filled, full square remains
    ents, _ = imgtrace.image_to_entities(_png(img), height_mm=50,
                                         min_channel_mm=3.0)
    face = sk.make_sketch("XY", 0, ents)
    assert abs(face.area - 50 * 50) < 50 * 50 * 0.02


def test_traced_sketch_extrudes_to_healthy_solid():
    ents, _ = imgtrace.image_to_entities(_png(_donut_rgba()), height_mm=30)
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 3.0)
    assert inspector.health(solid) == []
    m = inspector.measure(solid)
    # pi*(15^2 - 6^2) * 3 within a few % (polygonised circles)
    assert m["volume"] == pytest.approx(np.pi * (15**2 - 6**2) * 3, rel=0.03)


def test_garbage_input_raises():
    with pytest.raises(ValueError):
        imgtrace.image_to_entities(b"not an image at all", height_mm=50)


def test_api_trace_png_endpoint():
    """Upload through the HTTP API -> a new sketch feature in the doc."""
    import base64
    from fastapi.testclient import TestClient
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    client = TestClient(studio.app)
    b64 = base64.b64encode(_png(_donut_rgba())).decode()
    d = client.post("/api/trace-png", json={
        "png_base64": "data:image/png;base64," + b64,
        "feature_id": "logo", "height_mm": 42}).json()
    assert "error" not in d or not d["error"]
    assert d["trace_info"]["feature_id"] == "logo"
    assert abs(d["trace_info"]["height_mm"] - 42) < 0.5
    ids = [f["id"] for f in d["features"]]
    assert "logo" in ids
    logo = next(f for f in d["features"] if f["id"] == "logo")
    assert logo["op"] == "sketch" and logo["status"] == "ok"
    # duplicate id gets uniquified, not rejected
    d2 = client.post("/api/trace-png", json={
        "png_base64": b64, "feature_id": "logo", "height_mm": 20}).json()
    assert d2["trace_info"]["feature_id"] == "logo-2"


def test_api_trace_png_fits_selected_face():
    """A face pick makes the trace land ON that face (sketch_on_face), auto-
    scaled to fit_margin x the face bbox — height-bound for tall art, width-
    bound for wide art — and centred on the face (user request 2026-09-01)."""
    import base64
    from fastapi.testclient import TestClient
    import document as dm
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("plate")
    doc.add("base", "plate", {"width": 80, "depth": 40, "thickness": 10}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    client = TestClient(studio.app)

    # square art on the 80x40 top face -> height-bound: 0.9 * 40 = 36 x 36
    b64 = base64.b64encode(_png(_donut_rgba())).decode()
    d1 = client.post("/api/trace-png", json={
        "png_base64": b64, "feature_id": "logo",
        "face_center": [0, 0, 5], "face_normal": [0, 0, 1],
        "body_feature_id": "base"}).json()
    assert not d1.get("error")
    logo = next(f for f in d1["features"] if f["id"] == "logo")
    assert logo["op"] == "sketch_on_face" and logo["status"] == "ok"
    assert logo["inputs"] == ["base"]
    assert d1["trace_info"]["height_mm"] == pytest.approx(36, abs=0.5)
    assert d1["trace_info"]["width_mm"] == pytest.approx(36, abs=0.5)
    assert d1["trace_info"]["face_mm"] == [80.0, 40.0]
    # centred on the face (the plate's top-face frame centre is 0,0)
    xs = [e["x"] + p[0] for e in logo["params"]["entities"]
          for p in e["points"]]
    ys = [e["y"] + p[1] for e in logo["params"]["entities"]
          for p in e["points"]]
    assert (max(xs) + min(xs)) / 2 == pytest.approx(0, abs=0.5)
    assert (max(ys) + min(ys)) / 2 == pytest.approx(0, abs=0.5)
    # and it never overflows the face
    assert max(xs) <= 40 and min(xs) >= -40
    assert max(ys) <= 20 and min(ys) >= -20

    # 5:1 wide art on the same face -> width-bound: 0.9 * 80 = 72 x 14.4
    img = np.zeros((240, 1040, 4), np.uint8)
    cv2.rectangle(img, (20, 20), (1019, 219), (0, 0, 0, 255), -1)
    b64w = base64.b64encode(_png(img)).decode()
    d2 = client.post("/api/trace-png", json={
        "png_base64": b64w, "feature_id": "wide",
        "face_center": [0, 0, 5], "face_normal": [0, 0, 1],
        "body_feature_id": "base"}).json()
    assert not d2.get("error")
    assert d2["trace_info"]["width_mm"] == pytest.approx(72, abs=1.0)
    assert d2["trace_info"]["height_mm"] == pytest.approx(14.4, abs=0.5)

    # entities_only: the sketcher inserting into the OPEN sketch — traced
    # entities come back fitted to the given box, and NO feature is created
    n_before = len(client.get("/api/doc").json()["features"])
    d5 = client.post("/api/trace-png", json={
        "png_base64": b64, "entities_only": True,
        "fit_box": [60, 30, 5, -2]}).json()
    assert not d5.get("error")
    assert "features" not in d5           # no doc mutation, no version
    ents = d5["entities"]
    assert ents and ents[0]["mode"] == "add"
    exs = [e["x"] + p[0] for e in ents for p in e["points"]]
    eys = [e["y"] + p[1] for e in ents for p in e["points"]]
    # square art in a 60x30 box at (5,-2) -> 0.9*30 = 27 tall, centred there
    assert max(eys) - min(eys) == pytest.approx(27, abs=0.5)
    assert (max(exs) + min(exs)) / 2 == pytest.approx(5, abs=0.5)
    assert (max(eys) + min(eys)) / 2 == pytest.approx(-2, abs=0.5)
    assert d5["trace_info"].get("rotated") is False
    assert len(client.get("/api/doc").json()["features"]) == n_before

    # WIDE art in a TALL box auto-rotates 90° to run along the long axis
    # (user report 2026-09-01: the logo came in "vertical position, its no
    # use" — fitted tiny instead of turning). 5:1 art, 30x60 box: unrotated
    # caps at 0.9*30/5 = 5.4mm tall; rotated it runs 0.9*60 = 54mm long.
    d6 = client.post("/api/trace-png", json={
        "png_base64": b64w, "entities_only": True,
        "fit_box": [30, 60, 0, 0]}).json()
    assert not d6.get("error")
    assert d6["trace_info"]["rotated"] is True
    exs = [e["x"] + p[0] for e in d6["entities"] for p in e["points"]]
    eys = [e["y"] + p[1] for e in d6["entities"] for p in e["points"]]
    assert max(eys) - min(eys) == pytest.approx(54, abs=1.0)   # long side -> Y
    assert max(exs) - min(exs) == pytest.approx(10.8, abs=0.5)
    assert (max(exs) + min(exs)) / 2 == pytest.approx(0, abs=0.5)
    assert (max(eys) + min(eys)) / 2 == pytest.approx(0, abs=0.5)
    assert d6["trace_info"]["width_mm"] == pytest.approx(10.8, abs=0.5)
    assert d6["trace_info"]["height_mm"] == pytest.approx(54, abs=1.0)

    # a curved face refuses with an honest message, doc unharmed (a ball has
    # exactly one face and it is curved — no flat face to steer to)
    doc2 = dm.Document("ball")
    doc2.add("base", "ball", {"radius": 30}, [])
    studio._new_tab(doc2)
    studio._rebuild_and_mesh()
    d4 = client.post("/api/trace-png", json={
        "png_base64": b64, "feature_id": "bad",
        "face_center": [30, 0, 0], "face_normal": [1, 0, 0],
        "body_feature_id": "base"}).json()
    assert d4.get("error") and "FLAT" in d4["error"]
    assert not any(f["id"] == "bad" for f in d4["features"])
