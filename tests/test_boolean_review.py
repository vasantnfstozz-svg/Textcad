"""Section 4 review (booleans and transforms) — the findings, locked in.

Every test here was RED before its fix and reproduces a measured failure, not
a suspicion (probes/boolean_review_probe.py).
"""
import pytest

import document
import toolplan
from document import Document

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
RECT60 = [{"kind": "rectangle", "x": 0, "y": 0, "w": 60, "h": 60, "mode": "add"}]

# raw kernel vocabulary: none of it may ever reach a feature's problems
KERNEL_WORDS = ("Standard_", "StdFail", "TopoDS", "BRep_API", "NCollection",
                "Null TopoDS_Shape")


def _tail(d: Document):
    return d.features[-1]


# --- F1: a combiner given a sketch --------------------------------------------

def test_a_boolean_given_a_sketch_is_refused_by_name():
    """intersect(plate, sketch) used to be "ok": it returned a 2D Sketch, ate
    the plate, and left the design with NO bodies while every row stayed
    green (measured: leaves [], result_shape() None, warnings [])."""
    d = Document(name="ix")
    d.add("p1", "plate", {"width": 20, "depth": 20, "thickness": 10})
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0})
    d.add("ix", "intersect", {}, ["p1", "s1"])
    assert d.rebuild() is False
    f = d.get("ix")
    assert f.status == "failed"
    msg = " ".join(f.problems)
    assert "s1" in msg and "sketch" in msg.lower()
    assert not any(w in msg for w in KERNEL_WORDS), msg


@pytest.mark.parametrize("op", ["fuse", "cut", "intersect"])
def test_every_boolean_refuses_a_sketch_input(op):
    d = Document(name="b")
    d.add("p1", "plate", {"width": 20, "depth": 20, "thickness": 10})
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0})
    d.add("op1", op, {}, ["p1", "s1"])
    assert d.rebuild() is False
    assert "s1" in " ".join(d.get("op1").problems)


def test_a_boolean_of_two_solids_still_builds():
    d = Document(name="ok")
    d.add("a", "plate", {"width": 20, "depth": 20, "thickness": 10})
    d.add("b", "disc", {"radius": 4, "thickness": 30})
    d.add("cut1", "cut", {}, ["a", "b"])
    assert d.rebuild() is True
    assert d.get("cut1").volume < d.get("a").volume


# --- F2: no bodies must never pass a spec -------------------------------------

def test_a_design_with_no_bodies_fails_its_spec():
    """The spec block was skipped when there were no leaves, so a design with
    nothing in it reported that it met a spec demanding one 20x20x10 solid."""
    d = Document(name="z", spec={"n_solids": 1, "size": [20, 20, 10], "tol": 0.5})
    d.add("p1", "plate", {"width": 20, "depth": 20, "thickness": 10})
    assert d.rebuild() is True and d.spec_problems == []
    d.get("p1").suppressed = True
    d._mark_stale()
    assert d.rebuild() is False
    assert d.spec_problems and "no bodies" in " ".join(d.spec_problems).lower()


def test_a_sketch_only_design_with_no_spec_is_not_failed():
    """No spec, no verdict — drawing a sketch before extruding it is normal."""
    d = Document(name="s")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0})
    assert d.rebuild() is True
    assert d.spec_problems == []


# --- F3: the combine target is the body the sketch lives on -------------------

def _panel_with_new_body_boss():
    d = Document(name="dt")
    d.add("panel", "plate", {"width": 80, "depth": 40, "thickness": 10})
    d.rebuild()
    top = max(d._parts["panel"].faces(), key=lambda f: f.center().Z)
    fc = [top.center().X, top.center().Y, top.center().Z]
    d.add("boss", "extrude_face", {"face_center": fc, "amount": 5.0}, ["panel"])
    d.add("sk2", "sketch_on_face",
          {"face_center": fc, "offset": 0.0, "entities": CIRC}, ["panel"])
    d._mark_stale()
    assert d.rebuild() is True
    return d


