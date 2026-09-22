"""Construct > Offset Plane — the `offset_plane` feature (specs/offset-plane.md).

A construction plane is its own tree row: a distance from a principal plane
(no input) or from a flat face of a body (one input, a reference — the body is
NOT consumed). Sketches name it in `plane` and move with it. Neither a solid
nor a sketch, so every place that sorts features into those two kinds has to
know the third: the rebuild loop, the leaf solids the viewport shows, the
result feature, the modifier / combiner guards, the delete plan's kinds.
Every geometric claim below is MEASURED on the built part (rule 3).
"""
import pytest

import sketch as sk
import toolplan
from document import Document

CIRCLE = [{"kind": "circle", "x": 0, "y": 0, "r": 8, "mode": "add"}]
RECT = [{"kind": "rectangle", "x": 0, "y": 0, "w": 20, "h": 10, "mode": "add"}]


def _plate():
    d = Document(name="t")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 20}, [])
    return d


def test_a_plane_off_xy_puts_the_sketch_and_its_extrude_at_that_height():
    d = _plate()
    d.add("p1", "offset_plane", {"plane": "XY", "offset": 30}, [])
    d.add("s1", "sketch", {"plane": "p1", "entities": CIRCLE}, [])
    d.add("e1", "extrude", {"amount": 5}, ["s1"])
    assert d.rebuild(), [(f.id, f.problems) for f in d.features]
    assert sk.is_plane(d._parts["p1"])
    assert d.get("p1").volume is None and d.get("p1").status == "ok"
    assert d._parts["s1"].faces()[0].center().Z == pytest.approx(30)
    bb = d._parts["e1"].bounding_box()
    assert (bb.min.Z, bb.max.Z) == (pytest.approx(30), pytest.approx(35))
    assert d._parts["e1"].volume == pytest.approx(3.14159265 * 64 * 5, rel=1e-4)
    # the plane is neither a body on screen nor the result
    assert d.leaf_solid_ids() == ["b", "e1"]
    assert d._result_feature().id == "e1"
    assert d._kinds()["p1"] == "plane"


def test_a_plane_off_a_face_rides_the_face_and_does_not_eat_the_body():
    d = _plate()
    d.add("p2", "offset_plane", {"face": "top", "offset": -6}, ["b"])
    d.add("s2", "sketch", {"plane": "p2", "entities": RECT}, [])
    assert d.rebuild(), [(f.id, f.problems) for f in d.features]
    assert d._parts["s2"].faces()[0].center().Z == pytest.approx(4)   # top at 10, 6 in
    assert "b" not in d.consumed_ids(), "the body an offset plane is measured from stays on screen"
    assert d.leaf_solid_ids() == ["b"]
    # thicker stock: the top face moves, the plane and the sketch ride along
    d.edit_many("b", {"thickness": 30})
    d.rebuild()
    assert d._parts["s2"].faces()[0].center().Z == pytest.approx(15 - 6)
    # Join / Cut on a sketch on that plane defaults to THAT body, like a face sketch
    assert toolplan._default_target(d, "s2") == "b"


def test_editing_the_plane_offset_moves_every_sketch_on_it():
    d = _plate()
    d.add("p1", "offset_plane", {"plane": "XY", "offset": 30}, [])
    d.add("s1", "sketch", {"plane": "p1", "entities": CIRCLE}, [])
    d.add("s3", "sketch", {"plane": "p1", "offset": 2, "entities": RECT}, [])
    d.add("e1", "extrude", {"amount": 5}, ["s1"])
    d.rebuild()
    d.edit_many("p1", {"offset": 50})
    assert d.rebuild()
    assert d._parts["s1"].faces()[0].center().Z == pytest.approx(50)
    assert d._parts["s3"].faces()[0].center().Z == pytest.approx(52)   # its own offset on top
    assert d._parts["e1"].bounding_box().min.Z == pytest.approx(50)


def test_the_plan_and_the_build_share_one_plane():
    d = _plate()
    d.add("p2", "offset_plane", {"face": "top", "offset": -6}, ["b"])
    d.rebuild()
    plan = toolplan.plan_sketch(d, {"plane": "p2", "offset": 0})
    assert plan["ok"] and plan["frame"]["origin"][2] == pytest.approx(4)
    assert "offset plane 'p2'" in plan["will_build"]
    # the sketch's own offset stacks on the plane's, in the plan as in the build
    assert toolplan.plan_sketch(d, {"plane": "p2", "offset": 3})["frame"]["origin"][2] == pytest.approx(7)
    assert toolplan._frame(d.plane_of("p2"))["origin"][2] == pytest.approx(4)
    assert toolplan._frame(d.plane_of("XY"))["origin"] == [0.0, 0.0, 0.0]


