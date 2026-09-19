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

    def counted(d, height_mm=50.0, *knobs, **kw):
        calls.append(height_mm)
        return real(d, height_mm, *knobs, **kw)

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


def _ladder(radii=(30, 24, 20, 17, 14, 12, 10, 8, 7, 6), gap=130,
            bar_w=1000, bar_t=40):
    """A wide bar with a ladder of dots above it, each smaller than the one
    below — so EVERY drop in the trace height loses the topmost dot, shortens
    the artwork and raises its aspect, and the fit's iteration walks downhill
    without ever repeating. Measured aspects: 0.7431 at 50 mm, 1.7318 at
    12.6 mm, 4.9801 at 7.28 mm, 24.4146 at 2.53 mm."""
    h = bar_t + gap * (len(radii) + 1) + 80
    img = np.zeros((h, bar_w + 200, 4), np.uint8)
    y0 = h - 60
    cv2.rectangle(img, (100, y0 - bar_t), (100 + bar_w, y0), (0, 0, 0, 255), -1)
    for k, r in enumerate(radii):
        cv2.circle(img, (600, y0 - bar_t - gap * (k + 1)), int(r),
                   (0, 0, 0, 255), -1)
    return _png(img)


@pytest.mark.parametrize("margin,art", [(0.9, 17.85), (0.5, 9.9)])
def test_a_margin_inside_its_range_still_fits_the_art(margin, art):
    client = _client()
    info, w, h = _fit(client, _png(_disc_png()), (30.0, 20.0, 0, 0),
                      fit_margin=margin)
    assert w == pytest.approx(art, abs=0.6) and h == pytest.approx(art,
                                                                  abs=0.6)


@pytest.mark.parametrize("margin", [2.0, 1e9, 0.0, -0.5])
def test_a_margin_outside_its_range_says_so(margin):
    """`fit_margin` is the fraction of the face the artwork fills and nothing
    checked it — the browser never sends it, so only a script can. Measured
    2026-09-17 (round seven, probes/imgtrace_r7_doors.py): 2 put 39.72 mm of
    art on a 30 x 20 mm box and 1e9 put 993.80 mm of it there, both green and
    silent; a negative margin mirrored the art and rotated it."""
    client = _client()
    r = client.post("/api/trace-png", json={
        "png_base64": base64.b64encode(_png(_disc_png())).decode(),
        "entities_only": True, "fit_box": [30.0, 20.0, 0.0, 0.0],
        "fit_margin": margin})
    # 400, not 200: a route that answers a refusal with 200 tells a script the
    # opposite of what happened (REVIEW-QUEUE section 12) — and this door
    # answered 200 for every refusal it has
    assert r.status_code == 400
    d = r.json()
    assert "fit_margin" in (d.get("error") or ""), d
    assert "features" not in d          # nothing changed; do not redraw


def test_a_fit_box_that_is_not_four_numbers_says_so():
    client = _client()
    d = client.post("/api/trace-png", json={
        "png_base64": base64.b64encode(_png(_disc_png())).decode(),
        "entities_only": True, "fit_box": [30.0]}).json()
    assert "four numbers" in (d.get("error") or ""), d


def _slotted_ladder(slots=6):
    """the same ladder, with hairline slots cut into the bar — art that is
    fine enough for the 0.001 mm coordinate grid to matter once it is scaled"""
    radii, gap, bar_w, bar_t = (30, 24, 20, 17, 14, 12, 10, 8, 7, 6), 130, \
        1000, 40
    h = bar_t + gap * (len(radii) + 1) + 80
    img = np.zeros((h, bar_w + 200, 4), np.uint8)
    y0 = h - 60
    cv2.rectangle(img, (100, y0 - bar_t), (100 + bar_w, y0), (0, 0, 0, 255), -1)
    for k, r in enumerate(radii):
        cv2.circle(img, (600, y0 - bar_t - gap * (k + 1)), int(r),
                   (0, 0, 0, 255), -1)
    for k in range(slots):
        x = 200 + k * 37
        cv2.rectangle(img, (x, y0 - bar_t), (x + 1, y0 - 4), (0, 0, 0, 0), -1)
    return _png(img)


