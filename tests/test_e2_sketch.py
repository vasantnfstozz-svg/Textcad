"""E2 sketch system: entities, extrude/revolve/loft/sweep, tree integration."""
import pytest

import sketch as sk
import inspector
from document import Document, KNOWN_OPS


def test_sketch_compose_add_and_subtract():
    s = sk.make_sketch("XY", 0, [
        {"kind": "rectangle", "w": 40, "h": 20},
        {"kind": "circle", "r": 6, "x": 10, "mode": "subtract"}])
    assert sk.is_sketch(s) and s.area == pytest.approx(40*20 - 3.14159*36, rel=1e-2)


def test_all_entity_kinds():
    for e in ({"kind": "rectangle", "w": 10, "h": 10},
              {"kind": "circle", "r": 5},
              {"kind": "ellipse", "rx": 8, "ry": 4},
              {"kind": "slot", "length": 20, "height": 6},
              {"kind": "regular_polygon", "radius": 10, "sides": 6},
              {"kind": "polygon", "points": [[0, 0], [10, 0], [5, 8]]}):
        s = sk.make_sketch("XY", 0, [e])
        assert s.area > 0


def test_path_entity_lines_and_arcs():
    """The free-drawing tool: chained lines + 3-point arcs, auto-closed."""
    s = sk.make_sketch("XY", 0, [{
        "kind": "path", "start": [0, 0],
        "segments": [
            {"type": "line", "to": [40, 0]},
            {"type": "arc", "via": [50, 10], "to": [40, 20]},
            {"type": "line", "to": [0, 20]},
        ]}])
    assert sk.is_sketch(s) and s.area > 40 * 20        # rect + arc bulge


def test_path_in_document_extrudes():
    doc = Document(name="bracket-path")
    doc.add("prof", "sketch", {"plane": "XY", "entities": [{
        "kind": "path", "start": [0, 0],
        "segments": [
            {"type": "line", "to": [30, 0]},
            {"type": "arc", "via": [38, 10], "to": [30, 20]},
            {"type": "line", "to": [0, 20]},
        ]}]})
    doc.add("solid", "extrude", {"amount": 6}, inputs=["prof"])
    doc.spec = {"n_solids": 1}
    assert doc.rebuild(), doc.tree()


def test_path_requires_segments():
    with pytest.raises(ValueError):
        sk.make_sketch("XY", 0, [{"kind": "path", "start": [0, 0],
                                  "segments": []}])


def test_first_entity_cannot_subtract():
    with pytest.raises(ValueError):
        sk.make_sketch("XY", 0, [{"kind": "circle", "r": 5, "mode": "subtract"}])


def test_extrude_makes_solid():
    s = sk.make_sketch("XY", 0, [{"kind": "circle", "r": 10}])
    solid = sk.extrude_sketch(s, amount=5)
    assert inspector.health(solid) == []
    assert solid.volume == pytest.approx(3.14159*100*5, rel=1e-2)


def test_extrude_both_directions():
    s = sk.make_sketch("XY", 0, [{"kind": "rectangle", "w": 10, "h": 10}])
    solid = sk.extrude_sketch(s, amount=5, both=True)
    assert inspector.measure(solid)["size"][2] == pytest.approx(10, abs=0.01)


def test_revolve_makes_solid_of_revolution():
    prof = sk.make_sketch("XZ", 0, [{"kind": "rectangle", "w": 10, "h": 30, "x": 20}])
    solid = sk.revolve_sketch(prof, axis="Z", angle=360)
    assert inspector.health(solid) == []


def test_loft_between_sections():
    a = sk.make_sketch("XY", 0, [{"kind": "rectangle", "w": 40, "h": 40}])
    b = sk.make_sketch("XY", 30, [{"kind": "circle", "r": 10}])
    solid = sk.loft_sketches([a, b])
    assert inspector.health(solid) == [] and solid.volume > 0


def test_sweep_along_path():
    prof = sk.make_sketch("XY", 0, [{"kind": "circle", "r": 4}])
    solid = sk.sweep_sketch(prof, [[0, 0, 0], [0, 0, 30], [20, 0, 50]])
    assert inspector.health(solid) == [] and solid.volume > 0


def test_sketch_ops_registered():
    assert "sketch" in KNOWN_OPS
    assert {"extrude", "revolve", "loft", "sweep"} <= KNOWN_OPS


def test_sketch_then_extrude_in_document():
    doc = Document(name="bracket")
    doc.add("profile", "sketch", {"plane": "XY", "offset": 0, "entities": [
        {"kind": "rectangle", "w": 60, "h": 40},
        {"kind": "circle", "r": 8, "x": 20, "y": 10, "mode": "subtract"}]})
    doc.add("body", "extrude", {"amount": 8}, inputs=["profile"])
    doc.spec = {"n_solids": 1}
    assert doc.rebuild(), doc.tree()
    # the sketch node has no volume; the extrude node does
    assert doc.get("profile").volume is None
    assert doc.get("body").volume > 0
    assert doc.get("profile").status == "ok"


def test_result_skips_sketch_returns_solid():
    doc = Document(name="x")
    doc.add("s", "sketch", {"plane": "XY", "entities": [
        {"kind": "circle", "r": 10}]})
    doc.add("solid", "extrude", {"amount": 4}, inputs=["s"])
    doc.rebuild()
    assert not sk.is_sketch(doc.result())        # returns the solid, not sketch


def test_empty_sketch_flagged():
    doc = Document(name="x")
    # a lone sketch that fails to build (bad entity) -> failed status
    doc.add("s", "sketch", {"plane": "XY", "entities": [
        {"kind": "polygon", "points": [[0, 0], [1, 1]]}]})   # <3 pts
    assert not doc.rebuild()
    assert doc.get("s").status == "failed"
