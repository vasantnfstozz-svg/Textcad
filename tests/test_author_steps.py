"""P5 — the AI uses the tools (LAUNCH-PLAN.md §5 step B).

The model adds ONE feature per reply through `author.author_steps`; every
step goes through the same strict add + lint + rebuild the toolbar's Add
Feature uses and is judged on its own. These tests script the model and
check what reaches the tree, what the model is told, and what the chat route
does with a job — no API key, no browser."""
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

import author
import studio
from document import Document


class Scripted:
    """Replies in order; keeps every user message it was shown."""
    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r)
                        for r in replies]
        self.heard: list[str] = []

    def generate(self, messages):
        self.heard.append(messages[-1]["content"])
        assert self.replies, "the model was asked for more steps than scripted"
        return self.replies.pop(0)


DISC = {"name": "washer", "add": {"id": "body", "op": "disc",
                                  "params": {"radius": 20, "thickness": 4}}}
BORE = {"add": {"id": "bore", "op": "with_center_hole",
                "params": {"radius": 10}, "inputs": ["body"]}}
PLATE = {"add": {"id": "plate", "op": "plate",
                 "params": {"width": 20, "depth": 20, "thickness": 4}}}
DONE = {"done": True, "spec": {"n_solids": 1}}


def _sketch(fid, entities, **params):
    return {"add": {"id": fid, "op": "sketch",
                    "params": {"plane": "XY", "offset": 0, "entities": entities,
                               **params}}}


RECT = [{"kind": "rectangle", "w": 20, "h": 10, "x": 0, "y": 0, "mode": "add"}]


# ------------------------------------------------------------ the loop ------

def test_each_step_lands_verified_and_the_model_hears_measured_facts():
    doc = Document(name="untitled")
    events = []
    m = Scripted(DISC, BORE, {"done": True, "spec": {"n_solids": 1,
                                                    "holes": {"10": 1}}})
    ok, transcript = author.author_steps(doc, "a washer", m,
                                         on_step=events.append)
    assert ok and doc.name == "washer"
    assert [f.id for f in doc.features] == ["body", "bore"]
    assert all(f.status == "ok" for f in doc.features) and not doc.spec_problems
    # what the model was told after step one: the measured body, not a guess
    assert "5026.55" in m.heard[1] and "40×40×4" in m.heard[1]
    assert "Bodies: body" in m.heard[1]
    assert [e["kind"] for e in events] == ["add", "add", "done"]
    assert events[-1]["ok"] is True
    assert doc.spec == {"n_solids": 1, "holes": {10.0: 1}}


def test_a_hallucinated_op_is_refused_and_never_enters_the_tree():
    doc = Document(name="untitled")
    torus = {"add": {"id": "body", "op": "torus", "params": {"r": 20}}}
    m = Scripted(torus, DISC, DONE)
    ok, transcript = author.author_steps(doc, "a ring", m)
    assert ok
    assert [f.id for f in doc.features] == ["body"] and doc.get("body").op == "disc"
    assert "unknown op 'torus'" in m.heard[1]
    assert "corrected step" in m.heard[1]


def test_a_hallucinated_parameter_is_refused_at_its_own_step():
    doc = Document(name="untitled")
    bad = {"add": {"id": "body", "op": "disc",
                   "params": {"radiuss": 20, "thickness": 4}}}
    m = Scripted(bad, DISC, DONE)
    ok, _ = author.author_steps(doc, "a disc", m)
    assert ok and doc.get("body").params == {"radius": 20, "thickness": 4}
    assert "radiuss" in m.heard[1]


def test_a_step_that_builds_broken_geometry_is_undone_before_the_model_hears():
    doc = Document(name="untitled")
    huge = {"add": {"id": "round", "op": "fillet",
                    "params": {"radius": 50, "edges": "all"}, "inputs": ["plate"]}}
    m = Scripted(PLATE, huge, DONE)
    ok, transcript = author.author_steps(doc, "a plate", m)
    assert ok
    assert [f.id for f in doc.features] == ["plate"]      # the fillet is gone
    assert doc.get("plate").status == "ok"
    assert m.heard[2].startswith("UNDONE 'round'")
    assert "fillet" in m.heard[2]


def test_the_offset_method_lint_refuses_a_floating_sketch_per_step():
    doc = Document(name="untitled")
    base = _sketch("base_sketch", RECT)
    ext = {"add": {"id": "base", "op": "extrude", "params": {"amount": 3},
                   "inputs": ["base_sketch"]}}
    floating = _sketch("boss_sketch", RECT, offset=3)
    on_face = {"add": {"id": "boss_sketch", "op": "sketch_on_face",
                       "params": {"face": "top", "offset": 0, "entities": RECT},
                       "inputs": ["base"]}}
    m = Scripted(base, ext, floating, on_face, DONE)
    ok, _ = author.author_steps(doc, "a plate with a boss", m)
    assert ok
    assert doc.get("boss_sketch").op == "sketch_on_face"
    assert "history lint" in m.heard[3] and "sketch_on_face" in m.heard[3]


