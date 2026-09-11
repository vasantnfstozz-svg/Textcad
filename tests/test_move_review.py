"""Round-one review of the Move / Rotate commit (9e04ff6).

Every test here was RED before its fix and names the user action that reaches
it. The measurements behind them are in probes/move_review_probe.py.

The P0: a stored face pick is resolved by NEAREST CENTRE with the picked
normal as a mere nudge (25 mm^2 per unit of misalignment), so once a body is
translated further than roughly its own thickness the nearest face is the one
POINTING THE OTHER WAY. Dragging the Move arrow 8 mm on a 10 mm plate moved a
boss from the top face to the bottom face, where it was swallowed by the
material: 565 mm^3 of the user's part gone, every tree row green, nothing said.
"""
import build123d as b3d
import pytest

import blocks
import toolplan
from document import Document


# ---------------------------------------------------------------- F1: the P0 --

def plate_with_a_boss_on_the_moved_body(z=0.0):
    """the tool's own documented journey: Move a body, sketch on the face it
    now shows, extrude a boss, fuse - then re-open Move and drag"""
    d = Document(name="j")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 10}, [])
    d.add("move1", "move", {"x": 0, "y": 0, "z": z}, ["b"])
    d.rebuild()
    top = max(d._parts["move1"].faces(), key=lambda f: f.center().Z)
    c = top.center()
    n = top.normal_at(c)
    d.add("s", "sketch_on_face",
          {"face_center": [c.X, c.Y, c.Z], "face_normal": [n.X, n.Y, n.Z],
           "entities": [{"kind": "circle", "r": 6, "x": 0, "y": 0}]}, ["move1"])
    d.add("boss", "extrude", {"amount": 5}, ["s"])
    d.add("f", "fuse", {}, ["move1", "boss"])
    d.rebuild()
    return d


@pytest.mark.parametrize("dz", [8.0, 12.0, 25.0, -25.0])
def test_dragging_move_keeps_the_boss_on_the_face_it_was_drawn_on(dz):
    """the spec says downstream features ride along. Measured 2026-09-11:
    past ~7 mm on a 10 mm plate the boss jumped to the BOTTOM face and was
    buried in the material - the fused volume fell back to the bare plate's
    24000 mm3 with every row still `ok`."""
    d = plate_with_a_boss_on_the_moved_body()
    v0 = d.result().volume
    assert v0 == pytest.approx(24000 + 565.4867, abs=1e-3)
    d.edit_many("move1", {"x": 0, "y": 0, "z": dz})
    assert d.rebuild()
    assert all(f.status == "ok" for f in d.features)
    assert d.result().volume == pytest.approx(v0, abs=1e-3), \
        "the boss was swallowed by the body it was standing on"
    bb = d._parts["boss"].bounding_box()
    plate = d._parts["move1"].bounding_box()
    assert bb.min.Z == pytest.approx(plate.max.Z, abs=1e-6), \
        "the boss must still stand on the TOP face of the moved plate"


def test_a_parameter_change_still_lets_the_pick_follow_its_face():
    """the other half of the same rule: growing the plate moves the top face
    5 mm and the boss must FOLLOW it (this is what the nearest-centre rule was
    for, and the fix must not take it away)"""
    d = plate_with_a_boss_on_the_moved_body()
    d.edit_many("b", {"width": 60, "depth": 40, "thickness": 20})
    assert d.rebuild()
    assert d.result().volume == pytest.approx(48000 + 565.4867, abs=1e-3)
    assert d._parts["boss"].bounding_box().min.Z == pytest.approx(10.0, abs=1e-6)


def test_resolve_face_never_answers_with_a_face_pointing_the_other_way():
    """the rule, at the unit: a pick that carried a direction is never matched
    to a face facing away from it - the answer is a sentence, not a guess"""
    box = b3d.Box(20, 20, 4)
    top = blocks.resolve_face(box, [0, 0, 2], [0, 0, 1])
    assert top.center().Z == pytest.approx(2.0)
    # the same pick against the body 10 mm higher: the nearest face is the
    # bottom one, which faces DOWN - the top face is the only honest answer
    moved = b3d.Pos(0, 0, 10) * b3d.Box(20, 20, 4)
    f = blocks.resolve_face(moved, [0, 0, 2], [0, 0, 1])
    assert f.center().Z == pytest.approx(12.0), "it picked the down-facing face"
    assert f.normal_at(f.center()).Z > 0


def test_no_face_points_the_picked_way_at_all_is_a_sentence():
    """when the gate leaves nothing the answer is a sentence, never a guess.
    A CLOSED solid always has a face pointing any way you like, so this is the
    shape that reaches it: a single face (a profile) turned right over."""
    turned = b3d.Rot(180, 0, 0) * b3d.Rectangle(10, 10)
    with pytest.raises(ValueError) as e:
        blocks.resolve_face(turned, [0, 0, 0], [0, 0, 1])
    assert "does not point that way" in str(e.value)


