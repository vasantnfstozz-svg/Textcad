"""Primitives: where they sit, and what they say when a dimension is wrong.

Section 5 of the from-scratch review (2026-09-10). Two failures were measured
and both are banned by CLAUDE.md:

* `polygon_plate` / `hex_plate` span Z 0..thickness, but `author.AUTHOR_PROMPT`
  told the AI they were CENTERED like disc and plate. Every `move` it computed
  for a hex body was half a thickness out (designs/planetary-assembly: four
  bolt heads seated 1.4 mm high). The geometry is what two saved designs are
  built on, so the PROMPT was corrected, not the solid -- and this file is the
  guard that keeps the two in step.
* A degenerate dimension put raw kernel text in the feature row:
  `Standard_DomainError('')` for a zero thickness, a twelve-line pybind11
  constructor dump for the string "8mm". Every op now refuses in words, and
  the rebuild translates anything that still gets through.
"""
import re

import pytest

import author
import blocks
from document import Document


# --------------------------------------------------------- where they sit ---

# (op, params, centred in Z?) -- measured, not assumed
Z_CONVENTION = [
    ("plate", {"width": 40, "depth": 30, "thickness": 8}, True),
    ("disc", {"radius": 20, "thickness": 8}, True),
    ("ball", {"radius": 15}, True),
    ("cone", {"bottom_radius": 20, "top_radius": 8, "height": 8}, True),
    ("tube", {"outer_radius": 20, "inner_radius": 12, "height": 8}, True),
    ("polygon_plate", {"sides": 6, "circumradius": 20, "thickness": 8}, False),
    ("hex_plate", {"across_flats": 30, "thickness": 8}, False),
]


@pytest.mark.parametrize("op,params,centred", Z_CONVENTION)
def test_z_span_is_what_the_docs_claim(op, params, centred):
    """The measured Z span, so a future change to any primitive trips here."""
    part = blocks.EXPORTS[op](**params)
    bb = part.bounding_box()
    if centred:
        assert bb.min.Z == pytest.approx(-bb.max.Z, abs=1e-9), \
            f"{op} was documented as centred but spans {bb.min.Z}..{bb.max.Z}"
    else:
        assert bb.min.Z == pytest.approx(0.0, abs=1e-9), \
            f"{op} was documented as standing on Z=0 but spans " \
            f"{bb.min.Z}..{bb.max.Z}"


def test_the_ai_prompt_names_exactly_the_centred_primitives():
    """The AI positions bodies with `move` from this one sentence. When it
    lists an op that is NOT centred, every assembly it builds with that op is
    half a thickness out -- and nothing else in the system notices."""
    m = re.search(r"POSITIONING \(critical\):(.+?)are\s+CENTERED at the origin",
                  author.AUTHOR_PROMPT, re.S)
    assert m, "the AUTHOR_PROMPT no longer states the centring convention"
    claimed = {op for op, _, _ in Z_CONVENTION if op in m.group(1)}
    centred = {op for op, _, c in Z_CONVENTION if c}
    assert claimed == centred, (
        f"the prompt calls {sorted(claimed)} centred; measurement says "
        f"{sorted(centred)}")


def test_the_prompt_says_where_the_uncentred_ones_stand():
    """Naming them as not-centred is not enough -- the AI needs the span."""
    for op, _, centred in Z_CONVENTION:
        if not centred:
            assert re.search(rf"{op}[^.]*stands? on Z=0|{op}[^.]*Z=0 up to",
                             author.AUTHOR_PROMPT), \
                f"the prompt never says where {op} sits"


# ------------------------------------------------ dimensions that are wrong --