def test_the_blob_rule_judges_the_finished_design_not_the_second_step():
    """ONE sketch + ONE extrude with 6 entities is refused at DONE (it is a
    blob), not at step two (a ten-step part starts the same way)."""
    doc = Document(name="untitled")
    six = [{"kind": "circle", "r": 3 + i, "x": i * 10, "y": 0, "mode": "add"}
           for i in range(6)]
    ext = {"add": {"id": "art", "op": "extrude", "params": {"amount": 3},
                   "inputs": ["art_sketch"]}}
    base = _sketch("base_sketch", RECT)
    base_ext = {"add": {"id": "base_extrude", "op": "extrude",
                        "params": {"amount": 3}, "inputs": ["base_sketch"]}}
    m = Scripted(_sketch("art_sketch", six), ext, DONE,
                 {"remove": "art"}, {"remove": "art_sketch"},
                 base, base_ext, DONE)
    ok, transcript = author.author_steps(doc, "a plate", m)
    assert ok
    assert "history lint" not in m.heard[2]              # step two went in
    assert "REFUSED done (history lint)" in m.heard[3]   # the blob, at done
    assert [f.id for f in doc.features] == ["base_sketch", "base_extrude"]


def test_remove_only_takes_back_a_step_nothing_builds_on():
    doc = Document(name="untitled")
    m = Scripted(DISC, BORE, {"remove": "body"}, {"remove": "bore"}, DONE)
    ok, _ = author.author_steps(doc, "a washer", m)
    assert ok
    assert "REFUSED remove of 'body'" in m.heard[3]
    assert [f.id for f in doc.features] == ["body"]


def test_an_edit_points_at_one_parameter_and_is_measured():
    doc = Document(name="untitled")
    m = Scripted(DISC, {"edit": {"feature_id": "body", "param": "radius",
                                 "value": 25}}, DONE)
    ok, _ = author.author_steps(doc, "a disc", m)
    assert ok and len(doc.features) == 1
    assert doc.get("body").params["radius"] == 25
    assert doc.get("body").volume == pytest.approx(3.14159265 * 625 * 4, rel=1e-4)
    assert "50×50×4" in m.heard[2]


def test_an_edit_that_breaks_a_downstream_feature_is_undone():
    doc = Document(name="untitled")
    small = {"add": {"id": "round", "op": "fillet",
                     "params": {"radius": 1, "edges": "all"}, "inputs": ["plate"]}}
    m = Scripted(PLATE, small, {"edit": {"feature_id": "round", "param": "radius",
                                         "value": 50}}, DONE)
    ok, _ = author.author_steps(doc, "a plate", m)
    assert ok
    assert doc.get("round").params["radius"] == 1 and doc.get("round").status == "ok"
    assert m.heard[3].startswith("UNDONE edit 'round.radius' = 50")


def test_done_with_an_unmet_spec_is_refused_until_the_geometry_meets_it():
    doc = Document(name="untitled")
    strict = {"done": True, "spec": {"n_solids": 1, "size": [100, 100, 4],
                                    "tol": 0.5}}
    m = Scripted(DISC, strict, {"edit": {"feature_id": "body", "param": "radius",
                                         "value": 50}}, strict)
    ok, transcript = author.author_steps(doc, "a 100mm disc", m)
    assert ok
    assert "REFUSED done: the part does not meet the spec" in m.heard[2]
    assert "never weaken the spec" in m.heard[2]
    assert not doc.spec_problems


def test_done_on_a_design_without_a_body_is_refused():
    doc = Document(name="untitled")
    m = Scripted(_sketch("s", RECT), DONE, {"add": {"id": "b", "op": "extrude",
                                                  "params": {"amount": 3},
                                                  "inputs": ["s"]}}, DONE)
    ok, _ = author.author_steps(doc, "a plate", m)
    assert ok and "no solid body yet" in m.heard[2]


def test_gives_up_after_repeated_refusals_and_says_so():
    doc = Document(name="untitled")
    bad = {"add": {"id": "x", "op": "torus", "params": {}}}
    m = Scripted(bad, "not even json", bad)
    events = []
    ok, transcript = author.author_steps(doc, "a ring", m, on_step=events.append)
    assert not ok and doc.features == []
    assert events[-1]["kind"] == "gave_up"
    assert "GAVE UP after 3 refused steps" in transcript[-1]
    assert "not one JSON object" in transcript[1]


