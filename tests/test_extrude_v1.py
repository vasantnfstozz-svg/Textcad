"""Extrude v1 (Fusion-style): direction (one/symmetric/two), flip, taper.
All must build healthy solids with the expected extents."""
import pytest

import sketch as sk
import inspector
from document import Document


def _rect():
    return sk.make_sketch("XY", 0, [{"kind": "rectangle", "w": 40, "h": 40}])


def _zspan(solid):
    bb = solid.bounding_box()
    return round(bb.min.Z, 3), round(bb.max.Z, 3)


def test_one_side():
    s = sk.extrude_sketch(_rect(), amount=30)
    assert not inspector.health(s)
    assert _zspan(s) == (0, 30)


def test_flip_reverses_direction():
    s = sk.extrude_sketch(_rect(), amount=30, flip=True)
    assert _zspan(s) == (-30, 0)


def test_symmetric_both_sides():
    s = sk.extrude_sketch(_rect(), amount=10, both=True)
    assert _zspan(s) == (-10, 10)          # `amount` each side


def test_two_sided_asymmetric():
    s = sk.extrude_sketch(_rect(), amount=20, amount2=5)
    assert not inspector.health(s)
    assert _zspan(s) == (-5, 20)


def test_collapsing_taper_gives_friendly_error():
    """A profile WITH A HOLE at steep taper makes OCCT fail with a bare
    RuntimeError('Unexpected result type') — users must get guidance instead."""
    s = sk.make_sketch("XY", 0, [
        {"kind": "rectangle", "w": 40, "h": 20},
        {"kind": "circle", "r": 5, "mode": "subtract"}])
    with pytest.raises(ValueError, match="too steep"):
        sk.extrude_sketch(s, amount=15, taper=35)


def test_taper_narrows_and_is_healthy():
    straight = sk.extrude_sketch(_rect(), amount=30)
    tapered = sk.extrude_sketch(_rect(), amount=30, taper=10)
    assert not inspector.health(tapered)
    assert tapered.volume < straight.volume     # positive taper removes material


def test_string_bools_coerced():
    # dialog may send strings; must not silently misbehave (P0-1 lesson)
    s = sk.extrude_sketch(_rect(), amount=10, both="true")
    assert _zspan(s) == (-10, 10)
    s2 = sk.extrude_sketch(_rect(), amount=10, flip="false", both="false")
    assert _zspan(s2) == (0, 10)


def test_extrude_in_document_with_new_params():
    doc = Document(name="ext")
    doc.add("sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "circle", "r": 10}]})
    doc.add("body", "extrude", {"amount": 15, "taper": 5}, inputs=["sk"])
    assert doc.rebuild(), [f.problems for f in doc.features]
    assert doc.get("body").status == "ok" and doc.get("body").volume > 0


def test_op_catalog_exposes_new_extrude_params():
    import author
    cat = {c["op"]: c for c in author.op_catalog()}
    names = [p["name"] for p in cat["extrude"]["params"]]
    for p in ("amount", "both", "amount2", "taper", "flip"):
        assert p in names, f"{p} missing from extrude params: {names}"
    assert "extrude_face" in cat            # face extrude registered


# ---------------------------------------------------- extrude a picked FACE

def _box_doc():
    doc = Document(name="facebox")
    doc.add("sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["sk"])
    return doc


def test_extrude_face_boss_joins_exactly():
    """Fusion flow: pick the top face, pull 8mm, Join."""
    doc = _box_doc()
    doc.add("boss", "extrude_face",
            {"face_center": [0, 0, 10], "face_normal": [0, 0, 1], "amount": 8},
            inputs=["body"])
    doc.add("joined", "fuse", inputs=["body", "boss"])
    assert doc.rebuild(), [f.problems for f in doc.features]
    assert doc.result().volume == pytest.approx(40 * 30 * 18, rel=1e-6)


def test_extrude_face_negative_cut_makes_pocket():
    """Drag INTO the body + Cut = pocket."""
    doc = _box_doc()
    doc.add("plunge", "extrude_face",
            {"face_center": [0, 0, 10], "face_normal": [0, 0, 1], "amount": -4},
            inputs=["body"])
    doc.add("pocket", "cut", inputs=["body", "plunge"])
    assert doc.rebuild(), [f.problems for f in doc.features]
    assert doc.result().volume == pytest.approx(40 * 30 * 6, rel=1e-6)


def test_extrude_face_keeps_holes_exact():
    doc = _box_doc()
    doc.add("bore", "with_center_hole", {"radius": 5}, inputs=["body"])
    doc.add("boss", "extrude_face",
            {"face_center": [0, 0, 10], "face_normal": [0, 0, 1], "amount": 8},
            inputs=["bore"])
    assert doc.rebuild(), [f.problems for f in doc.features]
    import math
    assert doc.get("boss").volume == pytest.approx(
        (40 * 30 - math.pi * 25) * 8, rel=1e-6)   # hole preserved exactly


def test_extrude_face_rejects_curved_face():
    """Defense-in-depth for API/AI callers (the UI only offers PLANE picks):
    picking the cylinder side's true face center must raise, not extrude."""
    import blocks
    c = blocks.disc(10, 20)                      # side face center is (-10,0,0)
    with pytest.raises(ValueError, match="not flat"):
        sk.extrude_face(c, [-10, 0, 0], [-1, 0, 0], amount=5)
