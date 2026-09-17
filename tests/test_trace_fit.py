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
