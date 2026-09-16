"""Studio HTTP API (via FastAPI TestClient — no server process) + MCP tools
+ meanline design math."""
import pytest
from fastapi.testclient import TestClient

import studio
import mcp_server
import meanline


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def test_doc_endpoint(client):
    d = client.get("/api/doc").json()
    assert d["ok"] and len(d["features"]) == 3
    assert "suppressed" in d["features"][0]


def test_edit_and_undo(client):
    d = client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": 9}).json()
    assert d["features"][1]["params"]["radius"] == 9 and d["can_undo"]
    d = client.post("/api/undo").json()
    assert d["features"][1]["params"]["radius"] == 15


def test_spec_edit_flow(client):
    d = client.post("/api/spec", json={"spec": {
        "n_solids": 1, "symmetry": 8, "holes": {"4": 8}, "tol": 0.5}}).json()
    assert not d["ok"]                                     # geometry is 6-bolt
    d = client.post("/api/edit", json={"feature_id": "bolts",
                                       "param": "count", "value": 8}).json()
    assert d["ok"]


def test_rollback_endpoint(client):
    d = client.post("/api/rollback", json={"feature_id": "body"}).json()
    assert d["rollback"] == "body"
    assert d["features"][1]["status"] == "stale"
    d = client.post("/api/rollback", json={"feature_id": None}).json()
    assert d["ok"]


def test_feature_add_remove_suppress(client):
    d = client.post("/api/feature/add", json={
        "id": "rim", "op": "tube",
        "params": {"outer_radius": 55, "inner_radius": 50, "height": 10},
        "inputs": []}).json()
    assert d["features"][-1]["id"] == "rim"
    d = client.post("/api/feature/suppress",
                    json={"feature_id": "rim", "suppressed": True}).json()
    assert d["features"][-1]["suppressed"]
    d = client.post("/api/feature/remove", json={"feature_id": "rim"}).json()
    assert all(f["id"] != "rim" for f in d["features"])


def test_feature_rename_endpoint(client):
    d = client.post("/api/feature/rename",
                    json={"feature_id": "bore", "name": "center_hole"}).json()
    assert "error" not in d
    ids = [f["id"] for f in d["features"]]
    assert "center_hole" in ids and "bore" not in ids
    bolts = next(f for f in d["features"] if f["id"] == "bolts")
    assert bolts["inputs"] == ["center_hole"]     # references rewritten
    # geometry untouched: statuses survive without a rebuild
    assert all(f["status"] == "ok" for f in d["features"])
    # bad names are refused and undoable state is not corrupted
    d = client.post("/api/feature/rename",
                    json={"feature_id": "center_hole", "name": "has space"}).json()
    assert "error" in d
    d = client.post("/api/undo", json={}).json()
    assert any(f["id"] == "bore" for f in d["features"])  # rename undone


def test_save_open_roundtrip(client):
    client.post("/api/save")
    lst = client.get("/api/designs").json()
    assert any(x["name"] == "flange-100" for x in lst)
    d = client.post("/api/open/flange-100").json()
    assert d["ok"]


def test_bad_edit_reports_error_and_no_history_leak(client):
    before = len(studio._entry()["history"])
    d = client.post("/api/edit", json={"feature_id": "nope",
                                       "param": "radius", "value": 1}).json()
    assert "error" in d
    assert len(studio._entry()["history"]) == before


# ---------------------------------------------------------- document tabs ----

def test_new_design_opens_a_second_tab(client):
    d = client.post("/api/new", json={"name": "part-2"}).json()
    assert len(d["tabs"]) == 2
    assert d["name"] == "part-2"
    names = {t["name"] for t in d["tabs"]}
    assert "flange-100" in names          # the old design is still open


def test_switch_tab_restores_old_design_without_rebuild(client):
    first = client.get("/api/doc").json()["active_tab"]
    client.post("/api/new", json={"name": "part-2"})
    d = client.post("/api/tabs/switch", json={"id": first}).json()
    assert d["name"] == "flange-100"
    assert d["ok"]                        # still built + verified
    assert d["features"][0]["status"] == "ok"


def test_library_open_gives_a_new_tab_only_for_a_DIFFERENT_design(client):
    """Opening from the library must not replace the design you are working on
    — but it must not clone a tab either. Before the tab-reuse change (P0 of
    VERSION-TREE-PLAN.md) every open made a new tab unconditionally, so ten
    iterations of one design left ten identical tabs.

    Saving binds the tab to the file it wrote, so re-opening that name comes
    back HERE. tests/test_tab_reuse.py covers the rest of the matrix."""
    client.post("/api/save")                      # this tab is now flange-100
    d = client.post("/api/open/hex-nut-M16").json()
    assert len(d["tabs"]) == 2            # a DIFFERENT design -> new tab
    assert d["tab_reused"] is False
    d = client.post("/api/open/flange-100").json()
    assert len(d["tabs"]) == 2            # back to the first tab, not a third
    assert d["tab_reused"] is True and d["name"] == "flange-100"