@pytest.mark.parametrize("box", [(5.0, 5.0), (4.0, 4.0), (6.0, 6.0)])
def test_art_scaled_onto_a_small_face_still_keeps_both_promises(box):
    """`imgtrace.image_to_entities` ends by proving no polygon crosses itself
    and no two loops of the sketch meet. `_trace_fitted` then multiplies every
    point by its residual `s` and rounds it back onto the 0.001 mm grid —
    AFTER both proofs, and outside imgtrace entirely. The comment calls `s` a
    hair; `_trace_fit_height`'s own fallback calls it "traced and then SHRUNK
    by `_trace_fitted`'s residual rescale", and on a 5 x 5 mm face this
    picture is traced at 50 mm and shrunk by s = 0.0902.

    Measured 2026-09-17 (round seven, probes/imgtrace_r7_fit_pinch.py): one of
    the eleven polygons the browser was handed crossed itself, and over the
    corpus the same multiply left 287 polygons carrying a duplicate point, 22
    really crossing and 32 traces of 240 with two loops at exactly
    0.000000000 mm — the pinch that builds as an open shell."""
    import inspector
    import sketch as sk
    client = _client()
    d = client.post("/api/trace-png", json={
        "png_base64": base64.b64encode(_slotted_ladder()).decode(),
        "entities_only": True,
        "fit_box": [box[0], box[1], 0.0, 0.0]}).json()
    assert not d.get("error"), d.get("error")
    ents = d["entities"]
    bad = [n for n, e in enumerate(ents)
           if imgtrace._first_crossing([tuple(p) for p in e["points"]])
           is not None]
    assert not bad, (f"on a {box[0]} x {box[1]} mm face, polygons {bad} of "
                     f"{len(ents)} cross themselves")
    rings = [[(e["x"] + x, e["y"] + y) for x, y in e["points"]] for e in ents]
    worst = min(
        [min(float(imgtrace._nearest_on_ring(np.asarray(rings[i], float),
                                             np.asarray(rings[j], float))[0]
                   .min()),
             float(imgtrace._nearest_on_ring(np.asarray(rings[j], float),
                                             np.asarray(rings[i], float))[0]
                   .min()))
         for i in range(len(rings)) for j in range(i + 1, len(rings))] or [9.0])
    assert worst > 0.0, "two loops MEET once the art is scaled onto the face"
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert inspector.health(solid) == []


@pytest.mark.parametrize("fw,fh", [(12.0, 14.0), (12.0, 10.0), (12.0, 18.0)])
def test_art_whose_aspect_never_settles_is_not_shrunk_to_a_hairline(fw, fh):
    """When NO tried height fits, the fallback used to take the SMALLEST one
    — the height at which the most of the artwork has already been thrown
    away, so its aspect is the most extreme and `_trace_fitted`'s residual
    rescale shrinks it hardest.

    Measured 2026-09-17 (probes/imgtrace_fit_height_attack.py): this picture
    on a 12 x 14 mm face traced at 2.530 mm, where only the bar survives at
    aspect 24.41, and came back 0.50 x 12.60 mm — a hairline, 6 mm2 of art on
    a 151 mm2 face, where even the one-shot rule this replaced gave
    10.80 x 6.22 mm. The least bad height is the one whose OWN artwork comes
    closest to fitting already, not the smallest."""
    client = _client()
    info, w, h = _fit(client, _ladder(), (fw, fh, 0, 0))
    assert min(w, h) >= 0.25 * min(fw, fh), \
        f"art came back {w:.2f} x {h:.2f} mm on a {fw} x {fh} mm face"
    assert w * h >= 0.25 * (0.9 * fw) * (0.9 * fh), \
        f"art fills {w * h:.1f} mm2 of a {0.81 * fw * fh:.1f} mm2 fit box"
    assert w <= 0.9 * fw + 0.01 and h <= 0.9 * fh + 0.01, "art overflows"


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