def test_a_success_resets_the_failure_count():
    doc = Document(name="untitled")
    bad = {"add": {"id": "x", "op": "torus", "params": {}}}
    m = Scripted(bad, bad, DISC, bad, bad, BORE, DONE)
    ok, _ = author.author_steps(doc, "a washer", m)
    assert ok and [f.id for f in doc.features] == ["body", "bore"]


def test_adding_to_an_existing_design_shows_the_model_the_tree_first():
    doc = studio.sample_flange()
    doc.rebuild()
    hole = {"add": {"id": "side_hole", "op": "hole",
                    "params": {"face": "top", "at": [0, 25], "diameter": 6,
                               "through": True}, "inputs": ["bolts"]}}
    m = Scripted(hole, DONE)
    n = len(doc.features)
    ok, _ = author.author_steps(doc, "a 6mm hole through the centre", m)
    assert ok and len(doc.features) == n + 1
    assert "CURRENT TREE" in m.heard[0] and '"bolts"' in m.heard[0]
    assert "BODIES: bolts" in m.heard[0]


def test_author_design_is_the_step_loop_on_a_fresh_document():
    doc, transcript = author.author_design("a washer", Scripted(DISC, BORE, DONE))
    assert doc is not None and doc.name == "washer" and len(doc.features) == 2
    doc, transcript = author.author_design("a ring", Scripted(
        {"add": {"id": "x", "op": "torus"}}, {"add": {"id": "x", "op": "torus"}},
        {"add": {"id": "x", "op": "torus"}}))
    assert doc is None and "GAVE UP" in transcript[-1]


# ------------------------------------------- the review's findings, 2026-09-11

def _plate_with_a_spec():
    d = Document(name="my-plate")
    d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
    d.spec = {"size": [40, 30, 5], "n_solids": 1, "tol": 0.5}
    d.rebuild()
    return d


BOSS = {"add": {"id": "boss", "op": "disc",
                "params": {"radius": 6, "thickness": 8}}}


def test_the_design_keeps_its_own_spec_when_the_ai_adds_to_it():
    """The spec is the USER's requirement. `done` used to overwrite it:
    {"size": [40,30,5], ...} became {"n_solids": 1} and the chat reported
    success (31 of the 50 live designs pin a size, 22 pin holes)."""
    doc = _plate_with_a_spec()
    mine = dict(doc.spec)
    m = Scripted(BOSS, {"done": True, "spec": {"n_solids": 1}})
    ok, transcript = author.author_steps(doc, "add a boss", m)
    assert ok and doc.spec == mine
    assert "keeps the spec it already recorded" in transcript[-1]
    assert "SPEC IS THE USER'S and is kept as it is" in m.heard[0]


def test_a_refused_done_never_leaves_the_models_spec_behind():
    doc = _plate_with_a_spec()
    mine = dict(doc.spec)
    m = Scripted({"done": True, "spec": {"n_solids": 1, "volume": 999999}})
    author.author_steps(doc, "finish it", m, max_fails=1)
    assert doc.spec == mine


def test_a_spec_the_change_broke_is_reported_not_hidden():
    doc = _plate_with_a_spec()
    m = Scripted(BOSS, {"add": {"id": "join", "op": "fuse",
                                "inputs": ["base", "boss"]}},
                 {"done": True, "spec": {"n_solids": 1}})
    ok, transcript = author.author_steps(doc, "add a boss", m)
    assert ok and doc.spec["size"] == [40, 30, 5]
    assert doc.spec_problems, "the taller part no longer meets the size spec"
    assert "no longer meets it" in transcript[-1]


def test_adding_to_a_design_that_records_no_spec_does_not_write_one():
    """Round two: the guard keyed on "does it HAVE a spec", so the 8 live
    designs that carry none were still open to the model writing one over
    them - a requirement the user never set, that their status bar then
    reports against. A spec is the model's to author only on a design it is
    creating."""
    doc = Document(name="no-spec-design")
    doc.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
    doc.rebuild()
    m = Scripted(BOSS, {"add": {"id": "join", "op": "fuse",
                                "inputs": ["base", "boss"]}},
                 {"done": True, "spec": {"n_solids": 1, "size": [40, 30, 13]}})
    ok, transcript = author.author_steps(doc, "add a boss", m)
    assert ok and doc.spec == {}
    assert "RECORDS NO SPEC" in m.heard[0]
    assert "records no spec" in transcript[-1]