def test_close_tab_activates_neighbor_and_never_zero(client):
    first = client.get("/api/doc").json()["active_tab"]
    client.post("/api/new", json={"name": "part-2"})
    d = client.post("/api/tabs/close",
                    json={"id": client.get("/api/doc").json()["active_tab"]}).json()
    assert d["active_tab"] == first and len(d["tabs"]) == 1
    d = client.post("/api/tabs/close", json={"id": first}).json()
    assert len(d["tabs"]) == 1            # a blank tab was created
    assert d["name"] == "untitled"


def test_undo_history_is_per_tab(client):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 9})
    client.post("/api/new", json={"name": "part-2"})
    d = client.post("/api/undo").json()   # new tab has NOTHING to undo
    assert "error" in d
    first = [t["id"] for t in d["tabs"] if t["name"] == "flange-100"][0]
    client.post("/api/tabs/switch", json={"id": first})
    d = client.post("/api/undo").json()   # old tab's undo still works
    assert d["features"][1]["params"]["radius"] == 15


def test_ops_catalog(client):
    ops = client.get("/api/ops").json()
    assert {o["op"] for o in ops} >= {"disc", "ball", "cone", "fuse", "cut"}


# -------------------------------------------------------------- MCP tools ----

def test_mcp_build_design_and_verify(tmp_path, monkeypatch):
    # `designs/` is the user's tracked library and `_notify_studio` POSTs to
    # the live server on port 8123 — neither belongs in a code test. This one
    # already took `tmp_path` and never used it, so every run wrote
    # designs/t-washer.tcad.json + .step and rang the real doorbell (which
    # opens the design in the running app and pushes a version into its
    # .history/). Found by the section 13 review, 2026-09-16.
    monkeypatch.setattr(mcp_server, "OUT", tmp_path)
    monkeypatch.setattr(mcp_server, "_MINE", set(), raising=False)
    monkeypatch.setattr(mcp_server, "_notify_studio", lambda stem: None)
    tree = {"name": "t-washer", "features": [
        {"id": "b", "op": "disc", "params": {"radius": 20, "thickness": 4}},
        {"id": "h", "op": "with_center_hole", "params": {"radius": 10},
         "inputs": ["b"]}],
        "spec": {"n_solids": 1}}
    rep = mcp_server.build_design(tree)
    assert rep["verified"] and rep["step_path"].endswith(".step")
    v = mcp_server.verify_step(rep["step_path"], {"n_solids": 1})
    assert v["matches_spec"]


def test_mcp_rejects_unknown_op():
    rep = mcp_server.build_design(
        {"name": "x", "features": [{"id": "a", "op": "sphere", "params": {}}]})
    assert not rep["verified"] and "unknown op" in rep["rejected_before_build"]


# ---------------------------------------------------------------- meanline ----

def test_meanline_reference_duty():
    d = meanline.design(meanline.Duty(mass_flow=0.5, pressure_ratio=3.0,
                                      rpm=45000))
    assert 85 < d.tip_radius < 105          # ~93.8mm
    assert 400 < d.tip_speed < 480          # ~442 m/s
    assert 10 <= d.blade_count <= 16        # ~13
    assert 0.8 < d.slip_factor < 0.9
    assert d.exit_width >= 1.0
    spec = meanline.to_spec(d)
    assert spec.symmetry == d.blade_count
    assert spec.tip_radius == d.tip_radius


# ------------------------------------------ refusals are refusals (P0) --------

def test_a_refused_edit_is_http_400_with_the_unchanged_document(client):
    """A refusal used to come back as 200 with `ok: True` beside the error, so
    a script or the MCP reading the status saw success. `ok` is the BUILD's
    health and stays true; the status code says the request failed."""
    r = client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "rdius", "value": 1})
    assert r.status_code == 400
    d = r.json()
    assert "rdius" in d["error"] and d["ok"] is True
    assert d["features"][1]["params"] == {"radius": 15}


