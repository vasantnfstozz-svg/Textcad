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
