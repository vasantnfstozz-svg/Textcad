"""Feature-tree layer: document engine, AI author gates, assembly."""
import json
import pytest

import assembly
import author
import blocks
import inspector
from document import Document


def flange_doc():
    doc = Document(name="t-flange")
    doc.add("body", "disc", {"radius": 50, "thickness": 10})
    doc.add("bore", "with_center_hole", {"radius": 15}, inputs=["body"])
    doc.add("bolts", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 76},
            inputs=["bore"])
    doc.spec = {"symmetry": 6, "n_solids": 1, "holes": {"4": 6}, "tol": 0.5}
    return doc


# --------------------------------------------------------------- document ----

def test_document_builds_and_verifies():
    doc = flange_doc()
    assert doc.rebuild()
    assert all(f.status == "ok" for f in doc.features)


def test_edit_changes_one_param_and_marks_stale():
    doc = flange_doc()
    doc.rebuild()
    doc.edit("bore", "radius", 12)
    assert doc.get("bore").params["radius"] == 12
    assert all(f.status == "stale" for f in doc.features)
    assert doc.rebuild()


def test_bad_edit_caught_by_spec():
    doc = flange_doc()
    doc.edit("bolts", "count", 5)
    assert not doc.rebuild()
    assert doc.spec_problems


def test_unknown_op_and_duplicate_id_rejected():
    doc = Document(name="x")
    with pytest.raises(ValueError):
        doc.add("a", "sphere_of_doom", {})
    doc.add("a", "disc", {"radius": 5, "thickness": 2})
    with pytest.raises(ValueError):
        doc.add("a", "disc", {"radius": 5, "thickness": 2})


def test_remove_heals_the_tree_by_default_strict_still_refuses():
    # default (Fusion parity): mid-tree deletes work, dependents reconnect.
    # Full coverage lives in tests/test_delete_repair.py.
    doc = flange_doc()
    doc.remove("bore")
    assert doc.get("bolts").inputs == ["body"]
    assert len(doc.features) == 2
    with pytest.raises(ValueError):        # the old contract, on demand
        flange_doc().remove("body", mode="strict")


def test_rename_rewrites_references_everywhere():
    doc = flange_doc()
    doc.rebuild()
    doc.rollback = "bore"
    doc.rename("bore", "center_hole")
    assert doc.get("center_hole").op == "with_center_hole"
    assert doc.get("bolts").inputs == ["center_hole"]      # inputs rewritten
    assert doc.rollback == "center_hole"                   # bar follows
    assert "center_hole" in doc._parts and "bore" not in doc._parts
    assert doc.get("center_hole").status == "ok"           # no rebuild needed


def test_rename_rejects_duplicates_and_bad_names():
    doc = flange_doc()
    with pytest.raises(ValueError):
        doc.rename("bore", "bolts")            # collision with existing id
    with pytest.raises(ValueError):
        doc.rename("bore", "")                 # empty
    with pytest.raises(ValueError):
        doc.rename("bore", "my hole")          # spaces break URL/chat refs
    with pytest.raises(KeyError):
        doc.rename("nope", "x")                # unknown feature


def test_suppress_passes_through_input():
    doc = flange_doc()
    doc.rebuild()
    full = doc.get("bolts").volume
    doc.get("bore").suppressed = True
    doc._mark_stale()
    doc.rebuild()
    assert doc.get("bolts").volume > full   # no bore -> more material


def test_rollback_stops_building_and_result_respects_bar():
    doc = flange_doc()
    doc.rollback = "body"
    doc.rebuild()
    assert doc.get("bore").status == "stale"
    m = inspector.measure(doc.result())
    assert m["cylinder_radii"].get(15.0) is None      # bore never cut
    doc.rollback = None
    assert doc.rebuild()


def test_save_load_roundtrip(tmp_path):
    doc = flange_doc()
    doc.rebuild()
    p = tmp_path / "f.tcad.json"
    doc.save(str(p))
    doc2 = Document.load(str(p))
    assert doc2.rebuild()
    assert doc2.get("bolts").volume == doc.get("bolts").volume


def test_to_data_excludes_transient_state():
    doc = flange_doc()
    doc.rollback = "body"
    data = doc.to_data()
    assert "rollback" not in data
    assert set(data) == {"name", "spec", "features"}


# ----------------------------------------------------------------- author ----

class ScriptedModel:
    def __init__(self, *responses):
        self.responses = list(responses)
    def generate(self, messages):
        return self.responses.pop(0)


def test_author_rejects_unknown_op_then_repairs():
    bad = json.dumps({"name": "w", "features": [
        {"id": "a", "op": "torus", "params": {}}]})
    good = json.dumps({"name": "w", "features": [
        {"id": "a", "op": "disc", "params": {"radius": 20, "thickness": 4}}],
        "spec": {"n_solids": 1}})
    doc, transcript = author.author_design("a washer", ScriptedModel(bad, good))
    assert doc is not None
    assert "unknown op" in transcript[0]


