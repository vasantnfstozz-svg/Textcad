"""Deleting a feature out of the MIDDLE of a tree.

The bug these lock in: an AI-authored design is one long chain
(sketch -> extrude tool -> cut, repeated dozens of times), and the old rule
"refuse if anything downstream uses it" made every feature except the very last
one impossible to delete. The user could not remove a sketch or an extrude at
all. Deleting now repairs the history around the node, the way Fusion's browser
Delete does, and REPORTS everything it takes with it.
"""
import pytest
from fastapi.testclient import TestClient

import studio
from document import Document


def flange_doc():
    doc = Document(name="t-flange")
    doc.add("body", "disc", {"radius": 50, "thickness": 10})
    doc.add("bore", "with_center_hole", {"radius": 15}, inputs=["body"])
    doc.add("bolts", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 76},
            inputs=["bore"])
    return doc


def pocket_doc(n_pockets=2):
    """The shape the AI author emits: a base body, then per pocket a sketch, a
    tool prism extruded from it, and a cut of the running body by that tool."""
    doc = Document(name="t-pockets")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 80, "h": 60, "x": 0, "y": 0}]})
    doc.add("body", "extrude", {"amount": 12}, inputs=["outline"])
    prev = "body"
    for i in range(n_pockets):
        x = -20 + 40 * i
        doc.add(f"p{i}_sketch", "sketch", {"plane": "XY", "offset": 12,
                "entities": [{"kind": "circle", "r": 8, "x": x, "y": 0}]})
        doc.add(f"p{i}_tool", "extrude", {"amount": -5},
                inputs=[f"p{i}_sketch"])
        doc.add(f"p{i}", "cut", {}, inputs=[prev, f"p{i}_tool"])
        prev = f"p{i}"
    return doc


def ids(doc):
    return [f.id for f in doc.features]


def assert_tree_sane(doc):
    """No feature may reference a deleted id, or the same input twice."""
    have = {f.id for f in doc.features}
    for f in doc.features:
        assert all(d in have for d in f.inputs), f"{f.id} -> {f.inputs}"
        assert len(set(f.inputs)) == len(f.inputs), f"{f.id} -> {f.inputs}"


# ------------------------------------------------------------ the old bug ----

def test_mid_chain_modifier_is_deletable_and_dependents_reconnect():
    doc = flange_doc()
    assert doc.rebuild()
    plan = doc.remove("bore")                      # used by "bolts"!
    assert plan["deleted"] == ["bore"]
    assert doc.get("bolts").inputs == ["body"]     # reconnected upstream
    assert ids(doc) == ["body", "bolts"]
    assert doc.rebuild(), doc.tree()
    assert_tree_sane(doc)


def test_deleting_a_consumed_sketch_removes_its_pocket_group():
    doc = pocket_doc(2)
    assert doc.rebuild()
    plan = doc.remove("p0_sketch")                 # used by p0_tool -> p0
    assert plan["deleted"] == ["p0_sketch", "p0_tool", "p0"]
    assert set(plan["cascaded"]) == {"p0_tool", "p0"}
    assert doc.get("p1").inputs == ["body", "p1_tool"]   # chain stitched back
    assert doc.rebuild(), doc.tree()
    assert_tree_sane(doc)
    assert doc.leaf_solid_ids() == ["p1"]          # still one body


def test_deleting_the_cut_sweeps_its_tool_prism_and_sketch():
    """Deleting only the cut would leave the tool prism floating in the
    viewport as a stray body — the delete would look broken."""
    doc = pocket_doc(2)
    assert doc.rebuild()
    plan = doc.remove("p0")
    assert plan["deleted"] == ["p0_sketch", "p0_tool", "p0"]
    assert plan["orphans"] == ["p0_sketch", "p0_tool"]
    assert doc.get("p1").inputs == ["body", "p1_tool"]
    assert doc.rebuild(), doc.tree()
    assert doc.leaf_solid_ids() == ["p1"]          # no orphan prism left
    assert not doc.warnings                        # ...and no stray-body note


def test_deleting_a_pocket_restores_the_material_it_removed():
    """Measured, not assumed (house rule 3): the volume must come back."""
    two = pocket_doc(2)
    assert two.rebuild()
    v_two = two.result().volume
    one = pocket_doc(1)
    assert one.rebuild()
    v_one = one.result().volume

    doc = pocket_doc(2)
    assert doc.rebuild()
    doc.remove("p1")                    # drop the second pocket
    assert doc.rebuild(), doc.tree()
    assert doc.result().volume == pytest.approx(v_one, rel=1e-6)
    assert doc.result().volume > v_two


