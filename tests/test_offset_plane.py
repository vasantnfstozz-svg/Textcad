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
    # deleting the plane takes the sketch on it along, and leaves the sketch on
    # the PRINCIPAL plane where it is (the plan's own key, `deleted` — reading
    # keys that do not exist made this assertion pass on the summary text)
    plan = d.remove_plan("lid_plane", "auto")
    assert set(plan["deleted"]) == {"lid_plane", "s1"}, plan
    assert "s0" not in plan["deleted"]


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


def test_deleting_something_else_leaves_the_plane_and_its_sketches_alone():
    """A plane off a PRINCIPAL plane has no inputs and never loses one, so no
    other delete may sweep it up. The delete plan's "does this feature still
    have enough inputs?" rule read 1 for every op that is not a creator, so a
    plane, every sketch on it and everything built from those went with the
    first unrelated ✕ — 4 rows removed for a delete of 1, silently."""
    d = _plate()
    d.add("tool", "plate", {"width": 10, "depth": 10, "thickness": 10}, [])
    d.add("p1", "offset_plane", {"plane": "XY", "offset": 30}, [])
    d.add("s1", "sketch", {"plane": "p1", "entities": CIRCLE}, [])
    d.add("e1", "extrude", {"amount": 5}, ["s1"])
    assert d.rebuild(), [(f.id, f.problems) for f in d.features]
    plan = d.remove_plan("tool", "auto")
    assert plan["deleted"] == ["tool"], plan["summary"]
    assert plan["cascaded"] == []
    # the ✕ (soft delete) is the same plan, so it struck them out too
    d.strike("tool")
    assert [f.id for f in d.features if f.suppressed] == ["tool"]
    assert d.rebuild()
    assert d._parts["s1"].faces()[0].center().Z == pytest.approx(30)


def test_deleting_the_body_under_a_face_plane_takes_the_plane_along():
    """The other half of the same rule: a plane measured off a FACE cannot
    survive without its body (it would silently fall back to the XY plane),
    so it cascades — and so do the sketches on it."""
    d = _plate()
    d.add("p2", "offset_plane", {"face": "top", "offset": -6}, ["b"])
    d.add("s2", "sketch", {"plane": "p2", "entities": RECT}, [])
    assert d.rebuild()
    plan = d.remove_plan("b", "auto")
    assert set(plan["deleted"]) == {"b", "p2", "s2"}
    assert set(plan["cascaded"]) == {"p2", "s2"}


def test_a_face_named_without_a_body_is_refused_not_quietly_measured_from_xy():
    """`face: "top"` with no input used to build a plane off XY at the same
    number — a plane 20 mm below the stock where the user asked for one 6 mm
    into its top face, status ok. Wrong placement, said by nothing."""
    d = _plate()
    d.add("p", "offset_plane", {"face": "top", "offset": -6}, [])
    d.rebuild()
    f = d.get("p")
    assert f.status == "failed", f"built at {d._parts.get('p')}"
    assert "no body" in f.problems[0] and "Traceback" not in f.problems[0], f.problems
    # a plane with no face named and no input is the ordinary principal plane
    d.add("q", "offset_plane", {"plane": "XY", "offset": -6}, [])
    d.rebuild()
    assert d.get("q").status == "ok"


def test_moving_a_construction_plane_is_a_sentence_not_python_wording():
    """`move` is the one modifier that skips the kind check, so a plane fed to
    it answered `AttributeError: 'Plane' object has no attribute 'volume'`."""
    d = _plate()
    d.add("p1", "offset_plane", {"plane": "XY", "offset": 30}, [])
    d.add("m", "move", {"x": 10}, ["p1"])
    d.rebuild()
    f = d.get("m")
    assert f.status == "failed"
    assert "construction plane" in f.problems[0], f.problems
    assert "AttributeError" not in f.problems[0] and "Traceback" not in f.problems[0]


def test_the_offset_method_lint_does_not_fire_on_a_sketch_on_a_plane_row():
    """The offset-method rule bans a sketch at an ABSOLUTE Z once a body
    exists. A sketch on a construction plane is the opposite: its number is
    measured from a row that rides the geometry. And a plane is not a body,
    so it must not be what starts the rule either."""
    import author
    from document import Feature
    tree = [
        Feature(id="base", op="plate", params={"width": 60, "depth": 40, "thickness": 20}, inputs=[]),
        Feature(id="lid", op="offset_plane", params={"face": "top", "offset": -6}, inputs=["base"]),
        Feature(id="pocket_sketch", op="sketch", params={"plane": "lid", "offset": 2,
                                                         "entities": CIRCLE}, inputs=[]),
    ]
    assert not [w for w in author.lint_tree(tree) if "floats at absolute Z" in w], \
        author.lint_tree(tree)
    # a plane BEFORE any body does not make the rule think one exists
    early = [
        Feature(id="lid", op="offset_plane", params={"plane": "XY", "offset": 10}, inputs=[]),
        Feature(id="s", op="sketch", params={"plane": "XY", "offset": 3, "entities": CIRCLE}, inputs=[]),
    ]
    assert not [w for w in author.lint_tree(early) if "floats at absolute Z" in w], \
        author.lint_tree(early)
    # the rule itself is untouched: a body, then a floating absolute sketch
    still = [
        Feature(id="base", op="plate", params={"width": 60, "depth": 40, "thickness": 20}, inputs=[]),
        Feature(id="s", op="sketch", params={"plane": "XY", "offset": 20, "entities": CIRCLE}, inputs=[]),
    ]
    assert [w for w in author.lint_tree(still) if "floats at absolute Z" in w]


