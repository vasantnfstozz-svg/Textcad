"""Sketch polygons build counter-clockwise whichever way they were drawn.

OCCT takes the point order of a Polygon as the face's orientation: a polygon
drawn clockwise is a face whose normal points -Z. Adding it to a normal face did
not fail -- it silently produced TWO overlapping faces, which extrude into a
self-intersecting, non-manifold solid (BACKLOG P0, probed 2026-09-05). Paths
are not affected: make_face() orients them (probed the same day).
"""
import pytest

import inspector
import sketch as sk
from document import Document

CCW = {"kind": "polygon", "points": [[0, 0], [20, 0], [20, 20], [0, 20]]}
CW = {"kind": "polygon", "points": [[10, 10], [10, 30], [30, 30], [30, 10]]}


def test_signed_area_tells_the_winding():
    assert sk._signed_area([(0, 0), (20, 0), (20, 20), (0, 20)]) == 400
    assert sk._signed_area([(0, 0), (0, 20), (20, 20), (20, 0)]) == -400


def test_a_clockwise_polygon_faces_up():
    (face,) = sk._entity(CW).faces()
    assert tuple(round(v) for v in face.normal_at()) == (0, 0, 1)


def test_a_clockwise_polygon_fuses_with_a_counter_clockwise_one():
    faces = sk._compose([CCW, CW]).faces()
    assert len(faces) == 1 and faces[0].area == pytest.approx(700)


def test_a_clockwise_polygon_subtracts_too():
    faces = sk._compose([CCW, dict(CW, mode="subtract")]).faces()
    assert len(faces) == 1 and faces[0].area == pytest.approx(300)


def test_the_extruded_pair_is_one_healthy_solid_and_the_points_stay_as_drawn():
    doc = Document(name="t-winding")
    doc.add("s", "sketch", {"plane": "XY", "entities": [CCW, CW]})
    doc.add("b", "extrude", {"amount": 5}, inputs=["s"])
    assert doc.rebuild()
    solid = doc.result()
    assert inspector.health(solid) == []
    assert solid.volume == pytest.approx(700 * 5)
    assert doc.get("s").params["entities"][1]["points"] == CW["points"]