def test_a_face_sketch_targets_its_own_body_not_a_new_body_boss():
    """Fusion parity rule 6: a face sketch targets its parent body walked to
    its CURRENT state. extrude_face only POINTS AT a face (it is a
    FACE_REFERENCE op — consumed_ids already knows it does not consume the
    body), so a New-body boss is not what the panel became. It was returned
    anyway, so the next Cut on the panel cut the boss prism instead."""
    d = _panel_with_new_body_boss()
    assert toolplan._latest_descendant(d, "panel") == "panel"
    assert toolplan._default_target(d, "sk2") == "panel"
    assert toolplan.plan_extrude(d, {"sketch_id": "sk2"})["target_body"] == "panel"


def test_a_real_consumer_is_still_followed():
    """The walk must still follow ops that DO consume the body — otherwise a
    face sketch would target a body two cuts out of date."""
    d = _panel_with_new_body_boss()
    d.add("joined", "fuse", {}, ["panel", "boss"])
    d._mark_stale()
    assert d.rebuild() is True
    assert toolplan._latest_descendant(d, "panel") == "joined"
    assert toolplan._default_target(d, "sk2") == "joined"


# --- F4: loft speaks plainly ---------------------------------------------------

def _loft_doc(extra):
    d = Document(name="lf")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0})
    for fid, op, params, ins in extra:
        d.add(fid, op, params, ins)
    return d


LOFT_CASES = [
    ("two solids", [("p1", "plate", {"width": 20, "depth": 20, "thickness": 5}, []),
                    ("p2", "disc", {"radius": 5, "thickness": 5}, []),
                    ("lf", "loft", {}, ["p1", "p2"])]),
    ("sketch and solid", [("p1", "plate", {"width": 20, "depth": 20, "thickness": 5}, []),
                          ("lf", "loft", {}, ["s1", "p1"])]),
    ("the same sketch twice", [("lf", "loft", {}, ["s1", "s1"])]),
    ("coplanar profiles", [("s2", "sketch", {"entities": RECT60, "plane": "XY",
                                             "offset": 0.0}, []),
                           ("lf", "loft", {}, ["s1", "s2"])]),
]


@pytest.mark.parametrize("label,extra", LOFT_CASES, ids=[c[0] for c in LOFT_CASES])
def test_loft_never_hands_the_user_kernel_text(label, extra):
    """Measured before the fix: Standard_NoSuchObject('NCollection_DataMap::
    Find'), StdFail_NotDone('BRep_API: command not done') and a zero-volume
    "solid" all reached the tree verbatim — rule 5's first banned failure."""
    d = _loft_doc(extra)
    assert d.rebuild() is False
    msg = " ".join(d.get("lf").problems)
    assert msg, "the loft must say something"
    assert not any(w in msg for w in KERNEL_WORDS), msg
    assert "loft" in msg.lower()


def test_a_real_loft_still_builds():
    d = Document(name="good")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0})
    d.add("s2", "sketch", {"entities": RECT60, "plane": "XY", "offset": 20.0})
    d.add("lf", "loft", {}, ["s1", "s2"])
    assert d.rebuild() is True
    assert d.get("lf").volume > 0


# --- F5: a cut that removes nothing --------------------------------------------

def test_a_cut_that_removes_nothing_says_so():
    """The tool prism is CONSUMED by the cut, so it vanishes from the viewport
    while the body is untouched and every row is green — measured: cut volume
    4000.0 == its input's 4000.0, warnings []."""
    d = Document(name="miss")
    d.add("body", "plate", {"width": 20, "depth": 20, "thickness": 10})
    d.add("far", "disc", {"radius": 3, "thickness": 5})
    d.add("far_moved", "move", {"x": 100, "y": 0, "z": 0}, ["far"])
    d.add("pocket", "cut", {}, ["body", "far_moved"])
    assert d.rebuild() is True                 # not an error, but not silent
    assert d.get("pocket").volume == d.get("body").volume
    joined = " ".join(d.warnings)
    assert "pocket" in joined and "removed no material" in joined


def test_a_cut_that_does_remove_material_is_quiet():
    d = Document(name="hit")
    d.add("body", "plate", {"width": 20, "depth": 20, "thickness": 10})
    d.add("tool", "disc", {"radius": 3, "thickness": 30})
    d.add("pocket", "cut", {}, ["body", "tool"])
    assert d.rebuild() is True
    assert "removed no material" not in " ".join(d.warnings)