# every one of these produced raw kernel or pybind11 text in the tree row
DEGENERATE = [
    ("plate", {"width": 0, "depth": 40, "thickness": 10}, "width"),
    ("plate", {"width": -5, "depth": 40, "thickness": 10}, "width"),
    ("plate", {"width": 40, "depth": 40, "thickness": 0}, "thickness"),
    ("disc", {"radius": 0, "thickness": 10}, "radius"),
    ("disc", {"radius": 20, "thickness": 0}, "thickness"),
    ("ball", {"radius": 0}, "radius"),
    ("ball", {"radius": -4}, "radius"),
    ("cone", {"bottom_radius": 0, "top_radius": 0, "height": 20}, "radius"),
    ("cone", {"bottom_radius": 20, "top_radius": 10, "height": 0}, "height"),
    ("cone", {"bottom_radius": -20, "top_radius": 10, "height": 20}, "radius"),
    ("tube", {"outer_radius": 20, "inner_radius": -5, "height": 6}, "inner"),
    ("tube", {"outer_radius": 20, "inner_radius": 10, "height": 0}, "height"),
    ("polygon_plate", {"sides": 2, "circumradius": 20, "thickness": 8},
     "sides"),
    ("polygon_plate", {"sides": 6, "circumradius": 0, "thickness": 8},
     "circumradius"),
    ("polygon_plate", {"sides": 6, "circumradius": 20, "thickness": 0},
     "thickness"),
    ("hex_plate", {"across_flats": 0, "thickness": 8}, "across_flats"),
    ("hex_plate", {"across_flats": 30, "thickness": 0}, "thickness"),
]

# OCCT's own vocabulary plus the shape of a pybind11 signature dump
JARGON = ("TopoDS", "NCollection", "Standard_", "BRep", "StdFail", "Geom_",
          "gp_", "TColStd", "BOPAlgo", "OCP.", "incompatible constructor",
          "TypeError", "object cannot be interpreted", "not supported between")


def _row_text(op, params, inputs=None):
    """What the feature tree would actually print for this feature."""
    doc = Document(name="guard")
    if inputs:
        doc.add("d", "disc", {"radius": 50, "thickness": 10})
    doc.add("p", op, dict(params), inputs=inputs)
    doc.rebuild()
    f = doc.get("p")
    return f.status, " ".join(f.problems or [])


@pytest.mark.parametrize("op,params,word", DEGENERATE)
def test_degenerate_dimension_is_refused_in_words(op, params, word):
    status, text = _row_text(op, params)
    assert status == "failed", f"{op} {params} was accepted"
    assert word in text.lower(), \
        f"{op} {params} does not name the bad parameter: {text!r}"
    for j in JARGON:
        assert j not in text, f"{op} {params} leaks kernel text: {text!r}"


@pytest.mark.parametrize("op,params,word", DEGENERATE)
def test_degenerate_dimension_never_builds_a_body(op, params, word):
    """A refusal, not a zero-volume or half-open solid (banned failure #2)."""
    doc = Document(name="guard")
    doc.add("p", op, dict(params))
    doc.rebuild()
    assert doc._parts.get("p") is None


def test_revolve_profile_refuses_a_negative_radius():
    """Its docstring has always promised radii >= 0 and never checked."""
    status, text = _row_text("revolve_profile",
                             {"points": [[-10, 0], [10, 0], [10, 5]]})
    assert status == "failed"
    assert "radius" in text.lower() and "-10" in text
    for j in JARGON:
        assert j not in text


def test_a_number_typed_with_its_unit_is_refused_before_the_kernel():
    """"8mm" is what a CAD user types. It used to reach BRepPrimAPI_MakeBox
    and print twelve lines of C++ overloads into the feature row."""
    doc = Document(name="guard")
    doc.add("p", "plate", {"width": 40, "depth": 30, "thickness": 8})
    with pytest.raises(ValueError) as e:
        doc.edit("p", "width", "8mm")
    msg = str(e.value)
    assert "width" in msg and "8mm" in msg
    assert "number" in msg.lower()
    for j in JARGON:
        assert j not in msg


def test_a_numeric_string_from_an_older_file_still_builds():
    """`from_data` deliberately bypasses the guard so any file opens. The
    rebuild must cope rather than dump a constructor signature."""
    doc = Document.from_data({
        "name": "stringy",
        "features": [{"id": "p", "op": "plate",
                      "params": {"width": "40", "depth": 30, "thickness": 8},
                      "inputs": []}]})
    doc.rebuild()
    f = doc.get("p")
    assert f.status == "failed"
    text = " ".join(f.problems or [])
    assert "width" in text.lower()
    for j in JARGON:
        assert j not in text, f"leaks kernel text: {text!r}"