def test_a_sketch_nothing_consumes_yet_deletes_alone():
    doc = pocket_doc(1)
    doc.add("spare", "sketch", {"plane": "XY", "entities": [
        {"kind": "circle", "r": 4, "x": 0, "y": 0}]})
    assert doc.rebuild()
    plan = doc.remove("spare")
    assert plan["deleted"] == ["spare"] and not plan["rewired"]
    assert doc.rebuild()


def test_deleting_an_extrude_keeps_its_sketch():
    """Fusion parity: the sketch is reusable, so it survives its extrude."""
    doc = pocket_doc(1)
    assert doc.rebuild()
    doc.remove("p0_tool")
    assert "p0_sketch" in ids(doc)          # kept, ready to re-extrude
    assert "p0" not in ids(doc)             # the cut cannot live without it
    assert doc.rebuild(), doc.tree()


# ------------------------------------------------- real bodies are not tools --

def test_fuse_keeps_both_bodies_when_the_fuse_is_deleted():
    doc = Document(name="t-fuse")
    doc.add("a", "plate", {"width": 40, "depth": 40, "thickness": 10})
    doc.add("b", "disc", {"radius": 10, "thickness": 30})
    doc.add("both", "fuse", {}, inputs=["a", "b"])
    assert doc.rebuild()
    plan = doc.remove("both")
    assert plan["deleted"] == ["both"] and not plan["orphans"]
    assert ids(doc) == ["a", "b"]               # a fuse has no TOOL slot
    assert doc.rebuild()
    assert doc.leaf_solid_ids() == ["a", "b"]


def test_dropping_one_input_of_a_three_way_fuse_keeps_the_fuse():
    doc = Document(name="t-fuse3")
    doc.add("a", "plate", {"width": 40, "depth": 40, "thickness": 10})
    doc.add("b", "disc", {"radius": 10, "thickness": 30})
    doc.add("c", "ball", {"radius": 8})
    doc.add("all", "fuse", {}, inputs=["a", "b", "c"])
    assert doc.rebuild()
    doc.remove("c")
    assert doc.get("all").inputs == ["a", "b"]   # still 2 inputs -> survives
    assert doc.rebuild()


def two_tool_cut_doc():
    """One cut fed by TWO tool prisms — dropping a tool must not kill the cut,
    but dropping the base (its FIRST input) must."""
    doc = Document(name="t-2tool")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 80, "h": 60, "x": 0, "y": 0}]})
    doc.add("body", "extrude", {"amount": 12}, inputs=["outline"])
    for tag, x, r in (("p0", -20, 8), ("p0b", 20, 5)):
        doc.add(f"{tag}_sketch", "sketch", {"plane": "XY", "offset": 12,
                "entities": [{"kind": "circle", "r": r, "x": x, "y": 0}]})
        doc.add(f"{tag}_tool", "extrude", {"amount": -5},
                inputs=[f"{tag}_sketch"])
    doc.add("p0", "cut", {}, inputs=["body", "p0_tool", "p0b_tool"])
    return doc


def test_cut_dies_with_its_base_but_survives_losing_a_tool():
    doc = two_tool_cut_doc()
    assert doc.rebuild(), doc.tree()

    two = Document.from_data(doc.to_data())
    two.remove("p0b_tool")                       # one tool of three inputs
    assert two.get("p0").inputs == ["body", "p0_tool"]
    assert two.rebuild(), two.tree()

    base = Document.from_data(doc.to_data())
    plan = base.remove("body")                   # the STOCK: nothing survives
    assert "p0" in plan["deleted"]
    assert base.features == [] or base.rebuild()
    assert_tree_sane(base)


# ------------------------------------------------------------------- modes ---

def test_strict_mode_still_refuses():
    doc = flange_doc()
    with pytest.raises(ValueError):
        doc.remove("body", mode="strict")
    doc.remove("bolts", mode="strict")           # a leaf is fine
    assert len(doc.features) == 2


def test_cascade_mode_takes_everything_downstream():
    doc = flange_doc()
    plan = doc.remove("bore", mode="cascade")
    assert plan["deleted"] == ["bore", "bolts"]  # no reconnecting
    assert ids(doc) == ["body"]
    assert doc.rebuild()


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        flange_doc().remove("bolts", mode="obliterate")