def test_resolve_face_without_a_stored_normal_is_unchanged():
    """a pick with no normal (the UI sends null for some faces) keeps the
    plain nearest-centre rule"""
    moved = b3d.Pos(0, 0, 10) * b3d.Box(20, 20, 4)
    f = blocks.resolve_face(moved, [0, 0, 2], None)
    assert f.center().Z == pytest.approx(8.0)      # the nearest face, as before


# ------------------------------------- F2: a tree row that is not a body ------

def assembly():
    d = Document(name="a")
    d.add("cap", "plate", {"width": 40, "depth": 40, "thickness": 6}, [])
    d.add("rib", "plate", {"width": 6, "depth": 6, "thickness": 6}, [])
    d.add("rib_placed", "move", {"x": 12, "y": 0, "z": 6}, ["rib"])
    d.add("fused", "fuse", {}, ["cap", "rib_placed"])
    d.rebuild()
    return d


@pytest.mark.parametrize("tool", ["move", "rotate"])
def test_a_body_another_feature_is_built_from_is_refused_with_a_sentence(tool):
    """clicking the tree row of a CONSUMED solid and pressing Move used to
    build a second copy of it in a branch of its own (measured: the design
    silently grew a body and the result flipped to the 216 mm3 copy)"""
    d = assembly()
    p = toolplan.plan(d, {"tool": tool, "body_id": "rib"})
    assert p["ok"] is False
    assert p["error"] == ("'rib' is not a body on its own — 'rib_placed' is built "
                          "from it. Click a face of the body you can see, or its "
                          f"own row in the tree, then {tool} that.")
    # the body you CAN see is fine
    assert toolplan.plan(d, {"tool": tool, "body_id": "fused"})["ok"] is True


@pytest.mark.parametrize("tool", ["move", "rotate"])
def test_an_edit_still_plans_on_its_own_input(tool):
    """the feature being edited is the one consumer that does not count -
    every move's input is used by that move"""
    d = assembly()
    if tool == "rotate":
        d.add("r", "rotate", {"axis": "Z", "angle_deg": 30, "pivot": "center"}, ["fused"])
        d.rebuild()
        p = toolplan.plan(d, {"tool": "rotate", "feature_id": "r"})
        assert p["ok"] is True and p["input"] == "fused"
    else:
        p = toolplan.plan(d, {"tool": "move", "feature_id": "rib_placed"})
        assert p["ok"] is True and p["input"] == "rib"


# (round one's `test_a_struck_consumer_frees_its_body` stood here and asserted
#  that striking `rib_placed` frees `rib`. It does not: a struck row is a
#  PASS-THROUGH, so `fused` goes on consuming `rib` and the appended move gave
#  the design a second copy of it — the round-one P1 itself. The two halves of
#  the real rule are in round two below.)


# ---------------------------- F3: an edit is named by feature_id, not params --

def test_a_rotate_with_no_stored_params_keeps_the_world_origin_on_an_edit():
    """`plan_rotate` read the truthiness of the stored params to tell an EDIT
    from a new tool session, so a rotate carrying no params at all was planned
    as a NEW one - pivot "center" - and the first OK moved the body off the
    world origin it had always turned about"""
    d = Document(name="r")
    d.add("b", "plate", {"width": 20, "depth": 10, "thickness": 4}, [])
    d.add("m", "move", {"x": 40, "y": 0, "z": 0}, ["b"])
    d.add("r1", "rotate", {}, ["m"])            # defaults: Z, 90, world origin
    d.rebuild()
    before = d._parts["r1"].bounding_box()
    p = toolplan.plan(d, {"tool": "rotate", "feature_id": "r1"})
    assert p["pivot"] is None and p["origin"] == [0.0, 0.0, 0.0]
    # the boxes read what the op will actually do, not zeros
    assert p["params"] == {"axis": "Z", "angle_deg": 90.0, "pivot": None}
    d.edit_many("r1", dict(p["params"]))
    d.rebuild()
    after = d._parts["r1"].bounding_box()
    assert (after.min.X, after.max.Y) == pytest.approx((before.min.X, before.max.Y))


def test_a_new_rotate_is_still_planned_about_the_bodys_own_centre():
    d = Document(name="r")
    d.add("b", "plate", {"width": 20, "depth": 10, "thickness": 4}, [])
    d.add("m", "move", {"x": 40, "y": 0, "z": 0}, ["b"])
    d.rebuild()
    p = toolplan.plan(d, {"tool": "rotate", "body_id": "m"})
    assert p["pivot"] == "center" and p["origin"] == pytest.approx([40, 0, 0])


# ======================================================= ROUND TWO (4ee5670) ==
# The guard round one built for F2 ("a body another feature is built from")
# asked its question in its OWN words instead of Document.consumed_ids', and
# was wrong both ways. Measurements: probes/move_review2_probe.py.

