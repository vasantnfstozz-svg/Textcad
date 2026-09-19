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


# ---------------------------------------------------------------------------
# REVIEW-QUEUE section 9 (2026-09-17). Every one of these was measured red
# first; the probes are probes/imgtrace_*_probe.py.
# ---------------------------------------------------------------------------


def _self_crossings(pts):
    """proper self-crossings of a closed polygon, touches included"""
    n = len(pts)
    a = np.asarray(pts, float)
    b = np.roll(a, -1, axis=0)
    r = b - a
    hits = 0
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            den = r[i, 0] * r[j, 1] - r[i, 1] * r[j, 0]
            if abs(den) < 1e-15:
                continue
            d = a[j] - a[i]
            t = (d[0] * r[j, 1] - d[1] * r[j, 0]) / den
            u = (d[0] * r[i, 1] - d[1] * r[i, 0]) / den
            if 0 <= t <= 1 and 0 <= u <= 1:
                hits += 1
    return hits


def test_tight_crop_art_is_not_traced_inside_out():
    """A logo cropped to its own ink (what every image editor's "trim" does,
    and what designs/cam-cover-plaque.py does with PIL) covers MORE than half
    the picture. The polarity rule used to call the MINORITY the artwork, so
    a 40mm disc came back as its own NEGATIVE — the four corners, 343.5 mm2
    of a true 1256.6 — status ok, nothing said (measured 2026-09-17)."""
    img = np.full((400, 400, 3), 255, np.uint8)
    cv2.circle(img, (200, 200), 199, (0, 0, 0), -1)      # 78% ink
    ents, info = imgtrace.image_to_entities(_png(img), height_mm=40)
    area = sk.make_sketch("XY", 0, ents).area
    assert area == pytest.approx(np.pi * 20 ** 2, rel=0.03), (
        f"traced {area:.1f} mm2; the disc is {np.pi * 400:.1f}, "
        f"its negative {1600 - np.pi * 400:.1f}")
    assert info["contours"] == 1 and info["holes"] == 0


def test_light_art_on_a_dark_ground_still_traces_the_art():
    """The other direction of the same rule: inverse-video artwork (white on
    black) is the MAJORITY here and must still be the thing traced."""
    img = np.zeros((400, 400, 3), np.uint8)
    cv2.circle(img, (200, 200), 199, (255, 255, 255), -1)
    ents, _ = imgtrace.image_to_entities(_png(img), height_mm=40)
    assert sk.make_sketch("XY", 0, ents).area == pytest.approx(
        np.pi * 20 ** 2, rel=0.03)


def _specked_art(speck):
    """A TALL glyph (1:5) in a square picture, optionally with a 2x2 speck of
    dirt at each side — well under the 0.25mm floor image_to_entities drops,
    but enough to make the RAW mask read 1.15 wide instead of 0.20."""
    img = np.zeros((1200, 1200, 4), np.uint8)
    cv2.rectangle(img, (580, 100), (620, 1100), (0, 0, 0, 255), -1)
    cv2.rectangle(img, (500, 100), (700, 200), (0, 0, 0, 255), -1)
    if speck:
        cv2.rectangle(img, (20, 600), (21, 601), (0, 0, 0, 255), -1)
        cv2.rectangle(img, (1170, 600), (1171, 601), (0, 0, 0, 255), -1)
    return _png(img)


def test_artwork_aspect_ignores_the_specks_the_trace_removes():
    """artwork_aspect decides the fit height AND the 90-degree auto-rotate,
    and its docstring promises the mask image_to_entities traces. It read the
    RAW mask, so two 3-pixel specks in the corners moved it from 0.20 to 1.00
    while the traced art was identical (measured 2026-09-17)."""
    clean, dirty = _specked_art(False), _specked_art(True)
    # the traced art is the same either way ...
    assert (imgtrace.image_to_entities(clean, 50)[1]["width_mm"]
            == imgtrace.image_to_entities(dirty, 50)[1]["width_mm"])
    # ... so the aspect the fit is computed from must be the same too
    assert imgtrace.artwork_aspect(dirty) == pytest.approx(
        imgtrace.artwork_aspect(clean), rel=0.02)


