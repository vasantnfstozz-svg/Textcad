"""/api/measure over HTTP, and the mesh payload the readout labels picks from.

The endpoint is read-only by design (like /api/face-feature): measuring must
never snapshot, rebuild, mutate the document, or push a new version — a user
clicking around to read dimensions would otherwise fill their version tree with
noise. Those invariants are asserted here, not just the numbers.
"""
import pytest
from fastapi.testclient import TestClient

import studio


@pytest.fixture
def client():
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    return TestClient(studio.app)


def _add(c, payload):
    r = c.post("/api/feature/add", json=payload).json()
    f = next(x for x in r["features"] if x["id"] == payload["id"])
    assert f["status"] == "ok", (payload["id"], f["problems"])
    return r


def pocket(c):
    """80x60x12 plate with a ⌀18, 5 mm deep pocket — same known geometry as
    tests/test_measure.py, but built through the API."""
    c.post("/api/new", json={"name": "measure-api"})
    _add(c, {"id": "b", "op": "plate",
             "params": {"width": 80, "depth": 60, "thickness": 12},
             "inputs": []})
    _add(c, {"id": "sk", "op": "sketch_on_face",
             "params": {"face": "top", "offset": 0,
                        "entities": [{"kind": "circle", "mode": "add",
                                      "x": 15, "y": 0, "r": 9}]},
             "inputs": ["b"]})
    _add(c, {"id": "tool", "op": "extrude", "params": {"amount": -5},
             "inputs": ["sk"]})
    _add(c, {"id": "pk", "op": "cut", "params": {}, "inputs": ["b", "tool"]})
    return c.get("/api/model").json()


def body_of(model):
    return model["bodies"][-1]


def test_mesh_payload_carries_circle_radius_and_arc_centre(client):
    """So a pick can be labelled with no round trip — and with the CORRECT
    centre (edge.center() is a point on the circle, not its centre)."""
    model = pocket(client)
    body = body_of(model)
    circles = [e for e in body["edges"] if e["type"] == "CIRCLE"]
    assert circles, "the pocket has circular edges"
    e = circles[0]
    assert e["radius"] == pytest.approx(9.0, abs=1e-3)
    assert e["arc_center"][0] == pytest.approx(15.0, abs=1e-3), \
        "arc_center, not center() — center() would report ~6.0 here"


def test_mesh_payload_carries_cylinder_axis(client):
    model = pocket(client)
    body = body_of(model)
    cyl = [f for f in body["faces"] if f["type"] == "CYLINDER"]
    assert cyl
    assert cyl[0]["axis"] == pytest.approx([0, 0, 1], abs=1e-3)
    assert cyl[0]["radius"] == pytest.approx(9.0, abs=1e-2)


def test_measure_a_hole_gives_diameter(client):
    model = pocket(client)
    body = body_of(model)
    idx = next(f["id"] for f in body["faces"] if f["type"] == "CYLINDER")
    r = client.post("/api/measure", json={
        "a": {"body": body["id"], "kind": "face", "id": idx}}).json()
    assert r.get("error") is None, r
    assert r["kind"] == "diameter"
    assert r["value"] == pytest.approx(18.0, abs=1e-2)


def test_measure_two_faces_gives_thickness(client):
    model = pocket(client)
    body = body_of(model)
    flat = [f for f in body["faces"]
            if f.get("planar") and f.get("normal")
            and abs(abs(f["normal"][2]) - 1) < 1e-6]
    top = max(flat, key=lambda f: f["center"][2])
    bot = min(flat, key=lambda f: f["center"][2])
    r = client.post("/api/measure", json={
        "a": {"body": body["id"], "kind": "face", "id": top["id"]},
        "b": {"body": body["id"], "kind": "face", "id": bot["id"]}}).json()
    assert r.get("error") is None, r
    assert r["kind"] == "thickness"
    assert r["value"] == pytest.approx(12.0, abs=1e-2)
    assert r["from"] and r["to"], "witness points draw the dimension line"


def test_measuring_never_touches_the_document(client):
    """Read-only: no new version, no undo entry, no rebuild. Clicking around to
    read numbers must not pollute the design's history."""
    model = pocket(client)
    body = body_of(model)
    before = client.get("/api/doc").json()
    hist_before = len(studio._entry()["history"])

    for _ in range(3):
        client.post("/api/measure", json={
            "a": {"body": body["id"], "kind": "face", "id": 0},
            "b": {"body": body["id"], "kind": "face", "id": 1}})

    after = client.get("/api/doc").json()
    assert after["features"] == before["features"]
    assert len(studio._entry()["history"]) == hist_before, \
        "measuring pushed an undo snapshot"


def test_stale_face_index_answers_with_an_error_not_a_500(client):
    model = pocket(client)
    body = body_of(model)
    res = client.post("/api/measure", json={
        "a": {"body": body["id"], "kind": "face", "id": 4242}})
    assert res.status_code == 200, res.text
    assert "error" in res.json()


def test_measure_on_an_empty_design_is_an_error(client):
    client.post("/api/new", json={"name": "empty-measure"})
    r = client.post("/api/measure", json={
        "a": {"body": None, "kind": "face", "id": 0}}).json()
    assert "error" in r


def test_mesh_payload_carries_face_boundary_circles(client):
    """The pick box reads inner/outer dia straight from the tagged mesh, no
    round trip — so the payload must carry each face's FULL circular
    boundaries, largest first (user request 2026-08-31)."""
    client.post("/api/new", json={"name": "washer-mesh"})
    _add(client, {"id": "plate", "op": "disc",
                  "params": {"radius": 40, "thickness": 8}, "inputs": []})
    _add(client, {"id": "bore", "op": "with_center_hole",
                  "params": {"radius": 12}, "inputs": ["plate"]})
    body = client.get("/api/model").json()["bodies"][-1]
    tops = [f for f in body["faces"]
            if f.get("normal") and f["normal"][2] > 0.99]
    assert tops, "no top face in the payload"
    circles = tops[0].get("circles")
    assert circles == pytest.approx([40.0, 12.0]), circles
