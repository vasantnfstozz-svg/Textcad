"""Section 7 review (Extrude as a whole module, with loft and sweep) — the
findings, locked in.

Every test here was RED before its fix and reproduces a MEASURED failure, not a
suspicion: the numbers in the comments came off the kernel on 2026-09-11.
"""
import pytest

from document import Document

TWO_CIRCLES = [{"kind": "circle", "x": -15, "y": 0, "r": 5, "mode": "add"},
               {"kind": "circle", "x": 15, "y": 0, "r": 5, "mode": "add"}]
ONE_CIRCLE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
RECT = [{"kind": "rectangle", "x": 0, "y": 0, "w": 20, "h": 30, "mode": "add"}]

KERNEL_WORDS = ("Standard_", "StdFail", "TopoDS", "BRep_API", "NCollection",
                "not manifold", "invalid")


def _msg(d: Document, fid: str) -> str:
    return " ".join(d.get(fid).problems or [])


# --- F1: a loft blends ONE profile per sketch ---------------------------------

def test_a_loft_of_two_profile_sketches_is_refused_not_snaked():
    """MEASURED before the fix: two sketches of two circles each lofted into a
    SINGLE snaking solid of 1570.8 mm3 (the two honest tubes are 3141.6),
    spanning z -3.92..23.92 — outside BOTH sketch planes — with status ok and
    no warning. build123d chains every section's faces into one loft."""
    d = Document(name="l")
    d.add("a", "sketch", {"plane": "XY", "offset": 0, "entities": TWO_CIRCLES}, [])
    d.add("b", "sketch", {"plane": "XY", "offset": 20, "entities": TWO_CIRCLES}, [])
    d.add("l1", "loft", {}, ["a", "b"])
    d.rebuild()
    f = d.get("l1")
    assert f.status == "failed", f"a two-profile loft built silently: {f.volume} mm3"
    msg = _msg(d, "l1")
    assert "profile" in msg.lower() and "a" in msg
    assert not any(w in msg for w in KERNEL_WORDS), msg


def test_a_loft_of_single_profile_sketches_still_builds():
    """The six lofts in the user's two panel designs are all of this shape."""
    d = Document(name="l")
    d.add("a", "sketch", {"plane": "XY", "offset": 0, "entities": ONE_CIRCLE}, [])
    d.add("b", "sketch", {"plane": "XY", "offset": 20, "entities": ONE_CIRCLE}, [])
    d.add("l1", "loft", {}, ["a", "b"])
    d.rebuild()
    assert d.get("l1").status == "ok", d.get("l1").problems
    assert d.get("l1").volume > 0


# --- F2: a profile op fed a solid body ---------------------------------------

@pytest.mark.parametrize("op,params", [
    ("sweep", {"path_points": [[0, 0, 0], [20, 15, 30]]}),
    ("extrude", {"amount": 5}),
    ("revolve", {"axis": "Z", "angle": 90}),
])
def test_a_profile_op_fed_a_solid_body_is_refused_plainly(op, params):
    """MEASURED before the fix: `sweep` on a 24 000 mm3 plate swept EVERY FACE
    of it separately and returned a 178 000 mm3 six-lump blob — status ok, no
    problems, no warnings — while the plate itself was consumed. extrude and
    revolve failed, but with kernel wording that names nothing to change."""
    d = Document(name="s")
    d.add("plate1", "plate", {"width": 60, "depth": 40, "thickness": 10}, [])
    d.add("op1", op, params, ["plate1"])
    d.rebuild()
    f = d.get("op1")
    assert f.status == "failed", f"{op} on a body built silently: {f.volume} mm3"
    msg = _msg(d, "op1")
    assert "plate1" in msg and "sketch" in msg.lower(), msg
    assert not any(w in msg for w in KERNEL_WORDS), msg