def _tall_bar_and_hairline(tail=620, thick=1):
    """A tall 200 x 400 px bar (drawn aspect 0.5) and a loose 1 px horizontal
    hairline beside it — a scan streak, a stray rule, the tail of a signature.

    `_traceable` keeps the hairline: it is 620 PIXELS, far over the speckle
    floor. `image_to_entities` then drops it, because the outline of a 1 px
    line ENCLOSES nothing and fails the `min_area` gate — which is why the
    traced box holds only the bar."""
    img = np.zeros((520, 980, 4), np.uint8)
    cv2.rectangle(img, (40, 60), (239, 459), (0, 0, 0, 255), -1)
    if tail:
        img[259:259 + thick, 280:280 + tail] = (0, 0, 0, 255)
    return _png(img)


def test_the_fit_measures_the_art_that_is_actually_drawn():
    """`artwork_aspect` picks BOTH the fit height and the 90-degree rotate,
    and it promises to measure the artwork `image_to_entities` traces. It
    measured the speckle mask instead, which still holds the hairline.

    Measured 2026-09-17 on a 20 x 60 mm face (probes/imgtrace_r5_aspect_gate.py):
    the bar alone lands 17.91 x 35.91 mm standing up; add the hairline and the
    fit reads aspect 2.15 instead of 0.50, ROTATES the art and lays it down at
    17.95 x 8.96 mm — a quarter of the area, on art the hairline is not even
    part of."""
    clean = imgtrace.artwork_aspect(_tall_bar_and_hairline(tail=0), 40.0)
    assert clean == pytest.approx(0.5, rel=0.02)
    for tail in (200, 400, 620):
        data = _tall_bar_and_hairline(tail)
        assert imgtrace.artwork_aspect(data, 40.0) == pytest.approx(
            clean, rel=0.02), f"a loose {tail} px hairline moved the fit"
    client = _client()
    info, w, h = _fit(client, _tall_bar_and_hairline(620), (20.0, 60.0, 0, 0))
    assert info["rotated"] is False, "art drawn tall came in lying down"
    assert h > 30.0, f"art fitted only {h:.2f} mm tall on a 60 mm face"


def _crescent(r=60.0, thick=2.0, n=200):
    """A thin arc band, as a face outline in its own 2D — the shape of a
    curved rib top or a thin flange. Its BOUNDING box is 39 x 112 mm and its
    material is 2 mm wide."""
    a = np.linspace(-1.2, 1.2, n)
    return ([(r * np.cos(t), r * np.sin(t)) for t in a]
            + [((r - thick) * np.cos(t), (r - thick) * np.sin(t))
               for t in a[::-1]])


def _diag_strip(length=80.0, width=2.0):
    """a thin strip at 45 degrees: its bbox is 80 times its own width"""
    d = width / np.sqrt(2)
    return [(-length, -length), (-length + d, -length - d),
            (length + d, length - d), (length, length)]


def _corners_on(outer, box):
    poly = np.array(outer, np.float32)
    w, h, cx, cy = box
    return all(cv2.pointPolygonTest(poly, (float(cx + sx * w / 2),
                                           float(cy + sy * h / 2)),
                                    False) >= 0
               for sx in (-1, 1) for sy in (-1, 1))


@pytest.mark.parametrize("outline,name", [
    (_crescent(thick=2.0), "crescent 2 mm"),
    (_crescent(thick=6.0), "crescent 6 mm"),
    (_crescent(thick=12.0), "crescent 12 mm"),
    (_diag_strip(width=2.0), "45-degree strip 2 mm"),
    (_diag_strip(width=8.0), "45-degree strip 8 mm"),
])
def test_the_fit_box_stays_on_a_thin_face_too(outline, name):
    """A face too thin for the fit grid fell back to its BOUNDING box — the
    very thing the inscribed box was written to stop.

    Measured 2026-09-17: a 2 mm crescent of radius 60 handed back its whole
    38.98 x 111.84 mm bbox, of which 7.3% is on the face, and a 2 mm strip at
    45 degrees handed back 161.41 x 161.41 mm, of which 2.0%."""
    import studio
    box = studio._inscribed_box(outline)
    assert box[0] > 0 and box[1] > 0, f"{name}: no box at all"
    assert _corners_on(outline, box), f"{name}: the box is off the face"


