"""Review of the Named parameters tool (127f350 + 4343f30), 2026-09-23.

Each test was RED against the code as it was; the measurements are in
probes/named_params_review_probe.py.
"""
import pytest

import measure
import paramexpr as px
from document import Document

BOSS_TOP, UP = [0.0, 0.0, 15.0], [0.0, 0.0, 1.0]


def _stepped(z):
    """A 40 x 30 x 10 plate with a r8 x 5 boss, MOVED by `z`, and a 5 mm riser
    pulled from a pick on the boss top: two faces point +Z, so a pick that
    stays behind when the body moves lands on the plate instead (the design
    of probes/face_pick_frame_probe.py)."""
    d = Document(name="p-frame")
    d.set_parameter("lift", "0")
    d.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    d.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    d.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8, "x": 0, "y": 0}]})
    d.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    d.add("part", "fuse", {}, inputs=["base", "boss"])
    d.add("placed", "move", {"x": 0, "y": 0, "z": z}, inputs=["part"])
    d.add("riser", "extrude_face", {"face_center": list(BOSS_TOP),
                                    "face_normal": list(UP), "amount": 5},
          inputs=["placed"])
    d.add("final", "fuse", {}, inputs=["placed", "riser"])
    return d


def _volume(d):
    d.rebuild()
    assert all(f.status == "ok" for f in d.features), [(f.id, f.problems) for f in d.features]
    return round(d.result().volume, 2)


def test_a_parameter_that_drives_a_move_carries_the_face_picks_with_it():
    # the Move tool's own edit is the reference: the riser stays on the boss
    ref = _stepped(0)
    ref.edit_many("placed", {"z": 3})
    want = _volume(ref)
    assert want == pytest.approx(14010.62)
    # the Parameters panel: lift 0 -> 3 moves the body by the same 3 mm
    d = _stepped("lift")
    assert _volume(d) == pytest.approx(14010.62)
    d.set_parameter("lift", "3")
    assert _volume(d) == pytest.approx(want), "the riser jumped to the plate top"
    assert d.get("riser").params["face_center"] == pytest.approx([0, 0, 18])
    # ...and back again
    d.set_parameter("lift", "0")
    assert _volume(d) == pytest.approx(14010.62)
    assert d.get("riser").params["face_center"] == pytest.approx([0, 0, 15])


def test_a_formula_typed_into_a_move_carries_the_face_picks_by_its_value():
    d = _stepped(0)
    d.edit_many("placed", {"z": "lift+3"})           # lift is 0: 3 mm
    assert _volume(d) == pytest.approx(14010.62)
    assert d.get("riser").params["face_center"] == pytest.approx([0, 0, 18])
    d.edit_many("placed", {"z": 3})                  # the same place: nothing moves
    assert d.get("riser").params["face_center"] == pytest.approx([0, 0, 18])


def test_a_refused_parameter_change_carries_nothing():
    d = _stepped("lift")
    with pytest.raises(ValueError):
        d.set_parameter("lift", "lift_typo*2")
    assert d.get("riser").params["face_center"] == pytest.approx(BOSS_TOP)


@pytest.mark.parametrize("expr", ["floor(1e400)", "ceil(1e308*10)", "round(1e400)",
                                  "floor(-1e400)"])
def test_an_infinite_value_inside_a_function_is_a_sentence(expr):
    with pytest.raises(ValueError, match="cannot be worked out|no finite value"):
        px.evaluate(expr, {})


def test_an_infinite_parameter_is_refused_and_the_design_still_opens():
    d = Document(name="inf")
    d.set_parameter("a", "3")
    with pytest.raises(ValueError):
        d.set_parameter("b", "floor(1e400)")
    assert set(d.parameters) == {"a"}
    d.set_parameter("a", "4")                        # the document is not stuck
    assert Document.from_data(d.to_data()).param_values == {"a": 4.0}


def test_round_takes_a_number_of_digits():
    assert px.evaluate("round(3.14159, 2)", {}) == pytest.approx(3.14)
    assert px.evaluate("round(wall/3, 1)", {"wall": 10}) == pytest.approx(3.3)
    with pytest.raises(ValueError, match="whole number of digits"):
        px.evaluate("round(3.14159, 1.5)", {})


def test_a_whole_number_parameter_takes_a_formula():
    def plate(count):
        d = Document(name="bolt")
        d.set_parameter("n", "6")
        d.add("p", "polygon_plate", {"circumradius": 30, "sides": 6, "thickness": 5})
        d.add("bc", "with_bolt_circle", {"pitch_circle_dia": 30, "count": count,
                                         "bolt_radius": 2}, inputs=["p"])
        return d
    want = _volume(plate(6))
    d = plate("n")
    assert _volume(d) == pytest.approx(want)
    d.set_parameter("n", "5.5")
    d.rebuild()
    f = d.get("bc")
    assert f.status == "failed" and "whole number" in f.problems[0], f.problems
    assert "TypeError" not in f.problems[0]