def test_author_rejects_placeholder_hole_keys():
    bad = json.dumps({"name": "w", "features": [
        {"id": "a", "op": "disc", "params": {"radius": 20, "thickness": 4}}],
        "spec": {"holes": {"radius": 1}}})
    with pytest.raises(ValueError):
        author._to_document(json.loads(bad))


def test_author_rejects_non_integer_symmetry():
    bad = {"name": "w", "features": [
        {"id": "a", "op": "disc", "params": {"radius": 20, "thickness": 4}}],
        "spec": {"symmetry": "infinite"}}
    with pytest.raises(ValueError):
        author._to_document(bad)


def _sketch_tree(n_entities, extra_features=(), sketch_id="art_sketch"):
    ents = [{"kind": "circle", "r": 3 + i, "x": i * 10, "y": 0, "mode": "add"}
            for i in range(n_entities)]
    return {"name": "t", "features": [
        {"id": sketch_id, "op": "sketch",
         "params": {"plane": "XY", "offset": 0, "entities": ents}},
        {"id": "art_extrude", "op": "extrude", "params": {"amount": 3},
         "inputs": [sketch_id]},
        *extra_features,
    ], "spec": {"n_solids": 1}}


def test_lint_rejects_blob_sketch():
    with pytest.raises(ValueError, match="crams"):
        author._to_document(_sketch_tree(12))


def test_lint_rejects_single_sketch_extrude_blob():
    with pytest.raises(ValueError, match="blob"):
        author._to_document(_sketch_tree(6))


def test_lint_rejects_generic_ids():
    tree = {"name": "t", "features": [
        {"id": "feature1", "op": "disc",
         "params": {"radius": 10, "thickness": 3}}], "spec": {"n_solids": 1}}
    with pytest.raises(ValueError, match="meaningless"):
        author._to_document(tree)


def test_lint_accepts_recorded_history():
    # base sketch->extrude + eye sketch->extrude->cut: a real history passes
    tree = {"name": "logo", "features": [
        {"id": "base_sketch", "op": "sketch",
         "params": {"plane": "XY", "offset": 0, "entities": [
             {"kind": "rectangle", "w": 40, "h": 30, "x": 0, "y": 0,
              "mode": "add"}]}},
        {"id": "base_extrude", "op": "extrude", "params": {"amount": 3},
         "inputs": ["base_sketch"]},
        {"id": "eye_sketch", "op": "sketch",
         "params": {"plane": "XY", "offset": 0, "entities": [
             {"kind": "circle", "r": 4, "x": -8, "y": 5, "mode": "add"},
             {"kind": "circle", "r": 4, "x": 8, "y": 5, "mode": "add"}]}},
        {"id": "eye_extrude", "op": "extrude", "params": {"amount": 5},
         "inputs": ["eye_sketch"]},
        {"id": "eye_cut", "op": "cut",
         "inputs": ["base_extrude", "eye_extrude"]},
    ], "spec": {"n_solids": 1}}
    doc = author._to_document(tree)          # must not raise
    assert doc.rebuild(), [p for f in doc.features for p in f.problems]


def test_author_repairs_blob_into_history():
    blob = json.dumps(_sketch_tree(6))
    good = json.dumps({"name": "plate", "features": [
        {"id": "base_sketch", "op": "sketch",
         "params": {"plane": "XY", "offset": 0, "entities": [
             {"kind": "rectangle", "w": 20, "h": 10, "x": 0, "y": 0,
              "mode": "add"}]}},
        {"id": "base_extrude", "op": "extrude", "params": {"amount": 3},
         "inputs": ["base_sketch"]}], "spec": {"n_solids": 1}})
    doc, transcript = author.author_design("a plate", ScriptedModel(blob, good))
    assert doc is not None
    assert "history lint" in transcript[0]   # rejection fed back to the model


def test_op_catalog_matches_document_registry():
    from document import KNOWN_OPS
    assert {c["op"] for c in author.op_catalog()} == KNOWN_OPS


# --------------------------------------------------------------- assembly ----

def test_assembly_fuse_detects_floating_part():
    rep = assembly.build_and_verify(
        [assembly.Component("hub", lambda: blocks.disc(20, 10)),
         assembly.Component("island", lambda: blocks.disc(5, 5), at=(100, 0, 0))],
        mode="fuse")
    assert not rep.ok
    assert any("disconnected" in p for p in rep.assembly_problems)


def test_assembly_fit_detects_clash():
    rep = assembly.build_and_verify(
        [assembly.Component("a", lambda: blocks.disc(10, 40)),
         assembly.Component("b", lambda: blocks.disc(9, 40), at=(5, 0, 0))],
        mode="fit")
    assert not rep.ok
    assert any("interfere" in p for p in rep.assembly_problems)


def test_assembly_localizes_builder_crash():
    rep = assembly.build_and_verify(
        [assembly.Component("good", lambda: blocks.disc(10, 5)),
         assembly.Component("bad", lambda: blocks.tube(10, 12, 5))],
        mode="fuse")
    bad = [c for c in rep.components if c.name == "bad"][0]
    assert not bad.ok and "crashed" in bad.problems[0]
    assert [c for c in rep.components if c.name == "good"][0].ok