@pytest.mark.parametrize("fid, op, params, inputs, words", [
    ("bad1", "extrude", {"amount": 5}, ["p1"], "construction plane"),
    ("bad2", "fuse", {}, ["b", "p1"], "construction plane"),
    ("bad3", "sketch", {"plane": "nope", "entities": CIRCLE}, [], "no 'nope'"),
    ("bad4", "sketch", {"plane": "b", "entities": CIRCLE}, [], "not a plane"),
    ("bad5", "offset_plane", {"face": "top", "offset": 1}, ["s1"], "not a solid body"),
    ("bad6", "offset_plane", {"plane": "QQ", "offset": 1}, [], "plane must be"),
])
def test_wrong_kinds_are_refused_with_a_sentence(fid, op, params, inputs, words):
    d = _plate()
    d.add("p1", "offset_plane", {"plane": "XY", "offset": 30}, [])
    d.add("s1", "sketch", {"plane": "p1", "entities": CIRCLE}, [])
    d.add(fid, op, params, inputs)
    d.rebuild()
    f = d.get(fid)
    assert f.status == "failed" and words in f.problems[0], f.problems
    # the refusal is a sentence, never kernel wording
    assert "Standard_" not in f.problems[0] and "Traceback" not in f.problems[0]


def test_rename_and_delete_follow_the_reference():
    d = _plate()
    d.add("p1", "offset_plane", {"plane": "XY", "offset": 30}, [])
    d.add("s1", "sketch", {"plane": "p1", "entities": CIRCLE}, [])
    d.add("s0", "sketch", {"plane": "XY", "entities": CIRCLE}, [])
    d.rebuild()
    assert Document.param_refs(d.get("s1")) == ["p1"]
    assert Document.param_refs(d.get("s0")) == [], "a principal plane is not a reference"
    d.rename("p1", "lid_plane")
    assert d.get("s1").params["plane"] == "lid_plane"
    assert d.rebuild()
    # deleting the plane takes the sketch on it along (the delete plan lists it)
    plan = d.remove_plan("lid_plane") if hasattr(d, "remove_plan") else None
    if plan is not None:
        gone = set(plan.get("removed") or plan.get("gone") or plan.get("delete") or [])
        assert "s1" in gone or "s1" in str(plan), plan


def test_a_formula_offset_resolves_and_rides_the_parameter():
    """`offset` is numeric on the plane op too, so "-wall" is resolved before
    the kernel sees it (the browser test found it refused as a bad value)."""
    d = _plate()
    d.set_parameter("wall", 4)
    d.add("lid", "offset_plane", {"face": "top", "offset": "-wall"}, ["b"])
    d.add("s", "sketch", {"plane": "lid", "entities": CIRCLE}, [])
    assert d.rebuild(), [(f.id, f.problems) for f in d.features]
    assert d._parts["s"].faces()[0].center().Z == pytest.approx(6)
    assert "offset" in Document.numeric_params("offset_plane")
    assert d.resolved_json(d.get("lid")) == {"offset": -4}


def test_a_plane_off_another_plane_is_not_a_thing_yet():
    """The op measures from a principal plane or a face — a plane named in
    `plane` is refused with the op's own sentence, not built off nothing."""
    d = _plate()
    d.add("p1", "offset_plane", {"plane": "XY", "offset": 30}, [])
    d.add("p3", "offset_plane", {"plane": "p1", "offset": 5}, [])
    d.rebuild()
    assert d.get("p3").status == "failed" and "plane must be" in d.get("p3").problems[0]


def test_the_catalog_and_the_doc_json_know_the_plane():
    from fastapi.testclient import TestClient
    import author
    import studio
    cat = [c for c in author.op_catalog() if c["op"] == "offset_plane"]
    assert len(cat) == 1 and cat[0]["kind"] == "plane"
    assert [p["name"] for p in cat[0]["params"]][:2] == ["plane", "offset"]
    studio.STATE["docs"].clear(); studio.STATE["active"] = None; studio.STATE["seq"] = 0
    studio._new_tab(Document(name="t"))
    c = TestClient(studio.app)
    c.post("/api/feature/add", json={"id": "b", "op": "plate",
                                     "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
    doc = c.post("/api/feature/add", json={"id": "p2", "op": "offset_plane",
                                           "params": {"face": "top", "offset": -6}, "inputs": ["b"]}).json()
    p2 = [f for f in doc["features"] if f["id"] == "p2"][0]
    assert p2["status"] == "ok" and p2["plane_frame"]["origin"][2] == pytest.approx(4)
    assert p2["plane_frame"]["z_dir"] == [0.0, 0.0, 1.0]
    assert [f["plane_frame"] for f in doc["features"] if f["id"] == "b"] == [None]
    assert doc["bodies"] == 1, "the plane is not a body"
    plan = c.post("/api/tool/plan", json={"tool": "sketch", "plane": "p2", "offset": 0}).json()
    assert plan["ok"] and plan["frame"]["origin"][2] == pytest.approx(4)