def test_a_brand_new_design_still_gets_the_models_spec():
    doc = Document(name="untitled")
    m = Scripted(DISC, {"done": True, "spec": {"n_solids": 1,
                                               "holes": {"10": 0}}})
    ok, _ = author.author_steps(doc, "a disc", m)
    assert ok and doc.spec["n_solids"] == 1


def test_a_design_with_a_spec_of_its_own_is_told_not_to_send_one():
    doc = _plate_with_a_spec()
    m = Scripted(BOSS, {"done": True})
    ok, _ = author.author_steps(doc, "add a boss", m)
    assert ok, "done without a spec must be accepted when the design has one"


def test_a_step_is_judged_on_what_it_touched_not_on_the_whole_tree():
    """A design with a feature that is ALREADY red: a correct step used to
    come back "UNDONE - it built broken geometry" naming somebody else's
    feature, three in a row, and the AI could not touch the design at all."""
    doc = Document(name="half-broken")
    doc.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
    doc.add("bad", "with_center_hole", {"radius": 500}, inputs=["base"])
    doc.rebuild()
    assert doc.get("bad").status != "ok", "the fixture must start red"
    m = Scripted(BOSS, {"done": True, "spec": {"n_solids": 1}})
    ok, transcript = author.author_steps(doc, "add a boss", m, max_fails=1)
    assert [f.id for f in doc.features] == ["base", "bad", "boss"]
    assert transcript[0].startswith("OK: 'boss'")
    # ...and `done` still judges the WHOLE tree, naming the RIGHT feature
    assert not ok and transcript[1].startswith("REFUSED done: 'bad'")


def test_ignoring_a_feature_that_was_already_red_still_catches_a_new_break():
    """The other half of the same rule: a step may ignore a row that was
    ALREADY red, but it may never walk away from one it broke itself."""
    doc = Document(name="half-broken")
    doc.add("plate", "plate", {"width": 20, "depth": 20, "thickness": 4})
    doc.add("round", "fillet", {"radius": 1, "edges": "all"}, inputs=["plate"])
    doc.add("bad", "with_center_hole", {"radius": 500}, inputs=["round"])
    doc.rebuild()
    assert doc.get("bad").status != "ok" and doc.get("round").status == "ok"
    m = Scripted({"edit": {"feature_id": "round", "param": "radius", "value": 50}})
    ok, transcript = author.author_steps(doc, "fatter fillet", m, max_fails=1)
    assert not ok and doc.get("round").params["radius"] == 1
    assert transcript[0].startswith("UNDONE edit 'round.radius' = 50")
    assert "'round'" in transcript[0] and "it was fine before this step" in transcript[0]


def test_a_parked_rollback_bar_stops_the_job_with_a_sentence():
    """Nothing below the bar is built, so no step could be verified - and
    every step used to be undone as "broken geometry" instead."""
    doc = _plate_with_a_spec()
    doc.add("boss", "disc", {"radius": 6, "thickness": 8})
    doc.rollback = "base"
    doc.rebuild()
    m = Scripted(BOSS)
    ok, transcript = author.author_steps(doc, "add a pin", m)
    assert not ok and doc.rollback == "base"
    assert [f.id for f in doc.features] == ["base", "boss"]
    assert "rollback bar is parked at 'base'" in transcript[0]
    assert "release the bar" in transcript[0]


def test_the_ai_may_not_remove_a_feature_the_user_built():
    doc = _plate_with_a_spec()
    doc.add("boss", "disc", {"radius": 6, "thickness": 8})
    doc.rebuild()
    m = Scripted({"remove": "boss"}, {"done": True})
    ok, transcript = author.author_steps(doc, "add a hole", m)
    assert [f.id for f in doc.features] == ["base", "boss"]
    assert "it was in the design before you started" in transcript[0]


def test_the_ai_may_still_take_back_its_own_step():
    doc = _plate_with_a_spec()
    m = Scripted(BOSS, {"remove": "boss"}, {"done": True})
    ok, transcript = author.author_steps(doc, "never mind", m)
    assert ok and [f.id for f in doc.features] == ["base"]
    assert "removed 'boss'" in transcript[1]


def test_one_step_per_reply_or_the_verification_means_nothing():
    """{"add": ..., "done": true} took the add road, came back ok, and the
    loop then read "done" and FINISHED - no final lint, no spec check. Two
    loose bodies were reported as a verified design."""
    doc = Document(name="untitled")
    m = Scripted({"add": {"id": "a", "op": "plate",
                          "params": {"width": 20, "depth": 20, "thickness": 4}}},
                 {"add": {"id": "b", "op": "disc",
                          "params": {"radius": 5, "thickness": 10}},
                  "done": True})
    ok, transcript = author.author_steps(doc, "two bodies", m, max_fails=1)
    assert not ok and [f.id for f in doc.features] == ["a"]
    assert "one step per reply" in transcript[1]
    assert '"add" and "done"' in transcript[1]