def test_the_type_guard_leaves_the_shape_parameters_alone():
    """`edges`, `plane`, `open_face`, `axis` are words, not numbers."""
    doc = Document(name="guard")
    doc.add("d", "disc", {"radius": 20, "thickness": 10})
    doc.add("f", "fillet", {"radius": 2, "edges": "all"}, inputs=["d"])
    doc.edit("f", "edges", "top")            # must not raise
    doc.add("s", "shell", {"thickness": 2, "open_face": "top"}, inputs=["d"])
    doc.edit("s", "open_face", "bottom")     # must not raise
    assert doc.get("f").params["edges"] == "top"


def test_a_word_in_the_radius_of_a_finishing_op_is_refused_plainly():
    doc = Document(name="guard")
    doc.add("d", "disc", {"radius": 20, "thickness": 10})
    doc.add("f", "fillet", {"radius": 2, "edges": "all"}, inputs=["d"])
    with pytest.raises(ValueError) as e:
        doc.edit("f", "radius", "3mm")
    assert "radius" in str(e.value) and "number" in str(e.value).lower()


# ------------------------------------------------------- drills that miss ---

def test_a_zero_radius_hole_is_refused_not_reported_as_drilled():
    """Measured: volume came back 78539.82 -- the UNDRILLED disc -- with the
    row green. The placement popup posts 0 for a cleared field, so this is
    one keystroke away."""
    status, text = _row_text("with_center_hole", {"radius": 0}, inputs=["d"])
    assert status == "failed"
    assert "radius" in text.lower()


def test_a_bolt_circle_that_misses_the_body_is_refused():
    """PCD 200 on a 100 mm disc drilled nothing and reported ok."""
    status, text = _row_text("with_bolt_circle",
                             {"count": 6, "bolt_radius": 4,
                              "pitch_circle_dia": 200}, inputs=["d"])
    assert status == "failed"
    assert "outside" in text.lower() or "miss" in text.lower()


def test_a_bolt_circle_of_zero_diameter_is_refused():
    """It silently drilled ONE hole at the centre instead of six."""
    status, text = _row_text("with_bolt_circle",
                             {"count": 6, "bolt_radius": 4,
                              "pitch_circle_dia": 0}, inputs=["d"])
    assert status == "failed"
    assert "pitch" in text.lower() or "circle" in text.lower()


# ------------------------------------------------- not checked != failed ---

def _spec_doc():
    doc = Document(name="specced")
    doc.spec = {"n_solids": 1}
    doc.add("d", "disc", {"radius": 20, "thickness": 10})
    doc.add("f", "fillet", {"radius": 2, "edges": "top"}, inputs=["d"])
    return doc


def test_a_parked_rollback_bar_reports_not_checked_not_failed():
    """The tree paints any non-empty spec_problems red. While the bar is
    parked the spec cannot be checked at all, so 42 of the 50 saved designs
    said "spec FAIL" the moment an editor opened."""
    doc = _spec_doc()
    doc.rollback = "d"
    doc.rebuild()
    assert doc.spec_checked is False
    assert doc.spec_problems, "the reason must still be shown"
    assert "not checked" in doc.spec_problems[0]


def test_a_released_rollback_bar_checks_the_spec_again():
    doc = _spec_doc()
    doc.rollback = "d"
    doc.rebuild()
    doc.rollback = None
    doc.rebuild()
    assert doc.spec_checked is True
    assert not doc.spec_problems


def test_the_doc_payload_carries_whether_the_spec_ran():
    """The browser must not work this out from the wording of a line (R1)."""
    from fastapi.testclient import TestClient

    import studio
    with TestClient(studio.app) as c:
        doc = c.get("/api/doc").json()
        assert "spec_checked" in doc


def test_a_bolt_circle_that_does_drill_still_works():
    doc = Document(name="guard")
    doc.add("d", "disc", {"radius": 50, "thickness": 10})
    doc.add("b", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 76},
            inputs=["d"])
    assert doc.rebuild(), [f.problems for f in doc.features]
    holes = 6 * 3.14159265 * 16 * 10
    assert doc.get("b").volume == pytest.approx(78539.82 - holes, rel=1e-3)
