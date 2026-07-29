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