def test_a_parameter_the_op_knows_can_be_set_before_it_is_stored(client):
    """The original report: `through` on an extrude stored as {amount} was
    turned down as "no such parameter" (or, on the multi-param route, stored
    unchecked and failed the build)."""
    # a sketch ON the body's top face, not an absolute-offset one: the flange
    # is already a body, and CLAUDE.md bans an absolute-offset sketch once one
    # exists (author.lint_tree refuses the same shape from the AI)
    client.post("/api/feature/add", json={"id": "s", "op": "sketch_on_face",
                                          "params": {"face": "top", "offset": 0,
                                                     "entities": [{"kind": "circle", "r": 5}]},
                                          "inputs": ["bolts"]})
    client.post("/api/feature/add", json={"id": "post", "op": "extrude",
                                          "params": {"amount": 8}, "inputs": ["s"]})
    r = client.post("/api/edit", json={"feature_id": "post", "param": "through",
                                       "value": True})
    assert r.status_code == 200 and "error" not in r.json()
    post = next(f for f in r.json()["features"] if f["id"] == "post")
    assert post["params"] == {"amount": 8, "through": True}
    assert post["status"] == "ok"


def test_the_multi_param_route_refuses_unknown_keys_before_writing_any(client):
    r = client.post("/api/feature/params", json={
        "feature_id": "bore", "params": {"radius": 12, "bogus": 5}})
    assert r.status_code == 400 and "bogus" in r.json()["error"]
    d = client.get("/api/doc").json()
    assert d["features"][1]["params"] == {"radius": 15}     # radius NOT written
    assert d["features"][1]["status"] == "ok"


def test_a_refusal_does_not_cost_the_user_their_redo(client):
    """_snapshot() ends the redo line. Every refusal popped the history entry
    it added but never put the redo back, so typing a parameter name wrong
    after an undo killed Ctrl+Y -- and the refusal's own body said so
    (can_redo flipped to false while nothing had changed)."""
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 9})
    client.post("/api/undo")
    assert client.get("/api/doc").json()["can_redo"]
    hands = studio._entry()["hand_edits"]

    r = client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "rdius", "value": 1})
    assert r.status_code == 400
    assert r.json()["can_redo"], "the refusal reported the redo line as gone"
    assert studio._entry()["hand_edits"] == hands, "a refusal is not a hand edit"
    # and it still works
    assert client.post("/api/redo").json()["features"][1]["params"]["radius"] == 9


def test_the_multi_param_route_keeps_the_redo_line_too(client):
    client.post("/api/feature/params",
                json={"feature_id": "bore", "params": {"radius": 9}})
    client.post("/api/undo")
    assert client.get("/api/doc").json()["can_redo"]
    r = client.post("/api/feature/params",
                    json={"feature_id": "bore", "params": {"bogus": 1}})
    assert r.status_code == 400 and r.json()["can_redo"]
    assert client.post("/api/redo").json()["features"][1]["params"]["radius"] == 9


def test_adding_a_feature_refuses_a_param_the_op_cannot_take(client):
    """The guard used to sit only on the EDIT door: /api/feature/add stored
    any key unchecked and the tree grew a node that failed to build with a
    TypeError. That door is the AI's."""
    r = client.post("/api/feature/add", json={
        "id": "d", "op": "disc",
        "params": {"radius": 10, "thickness": 3, "diameter": 20}, "inputs": []})
    assert r.status_code == 400
    assert "diameter" in r.json()["error"]
    assert not any(f["id"] == "d" for f in r.json()["features"])


def test_every_unknown_key_is_named_at_once(client):
    r = client.post("/api/feature/params", json={
        "feature_id": "bore", "params": {"rdius": 1, "thikness": 2}})
    assert r.status_code == 400
    assert "rdius" in r.json()["error"] and "thikness" in r.json()["error"]


def test_loading_a_design_never_refuses_an_unknown_param():
    """strict is OFF for from_data on purpose: a file written by another build
    must OPEN (and say which node is unhappy), never fail to load."""
    from document import Document
    doc = Document.from_data({"name": "older", "features": [
        {"id": "d", "op": "disc",
         "params": {"radius": 10, "thickness": 3, "legacy_key": 1}, "inputs": []}]})
    assert doc.get("d").params["legacy_key"] == 1


def test_result_volume_comes_from_the_document_not_the_last_row(client):
    """The status bar used to pick "the last non-suppressed feature" in JS.
    On designs/spiderman-logo that is a SKETCH, so the volume readout went
    blank while the part had one; where the last row is a separate tool body
    it reported that body's volume as the design's (section 2 review,
    2026-09-10, launch rule R1: never re-derive a backend fact in JS)."""
    d = client.get("/api/doc").json()
    assert d["result_volume"] and d["result_volume"] > 0
    solid_volume = d["result_volume"]

    d = client.post("/api/feature/add", json={
        "id": "sketch9", "op": "sketch",
        "params": {"entities": [{"kind": "circle", "r": 3}]},
        "inputs": []}).json()
    assert d["features"][-1]["op"] == "sketch"
    assert d["features"][-1]["volume"] is None, "the last row has no volume"
    assert d["result_volume"] == solid_volume, \
        "a trailing sketch emptied the status bar's volume"
