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
    # the pinch `_pull_apart`'s "no room" guard used to REFUSE to open: the
    # vertex the two hole loops share sits on a sub-hair edge, so the push
    # was larger than a quarter of it and the vertex was left as traced.
    # Measured 2026-09-17 (probes/imgtrace_pull_apart_audit.py, 1 of 700
    # ring traces): two subtract loops at 0.000000000 mm, 84.472 mm3,
    # is_valid True, health "not manifold/watertight (open shell)"
    (130, (3.034032, 0.032646, 3.425228), 1),
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


def _dot_grid(n, size=600):
    m = np.zeros((size, size), np.uint8)
    step = size // n
    for i in range(n):
        for j in range(n):
            cv2.circle(m, (step // 2 + i * step, step // 2 + j * step),
                       step // 4, 1, -1)
    return m


def test_connect_pieces_says_so_when_it_gives_up():
    """`connect_pieces` welds disjoint art with straight bridges and stops
    after 16 of them. It used to hand back multi-piece art as if it had been
    welded into one, and say nothing (LAUNCH-PLAN section 10 P3)."""
    ents, info = imgtrace.image_to_entities(
        _png(_dot_grid(5)), height_mm=60.0, connect_pieces=True)
    assert ents
    assert info["contours"] > 1, "25 dots cannot be welded in 16 bridges"
    assert info["welded"] is False
    assert "separate pieces" in info["note"]


def test_connect_pieces_that_succeeds_says_that_too():
    ents, info = imgtrace.image_to_entities(
        _png(_dot_grid(2)), height_mm=60.0, connect_pieces=True)
    assert ents
    assert info["contours"] == 1
    assert info["welded"] is True
    assert "note" not in info


def test_a_plain_trace_is_not_asked_about_welding():
    _ents, info = imgtrace.image_to_entities(_png(_dot_grid(5)),
                                             height_mm=60.0)
    assert info["contours"] == 25
    assert "welded" not in info and "note" not in info


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


def _true_gap(loops):
    """The honest closest approach of two outlines: every vertex of each
    against the OTHER's edges. The minimum distance between two polylines
    sits on a vertex of one or of the other, and `_pull_apart` asks only one
    of those two questions."""
    arr = [np.asarray(p, float) for p in loops]
    best = float("inf")
    for i in range(len(arr)):
        for j in range(i + 1, len(arr)):
            d1, _f = imgtrace._nearest_on_ring(arr[i], arr[j])
            d2, _f = imgtrace._nearest_on_ring(arr[j], arr[i])
            best = min(best, float(d1.min()), float(d2.min()))
    return best


# The smaller loop is a BAR with a long straight top edge; the bigger loop
# is a plate with a needle whose tip lands on the middle of that edge. Every
# vertex of the bar is 4 mm from the plate's outline, so the guard's own
# one-way test reads 4.000 mm of clearance where the truth is 0.000 mm.
_BAR = [(-10.0, -1.0), (10.0, -1.0), (10.0, 1.0), (-10.0, 1.0)]
_NEEDLE = [(-20.0, 5.0), (-0.4, 5.0), (0.0, 1.0), (0.4, 5.0),
           (20.0, 5.0), (20.0, 20.0), (-20.0, 20.0)]


def test_a_vertex_on_the_OTHER_loops_edge_is_pulled_apart_too():
    """Measured 2026-09-17: the guard's one-way test reads 4.000 mm here and
    the two loops touch at exactly 0.000000000 mm."""
    assert _true_gap([_BAR, _NEEDLE]) == 0.0
    out = imgtrace._pull_apart([list(_BAR), list(_NEEDLE)])
    assert _true_gap(out) >= imgtrace._HAIR_MM * 0.99


def test_two_holes_that_touch_edge_to_vertex_build_a_watertight_solid():
    """The banned failure, through the direction the guard did not measure:
    two subtract loops meeting at a point built 3516.800 mm3 that
    OpenCASCADE calls valid and inspector.health calls an open shell."""
    out = imgtrace._pull_apart([list(_BAR), list(_NEEDLE)])
    plate = [(-30.0, -10.0), (30.0, -10.0), (30.0, 30.0), (-30.0, 30.0)]
    ents = [imgtrace._poly_entity(plate, "add")]
    ents += [imgtrace._poly_entity(imgtrace._round_pts(p), "subtract")
             for p in out]
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert inspector.health(solid) == []


def test_the_mirror_pass_leaves_art_that_is_already_clear_alone():
    """Nothing within a hair -> not one point inserted, not one moved."""
    a = [(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0)]
    b = [(0.0, 9.0), (10.0, 9.0), (10.0, 15.0), (0.0, 15.0)]
    out = imgtrace._pull_apart([list(a), list(b)])
    assert out == [a, b]


def _ring_with_mixed_spokes(radius, spokes):
    """the same ring, with a thickness PER spoke"""
    m = np.zeros((320, 420), np.uint8)
    cv2.circle(m, (210, 160), radius, 1, 30)
    for a, t in spokes:
        cv2.line(m, (210, 160),
                 (int(210 + 300 * np.cos(a)), int(160 + 300 * np.sin(a))),
                 1, int(t))
    return m


# The PICTURE that reaches the blind spot, found 2026-09-17 in 16 800 traces
# (probes/imgtrace_r5_mirror.py, seed 31337, "ring563"). Traced 9.5 mm tall it
# handed sketch.py two hole loops touching at exactly 0.000000000 mm while
# `_pull_apart`'s own one-way test read 0.025739602 mm of clearance, and built
# 47.933 mm3 that OpenCASCADE calls valid and inspector.health calls an open
# shell.
def test_the_ring_whose_holes_touch_through_the_blind_spot():
    m = _ring_with_mixed_spokes(131, [(5.825232830329833, 1),
                                      (4.6218438148683765, 2)])
    ents, info = imgtrace.image_to_entities(_png(m), height_mm=9.5)
    assert info["holes"] == 2
    assert _true_gap([[(e["x"] + x, e["y"] + y) for x, y in e["points"]]
                      for e in ents]) >= imgtrace._HAIR_MM * 0.99
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert inspector.health(solid) == []


def _hairline_star(radius, n, thickness=120, size=1600, off=0.3):
    """A ring with `n` ONE-PIXEL spokes on a 1600 px picture. Traced 8 mm tall
    that is 0.005 mm per pixel, so the sector holes the spokes cut are
    separated by walls a thousandth of a millimetre wide — the scale at which
    the 0.001 mm coordinate grid decides the geometry."""
    m = np.zeros((size, size), np.uint8)
    c = size // 2
    cv2.circle(m, (c, c), radius, 1, thickness)
    for k in range(n):
        a = off + k * 6.283185307179586 / n
        cv2.line(m, (c, c),
                 (int(c + size * np.cos(a)), int(c + size * np.sin(a))), 1, 1)
    return m


def _self_crossing(ents):
    """the entities whose OWN outline crosses itself — `_uncross` promises
    there are none, all the way to sketch.py"""
    return [n for n, e in enumerate(ents)
            if imgtrace._first_crossing([tuple(p) for p in e["points"]])
            is not None]


# Measured 2026-09-17 (round six, probes/imgtrace_r6_stage.py): the artwork is
# centred by dx, dy = (max + min) / 2 of the DRAWN points, which is a HALF-grid
# number whenever max + min is an odd multiple of 0.001 mm. The final
# `_round_pts` then re-rounds every point onto a SHIFTED grid and merges two
# distinct points — which puts a crossing back into an outline `_uncross` had
# just cleaned. `_poly_entity` rounds its own centre onto the grid for exactly
# this reason; the art-centring shift did not. This picture traced 8 mm tall
# handed sketch.py TWO self-crossing hole loops and built 20.023 mm3 that
# OpenCASCADE calls invalid.
@pytest.mark.parametrize("radius,n,thick,height", [(520, 11, 120, 8.0),
                                                   (600, 11, 120, 8.0),
                                                   (600, 9, 100, 9.0)])
def test_the_art_centring_shift_keeps_every_loop_simple(radius, n, thick,
                                                        height):
    ents, info = imgtrace.image_to_entities(
        _png(_hairline_star(radius, n, thick)), height_mm=height)
    assert info["holes"] == n
    assert _self_crossing(ents) == []
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert solid.is_valid
    assert inspector.health(solid) == []


# A ribbon folded back on itself: its two runs are NON-adjacent edges of one
# loop, so `_hair_cluster` — which walks the loop's index order — cannot see
# that the far wall is a hair away. Measured 2026-09-17 (round six,
# probes/imgtrace_r6_self.py): the push moved the bottom edge 0.0055 mm up
# through a ribbon 0.005 mm thick, and the 2 mm extrusion went from healthy to
# "OpenCASCADE reports the solid is invalid".
_RIBBON = [(0.0, 0.0), (1.0, 0.0), (1.0, 0.015), (0.05, 0.015),
           (0.05, 0.01), (0.995, 0.01), (0.995, 0.005), (0.0, 0.005)]
_UNDER = [(0.2, -5.0), (5.0, -5.0), (5.0, -0.0045), (0.2, -0.0045)]


def test_the_push_never_walks_a_loop_through_itself():
    assert imgtrace._first_crossing(_RIBBON) is None
    out = imgtrace._pull_apart([list(_RIBBON), list(_UNDER)])
    assert imgtrace._first_crossing(imgtrace._round_pts(out[0])) is None
    ents = [imgtrace._poly_entity(imgtrace._round_pts(out[0]), "add"),
            imgtrace._poly_entity(imgtrace._round_pts(out[1]), "subtract")]
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert solid.is_valid
    assert inspector.health(solid) == []


# ...and the same ribbon carrying ONE duplicate vertex, which is what
# `_split_at_feet` leaves behind when its inserted foot rounds onto an
# existing point of the 0.001 mm grid: 6 splits in 192 traces do exactly that
# (probes/imgtrace_r7_selftouch.py). The zero-length edge is harmless in
# itself — `_round_pts` drops it — but its two neighbours touch at that
# point, so `_walks_through_itself` used to read "this loop already touches
# itself" and waive EVERY push on that block. With the waiver in place the
# bottom edge is pushed 0.006 mm up through the ribbon's own far wall and the
# extrusion goes from healthy 0.019550 mm3 to
# "OpenCASCADE reports the solid is invalid" at 0.016240, feature green
# (measured 2026-09-17, round seven, probes/imgtrace_r7_escape.py).
_RIBBON_DUP = [_RIBBON[0]] + list(_RIBBON)


@pytest.mark.parametrize("at", [0, 1, 7])
def test_a_duplicate_vertex_does_not_waive_the_far_wall_guard(at):
    rib = list(_RIBBON[:at + 1]) + [_RIBBON[at]] + list(_RIBBON[at + 1:])
    assert imgtrace._first_crossing(imgtrace._round_pts(rib)) is None
    out = imgtrace._pull_apart([rib, list(_UNDER)])
    final = imgtrace._round_pts(out[0])
    assert imgtrace._first_crossing(final) is None, (
        f"a duplicate vertex at {at} waived the guard and the loop walked "
        f"through its own far wall")
    ents = [imgtrace._poly_entity(final, "add"),
            imgtrace._poly_entity(imgtrace._round_pts(out[1]), "subtract")]
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert solid.is_valid
    assert inspector.health(solid) == []


def test_a_duplicate_vertex_does_not_block_the_pushes_that_are_needed():
    """The other half: refusing outright whenever a loop already touches
    itself would stop pushes that are wanted — which is why round six asked
    the yes/no question in the first place. Asking WHICH PAIRS touch keeps
    them: a duplicate vertex changes nothing at all, on a loop the guard
    refuses (the ribbon, whose far wall is in the way) and on one it opens (a
    plain square a hair above a plate)."""
    clean = imgtrace._pull_apart([list(_RIBBON), list(_UNDER)])
    dup = imgtrace._pull_apart([list(_RIBBON_DUP), list(_UNDER)])
    assert imgtrace._round_pts(dup[0]) == imgtrace._round_pts(clean[0])

    square = [(0.0, 0.0), (0.4, 0.0), (0.4, 0.4), (0.0, 0.4)]
    plate = [(-5.0, -5.0), (5.0, -5.0), (5.0, -0.004), (-5.0, -0.004)]
    open_clean = imgtrace._pull_apart([list(square), list(plate)])
    open_dup = imgtrace._pull_apart([[square[0]] + list(square), list(plate)])
    assert imgtrace._round_pts(open_dup[0]) == imgtrace._round_pts(
        open_clean[0])
    d, _f = imgtrace._nearest_on_ring(np.asarray(open_dup[0], float),
                                      np.asarray(open_dup[1], float))
    assert float(d.min()) >= imgtrace._HAIR_MM - 1e-9, (
        "the push a duplicate vertex must not block")


# The guard gives way rather than turn a loop inside out, and it used to say
# NOTHING when it did. A sliver squeezed between two bigger loops is a fixed
# point for it: 8 of 960 ring traces end still inside the hair (round six,
# probes/imgtrace_r6_residual.py), the worst at 0.000255 mm — the very
# distance that produced round one's pinch. They build healthy today; going
# quiet about them is what produced two P0s.
_TIGHT_RING = dict(radius=138, spokes=[(1.1317991019756732, 1),
                                       (0.3325084868862962, 2),
                                       (0.6333420393182404, 2),
                                       (3.822255228295022, 1)], height=40.0)


def test_the_guard_says_when_it_could_not_open_a_wall():
    m = _ring_with_mixed_spokes(_TIGHT_RING["radius"], _TIGHT_RING["spokes"])
    ents, info = imgtrace.image_to_entities(_png(m),
                                            height_mm=_TIGHT_RING["height"])
    assert 0.0 < info["tight_mm"] < imgtrace._HAIR_MM
    assert "microns apart" in info["note"]
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    assert inspector.health(solid) == []


def test_art_the_guard_opened_says_nothing():
    """A trace whose loops are all clear carries no residual at all."""
    m = _ring_with_mixed_spokes(119, [(2.390072, 1), (0.839769, 1)])
    _ents, info = imgtrace.image_to_entities(_png(m), height_mm=12.0)
    assert "tight_mm" not in info and "note" not in info


# A loop every edge of which is shorter than the push has nothing that can be
# nudged rigidly, so `_hair_cluster` returns None and the guard leaves it as
# traced. That is allowed; going quiet about it is not.
_SPECK = [(0.0, 0.0), (0.003, 0.0), (0.0015, 0.0026)]
_PLATE = [(-5.0, -5.0), (5.0, -5.0), (5.0, 0.0), (-5.0, 0.0)]


def test_a_pair_the_guard_cannot_open_is_reported():
    stuck = []
    out = imgtrace._pull_apart([list(_SPECK), list(_PLATE)], report=stuck)
    assert out[0] == _SPECK                      # it really did give up
    assert stuck
    assert imgtrace._worst_residual(out, stuck) == 0.0
    clear = []
    away = [(x, y + 0.004) for x, y in _SPECK]
    out2 = imgtrace._pull_apart([list(away), list(_PLATE)], report=clear)
    assert imgtrace._worst_residual(out2, clear) == pytest.approx(0.004)


# Everything above is proved at the size imgtrace traced the art. The FIT then
# multiplies every point by a residual `s` and rounds it back onto the
# 0.001 mm grid, outside imgtrace entirely — the same move round six stopped
# the art-centring shift making. Measured 2026-09-17 (round seven,
# probes/imgtrace_r7_rescale_kind.py): over 240 traces rescaled at
# s = 0.9 … 0.02, 287 polygons came back carrying a DUPLICATE point, 22 came
# back really CROSSING and 32 traces ended with two loops at exactly
# 0.000000000 mm. `imgtrace.settle` asks both questions again afterwards.
def _rescaled(ents, s):
    return [{**e, "x": round(e["x"] * s, 3), "y": round(e["y"] * s, 3),
             "points": [[round(px * s, 3), round(py * s, 3)]
                        for px, py in e["points"]]} for e in ents]


@pytest.mark.parametrize("s", [0.5, 0.25, 0.1, 0.05])
def test_scaling_traced_art_down_keeps_both_promises(s):
    m = _hairline_star(radius=560, n=11)
    ents, _i = imgtrace.image_to_entities(_png(m), height_mm=8.0)
    assert not _self_crossing(ents)
    small = _rescaled(ents, s)
    try:
        out, _note = imgtrace.settle(small)
    except ValueError as exc:            # a refusal beats a pinched solid
        assert "meet at a point" in str(exc)
        return
    assert not _self_crossing(out), (
        f"scaled by {s}, {len(_self_crossing(out))} of {len(out)} polygons "
        f"cross themselves")
    rings = [[(e["x"] + x, e["y"] + y) for x, y in e["points"]] for e in out]
    assert _true_gap(rings) > 0.0, f"scaled by {s}, two loops MEET"


def test_a_pair_that_meets_by_a_rounding_error_is_still_a_pinch():
    """The refusal used to read `tight <= 0.0` exactly, and a contact does not
    come out of the arithmetic as an exact zero: two loops that share a grid
    point measure 3.469446951953614e-18 mm apart through `_nearest_on_ring`'s
    projection. So the refusal stood down and the sketch went out with a note
    reading "two parts of this artwork pass 0.00 microns apart" — measured
    2026-09-17 on 3 of 474 hard-scaled traces (round seven,
    probes/imgtrace_r7_report_gap.py)."""
    m = _ring_with_mixed_spokes(131, [(5.825232830329833, 1),
                                      (4.6218438148683765, 2)])
    for residual in (0.0, 3.469446951953614e-18, 1e-12, 1e-9):
        real = imgtrace._worst_residual
        imgtrace._worst_residual = lambda loops, stuck, r=residual: r
        try:
            with pytest.raises(ValueError, match="meet at a point"):
                imgtrace.image_to_entities(_png(m), height_mm=9.5)
            ents = [imgtrace._poly_entity(
                [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], "add")]
            with pytest.raises(ValueError, match="meet at a point"):
                imgtrace.settle(ents)
        finally:
            imgtrace._worst_residual = real


def test_settling_leaves_art_that_is_already_clear_alone():
    """The guard must not redraw art a rescale did not harm: a plain disc
    scaled to a tenth keeps every polygon, every point and its size."""
    m = np.zeros((400, 400), np.uint8)
    cv2.circle(m, (200, 200), 150, 1, -1)
    cv2.circle(m, (200, 200), 60, 0, -1)
    ents, _i = imgtrace.image_to_entities(_png(m), height_mm=30.0)
    for s in (0.9, 0.5, 0.1):
        out, note = imgtrace.settle(_rescaled(ents, s))
        assert note is None, f"s={s}: {note}"
        assert len(out) == len(ents)
        assert sum(len(e["points"]) for e in out) == sum(
            len(e["points"]) for e in ents), f"s={s}"


def test_artwork_whose_loops_still_meet_is_refused(monkeypatch):
    """With the guard unable to nudge anything, round five's own picture —
    whose two hole loops meet at exactly 0.000000000 mm — must come back as a
    sentence, not as a sketch that extrudes into a pinched open shell."""
    monkeypatch.setattr(imgtrace, "_hair_cluster",
                        lambda pts, v, span: None)
    m = _ring_with_mixed_spokes(131, [(5.825232830329833, 1),
                                      (4.6218438148683765, 2)])
    with pytest.raises(ValueError, match="meet at a point"):
        imgtrace.image_to_entities(_png(m), height_mm=9.5)