# --- F7: a pattern of copies is not a broken part ------------------------------

def test_a_pattern_of_copies_is_not_reported_as_broken_pieces():
    """16 designs in the library use the copy form; each was being told the
    part had fallen into N pieces because "something in it no longer touches
    the rest" — the exact false signal the extrude/revolve exclusion exists
    to prevent."""
    d = Document(name="pat")
    d.add("peg", "disc", {"radius": 3, "thickness": 5})
    d.add("row", "linear_pattern", {"count": 4, "dx": 20}, ["peg"])
    assert d.rebuild() is True
    assert d.get("row").pieces == 4            # the count is still reported
    assert not any("separate pieces" in w for w in d.warnings), d.warnings


def test_a_severing_cut_still_warns():
    """The control: the warning must still fire where it means something."""
    d = Document(name="sever")
    d.add("base", "plate", {"width": 40, "depth": 10, "thickness": 10})
    d.add("sk", "sketch", {"entities":
                           [{"kind": "rectangle", "x": 0, "y": 0,
                             "w": 4, "h": 40, "mode": "add"}],
                           "plane": "XY", "offset": 0.0})
    d.add("knife", "extrude", {"amount": 30.0, "both": True, "through": True}, ["sk"])
    d.add("halves", "cut", {}, ["base", "knife"])
    assert d.rebuild() is True
    assert d.get("halves").pieces == 2
    assert any("separate pieces" in w for w in d.warnings), d.warnings


# --- F8: the stranding heal leaves a SHARED tool alone -------------------------

def _strand_doc(shared: bool):
    d = Document(name="strand")
    d.add("base", "plate", {"width": 40, "depth": 40, "thickness": 20})
    d.add("bandsk", "sketch_on_face",
          {"face": "top", "offset": -6.0, "entities": RECT60}, ["base"])
    d.add("band", "extrude", {"amount": 2.0}, ["bandsk"])
    d.add("slice", "cut", {}, ["base", "band"])
    if shared:
        d.add("base2", "plate", {"width": 30, "depth": 30, "thickness": 20})
        d.add("slice2", "cut", {}, ["base2", "band"])
    return d


def test_the_heal_still_fixes_a_tool_of_its_own():
    d = _strand_doc(shared=False)
    assert d.rebuild() is True
    assert d.get("band").params.get("through") is True
    assert d.get("slice").pieces == 1
    assert any("all the way through" in w for w in d.warnings)


def test_the_heal_leaves_a_tool_that_another_cut_shares_alone():
    """Measured before the fix: `through` was ticked for 'slice' and 'slice2'
    silently lost 3600 mm3 more than its own parameters ask for (16200 ->
    12600). The proof the heal relies on was only ever computed for 'slice'.
    A design in the user's library (cam-cover-plaque) already shares a tool
    prism between two combiners this way."""
    d = _strand_doc(shared=True)
    assert d.rebuild() is True
    assert "through" not in d.get("band").params
    assert d.get("slice2").volume == pytest.approx(16200.0, rel=1e-6)
    assert not any("all the way through" in w for w in d.warnings)


# --- F9: a face pick never records a body it was not taken from ---------------

def test_pick_body_refuses_a_named_body_that_did_not_build():
    """It fell back to doc.result()'s GEOMETRY while keeping the requested
    ID, so a face was resolved on one body and recorded against another."""
    d = Document(name="pb")
    d.add("good", "plate", {"width": 20, "depth": 20, "thickness": 10})
    d.add("bad", "disc", {"radius": -5, "thickness": 5})
    d.rebuild()
    assert d.get("bad").status == "failed"
    with pytest.raises(ValueError, match="bad"):
        toolplan._pick_body(d, "bad", "extrude a face from")


def test_pick_body_still_falls_back_when_no_body_was_named():
    d = Document(name="pb2")
    d.add("good", "plate", {"width": 20, "depth": 20, "thickness": 10})
    d.rebuild()
    part, bid = toolplan._pick_body(d, None, "extrude a face from")
    assert part is not None and bid == "good"


# --- F6: the transforms state their real pivot --------------------------------

