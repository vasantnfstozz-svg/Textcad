"""The sketch plane's offset — the backend facts (R1: the browser draws what
the server says).

  * /api/face-outline reports `into_sign`: which sign of the offset goes INTO
    the material. The frame is canonical (face_sketch_plane), so it is NOT one
    sign per axis pair the way sketch_on_face's docstring says: +y's frame z
    points -Y, so on a +y face POSITIVE goes in. Measured, not derived.
  * the frame moves along its own z by the offset — the same Plane.offset the
    sketch build uses, so grid and geometry cannot differ.
  * `offset` on a sketch_on_face is an ordinary parameter: the tree edits it
    and downstream rebuilds.
The UI that sets an offset is Construct > Offset Plane (tests/test_offset_plane.py,
tests/e2e/test_offset_plane.py); the sketch's own `offset` stays for the AI
author and for every saved design.
"""

import build123d as b3d
import pytest

import sketch as sk
from document import Document

CIRCLE = [{"kind": "circle", "r": 5}]


def plate():
    return b3d.Box(60, 40, 20)          # centred: top z = +10, bottom z = -10


# --------------------------------------------------------------- backend ---

@pytest.mark.parametrize("face, sign, axis, inside", [
    ("top", -1, 2, 7), ("bottom", 1, 2, -7),
    ("+x", -1, 0, 27), ("-x", 1, 0, -27),
    ("+y", 1, 1, 17), ("-y", -1, 1, -17)])
def test_face_outline_says_which_sign_goes_into_the_material(face, sign, axis, inside):
    out = sk.face_outline_2d(plate(), face=face)
    assert out["planar"] and out["into_sign"] == sign
    # and it is the truth: 3 mm with that sign puts the frame origin 3 mm
    # INSIDE the 60 x 40 x 20 box on that face's axis
    moved = sk.face_outline_2d(plate(), face=face, offset=sign * 3)
    assert moved["frame"]["origin"][axis] == pytest.approx(inside, abs=1e-3)


def test_face_outline_frame_moves_by_the_offset_along_its_own_z():
    p = plate()
    o0 = sk.face_outline_2d(p, face="top")
    o5 = sk.face_outline_2d(p, face="top", offset=-5)
    z = o0["frame"]["z_dir"]
    for i in range(3):
        assert o5["frame"]["origin"][i] == pytest.approx(
            o0["frame"]["origin"][i] - 5 * z[i], abs=1e-3)
    assert o5["frame"]["origin"][2] == pytest.approx(5, abs=1e-3)
    # the 2D boundary is the same picture — only the plane moved
    assert o5["outer"] == o0["outer"]
    assert o5["into_sign"] == o0["into_sign"]


def test_face_sketch_offset_places_the_profile_where_the_frame_says():
    p = plate()
    placed = sk.sketch_on_face(p, face="top", offset=-5, entities=CIRCLE)
    bb = placed.bounding_box()
    assert bb.min.Z == pytest.approx(5) and bb.max.Z == pytest.approx(5)
    frame = sk.face_outline_2d(p, face="top", offset=-5)["frame"]
    assert frame["origin"][2] == pytest.approx(5, abs=1e-3)


def test_face_sketch_offset_is_an_editable_parameter_that_rebuilds():
    d = Document(name="t")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 20}, [])
    d.add("s", "sketch_on_face",
          {"face": "top", "offset": 0, "entities": CIRCLE}, ["b"])
    d.rebuild()
    assert d._parts["s"].bounding_box().center().Z == pytest.approx(10)
    d.edit("s", "offset", -5)                 # what the tree's offset row does
    d.rebuild()
    assert [f.status for f in d.features] == ["ok", "ok"]
    assert d._parts["s"].bounding_box().center().Z == pytest.approx(5)


def test_plane_sketch_offset_lands_the_profile_at_that_height():
    """the loft case: sections stacked on XY before any body exists"""
    d = Document(name="t")
    d.add("s1", "sketch", {"plane": "XY", "offset": 0, "entities": CIRCLE}, [])
    d.add("s2", "sketch", {"plane": "XY", "offset": 20, "entities": CIRCLE}, [])
    d.rebuild()
    assert d._parts["s1"].bounding_box().center().Z == pytest.approx(0)
    assert d._parts["s2"].bounding_box().center().Z == pytest.approx(20)