def test_a_sketch_of_disjoint_islands_still_extrudes():
    """The refusal tests SOLIDS, never `is_sketch`: disjoint entities compose
    into a Compound that is not a Sketch instance, and those must still build."""
    d = Document(name="i")
    d.add("s", "sketch", {"plane": "XY", "entities": TWO_CIRCLES}, [])
    d.add("e", "extrude", {"amount": 4}, ["s"])
    d.rebuild()
    assert d.get("e").status == "ok", d.get("e").problems
    assert d.get("e").pieces == 2


# --- F3: a join that adds nothing ---------------------------------------------

def test_a_join_that_adds_nothing_is_named():
    """MEASURED before the fix: a picked top face pulled 4 mm INTO the body and
    left at the default Join — plate 24 000, prism 9 600, join 24 000 mm3.
    Three green rows, an unchanged body and not one word."""
    d = Document(name="j")
    d.add("plate1", "plate", {"width": 60, "depth": 40, "thickness": 10}, [])
    d.add("ex1", "extrude_face",
          {"face_center": [0, 0, 5], "face_normal": [0, 0, 1], "amount": -4}, ["plate1"])
    d.add("ex1_join", "fuse", {}, ["plate1", "ex1"])
    d.rebuild()
    assert d.get("ex1_join").status == "ok"
    note = " ".join(d.warnings)
    assert "ex1_join" in note and "ex1" in note, d.warnings
    assert "no material" in note or "nothing" in note, d.warnings


def test_a_join_that_adds_material_is_not_named():
    d = Document(name="j")
    d.add("plate1", "plate", {"width": 60, "depth": 40, "thickness": 10}, [])
    d.add("ex1", "extrude_face",
          {"face_center": [0, 0, 5], "face_normal": [0, 0, 1], "amount": 4}, ["plate1"])
    d.add("ex1_join", "fuse", {}, ["plate1", "ex1"])
    d.rebuild()
    assert d.get("ex1_join").volume > 24000
    assert not [w for w in d.warnings if "ex1_join" in w], d.warnings


# --- F4: Through all cannot taper --------------------------------------------

def test_a_through_cut_says_the_taper_was_dropped():
    """MEASURED before the fix: through + a -10 deg taper built 1 200 000 mm3 =
    20 x 30 x 2000 — dead straight — while the panel's taper box and dashed ring
    still read -10 deg. Nothing said the angle had been thrown away."""
    d = Document(name="t")
    d.add("s", "sketch", {"plane": "XY", "entities": RECT}, [])
    d.add("e", "extrude", {"amount": 5, "through": True, "taper": -10}, ["s"])
    d.rebuild()
    f = d.get("e")
    assert f.status == "ok", f.problems
    note = " ".join(f.notes or [])
    assert "taper" in note.lower() and "through" in note.lower(), f.notes
    assert any("taper" in w.lower() for w in d.warnings), d.warnings


def test_a_through_cut_without_a_taper_says_nothing():
    d = Document(name="t")
    d.add("s", "sketch", {"plane": "XY", "entities": RECT}, [])
    d.add("e", "extrude", {"amount": 5, "through": True}, ["s"])
    d.rebuild()
    assert d.get("e").notes == []


# --- F5: the second side of a two-sided extrude ------------------------------

def test_the_second_side_is_built_whatever_its_sign():
    """MEASURED before the fix: amount 8 + amount2 -5 built 4800 mm3 — the first
    side alone. The typed second side was dropped without a word."""
    d = Document(name="2")
    d.add("s", "sketch", {"plane": "XY", "entities": RECT}, [])
    d.add("pos", "extrude", {"amount": 8, "amount2": 5}, ["s"])
    d.add("neg", "extrude", {"amount": 8, "amount2": -5}, ["s"])
    d.rebuild()
    assert d.get("pos").volume == pytest.approx(600 * 13)
    assert d.get("neg").volume == pytest.approx(d.get("pos").volume)
    bb = d._parts["neg"].bounding_box()
    assert bb.min.Z == pytest.approx(-5, abs=1e-6)
    assert bb.max.Z == pytest.approx(8, abs=1e-6)
