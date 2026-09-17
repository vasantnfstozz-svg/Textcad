"""Fitting traced art onto a face: the height, the 90-degree rotate and the
box the art is fitted INTO.

LAUNCH-PLAN.md section 10:
  * P1 - the fit asked `imgtrace.artwork_aspect` at the DEFAULT 50 mm and then
    traced at the height that answer produced, so the speckle clean-up that
    decides which pieces exist ran at one size and the trace at another.
  * P2 - the fit box was the face's BBOX, so square art on a round face put
    its corners off the face entirely.
"""
import base64

import cv2
import numpy as np
import pytest

import imgtrace


def _png(canvas):
    ok, buf = cv2.imencode(".png", canvas)
    assert ok
    return buf.tobytes()


def _bar_with_ornaments():
    """A tall 100 x 300 px bar plus two ~28 px ornaments far to its right.

    The ornaments clear imgtrace's physical 0.25 mm speckle floor at 50 mm
    tall (floor 9 px) and fall under it below about 14.2 mm (floor 31 px), so
    the SAME picture measures aspect 1.3467 with 3 pieces at one size and
    0.3333 with 1 piece at the other (probes/imgtrace_fit_height_probe.py)."""
    img = np.zeros((400, 600, 4), np.uint8)
    cv2.rectangle(img, (100, 50), (199, 349), (0, 0, 0, 255), -1)
    cv2.circle(img, (500, 120), 3, (0, 0, 0, 255), -1)
    cv2.circle(img, (500, 280), 3, (0, 0, 0, 255), -1)
    return _png(img)