def test_a_face_far_too_thin_for_art_says_so_instead():
    """Below any usable size the honest answer is a refusal, not a box: the
    caller's guard turns a non-positive box into "that face is too thin to
    fit artwork onto"."""
    import studio
    box = studio._inscribed_box(_crescent(thick=0.05))
    assert box[0] <= 0 or box[1] <= 0


def _blob_and_hairlines():
    """A solid disc with five loose 1 px hairlines beside it. Each hairline is
    hundreds of pixels and encloses nothing, so `image_to_entities`' contour
    gate drops it — until `connect_pieces` bridges them all into ONE contour
    that encloses plenty and the artwork is suddenly twice as wide as it is
    tall."""
    img = np.zeros((600, 900, 4), np.uint8)
    cv2.circle(img, (200, 300), 130, (0, 0, 0, 255), -1)
    for x in (420, 520, 620, 720, 820):
        cv2.line(img, (x, 120), (x, 480), (0, 0, 0, 255), 1)
    return _png(img)


# Round five made `artwork_aspect` drop sub-min_area CONTOURS, matching the
# trace. `image_to_entities` runs two MORE passes on the mask before it takes
# contours — the bridges and the channel absorb — and the fit ran neither.
# Measured 2026-09-17 (round six, probes/imgtrace_r6_gates.py): this picture
# reads aspect 1.0000 for art `connect_pieces` really draws at 2.1144, and on
# a 20 x 60 mm face the fit laid it down at 18.00 x 8.50 mm (rescaled by
# 0.479) where standing it up gives 17.75 x 37.57.
def test_the_fit_measures_the_artwork_the_knobs_will_really_draw():
    import studio
    data = _blob_and_hairlines()
    assert imgtrace.artwork_aspect(data, 20.0) == pytest.approx(1.0, abs=0.01)
    assert imgtrace.artwork_aspect(data, 20.0, 0.0, True) > 2.0
    h, rot = studio._trace_fit_height(data, 18.0, 54.0, connect_pieces=True)
    assert rot is True
    _e, info = studio._trace_fitted(
        data, studio.TracePngReq(png_base64="", connect_pieces=True),
        (20.0, 60.0, 0.0, 0.0))
    assert info["rotated"] is True
    assert info["width_mm"] * info["height_mm"] > 600.0


def _angled_sliver(length=400.0, t=0.5, deg=45.0):
    """A face too thin to hold ANY rectangle on the fit grid — `_inscribed_box`
    hands back a zero box, which is the honest answer."""
    import math
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[x * c - y * s, x * s + y * c]
            for x, y in ([0, 0], [length, 0], [length, t], [0, t])]


def test_a_face_that_holds_no_box_says_so_at_both_doors():
    """The browser only has the SKETCHER door, and it used to answer "the fit
    box needs a positive width and height" — an internal thing the user
    cannot act on (round six, probes/imgtrace_r6_fitbox.py)."""
    import studio
    w, h, cx, cy = studio._inscribed_box(_angled_sliver())
    assert (w, h) == (0.0, 0.0)
    with pytest.raises(ValueError, match="too thin to fit artwork onto"):
        studio._trace_fitted(b"", studio.TracePngReq(png_base64=""),
                             (w, h, cx, cy))


def test_the_fit_box_is_reported_under_its_own_name():
    """`face_mm` carries the FIT BOX — on a 30 mm disc the face is 60 x 60 and
    the box is 42 x 42 — so it is also reported as `fit_mm`. The old key stays
    until static/js/sketcher.js follows."""
    import studio
    _e, info = studio._trace_fitted(_png(_disc_png()), studio.TracePngReq(
        png_base64="", height_mm=20.0), (42.0, 42.0, 0.0, 0.0))
    assert info["fit_mm"] == [42.0, 42.0]
    assert info["face_mm"] == info["fit_mm"]