# an open path drawn on XZ that STARTS on a profile sitting at z = 30 (world
# (0,0,30) is local (0,30) there) and LEAVES along that profile's +Z normal —
# both of Sweep's own rules, so the plan can only fail on the plane lookup
PATH = [{"kind": "path", "start": [0, 30], "closed": False,
         "segments": [{"to": [0, 70]}, {"to": [40, 70]}], "mode": "add"}]


def test_extrude_and_sweep_plan_a_sketch_that_sits_on_a_plane_row():
    """The user (2026-09-23): "I draw something on xz or yz plane, I cannot
    extrude that shape, but revolve is working". It was never the principal
    plane — it was the offset plane under the sketch. `toolplan._profile`
    asked `sk.sketch_plane` for the plane the profile was drawn on, which only
    knows "XY"/"XZ"/"YZ", so Extrude and Sweep (its two callers) refused every
    sketch on a plane row with `sketch: plane must be "XY", "XZ" or "YZ"` —
    while the KERNEL built the same extrude happily, and Revolve worked
    because it reads the plane off the built sketch instead."""
    d = Document(name="t")
    d.add("p1", "offset_plane", {"plane": "XZ", "offset": 20}, [])
    d.add("s1", "sketch", {"plane": "p1", "entities": CIRCLE}, [])
    assert d.rebuild(), [(f.id, f.problems) for f in d.features]

    plan = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s1"})
    assert plan["ok"], plan.get("error")
    # the plan's frame IS the plane's — XZ's normal points -Y, so the plane
    # sits at y = -20 and the extrude runs -Y from there (R1: one source)
    assert plan["frame"]["origin"] == [0.0, -20.0, 0.0]
    assert plan["frame"]["z_dir"] == [0.0, -1.0, 0.0]

    # and the kernel puts the solid exactly where the plan said it would
    d.add("e1", "extrude", {"amount": 5}, ["s1"])
    assert d.rebuild(), [(f.id, f.problems) for f in d.features]
    bb = d._parts["e1"].bounding_box()
    assert (bb.min.Y, bb.max.Y) == (pytest.approx(-25), pytest.approx(-20))

    # Sweep is the other caller of the same helper: a profile on a plane row,
    # with a path that starts on it
    w = Document(name="t2")
    w.add("p2", "offset_plane", {"plane": "XY", "offset": 30}, [])
    w.add("prof", "sketch", {"plane": "p2", "entities": CIRCLE}, [])
    w.add("rail", "sketch", {"plane": "XZ", "entities": PATH}, [])
    assert w.rebuild(), [(f.id, f.problems) for f in w.features]
    sw = toolplan.plan(w, {"tool": "sweep", "sketch_id": "prof", "path_id": "rail"})
    assert sw["ok"], sw.get("error")


def test_a_sketch_on_a_plane_row_stacks_its_own_offset_in_the_extrude_plan():
    """The sketch's own `offset` rides ON TOP of the plane's, in the plan
    exactly as `make_sketch` stacks it on the build."""
    d = Document(name="t")
    d.add("p1", "offset_plane", {"plane": "XY", "offset": 30}, [])
    d.add("s1", "sketch", {"plane": "p1", "offset": 4, "entities": CIRCLE}, [])
    assert d.rebuild()
    plan = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s1"})
    assert plan["ok"], plan.get("error")
    assert plan["frame"]["origin"][2] == pytest.approx(34)
    assert d._parts["s1"].faces()[0].center().Z == pytest.approx(34), "plan and build agree"


def test_measure_finds_the_plane_of_a_sketch_on_a_plane_row_and_follows_it():
    """Measure derives a sketch's plane from the CURRENT geometry so it can
    drive a dimension back to the entity that made it. It read the plane out
    of `sketch._PLANES`, which only holds "XY"/"XZ"/"YZ", so every sketch on a
    construction plane answered None and quietly lost its drive link — the
    same circle drawn on `XY offset 30` kept it.

    And its cache is keyed on the SKETCH's own params, which do not move when
    the PLANE does: the entry has to follow the plane part the same way a face
    sketch's entry follows its body."""
    import measure
    d = Document(name="t")
    d.add("p1", "offset_plane", {"plane": "XY", "offset": 30}, [])
    d.add("s1", "sketch", {"plane": "p1", "entities": CIRCLE}, [])
    d.add("s0", "sketch", {"plane": "XY", "offset": 30, "entities": CIRCLE}, [])
    assert d.rebuild(), [(f.id, f.problems) for f in d.features]

    pl = measure._sketch_plane(d, d.get("s1"))
    assert pl is not None, "a sketch on a plane row has a plane like any other"
    ref = measure._sketch_plane(d, d.get("s0"))
    assert list(tuple(pl.origin)) == pytest.approx(list(tuple(ref.origin)))
    assert pl.origin.Z == pytest.approx(30)
    # the sketch's own offset still stacks on the plane's
    d.add("s2", "sketch", {"plane": "p1", "offset": 5, "entities": CIRCLE}, [])
    d.rebuild()
    assert measure._sketch_plane(d, d.get("s2")).origin.Z == pytest.approx(35)

    # move the plane: the cached answer must move with it, not stay at 30
    d.edit_many("p1", {"offset": 50})
    assert d.rebuild()
    assert d._parts["s1"].faces()[0].center().Z == pytest.approx(50), "the build moved"
    assert measure._sketch_plane(d, d.get("s1")).origin.Z == pytest.approx(50), \
        "measure's cached plane is stale — it keys on the sketch, which did not change"