def _disc_png(size=400):
    img = np.zeros((size, size, 4), np.uint8)
    cv2.circle(img, (size // 2, size // 2), size // 2 - 20,
               (10, 10, 10, 255), -1)
    return img


def _client():
    from fastapi.testclient import TestClient
    import document as dm
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    doc = dm.Document("plate")
    doc.add("base", "plate", {"width": 120, "depth": 80, "thickness": 10}, [])
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def _fit(client, data, box, **extra):
    d = client.post("/api/trace-png", json={
        "png_base64": base64.b64encode(data).decode(),
        "entities_only": True, "fit_box": list(box), **extra}).json()
    assert not d.get("error"), d.get("error")
    xs = [e["x"] + p[0] for e in d["entities"] for p in e["points"]]
    ys = [e["y"] + p[1] for e in d["entities"] for p in e["points"]]
    return (d["trace_info"], max(xs) - min(xs), max(ys) - min(ys))


@pytest.mark.parametrize("fw,fh,tall_mm", [(12.0, 14.0, 12.0),
                                           (12.0, 15.0, 13.0),
                                           (12.0, 20.0, 10.0)])
def test_art_drawn_tall_lands_tall_on_a_narrow_face(fw, fh, tall_mm):
    """Art three times taller than it is wide must stand UP on a narrow
    face, and fill it.

    The fit measured the aspect at the default 50 mm, where two ornaments
    survive the speckle floor and the picture reads 1.35 WIDE; it then traced
    at the fitted height, where the ornaments are gone and the art is the bar
    alone, 0.33 tall. Measured on a 12 x 14 mm face: the art came in
    9.36 x 3.12 mm, LYING DOWN, a third of the size it fits at
    (4.20 x 12.60 mm)."""
    client = _client()
    info, w, h = _fit(client, _bar_with_ornaments(), (fw, fh, 0, 0))
    assert info["rotated"] is False, "art drawn tall came in lying down"
    assert h > w, f"art drawn 3:1 tall landed {w:.2f} x {h:.2f} mm"
    assert h >= tall_mm, f"art fitted only {h:.2f} mm tall on a {fh} mm face"
    assert w <= 0.9 * fw + 0.01 and h <= 0.9 * fh + 0.01, "art overflows"


def test_the_fit_height_terminates_and_the_art_it_picks_fits():
    """The fit can OSCILLATE: on a 12 x 14 mm face this picture runs
    50 -> 9.356 -> 12.600 -> 9.356 for ever, because the ornaments come back
    at one size and go away again at the other. So the height is chosen from
    a FINITE set of heights, each measured at its own size, and the winner is
    the biggest one whose own artwork really fits."""
    import studio
    data = _bar_with_ornaments()
    calls = []
    real = imgtrace.artwork_aspect

    def counted(d, height_mm=50.0):
        calls.append(height_mm)
        return real(d, height_mm)

    studio.imgtrace.artwork_aspect = counted
    try:
        for fw in (12.0, 20.0, 40.0, 60.0):
            for fh in (14.0, 15.0, 20.0, 60.0):
                calls.clear()
                m_w, m_h = 0.9 * fw, 0.9 * fh
                h, rot = studio._trace_fit_height(data, m_w, m_h)
                assert 1 <= len(calls) <= 5, f"{len(calls)} aspect measures"
                a = real(data, h)          # the aspect AT the chosen height
                box = (m_h, m_w) if rot else (m_w, m_h)
                assert h <= box[1] * 1.000001 and h * a <= box[0] * 1.000001, \
                    f"{fw}x{fh}: chose {h:.3f} mm, aspect there {a:.4f}"
    finally:
        studio.imgtrace.artwork_aspect = real


def test_plain_art_on_a_big_face_is_unchanged_by_the_measured_fit():
    """The fit must still fill the face for ordinary art, where the aspect
    does not move with the size: a disc on a 60 x 30 mm face fills 27 mm."""
    client = _client()
    info, w, h = _fit(client, _png(_disc_png()), (60.0, 30.0, 0, 0))
    assert info["rotated"] is False
    assert h == pytest.approx(27.0, abs=0.6)
    assert w == pytest.approx(27.0, abs=0.6)


# --- P2: the fit box is the face's BBOX, so art overflows a round face -----

def _traced_points(client, data, centre, normal=(0, 0, 1), fid="art"):
    """Trace onto a picked face and read the entity points back out of the
    feature the server actually stored, in the face's own 2D."""
    import studio
    d = client.post("/api/trace-png", json={
        "png_base64": base64.b64encode(data).decode(),
        "face_center": list(centre), "face_normal": list(normal),
        "feature_id": fid}).json()
    assert not d.get("error"), d.get("error")
    feat = [f for f in studio._doc().features
            if f.id == d["trace_info"]["feature_id"]][0]
    pts = [(e["x"] + p[0], e["y"] + p[1])
           for e in feat.params["entities"] for p in e["points"]]
    return d["trace_info"], pts


def _square_png(size=400, pad=30):
    img = np.zeros((size, size, 4), np.uint8)
    cv2.rectangle(img, (pad, pad), (size - pad, size - pad),
                  (10, 10, 10, 255), -1)
    return _png(img)


def _tab(doc):
    from fastapi.testclient import TestClient
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(doc)
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def _disc_tab(radius=30.0, thick=10.0):
    import document as dm
    doc = dm.Document("disc")
    doc.add("base", "disc", {"radius": radius, "thickness": thick}, [])
    return _tab(doc)


def _ell_tab(a=60.0, b=60.0, bite=30.0, thick=10.0):
    import document as dm
    doc = dm.Document("ell")
    doc.add("base", "plate", {"width": a, "depth": b, "thickness": thick}, [])
    doc.add("bite", "plate",
            {"width": bite, "depth": bite, "thickness": thick * 3}, [])
    doc.add("bite_at", "move",
            {"x": (a - bite) / 2, "y": (b - bite) / 2, "z": 0}, ["bite"])
    doc.add("ell", "cut", {}, ["base", "bite_at"])
    return _tab(doc)


def test_traced_art_stays_on_a_round_face():
    """The fit box was the face's BOUNDING box, so square art auto-fitted to
    "the 60x60mm face" of a 30 mm disc put all 8 of its points off the disc,
    the furthest 37.96 mm from a 30.00 mm edge — green, with nothing said
    (measured 2026-09-17, probes/imgtrace_inscribed_box_probe.py)."""
    client = _disc_tab(radius=30.0, thick=10.0)
    info, pts = _traced_points(client, _square_png(), (0, 0, 5))
    worst = max((x * x + y * y) ** 0.5 for x, y in pts)
    n_off = sum(1 for x, y in pts if (x * x + y * y) ** 0.5 > 30.0)
    assert worst <= 30.0, (f"{n_off} of {len(pts)} traced points are off the "
                           f"disc, the furthest {worst:.2f} mm from a "
                           f"30.00 mm edge")
    assert info["width_mm"] > 20.0, "and the art must still be worth seeing"


def test_traced_art_stays_on_an_l_shaped_face():
    """Same box, an inside corner instead of a curve: 2 of 8 points sat up to
    11.68 mm off the material."""
    client = _ell_tab()
    _info, pts = _traced_points(client, _square_png(), (0, 0, 5))
    ell = np.array([[-30, -30], [30, -30], [30, 0], [0, 0], [0, 30],
                    [-30, 30]], np.float32)      # 30x30 bite at +x +y
    off = [cv2.pointPolygonTest(ell, (float(x), float(y)), True)
           for x, y in pts]
    assert min(off) >= -0.01, (f"{sum(1 for d in off if d < 0)} of {len(pts)} "
                               f"traced points are off the face, the furthest "
                               f"{-min(off):.2f} mm out")


def test_face_outline_hands_back_the_box_to_fit_into():
    """R1: the inscribed box is a server fact. The sketcher takes min/max of
    `outer` itself, which is the face only when the face is a rectangle."""
    client = _disc_tab(radius=30.0, thick=10.0)
    d = client.post("/api/face-outline", json={
        "face_center": [0, 0, 5], "face_normal": [0, 0, 1]}).json()
    assert d["planar"] and d.get("fit_box"), d.get("error")
    w, h, cx, cy = d["fit_box"]
    # a circle of radius r holds a square of side r*sqrt(2) = 42.43 mm
    assert w == pytest.approx(42.43, abs=0.6)
    assert h == pytest.approx(42.43, abs=0.6)
    assert (cx * cx + cy * cy) ** 0.5 < 0.5
    # and the box really is inside: its own corners are within the disc
    assert ((w / 2) ** 2 + (h / 2) ** 2) ** 0.5 <= 30.0


def test_a_rectangular_face_still_fits_its_whole_self():
    """Every flat plate face must behave exactly as it always did — the
    inscribed box of a rectangle IS its bounding box, by an early exit."""
    client = _client()          # the 120 x 80 x 10 plate
    d = client.post("/api/face-outline", json={
        "face_center": [0, 0, 5], "face_normal": [0, 0, 1]}).json()
    assert d["fit_box"] == [120.0, 80.0, 0.0, 0.0]
