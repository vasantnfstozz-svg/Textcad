"""E5 (scoped): sketch on a picked face, with rebuild-robust face resolution."""
import pytest

import sketch as sk
import inspector
from document import Document, KNOWN_OPS


def test_sketch_on_face_builds_on_the_top():
    box = __import__("blocks").plate(60, 40, 20)     # top face at z=10
    s = sk.sketch_on_face(box, face_center=[0, 0, 10], face_normal=[0, 0, 1],
                          entities=[{"kind": "circle", "r": 8}])
    assert sk.is_sketch(s)
    # the sketch sits at z=10 (on the top face), not at the origin
    assert s.center().Z == pytest.approx(10, abs=0.1)


def test_boss_workflow_in_document():
    doc = Document(name="boss")
    doc.add("base", "plate", {"width": 60, "depth": 40, "thickness": 20})
    doc.add("prof", "sketch_on_face",
            {"face_center": [0, 0, 10], "face_normal": [0, 0, 1],
             "entities": [{"kind": "circle", "r": 8}]}, inputs=["base"])
    doc.add("boss", "extrude", {"amount": 10}, inputs=["prof"])
    doc.add("part", "fuse", inputs=["base", "boss"])
    doc.spec = {"n_solids": 1}
    assert doc.rebuild(), doc.tree()
    assert inspector.measure(doc.result())["size"][2] == pytest.approx(30, abs=0.1)


def test_face_resolution_survives_parameter_change():
    """The whole point: change the base thickness and the sketch should still
    land on the (now moved) top face, because it's resolved by geometry."""
    doc = Document(name="robust")
    doc.add("base", "plate", {"width": 60, "depth": 40, "thickness": 20})
    doc.add("prof", "sketch_on_face",
            {"face_center": [0, 0, 10], "face_normal": [0, 0, 1],
             "entities": [{"kind": "circle", "r": 8}]}, inputs=["base"])
    doc.add("boss", "extrude", {"amount": 10}, inputs=["prof"])
    doc.add("part", "fuse", inputs=["base", "boss"])
    assert doc.rebuild()
    # make the base thicker: top face moves from z=10 to z=15
    doc.edit("base", "thickness", 30)
    assert doc.rebuild(), doc.tree()
    # boss still sits on top -> total height = 30 (base) + 10 (boss) = 40
    assert inspector.measure(doc.result())["size"][2] == pytest.approx(40, abs=0.6)


def test_sketch_on_face_registered():
    assert "sketch_on_face" in KNOWN_OPS
