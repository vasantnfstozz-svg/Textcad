"""Second review of the sketcher fix pass (556a611), 2026-09-09.

The first review's fix reordered every subtracting sketch to compose OUTERS
BEFORE HOLES. That fix shipped three defects of its own, each measured here
against the user's own library before it was fixed:

F1 (P0) `_compose` iterates in SORTED order but still refused a subtraction
        as the first entity of that order. `esp32-remote/logo_1_sketch`
        (modes add/subtract/add/add, depths [1, 0, 0, 0]) built at 4.37 mm2
        before the fix pass and raised
        `ValueError: sketch: first entity cannot be a subtraction` after it —
        the sketch and everything downstream of it went red.
F2 (P1) the new `try` wrapped only `make_face()`, so an arc whose middle
        point lies on the straight line between its ends raised raw
        `StdFail_NotDone: GC_MakeArcOfCircle::Value() - no result` out of
        `ThreePointArc` — kernel text in the tree, and a 500 from
        `/api/sketch/trim/pieces`.
F3 (P1) the bounding-box skip in `_nesting_depth` never fired:
        build123d's `BoundBox.is_inside` returns `not (strictly inside)` and
        a 2D sketch box is flat in Z, so it is ALWAYS True. Every pair ran a
        full boolean. Measured per rebuild: rocky-balboa/field_sketch
        +4128 ms (23 entities), rocky-keychain/words_sketch +1513 ms.
F8 (P3) a closed in-plane edge that is not a CIRCLE (an ellipse rim from an
        angled cut) produced no snap point at all — the seam is suppressed
        and the centre was added only under `if circle`.
"""
import math
import time

import build123d as b3d
import pytest

import sketch as sk
import sketch_snap as snap


def circle(r, mode="add", x=0.0, y=0.0):
    return {"kind": "circle", "mode": mode, "x": x, "y": y, "r": r}


# ------------------------------------------------------------------- F1 (P0)
# The shape of `esp32-remote/logo_1_sketch`: a small ADD nested inside a
# top-level SUBTRACT, then two adds standing clear of both. Depths are
# [1, 0, 0, 0], so sorting by depth hoists the subtraction to the front.
LOGO_1 = [circle(5, "add"), circle(20, "subtract"),
          circle(3, "add", x=100), circle(3, "add", x=110)]
LOGO_1_AREA = 2 * math.pi * 9      # the two clear adds; the nested one is eaten


def test_a_top_level_subtraction_no_longer_kills_the_sketch():
    """F1: measured on the real design this raised ValueError where it had
    built at 4.37 mm2. A subtraction that sorts first must WAIT for the first
    add, not refuse the whole sketch."""
    assert sk.make_sketch("XY", 0, LOGO_1).area == pytest.approx(
        LOGO_1_AREA, abs=0.01)


def test_the_deferred_subtraction_still_subtracts():
    """The held-back subtraction is not silently dropped: the add nested
    inside it is gone from the result."""
    area = sk.make_sketch("XY", 0, LOGO_1).area
    assert area < math.pi * 5**2, "the nested add survived a subtraction"


def test_a_sketch_of_nothing_but_holes_is_still_refused():
    """The guard has to stay reachable: with no add anywhere there is nothing
    to cut FROM, and that is a real mistake, not an ordering question."""
    with pytest.raises(ValueError, match="subtraction"):
        sk.make_sketch("XY", 0, [circle(10, "subtract")])


def test_the_first_review_fixes_are_untouched():
    """The two P0s the reorder exists for. A bore drawn before its rim was
    2827.43 mm2 (a solid disc) instead of 2513.27; r10/r30/r20 in drawing
    order was 1570.80 instead of 1884.96."""
    washer = sk.make_sketch("XY", 0, [circle(10, "subtract"), circle(30)])
    assert washer.area == pytest.approx(math.pi * (30**2 - 10**2), abs=1.0)
    island = sk.make_sketch(
        "XY", 0, [circle(10), circle(30), circle(20, "subtract")])
    assert island.area == pytest.approx(
        math.pi * (30**2 - 20**2 + 10**2), abs=1.0)


# ------------------------------------------------------------------- F2 (P1)
KERNEL_WORDS = ("StdFail", "Standard_", "GC_Make", "BRep_API", "gp_",
                "TypeMismatch", "NotDone")


def _plain(exc) -> bool:
    return not any(w in str(exc) for w in KERNEL_WORDS)


COLLINEAR_VIA = {"kind": "path", "start": [0, 0], "segments": [
    {"type": "line", "to": [20, 0]},
    {"type": "arc", "via": [10, 10], "to": [0, 20]},    # via ON the chord
    {"type": "line", "to": [0, 0]},
]}
VIA_ON_AN_END = {"kind": "path", "start": [0, 0], "segments": [
    {"type": "line", "to": [20, 0]},
    {"type": "arc", "via": [20, 0], "to": [0, 20]},     # via = the arc's start
    {"type": "line", "to": [0, 0]},
]}


@pytest.mark.parametrize("ent,label", [(COLLINEAR_VIA, "collinear"),
                                       (VIA_ON_AN_END, "via on an end")])
def test_an_unbuildable_arc_never_speaks_opencascade(ent, label):
    """F2: both of these raised StdFail_NotDone straight out of ThreePointArc,
    which is outside the try that wrapped make_face()."""
    with pytest.raises(ValueError) as e:
        sk._entity(ent)
    assert _plain(e.value), f"{label}: kernel text reached the user: {e.value}"