def test_done_false_beside_a_step_is_just_the_step():
    doc = Document(name="untitled")
    m = Scripted({"add": {"id": "a", "op": "plate",
                          "params": {"width": 20, "depth": 20, "thickness": 4}},
                  "done": False}, DONE)
    ok, _ = author.author_steps(doc, "a plate", m)
    assert ok and [f.id for f in doc.features] == ["a"]


def test_a_refused_first_step_does_not_rename_the_design():
    doc = Document(name="untitled")
    m = Scripted({"name": "sports-car",
                  "add": {"id": "a", "op": "torus", "params": {}}})
    author.author_steps(doc, "a car", m, max_fails=1)
    assert doc.name == "untitled"


def test_the_name_survives_a_refused_first_step_and_lands_with_the_next():
    doc = Document(name="untitled")
    m = Scripted({"name": "sports-car",
                  "add": {"id": "a", "op": "torus", "params": {}}},
                 {"add": {"id": "a", "op": "plate",
                          "params": {"width": 20, "depth": 20, "thickness": 4}}},
                 DONE)
    ok, _ = author.author_steps(doc, "a car", m)
    assert ok and doc.name == "sports-car"


def test_a_warning_belongs_to_the_feature_it_names():
    """A bare `f.id in str(w)` is a substring test on the whole sentence, so
    'boss' owned every line about 'boss_cut' — and a one-letter id owned the
    lot. Warnings quote the feature they are about; match that."""
    doc = Document(name="probe")
    doc.add("boss", "plate", {"width": 40, "depth": 30, "thickness": 5})
    doc.rebuild()
    doc.warnings = ["'boss_cut' removed nothing"]         # names someone else
    assert "Note:" not in author._built(doc, doc.get("boss"))
    doc.warnings = ["'boss' and 'pin' are separate bodies"]
    assert "Note:" in author._built(doc, doc.get("boss"))


# ------------------------------------------------------- the chat route -----

@pytest.fixture()
def client(monkeypatch):
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    monkeypatch.setattr(studio, "JOB_THREADS", False)
    return TestClient(studio.app)


def _intent(monkeypatch, action, description="x"):
    monkeypatch.setattr(studio, "chat_intent",
                        lambda *a, **k: {"action": action,
                                         "description": description})


def _tabs(client):
    return sorted(t["id"] for t in client.get("/api/doc").json()["tabs"])


def _model(monkeypatch, *replies):
    m = Scripted(*replies)
    monkeypatch.setattr(studio, "_make_model", lambda *a, **k: m)
    return m


def test_create_builds_in_its_own_tab_and_reports_every_step(client, monkeypatch):
    _intent(monkeypatch, "create", "a washer")
    _model(monkeypatch, DISC, BORE, DONE)
    mine = client.get("/api/doc").json()["active_tab"]
    d = client.post("/api/chat", json={"message": "design a washer"}).json()
    assert d["active_tab"] == mine, "the AI stole the tab I was working in"
    assert d["new_tab"] and d["new_tab"] != mine and d["job"]
    assert "own tab" in d["reply"] and "untouched" in d["reply"]
    j = client.get(f"/api/chat/job/{d['job']}").json()
    assert j["done"] and len(j["log"]) == 3 and j["log"][0].startswith("OK: 'body'")
    assert j["reply"] == d["reply"]
    tab = client.post("/api/tabs/switch", json={"id": d["new_tab"]}).json()
    assert tab["name"] == "washer" and tab["ok"] is True
    assert [f["id"] for f in tab["features"]] == ["body", "bore"]
    assert studio.STATE["docs"][d["new_tab"]]["pending"][-1]["kind"] == "ai"


def test_a_create_that_gives_up_leaves_its_verified_steps_in_its_own_tab(
        client, monkeypatch):
    bad = {"add": {"id": "x", "op": "torus", "params": {}}}
    _intent(monkeypatch, "create", "a ring")
    _model(monkeypatch, DISC, bad, bad, bad)
    d = client.post("/api/chat", json={"message": "design a ring"}).json()
    assert "could not finish" in d["reply"] and "untouched" in d["reply"]
    tab = client.post("/api/tabs/switch", json={"id": d["new_tab"]}).json()
    assert [f["id"] for f in tab["features"]] == ["body"] and tab["ok"] is True