def test_remove_plan_is_a_dry_run_and_names_everything():
    doc = pocket_doc(2)
    before = ids(doc)
    plan = doc.remove_plan("p0")
    assert ids(doc) == before                    # nothing changed
    assert plan["remaining"] == len(before) - 3
    assert "p0" in plan["summary"] and "p0_tool" in plan["summary"]
    assert doc.remove_plan("p0") == plan         # deterministic


def test_missing_feature_still_raises():
    with pytest.raises(KeyError):
        flange_doc().remove("nope")


def test_rollback_bar_cannot_survive_its_feature():
    doc = pocket_doc(1)
    doc.rollback = "p0_sketch"
    doc.remove("p0_sketch")
    assert doc.rollback is None
    assert doc.rebuild()


# --------------------------------------------------------------- HTTP API ----

@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(pocket_doc(2))
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def test_api_dry_run_then_delete_then_undo(client):
    dry = client.post("/api/feature/remove", json={
        "feature_id": "p0_sketch", "dry_run": True}).json()
    assert dry["remove_plan"]["deleted"] == ["p0_sketch", "p0_tool", "p0"]
    assert len(dry["features"]) == 8              # dry run changed nothing

    d = client.post("/api/feature/remove",
                    json={"feature_id": "p0_sketch"}).json()
    assert "error" not in d and d["ok"]
    assert [f["id"] for f in d["features"]] == [
        "outline", "body", "p1_sketch", "p1_tool", "p1"]
    assert d["remove_plan"]["summary"]

    back = client.post("/api/undo").json()        # one undo restores all three
    assert len(back["features"]) == 8


def test_api_delete_error_does_not_eat_the_undo_stack(client):
    before = client.get("/api/doc").json()["can_undo"]
    d = client.post("/api/feature/remove", json={"feature_id": "ghost"}).json()
    assert "error" in d and d["can_undo"] == before


# ---------------------------------------------------------- delete by chat ---

def test_chat_delete_removes_a_pocket_group(client, monkeypatch):
    monkeypatch.setattr(studio, "chat_intent",
                        lambda m, feedback=None: {"action": "delete",
                                                  "feature_id": "p0"})
    d = client.post("/api/chat", json={"message": "delete the left pocket"}).json()
    assert [f["id"] for f in d["features"]] == [
        "outline", "body", "p1_sketch", "p1_tool", "p1"]
    assert d["ok"] and "p0" in d["reply"] and d["can_undo"]


def test_chat_refuses_to_demolish_the_whole_design(client, monkeypatch):
    monkeypatch.setattr(studio, "chat_intent",
                        lambda m, feedback=None: {"action": "delete",
                                                  "feature_id": "body"})
    before = client.get("/api/doc").json()["features"]
    d = client.post("/api/chat", json={"message": "delete the body"}).json()
    assert len(d["features"]) == len(before)          # nothing was touched
    assert "did NOT touch" in d["reply"] and d["remove_plan"]["deleted"]


# ------------------------------------------- the gear-case wipe (P0, fixed) ----

def face_pocket_doc():
    """The shape that wiped a 14-feature tree (gear-case, 2026-08-31): the LAST
    pocket's sketch is drawn ON the running body, so the body is one of that
    sketch's inputs."""
    doc = pocket_doc(1)                              # outline, body, p0_*
    doc.add("s_sketch", "sketch_on_face",
            {"face": "top", "offset": 0,
             "entities": [{"kind": "circle", "r": 6, "x": 20, "y": 0}]},
            inputs=["p0"])
    doc.add("s_tool", "extrude", {"amount": -4}, inputs=["s_sketch"])
    doc.add("s_cut", "cut", {}, inputs=["p0", "s_tool"])
    return doc


def test_deleting_a_tail_cut_drawn_on_the_body_keeps_the_body():
    """Removing the LAST cut swept its tool prism, then its sketch -- and then,
    because the sketch was drawn on the body, the body and everything before
    it: "14 features removed, 0 left". A face is a place to draw, not tool
    geometry; the sweep stops at that reference now."""
    doc = face_pocket_doc()
    assert doc.rebuild(), [f.status for f in doc.features]
    plan = doc.remove_plan("s_cut")
    assert plan["orphans"] == ["s_sketch", "s_tool"]
    assert plan["deleted"] == ["s_sketch", "s_tool", "s_cut"]
    doc.remove("s_cut")
    assert ids(doc) == ["outline", "body", "p0_sketch", "p0_tool", "p0"]
    assert_tree_sane(doc)
    assert doc.rebuild() and doc.leaf_solid_ids() == ["p0"]