def test_the_named_arc_message_says_which_curve():
    with pytest.raises(ValueError, match="arc"):
        sk._entity(COLLINEAR_VIA)


def test_a_real_arc_is_not_a_false_positive():
    """The danger of any arc guard. OCCT itself accepts a via 1e-6 off a
    100 mm chord (probed), so the kernel stays the judge - we only translate
    its verdict."""
    flat = {"kind": "path", "start": [0, 0], "segments": [
        {"type": "line", "to": [100, 0]},
        {"type": "line", "to": [100, 20]},
        {"type": "arc", "via": [50, 20 + 1e-6], "to": [0, 20]},
    ]}
    assert sk._entity(flat).area > 0
    crescent = {"kind": "path", "start": [0, 0], "segments": [
        {"type": "arc", "via": [10, 8], "to": [20, 0]},
        {"type": "arc", "via": [10, 3], "to": [0, 0]},
    ]}
    assert sk._entity(crescent).area > 0


# ------------------------------------------------------------------- F3 (P1)
def test_the_bounding_box_skips_a_pair_that_cannot_be_nested():
    """F3: build123d's BoundBox.is_inside is `not (strictly inside)` and a
    sketch box is flat in Z, so the old call was always True."""
    small = b3d.Rectangle(2, 2).bounding_box()
    far = (b3d.Pos(200, 200) * b3d.Rectangle(2, 2)).bounding_box()
    big = b3d.Rectangle(50, 50).bounding_box()
    assert sk._box_within(small, big), "a nested box must NOT be skipped"
    assert not sk._box_within(far, big), "a far box must be skipped"
    assert not sk._box_within(big, small)


def test_a_straddling_circle_is_still_decided_by_measurement():
    """The bounding box may only SKIP a pair, never decide one: a circle
    straddling the rim passes the box test and must fail the real one."""
    shapes = [sk._entity(circle(30)), sk._entity(circle(10, x=25))]
    assert sk._nesting_depth(shapes) == [0, 0]


def test_the_box_may_skip_a_pair_but_never_decide_one():
    """The rule the docstring claims, with a shape that forces it: an L and a
    circle in the L's missing quadrant. The circle's box (10..20) sits well
    inside the L's box (-30..30), so the filter passes the pair through and
    only the measured boolean can say it is NOT contained."""
    ell = {"kind": "polygon", "mode": "add", "x": 0, "y": 0, "points": [
        [-30, -30], [30, -30], [30, 0], [0, 0], [0, 30], [-30, 30]]}
    shapes = [sk._entity(ell), sk._entity(circle(5, x=15, y=15))]
    boxes = [s.bounding_box() for s in shapes]
    assert sk._box_within(boxes[1], boxes[0]), "the filter must not skip this"
    assert sk._nesting_depth(shapes) == [0, 0]


def test_nesting_depth_is_not_quadratic_in_full_booleans():
    """F3: 24 disjoint entities took ~4 s of real booleans per rebuild on the
    user's rocky-balboa/field_sketch. With the box filter it is a few ms; the
    ceiling here is 400x under what it measured."""
    shapes = [sk._entity(circle(2, x=10 * i)) for i in range(24)]
    t = time.perf_counter()
    depth = sk._nesting_depth(shapes)
    assert depth == [0] * 24
    assert time.perf_counter() - t < 1.0


# ------------------------------------------------------------------- F5 (P1)
def test_a_path_entity_without_a_start_is_legal():
    """The frontend's entSamplePts read e.start[0] unguarded, so clicking Edit
    on this threw TypeError before sketch mode opened. Locking the backend
    contract the editor has to tolerate: start defaults to the origin."""
    ent = {"kind": "path", "segments": [
        {"type": "line", "to": [10, 0]},
        {"type": "line", "to": [10, 8]},
        {"type": "line", "to": [0, 8]},
    ]}
    assert "start" not in ent
    assert sk._entity(ent).area == pytest.approx(80.0, abs=0.01)


# ------------------------------------------------------------------- F8 (P3)
def test_an_elliptical_bore_still_offers_its_centre():
    """F8: the seam suppression is right, but the centre was added only for a
    CIRCLE, so a closed ELLIPSE edge left the user with no snap point on that
    feature at all. The edge here is the floor rim of an elliptical pocket
    (probed: GeomType.ELLIPSE, closed, arc_center (0, 0, 0) — note that the
    pocket's TOP rim is a closed BSPLINE, which has no defined centre and is
    deliberately still left alone)."""
    part = b3d.Box(40, 40, 10) - b3d.extrude(
        b3d.Plane.XY * b3d.Ellipse(8, 4), amount=20)
    out = snap.snap_geometry({"b": part}, "XY", 0.0)
    centres = [p for p in out["points"] if p["kind"] == "center"]
    assert any(abs(p["x"]) < 1e-6 and abs(p["y"]) < 1e-6 for p in centres), \
        f"no centre snap for the elliptical rim; got {out['points']}"


def test_a_bores_seam_is_still_not_a_corner():
    """The first review's fix stays: no corner/midpoint from a closed edge."""
    part = b3d.Box(40, 40, 10) - b3d.extrude(
        b3d.Plane.XY * b3d.Circle(5), amount=20)
    out = snap.snap_geometry({"b": part}, "XY", 5.0)
    for p in out["points"]:
        if p["kind"] in ("corner", "midpoint"):
            assert math.hypot(p["x"], p["y"]) > 6.0, f"seam point {p}"