def test_add_extends_the_design_on_screen_as_one_undo_step(client, monkeypatch):
    _intent(monkeypatch, "add", "a 6mm hole through the centre")
    hole = {"add": {"id": "centre_hole", "op": "hole",
                    "params": {"face": "top", "at": [0, 25], "diameter": 6,
                               "through": True}, "inputs": ["bolts"]}}
    _model(monkeypatch, hole, DONE)
    before = client.get("/api/doc").json()
    d = client.post("/api/chat", json={"message": "drill a 6mm hole"}).json()
    assert d["new_tab"] is None and d["active_tab"] == before["active_tab"]
    assert "Added 1 feature" in d["reply"] and "centre_hole" in d["reply"]
    assert [f["id"] for f in d["features"]][-1] == "centre_hole"
    assert len(d["features"]) == len(before["features"]) + 1
    # The flange records a 6-fold-symmetry spec, and a single centre hole
    # breaks it. Adding that hole BY HAND reports exactly this (measured), so
    # the AI path says the same thing instead of deleting the spec to look
    # green — the reply carries the news in words.
    assert d["spec"] == before["spec"] and not d["ok"]
    assert "no longer meets the spec it records" in d["reply"]
    u = client.post("/api/undo").json()
    assert len(u["features"]) == len(before["features"]), "one Undo, all back"


def test_an_add_that_gives_up_leaves_the_design_exactly_as_it_was(
        client, monkeypatch):
    _intent(monkeypatch, "add", "a boss")
    bad = {"add": {"id": "x", "op": "torus", "params": {}}}
    boss = {"add": {"id": "boss", "op": "plate",
                    "params": {"width": 5, "depth": 5, "thickness": 5}}}
    _model(monkeypatch, boss, bad, bad, bad)       # one step lands, then it fails
    before = client.get("/api/doc").json()
    d = client.post("/api/chat", json={"message": "add a boss"}).json()
    assert d["reply"].startswith("I did NOT change")
    assert [f["id"] for f in d["features"]] == [f["id"] for f in before["features"]]
    assert d["can_undo"] == before["can_undo"], "a refused job costs no undo step"
    assert d["ok"] is True
    assert not studio._INFLIGHT, "the job left an in-flight marker behind"


def test_without_an_api_key_the_chat_says_so(client, monkeypatch):
    _intent(monkeypatch, "create", "a washer")
    monkeypatch.setattr(studio, "_make_model", lambda *a, **k: None)
    d = client.post("/api/chat", json={"message": "design a washer"}).json()
    assert "API key" in d["reply"] and "job" not in d


def test_a_running_job_is_the_only_writer_on_its_tab(client, monkeypatch):
    """The busy overlay covers the VIEWPORT only, so the ribbon, the tree and
    the tab strip stay clickable. A parameter edit landing between two AI
    steps pushed a SECOND undo entry, and "one Undo takes it all back" then
    left the AI's first feature standing and silently reverted the user's own
    edit (measured 2026-09-11)."""
    _intent(monkeypatch, "add", "two pins")
    landed = []

    class Meddling:
        """Its second reply is preceded by the user editing the same tab."""
        n = 0

        def generate(self, messages):
            self.n += 1
            if self.n == 1:
                return json.dumps({"add": {"id": "p1", "op": "disc",
                                           "params": {"radius": 3, "thickness": 3}}})
            if self.n == 2:
                r = client.post("/api/feature/params",
                                json={"feature_id": "body",
                                      "params": {"radius": 99}})
                landed.append(r)
                return json.dumps({"add": {"id": "p2", "op": "disc",
                                           "params": {"radius": 4, "thickness": 3}}})
            return json.dumps({"done": True})

    monkeypatch.setattr(studio, "_make_model", lambda *a, **k: Meddling())
    before = client.get("/api/doc").json()
    d = client.post("/api/chat", json={"message": "two pins"}).json()
    assert landed[0].status_code == 400
    assert "still building" in landed[0].json()["error"]
    assert "p1" in d["reply"] and "p2" in d["reply"]
    u = client.post("/api/undo").json()
    assert [f["id"] for f in u["features"]] == [f["id"] for f in before["features"]]
    assert u["can_undo"] == before["can_undo"], "one job, one undo step"
    # ...and the tab is writable again the moment the job is done
    assert client.post("/api/feature/params",
                       json={"feature_id": "body",
                             "params": {"radius": 51}}).status_code == 200


