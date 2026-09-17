"""Two polygons of ONE traced sketch must never meet, and the bounding box
must describe the art that was actually drawn.

LAUNCH-PLAN.md section 10:
  * P2 - two traced HOLES that touch pinch the face: `is_valid` True, the
    right volume, and `inspector.health` "not manifold/watertight (open
    shell)". `_uncross` guarantees no ONE polygon crosses itself; nothing
    guaranteed two different polygons of one sketch stay apart.
  * P3 - the traced bounding box counted contours the `min_area` gate then
    dropped, so the art was scaled and centred on a box holding a piece that
    was never drawn.
"""
import cv2
import numpy as np
import pytest

import imgtrace
import inspector
import sketch as sk


def _png(mask):
    img = np.zeros(mask.shape + (4,), np.uint8)
    img[:, :, 3] = (mask > 0).astype(np.uint8) * 255
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _ring_with_spokes(radius, angles, thickness):
    """A 30 px ring cut into sectors by hairline spokes — the shape class of
    round three's fuzz cases f73 and f122, which are the two traces of 450
    that built an unhealthy solid."""
    m = np.zeros((320, 420), np.uint8)
    cv2.circle(m, (210, 160), radius, 1, 30)
    for a in angles:
        cv2.line(m, (210, 160),
                 (int(210 + 300 * np.cos(a)), int(160 + 300 * np.sin(a))),
                 1, thickness)
    return m


def _closest_pair(ents):
    """the closest approach between any two DIFFERENT entities, in mm"""
    rings = [np.array([[e["x"] + x, e["y"] + y] for x, y in e["points"]])
             for e in ents]
    best = float("inf")
    for i in range(len(rings)):
        for j in range(i + 1, len(rings)):
            p, q = rings[i], rings[j]
            best = min(best, float(np.hypot(p[:, None, 0] - q[None, :, 0],
                                            p[:, None, 1] - q[None, :, 1]
                                            ).min()))
    return best


# radius 119, two 1 px spokes: measured 2026-09-17 to hand sketch.py two hole
# loops at 0.000000 mm, building a solid of 75.243 mm3 that OpenCASCADE calls
# valid and inspector.health calls an open shell
PINCH = dict(radius=119, angles=(2.390072, 0.839769), thickness=1)


def test_two_traced_holes_never_meet():
    ents, info = imgtrace.image_to_entities(
        _png(_ring_with_spokes(**PINCH)), height_mm=12.0)
    assert info["holes"] >= 2
    gap = _closest_pair(ents)
    assert gap >= 0.002, (f"two polygons of one sketch come within "
                          f"{gap:.6f} mm — that pinches the face")
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert solid.is_valid
    assert inspector.health(solid) == [], "a pinched face is an open shell"
    # and the art is still the art: the pull-apart moves microns
    assert solid.volume == pytest.approx(75.24, rel=0.01)


@pytest.mark.parametrize("radius,angles,thickness", [
    (135, (1.924258, 5.229948, 3.893119, 1.17526), 1),
    (121, (0.789657, 1.157217, 5.021092, 4.047596), 1),
    (108, (0.865485, 4.775144, 6.235719), 1),
])
def test_more_pinched_rings_build_a_watertight_solid(radius, angles,
                                                     thickness):
    """Three more of the same class, found by the same search."""
    ents, _info = imgtrace.image_to_entities(
        _png(_ring_with_spokes(radius, angles, thickness)), height_mm=12.0)
    assert _closest_pair(ents) >= 0.002
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert inspector.health(solid) == []


def _square_and_hairline(tail=0, thick=1, detached=True):
    """A 400 x 400 px square and, beside it, a `thick` px hairline.

    A hairline is a big connected COMPONENT (hundreds of pixels), so
    `_traceable`'s pixel floor keeps it, and it ENCLOSES nothing, so the
    contour gate drops it. It used to stay in the box every surviving piece
    was scaled and centred on."""
    m = np.zeros((500, 700), np.uint8)
    cv2.rectangle(m, (40, 40), (439, 439), 1, -1)
    if tail:
        x0 = 440 + (20 if detached else 0)
        m[239:239 + thick, x0:x0 + tail] = 1
    return m


def _extent(ents):
    xs = [e["x"] + p[0] for e in ents for p in e["points"]]
    ys = [e["y"] + p[1] for e in ents for p in e["points"]]
    return (max(xs) - min(xs), max(ys) - min(ys),
            (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)


@pytest.mark.parametrize("tail,thick,detached", [(200, 1, True),
                                                 (140, 2, True),
                                                 (260, 1, False)])
def test_the_traced_box_holds_only_what_was_drawn(tail, thick, detached):
    """Measured 2026-09-17 (probes/imgtrace_bbox_gate_probe.py): a 40 mm
    square beside a loose 200 px hairline reported `width_mm` 62.00 for
    39.90 mm of drawn art, and put that art 11.05 mm off the sketch origin —
    scaled and centred on a box holding a piece that was never drawn."""
    plain, p_info = imgtrace.image_to_entities(
        _png(_square_and_hairline()), height_mm=40.0)
    ents, info = imgtrace.image_to_entities(
        _png(_square_and_hairline(tail, thick, detached)), height_mm=40.0)
    w, h, cx, cy = _extent(ents)
    assert info["width_mm"] == pytest.approx(w, abs=0.01), \
        "width_mm counts a piece that was never drawn"
    assert info["height_mm"] == pytest.approx(h, abs=0.01)
    assert abs(cx) < 0.05 and abs(cy) < 0.05, \
        f"the sketch sits {cx:.2f}, {cy:.2f} mm off the origin"
    # and the square itself is traced the same size with or without the tail
    assert w == pytest.approx(_extent(plain)[0], abs=0.5)
    assert info["width_mm"] == pytest.approx(p_info["width_mm"], abs=0.5)


def test_pulling_loops_apart_leaves_art_that_is_already_clear_alone():
    """A picture whose pieces are properly separated must come out of the
    tracer unchanged, to the last decimal."""
    m = np.zeros((400, 400), np.uint8)
    cv2.circle(m, (120, 200), 70, 1, -1)
    cv2.circle(m, (290, 200), 70, 1, -1)
    ents, info = imgtrace.image_to_entities(_png(m), height_mm=40.0)
    loops = [[(e["x"] + x, e["y"] + y) for x, y in e["points"]]
             for e in ents]
    same = imgtrace._pull_apart([list(p) for p in loops])
    assert info["contours"] == 2
    for before, after in zip(loops, same):
        assert before == pytest.approx(np.array(after), abs=1e-12)
