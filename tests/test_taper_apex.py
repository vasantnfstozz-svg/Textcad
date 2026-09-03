"""Fusion's taper semantics: the distance is a MAXIMUM — when the narrowing
walls meet before it, the solid ends where they meet.

User, 2026-09-03: "I checked with Fusion 360, tried every shape, all of them go
until -90 taper angle, until flat as the sketch — there is no limit." Before
this, TextCAD stopped the ANGLE where the walls would meet (the ring's handle
froze). Now any angle builds: a steeper taper is simply a lower cone /
pyramid / ridge, flat on the sketch at 90°.

The meeting depth is measured on the kernel's own 2D offset by bisection
(sketch.collapse_offset) — exact for odd outlines and holes — and the tool plan
reports the same number, so the handle, the ghost and the solid agree.
Taper sign is Fusion's: negative narrows.
"""
import math

import pytest

import inspector
import sketch as sk
import toolplan
from document import Document

F = sk.APEX_FRACTION


def sketch(*ents, plane="XY", offset=0.0):
    return sk.make_sketch(plane=plane, offset=offset, entities=list(ents))


def zspan(solid):
    bb = solid.bounding_box()
    return bb.min.Z, bb.max.Z


# ------------------------------------------------------- the measurement ---

@pytest.mark.parametrize("ents, expected", [
    ([{"kind": "rectangle", "w": 20, "h": 30}], 10.0),            # ridge: half the short side
    ([{"kind": "rectangle", "w": 40, "h": 40}], 20.0),            # point: half the side
    ([{"kind": "circle", "r": 5}], 5.0),                          # point: the radius
    ([{"kind": "slot", "length": 30, "height": 10}], 5.0),        # half the height
    # an L: 40x40 with a 20x20 corner removed — both arms are 20 wide -> 10
    ([{"kind": "polygon", "points": [[0, 0], [40, 0], [40, 20], [20, 20], [20, 40], [0, 40]]}], 10.0),
    # a ring: 40x40 with an r10 hole — the wall is 10, walls meet at 5
    ([{"kind": "rectangle", "w": 40, "h": 40}, {"kind": "circle", "r": 10, "mode": "subtract"}], 5.0),
])
def test_collapse_offset_is_where_the_walls_meet(ents, expected):
    face = sketch(*ents).faces()[0]
    assert sk.collapse_offset(face) == pytest.approx(expected, abs=0.02)


def test_the_l_shape_is_measured_not_estimated():
    """the naive 'min centroid-to-boundary' estimate is wrong for an L (its
    centroid sits near the inner corner); the kernel measurement is 10"""
    ents = [{"kind": "polygon", "points": [[0, 0], [40, 0], [40, 20], [20, 20], [20, 40], [0, 40]]}]
    d = Document(name="l")
    d.add("s", "sketch", {"plane": "XY", "entities": ents}, [])
    d.rebuild()
    p = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"})
    assert p["ok"], p
    assert p["limits"]["inradius"] == pytest.approx(10.0, abs=0.02)
    assert p["limits"]["collapse_offset"] == p["limits"]["inradius"]


# ------------------------------------------------------ the built height ---

def test_a_cone_ends_at_its_tip_and_gets_lower_as_the_angle_steepens():
    r, h = 35.39, 37.13                                  # the user's screenshot
    prof = sketch({"kind": "circle", "r": r})
    below = sk.extrude_sketch(prof, h, taper=-40)        # meets at 43.6: full height
    assert zspan(below)[1] == pytest.approx(h, abs=1e-3)
    last_top = None
    for t in (-45, -60, -75, -89):
        s = sk.extrude_sketch(prof, h, taper=t)
        top = zspan(s)[1]
        expect = F * r / math.tan(math.radians(-t))
        assert top == pytest.approx(expect, abs=0.01), (t, top, expect)
        assert not inspector.health(s), (t, inspector.health(s))
        # a complete cone: volume within 0.5% of pi r^2 h / 3
        assert s.volume == pytest.approx(math.pi * r * r * top / 3, rel=5e-3), t
        assert last_top is None or top < last_top
        last_top = top
    assert last_top < 0.7                                # -89: practically flat