def test_the_tab_a_job_builds_in_cannot_be_closed_under_it(client, monkeypatch):
    """A "create" job builds in a tab that is NOT the active one, so the
    one-writer rule never sees it."""
    _intent(monkeypatch, "create", "a washer")
    monkeypatch.setattr(studio, "JOB_THREADS", True)
    started = threading.Event()
    release = threading.Event()

    class Slow:
        n = 0

        def generate(self, messages):
            self.n += 1
            if self.n == 1:
                started.set()
                release.wait(5)
                return json.dumps(DISC)
            return json.dumps(DONE)

    monkeypatch.setattr(studio, "_make_model", lambda *a, **k: Slow())
    d = client.post("/api/chat", json={"message": "design a washer"}).json()
    assert started.wait(5)
    shut = client.post("/api/tabs/close", json={"id": d["new_tab"]})
    release.set()
    assert shut.status_code == 400 and "still building" in shut.json()["error"]
    assert d["new_tab"] in studio.STATE["docs"]
    for _ in range(200):
        if client.get(f"/api/chat/job/{d['job']}").json()["done"]:
            break
        time.sleep(0.05)
    assert client.post("/api/tabs/close", json={"id": d["new_tab"]}).status_code == 200


def test_a_job_whose_thread_dies_still_says_done(client, monkeypatch):
    """GET /api/chat/job answered done=False for ever, and the browser's
    follow loop holds the busy overlay while it polls: one unhandled
    exception locked the viewport until a reload."""
    _intent(monkeypatch, "add", "a pin")
    _model(monkeypatch, {"add": {"id": "pin", "op": "disc",
                                 "params": {"radius": 3, "thickness": 3}}},
           {"done": True})

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(studio, "_pending", boom)
    d = client.post("/api/chat", json={"message": "add a pin"}).json()
    j = client.get(f"/api/chat/job/{d['job']}").json()
    assert j["done"] and "stopped" in j["reply"] and "boom" in j["reply"]


def test_a_finished_job_leaves_its_tab_built_not_grey(client, monkeypatch):
    """`ok` reads None (a grey "not loaded yet" dot) while rebuild_ms is
    None, and switching to the tab then rebuilds the whole tree again."""
    _intent(monkeypatch, "create", "a washer")
    _model(monkeypatch, DISC, BORE, DONE)
    d = client.post("/api/chat", json={"message": "design a washer"}).json()
    tab = next(t for t in d["tabs"] if t["id"] == d["new_tab"])
    assert tab["ok"] is True, "the AI's own tab reports what it verified"
    assert studio.STATE["docs"][d["new_tab"]]["rebuild_ms"] is not None


def test_a_job_that_gives_up_keeps_the_tab_document_and_its_rollback_bar(
        client, monkeypatch):
    """The give-up path replaced e["doc"] wholesale; to_data does not carry
    the rollback bar, so the user's parked bar vanished (measured)."""
    e = studio.STATE["docs"][studio.STATE["active"]]
    was = e["doc"]
    was.rollback = "body"
    studio._rebuild_and_mesh()
    _intent(monkeypatch, "add", "a boss")
    bad = {"add": {"id": "x", "op": "torus", "params": {}}}
    _model(monkeypatch, bad, bad, bad)
    d = client.post("/api/chat", json={"message": "add a boss"}).json()
    assert d["reply"].startswith("I did NOT change")
    assert e["doc"] is was, "the tab must keep its document object"
    assert d["rollback"] == "body"
    assert "rollback bar is parked" in d["reply"]


def test_the_one_writer_guard_fails_open_instead_of_with_a_bare_500(
        client, monkeypatch):
    """Round two: the guard is registered after _never_die, so Starlette puts
    it OUTSIDE that barrier — anything it raised was a bare 500 in plain
    text, which the browser reads as "the server restarted during this step".
    _job_on walks a LIVE dict that _start_job prunes from a request thread."""
    class Exploding(dict):
        def values(self):
            raise RuntimeError("dictionary changed size during iteration")

    monkeypatch.setattr(studio, "JOBS", Exploding())
    r = client.post("/api/feature/params",
                    json={"feature_id": "body", "params": {"radius": 51}})
    assert r.status_code == 200, "a broken guard must not break the request"
    assert r.json()["features"], "and the answer is still a readable document"


def test_a_tool_plan_is_refused_while_the_ai_is_in_the_kernel(client, monkeypatch):
    """Round three: /api/tool/plan was on the open list as "read-only", but
    toolplan.plan reads doc._parts and rebuild() CLEARS that at the start of
    every step - so a plan landing between two steps answered a confident
    sentence about geometry that was not there, from inside OCCT, beside the
    job's own kernel call."""
    monkeypatch.setitem(studio.JOBS, "jX",
                        {"id": "jX", "done": False, "tab": studio.STATE["active"]})
    r = client.post("/api/tool/plan", json={"tool": "fillet",
                                            "feature_id": "body"})
    assert r.status_code == 400 and "still building" in r.json()["error"]
    assert not r.json().get("ok"), "the tool must read this as a plan failure"
    # switching away is still how the user gets back to work
    assert client.post("/api/tabs/switch",
                       json={"id": studio.STATE["active"]}).status_code == 200