def test_a_speck_cannot_flip_the_90_degree_auto_rotate():
    """End to end: the same tall art on a 120x40 face came in 107.9 x 21.6mm
    lying along the face, and 7.2 x 35.96mm standing up — a ninth of the
    area — when two 3-pixel specks were added (measured 2026-09-17)."""
    import base64
    from fastapi.testclient import TestClient
    import document as dm
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("plate")
    doc.add("base", "plate", {"width": 120, "depth": 40, "thickness": 10}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    client = TestClient(studio.app)

    def fitted(speck):
        d = client.post("/api/trace-png", json={
            "png_base64": base64.b64encode(_specked_art(speck)).decode(),
            "entities_only": True, "fit_box": [120, 40, 0, 0]}).json()
        assert not d.get("error"), d.get("error")
        xs = [e["x"] + p[0] for e in d["entities"] for p in e["points"]]
        ys = [e["y"] + p[1] for e in d["entities"] for p in e["points"]]
        return (d["trace_info"]["rotated"],
                max(xs) - min(xs), max(ys) - min(ys))

    clean, dirty = fitted(False), fitted(True)
    assert clean[0] is True, "tall art on a wide face must lie down"
    assert dirty[0] is clean[0], "a speck flipped the auto-rotate"
    assert dirty[1] == pytest.approx(clean[1], abs=0.5)
    assert dirty[2] == pytest.approx(clean[2], abs=0.5)


def test_traced_outline_never_crosses_itself():
    """OpenCV walks out and back along a one-pixel whisker, and Douglas-
    Peucker then shortcuts one side past the other: a comb of 1px teeth came
    out with 26 self-crossings in ONE outline (measured 2026-09-17), which is
    a polygon sketch.py has no business being handed."""
    img = np.zeros((300, 300, 4), np.uint8)
    cv2.rectangle(img, (40, 150), (260, 250), (0, 0, 0, 255), -1)
    for i in range(20):
        img[60:150, 50 + i * 10] = (0, 0, 0, 255)
    ents, _ = imgtrace.image_to_entities(_png(img), height_mm=30)
    for k, e in enumerate(ents):
        assert _self_crossings(e["points"]) == 0, f"entity {k} crosses itself"
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert inspector.health(solid) == []


def test_art_too_fine_for_the_target_size_says_so():
    """height_mm=1 on detailed art left NOTHING above the 0.25mm speckle
    floor and the user was handed numpy's "zero-size array to reduction
    operation minimum which has no identity" (measured 2026-09-17)."""
    img = np.zeros((2000, 2000, 4), np.uint8)
    for i in range(10):
        cv2.rectangle(img, (100 + i * 180, 100), (160 + i * 180, 1900),
                      (0, 0, 0, 255), -1)
    with pytest.raises(ValueError) as ex:
        imgtrace.image_to_entities(_png(img), height_mm=1.0)
    msg = str(ex.value)
    assert "array" not in msg and "reduction" not in msg, msg
    assert "0.25" in msg or "too fine" in msg or "bigger" in msg, msg


def test_holes_inside_holes_alternate_add_and_subtract():
    """Nesting deeper than two: ring, island, hole in the island. RETR_CCOMP
    is a two-level hierarchy, so this is worth locking down."""
    img = np.zeros((900, 900, 4), np.uint8)
    cv2.circle(img, (450, 450), 400, (0, 0, 0, 255), -1)
    cv2.circle(img, (450, 450), 300, (0, 0, 0, 0), -1)
    cv2.circle(img, (450, 450), 200, (0, 0, 0, 255), -1)
    cv2.circle(img, (450, 450), 100, (0, 0, 0, 0), -1)
    ents, info = imgtrace.image_to_entities(_png(img), height_mm=60)
    assert [e["mode"] for e in ents] == ["add", "subtract", "add", "subtract"]
    want = np.pi * (30 ** 2 - 22.5 ** 2 + 15 ** 2 - 7.5 ** 2)
    assert sk.make_sketch("XY", 0, ents).area == pytest.approx(want, rel=0.03)
    assert info["holes"] == 2 and info["contours"] == 2


# ---------------------------------------------------------------------------
# REVIEW-QUEUE section 9, ROUND TWO (2026-09-17): the fix pass's own new code.
# Each was measured red first; the probes are probes/imgtrace_r2_*.py.
# ---------------------------------------------------------------------------


def _ink_mm2(mask, h_mm):
    """what the picture's ink is worth in mm2 once scaled to h_mm tall"""
    ys, _ = np.where(mask)
    mm_px = h_mm / (int(ys.max()) - int(ys.min()) + 1)
    return float((mask > 0).sum()) * mm_px * mm_px


def _alpha_png(mask):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    return _png(img)


def _lettered_sheet(frame_px):
    """Five dark letters on paper, inside a dark edge frame_px thick — a
    scan's platen edge, a printed rule box, or the one-pixel border an
    exporter leaves behind."""
    img = np.full((400, 400, 3), 255, np.uint8)
    for i in range(5):
        cv2.rectangle(img, (60 + i * 60, 160), (95 + i * 60, 240),
                      (0, 0, 0), -1)
    cv2.rectangle(img, (0, 0), (399, 399), (0, 0, 0), frame_px)
    return img


@pytest.mark.parametrize("frame_px", [1, 5, 12])
def test_a_thin_dark_edge_is_not_a_dark_background(frame_px):
    """Round one made the background "whichever side fills the picture's
    outer BORDER" — read one pixel deep. A scan's dark platen edge, a printed
    rule box, even a 1 px frame, all fill that pixel, so the paper became the
    artwork and the tracer produced the NEGATIVE: ONE contour with five
    letter-shaped holes, 1435.4 mm2 (measured 2026-09-17, round two). That is
    the same P0 round one fixed, through the other door."""
    ents, info = imgtrace.image_to_entities(
        _png(_lettered_sheet(frame_px)), height_mm=40)
    # the five letters come back as MATERIAL. The frame ring is ink too, so
    # it rides along as a sixth piece with its own inside as the one hole -
    # what the pre-4c9ea32 rule gave, to the contour: 6 pieces, 1 hole.
    assert info["contours"] >= 5 and info["holes"] <= 1, (
        f"{frame_px} px frame: {info['contours']} pieces and "
        f"{info['holes']} holes — the paper traced as a slab with "
        f"letter-shaped holes is the NEGATIVE of the art")
    area = sk.make_sketch("XY", 0, ents).area
    assert area < 700, f"{area:.1f} mm2 is the paper, not the lettering"


def test_a_dark_ground_that_is_not_a_frame_still_wins():
    """The guard must not undo round one: inverse-video art (white on black)
    has a genuinely dark ground, and a white disc that nearly fills its
    picture is still the artwork."""
    for r in (110, 190):
        img = np.zeros((400, 400, 3), np.uint8)
        cv2.circle(img, (200, 200), r, (255, 255, 255), -1)
        ents, _ = imgtrace.image_to_entities(_png(img), height_mm=40)
        assert sk.make_sketch("XY", 0, ents).area == pytest.approx(
            np.pi * 20 ** 2, rel=0.04), f"radius {r}"


def _dumbbell(neck_px):
    """Two discs joined by a bar neck_px wide — a barbell pendant, and what
    any hairline join looks like at raster resolution."""
    m = np.zeros((420, 820), np.uint8)
    cv2.circle(m, (170, 210), 130, 1, -1)
    cv2.circle(m, (650, 210), 130, 1, -1)
    cv2.line(m, (170, 210), (650, 210), 1, neck_px)
    return m


def test_uncross_keeps_both_halves_of_a_pinched_outline():
    """_uncross cut the SMALLER loop off at every self-crossing, and round
    one's claim was "the loop thrown away is the width of eps — under a tenth
    of a millimetre of artwork". Douglas-Peucker shortcuts a ONE-PIXEL join
    into a real crossing, and there both loops are a whole disc: 1237.16 mm2
    came back of a true 2498.45, healthy and green, no warning (measured
    2026-09-17, round two)."""
    m = _dumbbell(1)
    ents, _ = imgtrace.image_to_entities(_alpha_png(m), height_mm=40)
    area = sk.make_sketch("XY", 0, ents).area
    want = _ink_mm2(m, 40.0)
    assert area == pytest.approx(want, rel=0.05), (
        f"traced {area:.2f} mm2 of a true {want:.2f} — half the artwork "
        f"is one of the two discs")


def test_a_pinched_outline_still_builds_a_healthy_solid():
    """Keeping both loops must not hand OpenCASCADE a pinch instead."""
    for neck in (1, 2, 3):
        ents, _ = imgtrace.image_to_entities(
            _alpha_png(_dumbbell(neck)), height_mm=40)
        for k, e in enumerate(ents):
            assert _self_crossings(e["points"]) == 0, f"neck {neck}, ent {k}"
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
        assert inspector.health(solid) == [], f"neck {neck}"


def _dotted_sheet(speck):
    m = np.zeros((3000, 1200), np.uint8)
    for i in range(5):
        cv2.rectangle(m, (200 + i * 180, 1400), (230 + i * 180, 1430), 1, -1)
    if speck:
        m[40:42, 40:42] = 1
    return m


def test_a_speck_cannot_raise_the_speckle_floor():
    """Round one's P1 was "a speck of dirt decided the fit"; its own
    _traceable still measures `h_all` on the RAW mask, and h_all is what the
    0.25 mm floor is computed from. Five pieces 9.7 mm across were REFUSED
    outright — "every piece of this artwork would be under 0.25 mm at 10 mm
    tall" — because of one 2x2 speck in the corner (measured 2026-09-17)."""
    info = imgtrace.image_to_entities(
        _alpha_png(_dotted_sheet(False)), height_mm=10)[1]
    assert info["contours"] == 5
    info2 = imgtrace.image_to_entities(
        _alpha_png(_dotted_sheet(True)), height_mm=10)[1]
    assert info2["contours"] == 5, (
        "a 2x2 speck refused or ate artwork 9.7 mm across")
    assert info2["height_mm"] == pytest.approx(info["height_mm"], abs=0.2)


def test_a_speck_cannot_drop_the_dot_of_an_i():
    """The same defect without the refusal: a 1.66 mm dot vanished from art
    that traced fine, silently, 3 contours -> 2 (measured 2026-09-17)."""
    def sheet(speck):
        m = np.zeros((3000, 1200), np.uint8)
        cv2.rectangle(m, (200, 1400), (230, 1560), 1, -1)
        cv2.rectangle(m, (208, 1350), (215, 1357), 1, -1)     # the dot
        cv2.rectangle(m, (300, 1400), (330, 1560), 1, -1)
        if speck:
            m[40:42, 40:42] = 1
        return m
    a = imgtrace.image_to_entities(_alpha_png(sheet(False)), height_mm=50)[1]
    b = imgtrace.image_to_entities(_alpha_png(sheet(True)), height_mm=50)[1]
    assert a["contours"] == 3
    assert b["contours"] == 3, "a 2x2 speck dropped the dot of the i"


def test_art_too_fine_for_the_target_size_still_refuses():
    """The floor fix must not take the P2 refusal away: art that really is
    under 0.25 mm at the asked-for height must still get a sentence."""
    img = np.zeros((2000, 2000, 4), np.uint8)
    for i in range(10):
        cv2.rectangle(img, (100 + i * 180, 100), (160 + i * 180, 1900),
                      (0, 0, 0, 255), -1)
    with pytest.raises(ValueError) as ex:
        imgtrace.image_to_entities(_png(img), height_mm=1.0)
    assert "0.25" in str(ex.value), str(ex.value)


# ---------------------------------------------------------------------------
# REVIEW-QUEUE section 9, ROUND THREE (2026-09-17): round two's own new code.
# Round two started reading the picture's border PAST a thin shell. A shell
# of INK at the edge really is an artefact (a scan's platen edge, a printed
# rule box) — but a thin shell of PAPER is the ordinary margin of an exported
# logo, and reading past it turns art into its negative. Measured first in
# probes/imgtrace_r3_negative.py.
# ---------------------------------------------------------------------------


def _padded_plate(size, pad, n=3):
    """A rectangular part silhouette with round holes and a UNIFORM light
    pad — what `img.crop(getbbox())` plus any padding gives, and the shape
    the Trace Image button exists for."""
    img = np.full((size, size, 3), 255, np.uint8)
    cv2.rectangle(img, (pad, pad), (size - 1 - pad, size - 1 - pad),
                  (0, 0, 0), -1)
    step = (size - 2 * pad) // (n + 1)
    for i in range(n):
        for j in range(n):
            cv2.circle(img, (pad + (i + 1) * step, pad + (j + 1) * step),
                       size // 12, (255, 255, 255), -1)
    return img


@pytest.mark.parametrize("size,pad", [(400, 8), (1200, 20), (2400, 50)])
def test_a_light_pad_is_a_margin_not_a_frame(size, pad):
    """Round two reads the border past ANY thin shell, a light one too. A
    light pad is not an artefact, it is the margin every exported logo has,
    and once it is stripped the art's own outer boundary is all ink — so the
    rule says "the ground is dark" and the tracer returns the NEGATIVE. A
    2400 px plate with a 50 px pad traced 440.1 mm2 of a true 1258.0 as ten
    pieces with one hole, green and healthy (measured 2026-09-17, round
    three); round one had it right at 1257.1."""
    ents, info = imgtrace.image_to_entities(
        _png(_padded_plate(size, pad)), height_mm=40)
    assert info["contours"] == 1 and info["holes"] == 9, (
        f"{size} px plate, {pad} px pad: {info['contours']} pieces and "
        f"{info['holes']} holes — the pad traced as a ring round nine discs "
        f"is the NEGATIVE of the plate")
    area = sk.make_sketch("XY", 0, ents).area
    assert area > 1000, f"{area:.1f} mm2 is the pad and the holes, not the plate"


def _scan_sheet(size, band, logo_frac):
    """paper with a dark platen edge and a logo of a given area fraction"""
    img = np.full((size, size, 3), 255, np.uint8)
    r = int(np.sqrt(logo_frac * size * size / np.pi))
    cv2.circle(img, (size // 2, size // 2), r, (0, 0, 0), -1)
    img[:band] = img[-band:] = 0
    img[:, :band] = img[:, -band:] = 0
    return img


@pytest.mark.parametrize("frac", [0.005, 0.002])
def test_a_small_logo_inside_a_scan_edge_is_still_the_artwork(frac):
    """Round two's guard for "is there anything inside the shell to read" is
    max(64 px, 1% OF THE PICTURE), so its own headline P0 stayed open for
    small art: an 800 px sheet with a 12 px platen edge and a logo at 0.5%
    of it traced 1587.8 mm2 of a true 102.1 — the paper as a slab with a
    logo-shaped hole — green (measured 2026-09-17, round three). The
    pre-4c9ea32 rule got it right."""
    ents, info = imgtrace.image_to_entities(
        _png(_scan_sheet(800, 12, frac)), height_mm=40)
    area = sk.make_sketch("XY", 0, ents).area
    assert area < 400, (
        f"logo at {frac * 100:.1f}% of the sheet: {area:.1f} mm2 with "
        f"{info['contours']} pieces and {info['holes']} holes is the PAPER, "
        f"not the logo")
    assert info["holes"] <= 1


def _logo_on_a_card(alpha):
    """A dark logo on a white card, saved RGBA with ONE opacity for the whole
    picture — what an exporter writes when a layer's opacity is not 100%.
    The alpha channel carries no silhouette at all: every pixel is the same."""
    img = np.full((300, 400, 4), 255, np.uint8)
    img[:, :, 3] = alpha
    cv2.circle(img, (200, 150), 90, (10, 10, 10, alpha), -1)
    return img


@pytest.mark.parametrize("alpha", [249, 230, 200, 129])
def test_one_flat_opacity_is_not_a_silhouette(alpha):
    """`min(alpha) < 250` was the whole test for "this PNG has a real alpha
    channel", and a picture saved at 95% opacity passes it with an alpha that
    is the SAME everywhere. Every pixel then reads "foreground", so the
    tracer drew the picture's own rectangle and threw the logo away: a 90 px
    disc traced 26.60 x 19.93 mm — the whole 400 x 300 frame — instead of
    19.86 x 19.86 mm, one piece, status ok, nothing said (measured
    2026-09-17, round seven). An alpha channel that does not cut the picture
    in two is not a silhouette; the luminance is."""
    ents, info = imgtrace.image_to_entities(_png(_logo_on_a_card(alpha)),
                                            height_mm=20)
    assert info["width_mm"] == pytest.approx(19.9, abs=0.6), (
        f"alpha {alpha} everywhere: traced {info['width_mm']} x "
        f"{info['height_mm']} mm — that is the picture's own frame, not the "
        f"logo")
    area = sk.make_sketch("XY", 0, ents).area
    assert area == pytest.approx(np.pi * 10 ** 2, rel=0.05), (
        f"alpha {alpha} everywhere: {area:.1f} mm2 is not the disc")


@pytest.mark.parametrize("alpha", [0, 40, 128])
def test_one_flat_transparency_is_not_a_silhouette_either(alpha):
    """The same rule read from the other end: a picture saved at 15% opacity
    has an alpha under the 128 cut everywhere, so the mask came back EMPTY
    and the tracer refused "no artwork found in the image" for a picture
    that plainly has a logo in it."""
    ents, info = imgtrace.image_to_entities(_png(_logo_on_a_card(alpha)),
                                            height_mm=20)
    assert info["width_mm"] == pytest.approx(19.9, abs=0.6)
    assert sk.make_sketch("XY", 0, ents).area == pytest.approx(
        np.pi * 10 ** 2, rel=0.05)


def test_a_real_alpha_channel_still_wins():
    """The guard must not take the alpha away from a picture that really uses
    it: a disc cut out of a transparent background, and a full-bleed picture
    whose only transparent pixels are a one-pixel border."""
    img = np.zeros((300, 400, 4), np.uint8)
    cv2.circle(img, (200, 150), 90, (255, 255, 255, 255), -1)
    _e, info = imgtrace.image_to_entities(_png(img), height_mm=20)
    assert info["width_mm"] == pytest.approx(19.9, abs=0.6)
    bleed = np.full((300, 400, 4), 255, np.uint8)
    bleed[0] = bleed[-1] = 0
    bleed[:, 0] = bleed[:, -1] = 0
    _e2, info2 = imgtrace.image_to_entities(_png(bleed), height_mm=20)
    assert info2["contours"] == 1 and info2["holes"] == 0


def test_an_empty_image_file_is_a_sentence_not_an_opencv_assertion():
    r"""A zero-byte file dragged into Trace Image (a failed download, an empty
    export) reaches `cv2.imdecode` as an empty buffer, and OpenCV's own
    assertion is not a ValueError — so it went straight past
    `image_to_entities` and `studio.trace_png` put the raw text in the user's
    chat: "OpenCV(5.0.0) D:\a\opencv-python\...\loadsave.cpp:1291: error:
    (-215:Assertion failed) !buf.empty() in function 'cv::imdecode_'"
    (measured 2026-09-17, round seven). The browser's own reader hands a
    0-byte .png through as "data:image/png;base64," with nothing after the
    comma, so this is one drag away."""
    with pytest.raises(ValueError) as exc:
        imgtrace.image_to_entities(b"", height_mm=20)
    assert "OpenCV" not in str(exc.value) and "Assertion" not in str(exc.value)


def test_the_empty_file_reaches_the_user_as_a_sentence():
    import base64
    from fastapi.testclient import TestClient
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    client = TestClient(studio.app)
    assert base64.b64decode("") == b""          # the browser's own payload
    d = client.post("/api/trace-png", json={
        "png_base64": "data:image/png;base64,",
        "feature_id": "logo", "height_mm": 42})
    assert d.status_code == 400
    msg = d.json()["error"]
    assert "OpenCV" not in msg and "Assertion" not in msg, msg


def _slotted_bar(w=400, h=300):
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (w // 8, h // 4), (w - w // 8, h - h // 4), 255, -1)
    step = max(4, w // 20)
    for x in range(w // 6, w - w // 6, step):
        cv2.rectangle(m, (x, h // 4), (x + max(1, step // 4), h // 2), 0, -1)
    return m


@pytest.mark.parametrize("channel", [16.0, 20.0, 30.0, 60.0])
def test_a_channel_wider_than_the_recesses_says_so(channel):
    """`min_channel_mm` had no bound, and the browser never sends it — only
    the HTTP door and a script do. The open erases the space AROUND the art
    as readily as the recesses IN it: on artwork 19.9 mm across, a 30 mm
    channel traced the picture's own 26.60 x 19.93 mm rectangle, one piece,
    no holes, status ok and nothing said, and a 60 mm channel on a
    1500 x 1200 picture took 119.56 SECONDS to do it (measured 2026-09-17,
    round seven, probes/imgtrace_r7_channel.py)."""
    data = _png(_slotted_bar())
    with pytest.raises(ValueError) as exc:
        imgtrace.image_to_entities(data, height_mm=20, min_channel_mm=channel)
    assert "rectangle" in str(exc.value)


@pytest.mark.parametrize("channel", [0.5, 2.0, 8.0, 12.0])
def test_an_ordinary_channel_is_untouched_by_that_guard(channel):
    data = _png(_slotted_bar())
    _e, info = imgtrace.image_to_entities(data, height_mm=20,
                                          min_channel_mm=channel)
    assert info["width_mm"] == pytest.approx(39.7, abs=0.5)
    assert info["height_mm"] == pytest.approx(19.9, abs=0.5)
