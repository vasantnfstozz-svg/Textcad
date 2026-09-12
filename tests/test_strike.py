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


def _two_pockets(client):
    """plate, then two pockets cut into it (sketch -> tool prism -> cut).
    designs/esp32-remote in miniature: the first pocket is the "logo" the user
    switches off, the second is an ordinary feature further down the chain."""
    client.post("/api/new", json={"name": "two-pockets"})
    client.post("/api/feature/add", json={
        "id": "base", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 10}, "inputs": []})
    for n, (x, r) in enumerate((( -15, 6), (15, 4)), start=1):
        client.post("/api/feature/add", json={
            "id": f"sk{n}", "op": "sketch",
            "params": {"plane": "XY", "offset": 0,
                       "entities": [{"kind": "circle", "mode": "add",
                                     "x": x, "y": 0, "r": r}]}, "inputs": []})
        client.post("/api/feature/add", json={
            "id": f"t{n}", "op": "extrude", "params": {"amount": 20},
            "inputs": [f"sk{n}"]})
        stock = "base" if n == 1 else f"cut{n - 1}"
        rr = client.post("/api/feature/add", json={
            "id": f"cut{n}", "op": "cut", "params": {},
            "inputs": [stock, f"t{n}"]}).json()
    feats = {f["id"]: f for f in rr["features"]}
    assert feats["cut2"]["status"] == "ok"
    return feats


def test_restore_leaves_a_feature_the_user_struck_ON_PURPOSE_alone(client):
    """P5b review, 2026-09-12 — found by tests/journeys.py on esp32-remote.

    unstrike() walked UPSTREAM and un-struck every struck ancestor it met, so
    in a design where the user has a feature switched off (the logo in
    designs/esp32-remote: six struck rows), striking and restoring ANY feature
    downstream of it turned it back on — 107484.782 mm3 became 107256.922, the
    logo milled back in, with nothing but a list of ids in a chat line to say
    so. The un-strike was never needed: rebuild resolves a suppressed node to
    its first input's part, so the chain builds straight through it."""
    _two_pockets(client)
    client.post("/api/feature/strike", json={"feature_id": "cut1"})   # logo off
    with_logo_off = _feats(client)["cut2"]["volume"]
    assert set(k for k, f in _feats(client).items() if f["suppressed"]) == {
        "cut1", "t1", "sk1"}

    client.post("/api/feature/strike", json={"feature_id": "cut2"})
    r = client.post("/api/feature/strike",
                    json={"feature_id": "cut2", "restore": True}).json()

    feats = _feats(client)
    assert feats["cut1"]["suppressed"], "the feature the user switched off came back"
    assert {k for k, f in feats.items() if f["suppressed"]} == {"cut1", "t1", "sk1"}
    assert set(r["strike_plan"]["restored"]) == {"cut2", "t2", "sk2"}
    assert feats["cut2"]["status"] == "ok"
    assert feats["cut2"]["volume"] == pytest.approx(with_logo_off, rel=1e-9)


def test_restore_leaves_a_DEPENDENT_struck_on_purpose_alone(client):
    """The same defect through the other door (P5b review): the restore put
    back the delete PLAN, and a dependent the user had struck earlier was in
    that plan too. A restore puts back what its own ✕ took away."""
    client.post("/api/new", json={"name": "door-two"})
    client.post("/api/feature/add", json={
        "id": "base", "op": "plate",
        "params": {"width": 40, "depth": 30, "thickness": 6}, "inputs": []})
    client.post("/api/feature/add", json={
        "id": "round", "op": "fillet", "params": {"radius": 2, "edges": "all"},
        "inputs": ["base"]})
    client.post("/api/feature/strike", json={"feature_id": "round"})   # rounding off
    client.post("/api/feature/strike", json={"feature_id": "base"})
    assert {k for k, f in _feats(client).items() if f["suppressed"]} == {"base", "round"}

    r = client.post("/api/feature/strike",
                    json={"feature_id": "base", "restore": True}).json()
    feats = _feats(client)
    assert feats["round"]["suppressed"], "the rounding the user turned off came back"
    assert not feats["base"]["suppressed"]
    assert r["strike_plan"]["restored"] == ["base"]


def test_a_rename_between_the_strike_and_the_restore_still_restores(client):
    """The renamed row is INSIDE the record, not the row being restored. Two
    mechanisms would each have to fail for this to break (the rename rewrites
    the record, and the upstream walk pulls a tool prism back anyway because a
    suppressed extrude hands a SKETCH down); measured 2026-09-12, the walk
    alone is enough. Locked so that a later change to either one is caught."""
    _two_pockets(client)
    client.post("/api/feature/strike", json={"feature_id": "cut2"})
    client.post("/api/feature/rename", json={"feature_id": "t2", "name": "prism2"})
    r = client.post("/api/feature/strike",
                    json={"feature_id": "cut2", "restore": True}).json()
    assert not r.get("error"), r.get("error")
    feats = _feats(client)
    assert not feats["prism2"]["suppressed"], "the renamed tool prism stayed struck"
    assert not any(f["suppressed"] for f in feats.values()), {
        k: f["suppressed"] for k, f in feats.items()}
    assert feats["cut2"]["status"] == "ok"


def test_a_rename_of_the_struck_row_itself_still_restores_only_its_own_set(client):
    """And here the renamed row is the KEY: without the rename the record is
    lost, the restore falls back to the delete plan, and the rounding the user
    turned off comes back with it."""
    client.post("/api/new", json={"name": "rename-key"})
    client.post("/api/feature/add", json={
        "id": "base", "op": "plate",
        "params": {"width": 40, "depth": 30, "thickness": 6}, "inputs": []})
    client.post("/api/feature/add", json={
        "id": "round", "op": "fillet", "params": {"radius": 2, "edges": "all"},
        "inputs": ["base"]})
    client.post("/api/feature/strike", json={"feature_id": "round"})
    client.post("/api/feature/strike", json={"feature_id": "base"})
    client.post("/api/feature/rename", json={"feature_id": "base", "name": "plate"})

    r = client.post("/api/feature/strike",
                    json={"feature_id": "plate", "restore": True}).json()
    feats = _feats(client)
    assert feats["round"]["suppressed"], "the rounding the user turned off came back"
    assert not feats["plate"]["suppressed"]
    assert r["strike_plan"]["restored"] == ["plate"]


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