def test_a_create_that_built_nothing_leaves_no_empty_tab(client, monkeypatch):
    _intent(monkeypatch, "create", "a ring")
    bad = {"add": {"id": "x", "op": "torus", "params": {}}}
    _model(monkeypatch, bad, bad, bad)
    before = _tabs(client)
    d = client.post("/api/chat", json={"message": "design a ring"}).json()
    assert "closed the empty tab" in d["reply"] and "untouched" in d["reply"]
    assert _tabs(client) == before
    assert "designing" not in json.dumps(d["tabs"])


def test_a_long_job_gives_the_tab_back_instead_of_holding_it(client, monkeypatch):
    """Round five: an "add" job makes its tab READ-ONLY while it runs, so a
    model that is merely slow locks the user out of their own design with no
    Cancel to press. Steps alone do not bound that - a clock does."""
    monkeypatch.setattr(author, "MAX_SECONDS", 0)
    _intent(monkeypatch, "add", "a pin")
    _model(monkeypatch, {"add": {"id": "pin", "op": "disc",
                                 "params": {"radius": 3, "thickness": 3}}})
    before = client.get("/api/doc").json()
    d = client.post("/api/chat", json={"message": "add a pin"}).json()
    assert "0 seconds without" in json.dumps(d["reply"]) or \
           d["reply"].startswith("I did NOT change")
    assert [f["id"] for f in d["features"]] == [f["id"] for f in before["features"]]
    # ...and the tab is the user's again
    assert client.post("/api/feature/params",
                       json={"feature_id": "body",
                             "params": {"radius": 51}}).status_code == 200


def test_a_tab_closed_before_the_job_started_is_a_sentence_not_a_keyerror(
        client, monkeypatch):
    _intent(monkeypatch, "create", "a washer")
    _model(monkeypatch, DISC, DONE)
    real = studio._start_job

    def start(kind, description, tid, model, before=None):
        del studio.STATE["docs"][tid]          # closed in the blink before it ran
        return real(kind, description, tid, model, before)

    monkeypatch.setattr(studio, "_start_job", start)
    d = client.post("/api/chat", json={"message": "design a washer"}).json()
    j = client.get(f"/api/chat/job/{d['job']}").json()
    assert j["done"] and "tab was closed before I could start" in j["reply"]


def test_the_tab_a_watched_create_left_empty_is_not_claimed_to_be_closed(
        client, monkeypatch):
    """Round four: the tab stays if the user has SWITCHED to it - closing the
    tab somebody is looking at is not ours to do - but the sentence said "I
    have closed the empty tab" either way, with the tab still on the strip."""
    _intent(monkeypatch, "create", "a ring")
    bad = {"add": {"id": "x", "op": "torus", "params": {}}}
    _model(monkeypatch, bad, bad, bad)
    real = studio._new_tab

    def watched(doc, source=None, activate=True):
        tid = real(doc, source, activate)
        studio.STATE["active"] = tid          # the user clicks it to watch
        return tid

    monkeypatch.setattr(studio, "_new_tab", watched)
    d = client.post("/api/chat", json={"message": "design a ring"}).json()
    assert d["new_tab"] in studio.STATE["docs"], "a watched tab is not closed"
    assert "closed the empty tab" not in d["reply"]
    assert "close it when you like" in d["reply"]


def test_the_ai_cannot_open_more_tabs_than_the_new_button_can(client, monkeypatch):
    _intent(monkeypatch, "create", "a ring")
    while len(studio.STATE["docs"]) < studio.MAX_TABS:
        studio._new_tab(Document(name=f"t{len(studio.STATE['docs'])}"))
    _model(monkeypatch, DISC, DONE)
    d = client.post("/api/chat", json={"message": "design a ring"}).json()
    assert f"already {studio.MAX_TABS} tabs open" in d["reply"]
    assert d.get("job") is None
    assert len(studio.STATE["docs"]) == studio.MAX_TABS


def test_a_threaded_job_is_followed_through_its_status_route(client, monkeypatch):
    monkeypatch.setattr(studio, "JOB_THREADS", True)
    _intent(monkeypatch, "create", "a washer")
    _model(monkeypatch, DISC, BORE, DONE)
    d = client.post("/api/chat", json={"message": "design a washer"}).json()
    assert d["job"]
    for _ in range(200):
        j = client.get(f"/api/chat/job/{d['job']}").json()
        if j["done"]:
            break
        time.sleep(0.05)
    assert j["done"] and len(j["log"]) == 3 and "Designed" in j["reply"]
    assert client.get("/api/chat/job/nope").status_code == 404
