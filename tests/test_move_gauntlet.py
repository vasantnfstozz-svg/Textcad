"""THE MOVE / ROTATE GAUNTLET (tests/gauntlet.py): every corpus body moved by
one offset and turned about its own centre on each world axis. A placement
must never break a body: a healthy solid, the same volume, the centre kept
(rotate) or shifted by exactly the offset (move). No refusal is allowed — a
transform of a valid solid has nothing to refuse (allow_failure=False).
"""
import build123d as b3d
import pytest

import blocks
from document import Document
from tests.gauntlet import BODIES, assert_op


def centre(part):
    c = part.bounding_box().center()
    return [c.X, c.Y, c.Z]


@pytest.mark.parametrize("body", sorted(BODIES))
def test_every_body_turns_in_place_about_every_axis(body):
    """the PIVOT stays put, not the bounding box's centre — an L-bracket's box
    is a different box once it has turned — so the proof is the way back:
    turned back by the same angle about the same point, the body is where it
    was"""
    solid = BODIES[body]()
    pivot = centre(solid)
    for axis in ("X", "Y", "Z"):
        for deg in (37.0, 90.0, -120.0):
            out = assert_op(f"{body} rotate {axis} {deg}",
                            lambda axis=axis, deg=deg: blocks.rotate(solid, axis, deg, pivot="center"),
                            allow_failure=False)
            assert out.volume == pytest.approx(solid.volume, rel=1e-6)
            back = blocks.rotate(out, axis, -deg, pivot=pivot)
            assert centre(back) == pytest.approx(pivot, abs=1e-5)
            # the pivot itself did not move: a dot there is untouched by the turn
            dot = blocks.rotate(b3d.Pos(*pivot) * b3d.Box(1, 1, 1), axis, deg, pivot=pivot)
            assert centre(dot) == pytest.approx(pivot, abs=1e-6)


@pytest.mark.parametrize("body", sorted(BODIES))
def test_every_body_moves_by_exactly_the_offset(body):
    solid = BODIES[body]()
    d = Document(name="g")
    d.add("b", "plate", {"width": 10, "depth": 10, "thickness": 10}, [])
    d.rebuild()
    d._parts["b"] = solid                      # the corpus body stands in for the plate
    d.add("m", "move", {"x": 3, "y": -4, "z": 5}, ["b"])
    f = next(x for x in d.features if x.id == "m")
    out = assert_op(f"{body} move", lambda: d._eval(f), allow_failure=False)
    c0 = centre(solid)
    assert centre(out) == pytest.approx([c0[0] + 3, c0[1] - 4, c0[2] + 5], abs=1e-6)
    assert out.volume == pytest.approx(solid.volume, rel=1e-6)
