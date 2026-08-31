"""STEP export exports the FINISHED DESIGN — never the transient build state.

Locks in the 2026-08-31 bug: the sketch/extrude editors park the rollback
bar for edit isolation, and /api/export while it was parked wrote whatever
intermediate body was last built (a bare cavity-cutter slab reached the
user's CAM tool instead of their edited part). Also locks the canonical
location (designs/, next to the .tcad.json the MCP builds write) and the
measured-readback contract of the response.
"""
import os

import pytest
from fastapi.testclient import TestClient

import studio


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    yield TestClient(studio.app)
    step = studio.DESIGNS / "flange-100.step"   # keep the library clean
    if step.exists():
        os.remove(step)


def test_export_lands_in_designs_and_is_measured(client):
    d = client.post("/api/export").json()
    assert "error" not in d
    assert d["path"] == str(studio.DESIGNS / "flange-100.step")
    assert os.path.exists(d["path"])
    # the response is measured FROM THE FILE, not assumed from the doc
    assert d["n_solids"] == 1
    assert d["volume"] > 0
    assert d["size"] == pytest.approx([100, 100, 10], abs=0.1)


def test_export_ignores_parked_rollback_bar(client):
    full = client.post("/api/export").json()          # ground truth, bar off
    d = client.post("/api/rollback", json={"feature_id": "body"}).json()
    assert d["rollback"] == "body"                    # bar parked mid-tree
    parked = client.post("/api/export").json()
    # the export contains the WHOLE design, not the body-only build state
    assert "error" not in parked
    assert parked["volume"] == pytest.approx(full["volume"], rel=1e-6)
    # ...and the bar is still parked afterwards (editors depend on it)
    assert client.get("/api/doc").json()["rollback"] == "body"


def test_export_refuses_failed_tail_by_name(client):
    d = client.post("/api/feature/add", json={
        "id": "bad_fillet", "op": "fillet",
        "params": {"radius": 100000, "edges": "all"},
        "inputs": ["bolts"]}).json()
    assert d["features"][-1]["status"] == "failed"    # precondition
    d = client.post("/api/export").json()
    assert "error" in d
    assert "bad_fillet" in d["error"]
    assert "cannot export" in d["error"]