def test_a_rectangle_ends_at_its_ridge():
    prof = sketch({"kind": "rectangle", "w": 20, "h": 30})
    full = sk.extrude_sketch(prof, 10, taper=-30)         # meets at 45: full height
    assert zspan(full)[1] == pytest.approx(10, abs=1e-3)
    roof = sk.extrude_sketch(prof, 10, taper=-60)
    assert zspan(roof)[1] == pytest.approx(F * 10 / math.tan(math.radians(60)), abs=0.01)
    assert not inspector.health(roof)
    flat = sk.extrude_sketch(prof, 10, taper=-89)
    assert zspan(flat)[1] == pytest.approx(F * 10 / math.tan(math.radians(89)), abs=0.01)
    assert zspan(flat)[1] < 0.2


def test_symmetric_and_flipped_extrudes_cap_both_ways():
    prof = sketch({"kind": "rectangle", "w": 20, "h": 30})
    h = F * 10 / math.tan(math.radians(60))
    sym = sk.extrude_sketch(prof, 10, both=True, taper=-60)
    lo, hi = zspan(sym)
    assert hi == pytest.approx(h, abs=0.01) and lo == pytest.approx(-h, abs=0.01)
    down = sk.extrude_sketch(prof, 10, flip=True, taper=-60)
    lo, hi = zspan(down)
    assert lo == pytest.approx(-h, abs=0.01) and hi == pytest.approx(0, abs=1e-3)


def test_a_ring_profile_ends_where_hole_and_wall_meet():
    prof = sketch({"kind": "rectangle", "w": 40, "h": 40},
                  {"kind": "circle", "r": 10, "mode": "subtract"})
    s = sk.extrude_sketch(prof, 30, taper=-45)            # wall 10 -> meets at 5 mm up
    assert zspan(s)[1] == pytest.approx(F * 5.0, abs=0.02)
    assert not inspector.health(s)


def test_a_face_pick_caps_too_and_stays_on_the_outward_side():
    d = Document(name="b")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 20}, [])
    d.rebuild()
    body = d._parts["b"]
    boss = sk.extrude_face(body, [0, 0, 10], [0, 0, 1], amount=30, taper=-80)   # meets at 20/tan80
    lo, hi = zspan(boss)
    assert lo == pytest.approx(10, abs=1e-3)
    assert hi == pytest.approx(10 + F * 20 / math.tan(math.radians(80)), abs=0.01)
    assert not inspector.health(boss)
    pocket = sk.extrude_face(body, [0, 0, 10], [0, 0, 1], amount=30, taper=-80, flip=True)
    lo, hi = zspan(pocket)
    assert hi == pytest.approx(10, abs=1e-3) and lo > 6.4


def test_flaring_and_through_cuts_are_untouched():
    prof = sketch({"kind": "rectangle", "w": 20, "h": 30})
    flare = sk.extrude_sketch(prof, 10, taper=60)
    assert zspan(flare)[1] == pytest.approx(10, abs=1e-3)
    thru = sk.extrude_sketch(prof, 4, taper=-80, through=True)   # through ignores taper
    assert zspan(thru)[1] == pytest.approx(sk.THROUGH_MM, rel=1e-6)


def test_the_plan_and_the_build_share_one_number():
    d = Document(name="p")
    d.add("s", "sketch", {"plane": "XY", "entities": [{"kind": "slot", "length": 30, "height": 10}]}, [])
    d.rebuild()
    p = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s"})
    r = p["limits"]["inradius"]
    s = sk.extrude_sketch(d._parts["s"], 20, taper=-70)
    assert zspan(s)[1] == pytest.approx(F * r / math.tan(math.radians(70)), abs=0.02)
