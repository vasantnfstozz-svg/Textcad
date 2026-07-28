"""P0 regression tests — the silent-wrong-geometry / false-verification bugs
found by dogfooding round 1 (2026-07-28). Every one of these locked in a fix:

  P0-1  extrude both="false" (string) silently extruded both directions
  P0-2  slot built center-to-center while the canvas drew overall length
  P0-3  dangling branches (wrong upstream input) were invisible + "verified"
  P0-4  disjoint-entity sketches failed solid-verification (false alarm)
  P0-5  sketch_on_face accepted (then crashed on) curved faces
"""
import pytest

import build123d as b3d
import sketch as sk
from document import Document


# ---------------------------------------------------------------- P0-1: bools

def test_to_bool_strict():
    assert sk._to_bool(True, "x") is True
    assert sk._to_bool(False, "x") is False
    assert sk._to_bool("false", "x") is False      # THE bug: bool("false") is True
    assert sk._to_bool("true", "x") is True
    assert sk._to_bool("False", "x") is False
    assert sk._to_bool(0, "x") is False
    assert sk._to_bool(1, "x") is True
    assert sk._to_bool("", "x") is False
    with pytest.raises(ValueError):
        sk._to_bool("maybe", "x")
    with pytest.raises(ValueError):
        sk._to_bool(2, "x")


def test_extrude_string_false_is_single_sided():
    s = sk.make_sketch("XY", 0, [{"kind": "circle", "r": 10}])
    solid = sk.extrude_sketch(s, amount=5, both="false")
    bb = solid.bounding_box()
    assert bb.max.Z - bb.min.Z == pytest.approx(5, abs=1e-6)   # was 10 (doubled)


def test_extrude_string_true_is_double_sided():
    s = sk.make_sketch("XY", 0, [{"kind": "circle", "r": 10}])
    solid = sk.extrude_sketch(s, amount=5, both="true")
    bb = solid.bounding_box()
    assert bb.max.Z - bb.min.Z == pytest.approx(10, abs=1e-6)


def test_extrude_garbage_bool_rejected():
    s = sk.make_sketch("XY", 0, [{"kind": "circle", "r": 10}])
    with pytest.raises(ValueError, match="both"):
        sk.extrude_sketch(s, amount=5, both="maybe")


# ---------------------------------------------------------------- P0-2: slot

def test_slot_length_is_overall():
    """What the canvas draws (end-to-end 20) is what the solid measures."""
    s = sk.make_sketch("XY", 0, [{"kind": "slot", "length": 20, "height": 8}])
    solid = sk.extrude_sketch(s, amount=3)
    bb = solid.bounding_box()
    assert bb.max.X - bb.min.X == pytest.approx(20, abs=1e-6)  # was 28 (c2c + h)
    assert bb.max.Y - bb.min.Y == pytest.approx(8, abs=1e-6)


def test_slot_length_must_exceed_height():
    with pytest.raises(ValueError, match="length"):
        sk.make_sketch("XY", 0, [{"kind": "slot", "length": 5, "height": 8}])


# ------------------------------------------------------ P0-4: disjoint sketch

def test_disjoint_sketch_is_normalized_to_sketch():
    s = sk.make_sketch("XY", 0, [
        {"kind": "circle", "r": 3, "x": -20},
        {"kind": "circle", "r": 3, "x": 20}])
    assert isinstance(s, b3d.Sketch) and sk.is_sketch(s)
    assert s.area == pytest.approx(2 * 3.14159 * 9, rel=1e-3)


def test_disjoint_sketch_feature_verifies_ok_in_document():
    """The L-bracket false alarm: a valid 2-circle sketch turned the doc red."""
    doc = Document(name="bracket-holes")
    doc.add("base", "plate", {"width": 80, "depth": 60, "thickness": 6})
    doc.add("holes_sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "circle", "r": 3, "x": -20},
        {"kind": "circle", "r": 3, "x": 20}]})
    doc.add("pegs", "extrude", {"amount": 8, "both": True}, inputs=["holes_sk"])
    doc.add("final", "cut", inputs=["base", "pegs"])
    ok = doc.rebuild()
    assert ok, [f"{f.id}: {f.problems}" for f in doc.features]
    assert doc.get("holes_sk").status == "ok"
    assert doc.get("holes_sk").volume is None          # verified as 2D, not solid
    # cut removed two full-depth 3mm holes
    expected = 80 * 60 * 6 - 2 * 3.14159 * 9 * 6
    assert doc.result().volume == pytest.approx(expected, rel=1e-3)


# ------------------------------------------------------- P0-3: dangling body

def test_dangling_branch_is_warned():
    """The flange trap: bolt circle chained to disc1 instead of the bore —
    the bore vanished from the result while everything stayed green."""
    doc = Document(name="flange-trap")
    doc.add("disc1", "disc", {"radius": 50, "thickness": 12})
    doc.add("bore", "with_center_hole", {"radius": 12}, inputs=["disc1"])
    doc.add("bolts2", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 75},
            inputs=["disc1"])                      # WRONG: should chain from bore
    assert doc.rebuild()
    assert doc.warnings, "dangling 'bore' branch must be flagged"
    assert any("'bore'" in w for w in doc.warnings)


def test_linear_chain_has_no_warnings():
    doc = Document(name="flange-good")
    doc.add("disc1", "disc", {"radius": 50, "thickness": 12})
    doc.add("bore", "with_center_hole", {"radius": 12}, inputs=["disc1"])
    doc.add("bolts", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 75},
            inputs=["bore"])
    assert doc.rebuild()
    assert doc.warnings == []


def test_unconsumed_sketch_is_not_a_dangling_warning():
    doc = Document(name="sketch-only-extra")
    doc.add("body", "disc", {"radius": 20, "thickness": 10})
    doc.add("sk1", "sketch", {"plane": "XY", "entities": [
        {"kind": "circle", "r": 5}]})              # drawn but not yet consumed
    assert doc.rebuild()
    assert doc.warnings == []                      # sketches render separately


# --------------------------------------------------- P0-5: curved-face guard

def test_sketch_on_cylinder_face_rejected_clearly():
    cyl = b3d.Cylinder(10, 30)
    side = next(f for f in cyl.faces()
                if f.geom_type == b3d.GeomType.CYLINDER)
    c = side.center()
    with pytest.raises(ValueError, match="PLANAR|planar"):
        sk.sketch_on_face(cyl, [c.X, c.Y, c.Z], None,
                          [{"kind": "rectangle", "w": 6, "h": 25}])


def test_sketch_on_planar_face_still_works():
    cyl = b3d.Cylinder(10, 30)
    s = sk.sketch_on_face(cyl, [0, 0, 15], [0, 0, 1],
                          [{"kind": "circle", "r": 4}])
    assert sk.is_sketch(s) and s.area > 0
