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


def test_only_a_BARE_function_name_is_translated():
    """What keeps the translation off OUR bugs, measured rather than assumed
    (review of 15eff19, probes/s10_required_review_probe.py §4).

    Every constructor and method inside the kernel stack says its name with a
    DOT — `Box.__init__() missing 1 required positional argument: 'height'`,
    `Shape.cut() got an unexpected keyword argument ...` — and `^\\w+\\(\\)`
    does not match a dot, so those keep saying they are a bug of ours. Only a
    bare name is translated, and the op the document unpacks the params into
    is the one bare name in that call. A helper of ours renamed into that
    shape would start lying, which is what this test is here to catch."""
    for msg in ("Box.__init__() missing 1 required positional argument: 'height'",
                "Shape.cut() got an unexpected keyword argument 'tol'",
                "<lambda>() missing 1 required positional argument: 'x'",
                "round() missing required argument 'number' (pos 1)"):
        assert blocks.plain_cause(TypeError(msg)) == f"TypeError: {msg}", msg
    # and the shapes that ARE translated, for the boundary's other side
    assert blocks.plain_cause(TypeError(
        "extrude_sketch() missing 1 required keyword-only argument: 'amount'")
    ) == "amount is required — set a value for it"


def test_a_feature_that_has_its_required_parameter_still_builds():
    d = _sketch_doc()
    d.add("e1", "extrude", {"amount": 4}, ["s1"])
    assert d.rebuild() is True
    assert d.get("e1").volume == pytest.approx(314.16, abs=0.01)


# ---------------------------------------------------------------------------
# Round TWO of the same review: the OTHER way a parameter reaches the row as
# raw Python. A REQUIRED parameter left OUT is now a sentence (above); one
# that is present but null or "" was not. MEASURED 2026-09-17 over every
# numeric parameter of every op (probes/s10_numeric_null_door.py): 14 raw
# Python messages across 7 ops, every one of them a modifier —
#   extrude / extrude_face  amount  -> TypeError: float() argument must be a
#                                      string or a real number, not 'NoneType'
#                                   -> could not convert string to float: ''
#   revolve / revolve_face  angle   -> the same two
#   scale                   factor  -> TypeError: '<=' not supported between
#                                      instances of 'NoneType' and 'int'
#   fillet / chamfer     radius,    -> TypeError: '>' not supported between
#                        length        instances of 'str' and 'int'
#   with_bolt_circle        count   -> TypeError: '<' not supported between
#                                      instances of 'NoneType' and 'int'
# The authoring doors refuse all three forms already (Document.check_params),
# so this is reachable only through a hand-edited or foreign file — the same
# door `Document.add(strict=False)` opens on purpose for the unknown-keyword
# case above. The rebuild now says the SAME sentence the authoring door says,
# out of the same function, so the two cannot drift.
# ---------------------------------------------------------------------------

NULL_LEAKS = [
    ("extrude", {"amount": 4}, "amount", "sketch"),
    ("revolve", {"axis": "Z", "angle": 180}, "angle", "sketch"),
    ("scale", {"factor": 2}, "factor", "solid"),
    ("fillet", {"radius": 1, "edges": "all"}, "radius", "solid"),
    ("chamfer", {"length": 1, "edges": "all"}, "length", "solid"),
    ("with_bolt_circle", {"count": 4, "bolt_radius": 1,
                          "pitch_circle_dia": 14}, "count", "solid"),
    ("extrude_face", {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                      "amount": 3}, "amount", "solid"),
    ("revolve_face", {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                      "axis": [[-12, -12], [12, -12]], "angle": 90},
     "angle", "solid"),
]


def _feature_on(kind: str, op: str, params: dict):
    d = Document(name="n")
    if kind == "sketch":
        # off the Z axis, so `revolve` has a profile it can sweep
        d.add("s1", "sketch",
              {"entities": [{"kind": "circle", "x": 12, "y": 0, "r": 4,
                             "mode": "add"}], "plane": "XZ", "offset": 0.0},
              [])
        src = "s1"
    else:
        d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
        src = "b1"
    d.add("p1", op, params, [src])
    d.rebuild()
    return d.get("p1")


@pytest.mark.parametrize("op,base,key,kind", NULL_LEAKS)
@pytest.mark.parametrize("bad", [None, "", "8mm"])
def test_a_numeric_parameter_that_is_not_a_number_is_a_sentence(
        op, base, key, kind, bad):
    f = _feature_on(kind, op, {**base, key: bad})
    assert f.status == "failed"
    msg = " ".join(f.problems)
    assert msg == (f"'p1' ({op}): {key} must be a number (got {bad!r}) — "
                   f"type just the number, without units")
    assert not any(w in msg for w in PYTHON_WORDS), msg
    assert not any(w in msg for w in KERNEL_WORDS), msg


@pytest.mark.parametrize("op,base,key,kind", NULL_LEAKS)
def test_the_same_feature_with_a_real_number_still_builds(op, base, key, kind):
    """The half that matters more: the check must not fire on sound work."""
    f = _feature_on(kind, op, base)
    assert f.status == "ok", f.problems


def test_the_rebuild_says_exactly_what_the_authoring_door_says():
    """ONE rule, one sentence: typing the bad value into the panel and loading
    a file that already holds it must read the same."""
    with pytest.raises(ValueError) as e:
        Document.check_params("extrude", {"amount": None}, "p1")
    assert str(e.value) == " ".join(
        _feature_on("sketch", "extrude", {"amount": None}).problems)


def test_move_still_reads_a_missing_offset_as_zero():
    """`document._move_offsets` takes None as 0 ON PURPOSE (its comment says
    so), so `move` is deliberately outside the check — measured: it still
    builds, unmoved."""
    d = Document(name="m")
    d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    d.add("m1", "move", {"x": None, "y": 2, "z": None}, ["b1"])
    assert d.rebuild() is True, d.get("m1").problems
    assert d.get("m1").volume == pytest.approx(2000.0, abs=0.01)


def test_a_creator_keeps_its_own_wording():
    """The leak was in the modifiers; every creator already named the
    parameter AND its unit (measured), and that sentence is not replaced."""
    d = Document(name="c")
    d.add("c1", "plate", {"width": None, "depth": 20, "thickness": 5}, [])
    d.rebuild()
    assert d.get("c1").problems == [
        "plate: width must be a number in mm (got None) — type just the "
        "number, no units"]


def test_the_kind_of_the_input_is_still_the_more_basic_fact():
    """A sketch fed to fillet AND a null radius: the user hears about the
    sketch, because fixing the number would not help."""
    d = Document(name="k")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add("p1", "fillet", {"radius": None}, ["s1"])
    d.rebuild()
    assert "is a sketch" in " ".join(d.get("p1").problems)
