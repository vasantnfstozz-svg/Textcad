"""P5 — the AI uses the tools (LAUNCH-PLAN.md §5 step B).

The model adds ONE feature per reply through `author.author_steps`; every
step goes through the same strict add + lint + rebuild the toolbar's Add
Feature uses and is judged on its own. These tests script the model and
check what reaches the tree, what the model is told, and what the chat route
does with a job — no API key, no browser."""
import json
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
    assert [f["id"] for f in d["features"]][-1] == "centre_hole" and d["ok"]
    assert len(d["features"]) == len(before["features"]) + 1
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