def test_the_transform_docstrings_state_the_measured_pivot():
    """Measured: rotate is about the WORLD ORIGIN (a plate at x[90,110] lands
    at y[90,110]) and scale is about the SHAPE CENTRE (x[90,110] -> x[80,120]),
    while scale's docstring claimed the origin. A false statement about a
    pivot is what the next builder — and the AI — reads."""
    import blocks
    import author
    assert "shape" in blocks.scale_uniform.__doc__.lower()
    assert "origin" in blocks.rotate.__doc__.lower()
    assert author.OP_NOTES.get("scale"), "Scale needs a note like rotate's"
    note = author.OP_NOTES["scale"].lower()
    assert "centre" in note or "center" in note


def test_scale_is_measurably_about_the_shape_centre():
    import build123d as b3d
    import blocks
    moved = b3d.Pos(100, 0, 0) * blocks.plate(20, 20, 10)
    scaled = blocks.scale_uniform(moved, 2.0)
    bb = scaled.bounding_box()
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(100.0, abs=1e-6)


def test_rotate_is_measurably_about_the_world_origin():
    import build123d as b3d
    import blocks
    moved = b3d.Pos(100, 0, 0) * blocks.plate(20, 20, 10)
    turned = blocks.rotate(moved, "Z", 90.0)
    bb = turned.bounding_box()
    assert bb.min.Y == pytest.approx(90.0, abs=1e-6)


def test_n_solids_of_a_missing_part_is_zero():
    assert document.n_solids(None) == 0


# --- the follow-up read of c9b2e92 (the fix pass reviewed) --------------------

def test_loft_translates_a_bare_build123d_valueerror(monkeypatch):
    """The first guard re-raised ValueError as "already a sentence", but
    build123d raises its OWN bare ones with kernel wording — measured,
    `loft_sketches([sketch, Part()])` gives ValueError('More than one wire is
    required'). Nothing but our sentence may leave `_loft`."""
    def boom(_parts):
        raise ValueError("More than one wire is required")
    monkeypatch.setattr(document.sk, "loft_sketches", boom)
    with pytest.raises(ValueError) as e:
        document._loft(["a", "b"])
    assert "wire" not in str(e.value)
    assert "loft" in str(e.value).lower()


def test_loft_survives_a_volume_that_raises(monkeypatch):
    """`getattr(out, "volume", 0)` does NOT swallow an exception from the
    property — the default only covers AttributeError (measured). So a
    degenerate result escaped as raw kernel text."""
    class Degenerate:
        @property
        def volume(self):
            raise RuntimeError("StdFail_NotDone: BRep_API: command not done")

    monkeypatch.setattr(document.sk, "loft_sketches", lambda _p: Degenerate())
    with pytest.raises(ValueError) as e:
        document._loft(["a", "b"])
    msg = str(e.value)
    assert not any(w in msg for w in KERNEL_WORDS), msg
    assert "loft" in msg.lower()


def test_a_body_behind_the_rollback_bar_is_not_called_broken():
    """The new refusal said "fix that feature first" for a body that builds at
    1206.37 mm3 the moment the bar is released. The editors park the bar, so
    this sentence is one an ordinary edit could produce."""
    d = Document(name="rb")
    d.add("base", "plate", {"width": 40, "depth": 40, "thickness": 10})
    d.add("boss", "disc", {"radius": 8, "thickness": 6})
    d.rebuild()
    assert d.get("boss").volume == pytest.approx(1206.37, abs=0.01)
    d.rollback = "base"
    d._mark_stale()
    d.rebuild()
    with pytest.raises(ValueError) as e:
        toolplan._pick_body(d, "boss", "drill")
    msg = str(e.value)
    assert "rollback bar" in msg
    assert "fix that feature" not in msg


def test_a_body_that_really_failed_is_still_called_broken():
    d = Document(name="rb2")
    d.add("good", "plate", {"width": 20, "depth": 20, "thickness": 10})
    d.add("bad", "disc", {"radius": -5, "thickness": 5})
    d.rebuild()
    with pytest.raises(ValueError, match="fix that feature"):
        toolplan._pick_body(d, "bad", "drill")
