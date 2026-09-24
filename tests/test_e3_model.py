"""E3: /api/model face-tagged mesh + edge polylines for viewport picking."""
import pytest
from fastapi.testclient import TestClient

import studio
from fixture_docs import flange


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(flange())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def test_model_returns_faces_edges_and_tagged_mesh(client):
    m = client.get("/api/model").json()
    assert m["faces"] and m["edges"]
    # every triangle vertex carries a faceId, parallel to positions
    assert len(m["faceId"]) == len(m["positions"]) // 3
    assert max(m["indices"]) < len(m["faceId"])
    # face ids referenced by the mesh all exist in the faces metadata
    ids = {f["id"] for f in m["faces"]}
    assert set(m["faceId"]) <= ids


def test_face_metadata_has_type_and_cylinder_radius(client):
    m = client.get("/api/model").json()
    types = {f["type"] for f in m["faces"]}
    assert "PLANE" in types and "CYLINDER" in types
    cyls = [f for f in m["faces"] if f["type"] == "CYLINDER"]
    assert all("radius" in f for f in cyls)


def test_edges_are_polylines_with_length(client):
    m = client.get("/api/model").json()
    for e in m["edges"]:
        assert len(e["points"]) >= 2
        assert e["length"] > 0
        assert all(len(p) == 3 for p in e["points"])


def test_empty_design_returns_empty_model(client):
    client.post("/api/new", json={"name": "blank"})
    m = client.get("/api/model").json()
    assert m["positions"] == [] and m["faces"] == []


def test_bare_sketch_is_visible_in_model(client):
    """A design that is ONLY a sketch must still show up in the viewport."""
    client.post("/api/new", json={"name": "sketch-only"})
    client.post("/api/feature/add", json={
        "id": "s", "op": "sketch", "params": {"plane": "XY", "entities": [
            {"kind": "circle", "r": 20}]}, "inputs": []})
    m = client.get("/api/model").json()
    assert m["positions"] == []                    # no solid yet
    assert len(m["sketches"]) == 1                 # but the sketch IS there
    sk = m["sketches"][0]
    assert sk["id"] == "s" and len(sk["positions"]) > 0 and sk["outlines"]
    # once consumed by an extrude, the sketch disappears from the overlay
    client.post("/api/feature/add", json={
        "id": "solid", "op": "extrude", "params": {"amount": 5},
        "inputs": ["s"]})
    m = client.get("/api/model").json()
    assert m["sketches"] == [] and len(m["positions"]) > 0


def test_model_reflects_sketch_extrude(client):
    client.post("/api/new", json={"name": "box-with-hole"})
    client.post("/api/feature/add", json={
        "id": "s", "op": "sketch", "params": {"plane": "XY", "entities": [
            {"kind": "rectangle", "w": 40, "h": 40},
            {"kind": "circle", "r": 8, "mode": "subtract"}]}, "inputs": []})
    client.post("/api/feature/add", json={
        "id": "solid", "op": "extrude", "params": {"amount": 10},
        "inputs": ["s"]})
    m = client.get("/api/model").json()
    # a square tube: outer planes + inner cylinder wall present
    assert any(f["type"] == "CYLINDER" for f in m["faces"])
    assert len(m["faces"]) >= 6
