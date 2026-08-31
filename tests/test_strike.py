"""Strike-out: the tree's ✕ is a SOFT delete (user mandate 2026-08-31 —
"instead of deleting the operation, just strike out that operation, also
delete it in the design; if I want it back I simply press undo on that
struck-out feature").

The geometry is removed exactly as delete would remove it (same plan, and
rebuild's suppress pass-through equals the plan's rewiring), but the rows
stay — struck out — and /api/feature/strike {restore:true} puts everything
back, including struck upstream features a restored node depends on."""
import pytest
from fastapi.testclient import TestClient

import studio


@pytest.fixture()
def client():
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    return TestClient(studio.app)


def _chain(client):
    """plate -> sketch on its top -> extrude boss -> fuse. The bread-and-
    butter AI-authored shape (sketch -> tool -> boolean)."""
    client.post("/api/new", json={"name": "strike-me"})
    client.post("/api/feature/add", json={
        "id": "b", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 10}, "inputs": []})
    client.post("/api/feature/add", json={
        "id": "sk", "op": "sketch_on_face",
        "params": {"face": "top",
                   "entities": [{"kind": "circle", "mode": "add",
                                 "x": 0, "y": 0, "r": 8}]},
        "inputs": ["b"]})
    client.post("/api/feature/add", json={
        "id": "boss", "op": "extrude", "params": {"amount": 5},
        "inputs": ["sk"]})
    r = client.post("/api/feature/add", json={
        "id": "join", "op": "fuse", "params": {}, "inputs": ["b", "boss"]})
    feats = {f["id"]: f for f in r.json()["features"]}
    assert feats["join"]["status"] == "ok"
    return feats


def _feats(client):
    return {f["id"]: f for f in client.get("/api/doc").json()["features"]}


def test_strike_removes_geometry_but_keeps_the_rows(client):
    base_vol = 60 * 40 * 10
    joined = _chain(client)["join"]["volume"]
    assert joined > base_vol

    r = client.post("/api/feature/strike", json={"feature_id": "sk"}).json()
    assert "error" not in r or not r.get("error")
    # the whole dependent chain is struck WITH it (extrude can't build
    # without its sketch; the fuse would fuse the plate with itself)
    assert set(r["strike_plan"]["deleted"]) == {"sk", "boss", "join"}
    feats = _feats(client)
    assert len(feats) == 4                          # every row still there
    assert all(feats[i]["suppressed"] for i in ("sk", "boss", "join"))
    assert not feats["b"]["suppressed"]
    # geometry: the boss is gone — the displayed result is the bare plate
    # (suppressed nodes pass their first input through)
    assert feats["join"]["volume"] is None
    assert feats["b"]["volume"] == pytest.approx(base_vol, rel=1e-6)


def test_restore_brings_the_geometry_back(client):
    joined = _chain(client)["join"]["volume"]
    client.post("/api/feature/strike", json={"feature_id": "sk"})
    r = client.post("/api/feature/strike",
                    json={"feature_id": "sk", "restore": True}).json()
    assert set(r["strike_plan"]["restored"]) == {"sk", "boss", "join"}
    feats = _feats(client)
    assert not any(f["suppressed"] for f in feats.values())
    assert feats["join"]["status"] == "ok"
    assert feats["join"]["volume"] == pytest.approx(joined, rel=1e-6)


def test_restoring_a_dependent_restores_its_struck_sketch_too(client):
    """Restoring the extrude while its sketch is still struck must NOT bring
    it back broken — the sketch it depends on comes back with it."""
    _chain(client)
    client.post("/api/feature/strike", json={"feature_id": "sk"})
    r = client.post("/api/feature/strike",
                    json={"feature_id": "boss", "restore": True}).json()
    assert "sk" in r["strike_plan"]["restored"]
    feats = _feats(client)
    assert not any(f["suppressed"] for f in feats.values())
    assert feats["boss"]["status"] == "ok" and feats["join"]["status"] == "ok"


def test_strike_is_one_undo_step(client):
    _chain(client)
    client.post("/api/feature/strike", json={"feature_id": "sk"})
    assert _feats(client)["sk"]["suppressed"]
    client.post("/api/undo", json={})
    assert not _feats(client)["sk"]["suppressed"]


def test_struck_feature_can_be_deleted_for_good(client):
    _chain(client)
    client.post("/api/feature/strike", json={"feature_id": "sk"})
    r = client.post("/api/feature/remove", json={"feature_id": "sk"}).json()
    assert set(r["remove_plan"]["deleted"]) == {"sk", "boss", "join"}
    assert set(_feats(client)) == {"b"}


def test_strike_errors_speak(client):
    _chain(client)
    r = client.post("/api/feature/strike", json={"feature_id": "nope"}).json()
    assert "nope" in r["error"]
    r = client.post("/api/feature/strike",
                    json={"feature_id": "b", "restore": True}).json()
    assert "not struck out" in r["error"]
    client.post("/api/feature/strike", json={"feature_id": "sk"})
    r = client.post("/api/feature/strike", json={"feature_id": "sk"}).json()
    assert "already struck out" in r["error"]
