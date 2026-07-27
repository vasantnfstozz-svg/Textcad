"""Studio HTTP API (via FastAPI TestClient — no server process) + MCP tools
+ meanline design math."""
import pytest
from fastapi.testclient import TestClient

import studio
import mcp_server
import meanline


@pytest.fixture()
def client():
    studio.STATE["doc"] = studio.sample_flange()
    studio.STATE["history"] = []
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


def test_save_open_roundtrip(client):
    client.post("/api/save")
    lst = client.get("/api/designs").json()
    assert any(x["name"] == "flange-100" for x in lst)
    d = client.post("/api/open/flange-100").json()
    assert d["ok"]


def test_bad_edit_reports_error_and_no_history_leak(client):
    before = len(studio.STATE["history"])
    d = client.post("/api/edit", json={"feature_id": "nope",
                                       "param": "radius", "value": 1}).json()
    assert "error" in d
    assert len(studio.STATE["history"]) == before


def test_ops_catalog(client):
    ops = client.get("/api/ops").json()
    assert {o["op"] for o in ops} >= {"disc", "ball", "cone", "fuse", "cut"}


# -------------------------------------------------------------- MCP tools ----

def test_mcp_build_design_and_verify(tmp_path):
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