def test_measure_reads_a_formula_offset_and_follows_the_parameter():
    d = Document(name="m")
    d.set_parameter("h", "10")
    d.add("sk", "sketch", {"plane": "XY", "offset": "h", "entities": [
        {"kind": "circle", "r": 5, "x": 0, "y": 0}]})
    d.add("e", "extrude", {"amount": 5}, inputs=["sk"])
    d.rebuild()
    pl = measure._sketch_plane(d, d.get("sk"))
    assert pl is not None and pl.origin.Z == pytest.approx(10)
    d.set_parameter("h", "20")
    d.rebuild()
    assert measure._sketch_plane(d, d.get("sk")).origin.Z == pytest.approx(20)


def test_measure_reads_a_formula_hole_diameter():
    d = Document(name="hole")
    d.set_parameter("dia", "6")
    d.add("hole1", "hole", {"diameter": "dia", "depth": 5})
    hit = measure._hole_driver(d, {"origin": "hole1", "origin_op": "hole"}, 3.0)
    assert hit is not None and hit["current"] == pytest.approx(6)


def test_a_parameter_that_needs_a_broken_one_says_so():
    d = Document.from_data({"name": "x", "features": [], "parameters": {
        "a": {"expr": "zz+1"}, "b": {"expr": "a*2"},
        "p": {"expr": "q"}, "q": {"expr": "p"}, "c": {"expr": "p+1"}}})
    assert "no parameter named 'zz'" in d.param_problems["a"]
    assert "'a' has a problem of its own" in d.param_problems["b"]
    assert "p -> q -> p" in d.param_problems["p"]
    assert "q -> p -> q" in d.param_problems["q"]
    assert "is in a loop" not in d.param_problems["c"] and "needs 'p'" in d.param_problems["c"]
    # ...and a FEATURE naming a broken parameter says that parameter's problem
    d.add("sk", "sketch", {"plane": "XY", "entities": [{"kind": "rectangle", "w": 5, "h": 5}]})
    d.add("e", "extrude", {"amount": "p*2"}, inputs=["sk"])
    d.rebuild()
    assert "parameter 'p' has a problem" in d.get("e").problems[0], d.get("e").problems


def test_a_file_where_a_feature_and_a_parameter_share_a_name_still_opens():
    d = Document.from_data({"name": "x", "parameters": {"e": {"expr": "3"}}, "features": [
        {"id": "sk", "op": "sketch", "params": {"plane": "XY", "entities": [
            {"kind": "rectangle", "w": 10, "h": 10}]}, "inputs": []},
        {"id": "e", "op": "extrude", "params": {"amount": 5}, "inputs": ["sk"]}]})
    assert [f.id for f in d.features] == ["sk", "e"]
    assert "name of a feature" in d.param_problems["e"]
    # the authoring doors still refuse the clash
    d2 = Document(name="y")
    d2.set_parameter("w", "1")
    with pytest.raises(ValueError, match="name of a parameter"):
        d2.add("w", "sketch", {"plane": "XY", "entities": []}, strict=True)


def test_extrude_and_sweep_start_on_a_sketch_whose_offset_is_a_formula():
    import toolplan
    d = Document(name="off")
    d.set_parameter("h", "10")
    d.add("sk", "sketch", {"plane": "XY", "offset": "h", "entities": [
        {"kind": "rectangle", "w": 20, "h": 10}]})
    d.rebuild()
    for tool in ("extrude", "sweep"):
        plan = toolplan.plan(d, {"tool": tool, "sketch_id": "sk"})
        assert "could not convert" not in str(plan.get("error")), plan.get("error")
    plan = toolplan.plan(d, {"tool": "extrude", "sketch_id": "sk"})
    assert plan["ok"] and plan["origin"][2] == pytest.approx(10)


def test_the_move_tool_reopens_a_move_whose_offset_is_a_formula():
    import toolplan
    d = _stepped("lift+3")
    d.rebuild()
    plan = toolplan.plan(d, {"tool": "move", "feature_id": "placed"})
    assert plan["ok"], plan.get("error")
    assert plan["params"] == {"x": 0, "y": 0, "z": pytest.approx(3)}


def test_the_ai_door_takes_parameters_in_any_order():
    import author
    feats = [{"id": "sk", "op": "sketch", "params": {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 10, "h": 10}]}},
        {"id": "e", "op": "extrude", "params": {"amount": "depth"}, "inputs": ["sk"]}]
    d = author._to_document({"name": "x", "features": feats, "parameters": {
        "depth": {"expr": "wall*2"}, "wall": {"expr": "3", "comment": "the wall"}}})
    assert d.param_values == {"wall": 3.0, "depth": 6.0}
    assert d.parameters["wall"]["comment"] == "the wall"
    with pytest.raises(ValueError, match="no parameter named 'wal'"):
        author._to_document({"name": "x", "features": feats, "parameters": {
            "depth": "wal*2", "wall": "3"}})
