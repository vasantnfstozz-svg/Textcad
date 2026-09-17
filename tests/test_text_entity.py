"""Text sketch entity (Tier 2, specs/text-entity.md): a word as glyph faces.

Every figure came off the kernel first (probes/text_api_probe.py, Arial on
this box): 'Hi' at 10 mm is 3 faces of 22.150 mm2 in a 7.96 x 7.16 box;
'OBA' carries 4 holes; plate 40x20 minus 'AB' at 10 is 800 - 35.921; an
empty word raises a raw kernel ValueError.
"""
import pytest

import sketch as sk
from document import Document

KERNEL_WORDS = ("StdFail", "Standard_", "BRep", "TopoDS", "OCP", "NoneType", "Traceback",
                "repositioned")


def text(word="Hi", size=10.0, **kw):
    return {"kind": "text", "text": word, "size": size, "mode": "add", **kw}


def test_a_word_is_finished_glyph_faces_with_their_holes():
    s = sk.make_sketch(plane="XY", entities=[text("Hi")])
    assert len(s.faces()) == 3 and s.area == pytest.approx(22.150, abs=0.01)
    bb = s.bounding_box()
    assert bb.size.X == pytest.approx(7.96, abs=0.02) and bb.size.Y == pytest.approx(7.16, abs=0.02)
    assert bb.center().X == pytest.approx(0, abs=1e-6) and bb.center().Y == pytest.approx(0, abs=1e-6)
    o = sk.make_sketch(plane="XY", entities=[text("OBA")])
    assert sum(len(f.inner_wires()) for f in o.faces()) == 4


def test_x_y_and_rotation_place_the_words_centre():
    s = sk.make_sketch(plane="XY", entities=[text("Hi", x=20, y=5, rotation=30)])
    c = s.bounding_box().center()
    assert (c.X, c.Y) == pytest.approx((20, 5), abs=0.05)
    assert s.area == pytest.approx(22.150, abs=0.01)


def test_engraving_is_the_plate_minus_the_word():
    s = sk.make_sketch(plane="XY", entities=[
        {"kind": "rectangle", "w": 40, "h": 20, "mode": "add"},
        text("AB", mode="subtract")])
    # 764.099 measured (the standalone 'AB' is 35.921; the difference of 0.02
    # is the kernel's boolean, not a lost piece: 4 faces come back)
    assert s.area == pytest.approx(764.099, abs=0.01)
    assert len(s.faces()) == 4
    # rel 1e-4, not 1e-6: the kernel integrates a spline-walled prism's volume
    # numerically (measured 1528.159 against 2 x 764.099 = 1528.197)
    assert sk.extrude_sketch(s, 2).volume == pytest.approx(2 * s.area, rel=1e-4)


def test_a_word_extrudes_into_one_body_per_piece_and_the_document_allows_it():
    d = Document(name="t")
    d.add("s", "sketch", {"plane": "XY", "entities": [text("TEXTCAD")]}, [])
    d.add("e", "extrude", {"amount": 3}, ["s"])
    d.rebuild()
    f = d.get("e")
    assert f.status == "ok", f.problems
    assert f.pieces == 7 and f.volume == pytest.approx(308.398, abs=0.05)
    assert not d.warnings, d.warnings


def test_engraving_a_face_sketch_drops_the_volume_by_the_letters():
    d = Document(name="t")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("s", "sketch_on_face", {"face": "top", "offset": 0, "entities": [text("AB")]}, ["b"])
    d.add("e", "extrude", {"amount": -2}, ["s"])
    d.add("cut1", "cut", {}, ["b", "e"])
    d.rebuild()
    assert d.get("cut1").status == "ok", d.get("cut1").problems
    assert d.get("cut1").volume == pytest.approx(60 * 40 * 12 - 2 * 35.921, abs=0.2)


@pytest.mark.parametrize("font", ["Arial", "Times New Roman", "Courier New", "NoSuchFont123"])
def test_fonts_build_and_an_unknown_one_falls_back(font):
    s = sk.make_sketch(plane="XY", entities=[text("Hi", font=font)])
    assert len(s.faces()) == 3 and s.area > 10


@pytest.mark.parametrize("bad,needle", [
    (text(""), "needs a word"),
    (text("   "), "needs a word"),
    ({"kind": "text", "size": 10, "mode": "add"}, "needs a word"),
    (text("Hi", size=0), "greater than 0"),
    (text("Hi", size=-3), "greater than 0"),
    (text("Hi", font=3), "font must be a name"),
    (text("Hi", size="ten"), "must be a number"),
])
def test_refusals_are_sentences(bad, needle):
    with pytest.raises(ValueError) as e:
        sk.make_sketch(plane="XY", entities=[bad])
    msg = str(e.value)
    assert needle in msg, msg
    assert not any(w in msg for w in KERNEL_WORDS), msg


def test_the_schema_tells_the_tree_about_the_word_and_the_server_outline():
    schema = sk.entity_schema()
    assert schema["fields"]["text"] == [{"key": "size", "label": "height", "unit": "mm"}]
    assert {f["key"] for f in schema["strings"]["text"]} == {"text", "font"}
    assert schema["server_outline"] == ["text"]
    assert "text" in sk.entity_kinds_in_code()


def test_entity_outlines_are_the_glyph_loops_placed_like_the_entity():
    loops = sk.entity_outlines(text("OBA"))
    assert len(loops) == 3 + 4, "one outer loop per piece plus every hole"
    xs = [p[0] for L in loops for p in L]
    ys = [p[1] for L in loops for p in L]
    assert max(xs) - min(xs) == pytest.approx(20.65, abs=0.1)
    assert (max(xs) + min(xs)) / 2 == pytest.approx(0, abs=0.05)
    moved = sk.entity_outlines(text("OBA", x=30, y=-10))
    xs2 = [p[0] for L in moved for p in L]
    ys2 = [p[1] for L in moved for p in L]
    assert (max(xs2) + min(xs2)) / 2 == pytest.approx(30, abs=0.05)
    assert (max(ys2) + min(ys2)) / 2 == pytest.approx(-10, abs=0.05)
    assert max(ys) - min(ys) == pytest.approx(max(ys2) - min(ys2), abs=1e-6)


def test_the_outline_endpoint_answers_per_entity():
    from fastapi.testclient import TestClient

    import studio
    with TestClient(studio.app) as c:
        r = c.post("/api/sketch/outline", json={"entities": [
            {"kind": "circle", "r": 5, "mode": "add"}, text("Hi"), text("")]}).json()
    assert r["outlines"][0] == [] and len(r["outlines"][1]) == 3 and r["outlines"][2] == []
    assert "needs a word" in r["errors"]["2"]