def plate_with_a_face_sketch():
    d = Document(name="fs")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 10}, [])
    d.rebuild()
    top = max(d._parts["b"].faces(), key=lambda f: f.center().Z)
    c, n = top.center(), top.normal_at(top.center())
    d.add("s", "sketch_on_face",
          {"face_center": [c.X, c.Y, c.Z], "face_normal": [n.X, n.Y, n.Z],
           "entities": [{"kind": "circle", "r": 6, "x": 0, "y": 0}]}, ["b"])
    d.rebuild()
    return d


@pytest.mark.parametrize("tool", ["move", "rotate"])
def test_a_sketch_drawn_on_a_body_does_not_stop_the_body_being_placed(tool):
    """A FACE-REFERENCE op points AT a face and consumes nothing — the rule
    Document.consumed_ids and _latest_descendant already live by. The guard
    counted it, so the user's own method (base body first, then sketch on a
    named face) made the ONLY body on screen unmovable: 3 of the 50 saved
    designs, esp32-remote among them."""
    d = plate_with_a_face_sketch()
    assert d.leaf_solid_ids() == ["b"] and "b" not in d.consumed_ids()
    assert toolplan.plan(d, {"tool": tool, "body_id": "b"})["ok"] is True


@pytest.mark.parametrize("tool", ["move", "rotate"])
def test_a_new_body_boss_pulled_off_a_face_leaves_its_parent_placeable(tool):
    d = plate_with_a_face_sketch()
    d.add("boss", "extrude_face", {"amount": 5}, ["b", "s"])
    d.rebuild()
    assert "b" in d.leaf_solid_ids()
    assert toolplan.plan(d, {"tool": tool, "body_id": "b"})["ok"] is True


def test_a_consumer_reading_through_a_struck_row_still_refuses():
    """A struck node is a PASS-THROUGH to its first input, so `fused` really
    consumes `rib`. The guard looked at `inputs` raw and let the round-one P1
    straight back in: the appended move gave the design a second copy of the
    rib and the displayed result flipped from 9600 mm3 to 216 mm3, green."""
    d = assembly()
    d.strike("rib_placed")
    d.rebuild()
    assert "rib" in d.consumed_ids()
    p = toolplan.plan(d, {"tool": "move", "body_id": "rib"})
    assert p["ok"] is False and "'fused' is built" in p["error"]


def test_striking_the_only_consumer_does_free_its_body():
    """the other half of the same rule: with nothing active reading through it,
    a struck consumer really does hand the body back"""
    d = Document(name="s")
    d.add("cap", "plate", {"width": 40, "depth": 40, "thickness": 6}, [])
    d.add("rib", "plate", {"width": 6, "depth": 6, "thickness": 6}, [])
    d.add("rib_placed", "move", {"x": 12, "y": 0, "z": 6}, ["rib"])
    d.strike("rib_placed")
    d.rebuild()
    assert "rib" not in d.consumed_ids()
    assert toolplan.plan(d, {"tool": "move", "body_id": "rib"})["ok"] is True


@pytest.mark.parametrize("tool", ["move", "rotate"])
def test_a_replan_is_about_the_feature_this_session_built(tool):
    """The tool applies as the user drags, so from the second plan on the body
    HAS a consumer — the session's own feature. Without `own_id` (the field
    Mirror and the Patterns already send for exactly this) changing Rotate's
    Axis box answered '⚠ Rotate cannot start: b is not a body on its own' and
    left the ring on the old axis."""
    d = Document(name="c")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.rebuild()
    assert toolplan.plan(d, {"tool": tool, "body_id": "b"})["ok"] is True
    d.add("own1", tool, {"axis": "Z", "angle_deg": 30, "pivot": "center"}
          if tool == "rotate" else {"x": 5, "y": 0, "z": 0}, ["b"])
    d.rebuild()
    assert toolplan.plan(d, {"tool": tool, "body_id": "b"})["ok"] is False
    p = toolplan.plan(d, {"tool": tool, "body_id": "b", "own_id": "own1"})
    assert p["ok"] is True and p["input"] == "b"


def test_own_id_is_a_field_of_the_plan_request():
    """`own_id` has to survive the HTTP model or the browser's fix is a no-op
    (the lesson test_mirror_tool.py already records)"""
    import studio
    req = studio.ToolPlanReq(tool="move", body_id="b", own_id="move1").model_dump()
    assert req["own_id"] == "move1"


def test_own_id_does_not_excuse_another_features_claim():
    """it names ONE feature, not an amnesty: the round-one repro still refuses"""
    d = assembly()
    p = toolplan.plan(d, {"tool": "move", "body_id": "rib", "own_id": "move9"})
    assert p["ok"] is False and "'rib_placed' is built" in p["error"]
