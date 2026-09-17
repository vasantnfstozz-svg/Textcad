"""LAUNCH-PLAN §10, 2026-09-17 — the row about REQUIRED parameters, locked in.

`op_params` could not say which parameters are required: it returned None both
for a parameter with no default and for one whose default IS None, so the
catalogue the AI reads could not say it either, and an omitted required
parameter reached the feature row as raw Python.

Every assertion below was measured first (probes/s10_required_params_probe.py,
probes/s10_required_census.py) and every test here was RED before the fix.
"""
import json
import re

import pytest

import author
import blocks
import document
from document import REQUIRED, Document, op_params, required_params

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]

# raw kernel or raw Python: neither may ever reach a feature row
KERNEL_WORDS = ("Standard_", "StdFail", "TopoDS", "BRep_API", "NCollection")
PYTHON_WORDS = ("TypeError", "positional argument", "keyword argument",
                "Traceback", "()")


def _sketch_doc() -> Document:
    d = Document(name="r")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    return d


# --- the sentinel -------------------------------------------------------------

def test_op_params_tells_a_required_parameter_from_one_that_defaults_to_none():
    """MEASURED before the fix: both came back as None, so `extrude`'s amount
    (no default, really required) and `hole`'s face_center (default None,
    optional and filled in from a mouse click) were indistinguishable."""
    ext = dict(op_params("extrude"))
    assert ext["amount"] is REQUIRED
    assert ext["both"] is False                      # an ordinary default survives

    hole = dict(op_params("hole"))
    for optional in ("face_center", "face_normal", "face", "face_area"):
        assert hole[optional] is None, optional
        assert hole[optional] is not REQUIRED


def test_required_params_names_them():
    assert required_params("extrude") == ("amount",)
    assert required_params("plate") == ("width", "depth", "thickness")
    assert required_params("hole") == ()
    assert required_params("move") == ()
    assert required_params("emboss") == ()           # an op this build lacks


def test_every_op_the_signature_calls_required_is_marked():
    """The census: 22 of the 29 ops have at least one, and the sentinel is
    read from the signature, so it can never disagree with the function."""
    marked = {op for op in document.KNOWN_OPS if required_params(op)}
    assert "extrude" in marked and "plate" in marked and "fillet" in marked
    assert "hole" not in marked and "shell" not in marked and "move" not in marked
    assert len(marked) == 22, sorted(marked)


# --- what the AI reads --------------------------------------------------------

def test_the_catalogue_text_marks_required_and_shows_every_other_default():
    """Before: `extrude(amount, both=False, ...)` and `hole(face_center,
    face_normal, face, face_area, at=(0.0, 0.0), ...)` — the same rendering
    for the one parameter that must be given and the four the prompt forbids
    the model to compute."""
    txt = author._catalog_text()
    assert "REQUIRED" in txt.splitlines()[0]          # the legend, once
    assert "extrude(amount*, both=False," in txt
    assert "hole(face_center=null, face_normal=null," in txt
    # nothing may be left bare any more: every parameter is either starred or
    # shows its value
    for line in txt.splitlines()[1:]:
        inside = line[line.index("(") + 1:line.rindex(")")]
        for part in re.split(r",(?![^()\[\]]*[)\]])", inside):
            part = part.strip()
            if part:
                assert part.endswith("*") or "=" in part, line


def test_the_catalogue_json_carries_required_and_is_still_json():
    """/api/ops and the MCP doorbell both serve this list: the sentinel must
    never leave author.op_catalog()."""
    cat = {c["op"]: c for c in author.op_catalog()}
    amount = next(p for p in cat["extrude"]["params"] if p["name"] == "amount")
    assert amount["required"] is True
    # the Add Feature dialog reads `p.default ?? ''` — the key stays, and null
    assert amount["default"] is None
    centre = next(p for p in cat["hole"]["params"] if p["name"] == "face_center")
    assert "required" not in centre and centre["default"] is None
    json.dumps(cat)                                   # would raise on the sentinel


# --- what a user sees ---------------------------------------------------------

def test_a_missing_required_parameter_is_a_sentence_not_python():
    """MEASURED before the fix, in the feature row:
    "TypeError: extrude_sketch() missing 1 required positional argument:
    'amount'" — Python in the row blocks.plain_cause exists to keep it out of."""
    d = _sketch_doc()
    d.add("e1", "extrude", {}, ["s1"])
    d.rebuild()
    f = d.get("e1")
    assert f.status == "failed"
    assert f.problems == ["amount is required — set a value for it"]
    msg = " ".join(f.problems)
    assert not any(w in msg for w in PYTHON_WORDS + KERNEL_WORDS), msg


@pytest.mark.parametrize("op,names", [
    ("plate", "width, depth and thickness are required — set a value for each"),
    ("ball", "radius is required — set a value for it"),
    ("disc", "radius and thickness are required — set a value for each"),
])
def test_a_creator_with_no_parameters_at_all_names_every_one(op, names):
    d = Document(name="c")
    d.add("c1", op, {}, [])
    d.rebuild()
    assert d.get("c1").problems == [names]


def test_a_parameter_this_build_no_longer_has_is_named_too():
    """The other half of the same leak. A design written by another build must
    OPEN (Document.add strict=False) and say so at the next rebuild — it said
    so as "TypeError: polar_pattern() got an unexpected keyword argument
    'radius'" (measured 2026-09-17)."""
    d = Document(name="u")
    d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    d.add("p1", "polar_pattern", {"count": 4, "radius": 20}, ["b1"])
    d.rebuild()
    f = d.get("p1")
    assert f.status == "failed"
    assert f.problems == ["radius is not a parameter of this feature — remove it"]


def test_plain_cause_still_names_our_own_bugs_as_bugs():
    """The translation is for those two shapes ONLY: any other TypeError is a
    bug of ours and must keep saying what it is instead of being dressed up."""
    assert blocks.plain_cause(TypeError("'bool' object is not callable")) == (
        "TypeError: 'bool' object is not callable")
    assert blocks.plain_cause(ValueError("pick a face first")) == "pick a face first"


def test_a_feature_that_has_its_required_parameter_still_builds():
    d = _sketch_doc()
    d.add("e1", "extrude", {"amount": 4}, ["s1"])
    assert d.rebuild() is True
    assert d.get("e1").volume == pytest.approx(314.16, abs=0.01)
