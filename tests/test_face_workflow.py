"""The user's REAL journey, backend half: block -> sketch on its face ->
extrude the sketch -> the ORIGINAL body must stay visible.

Reported (2026-08-04): "when I draw some block, and I am drawing some
sketches on the selected side, after finishing the sketch and extruding,
the main body vanishes." Root cause: leaf_solid_ids counted the body input
of sketch_on_face as CONSUMED — but face-reference ops (sketch_on_face,
extrude_face) only POINT at a face; they never eat the solid.

Written per the user's testing mandate: test the workflow being improved,
step by step, not an unrelated part.
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


def test_face_sketch_then_extrude_keeps_the_base_body(client):
    c = client
    c.post("/api/new", json={"name": "wf"})
    _add(c, {"id": "b", "op": "plate",
             "params": {"width": 60, "depth": 40, "thickness": 20},
             "inputs": []})
    doc = studio._doc()
    assert doc.leaf_solid_ids() == ["b"]

    _add(c, {"id": "sk1", "op": "sketch_on_face",
             "params": {"face_center": [0, 0, 10], "face_normal": [0, 0, 1],
                        "entities": [{"kind": "circle", "mode": "add",
                                      "x": 0, "y": 0, "r": 8}]},
             "inputs": ["b"]})
    assert doc.leaf_solid_ids() == ["b"], \
        "a 2D sketch on a face must not consume the body"

    _add(c, {"id": "ex1", "op": "extrude", "params": {"amount": 5},
             "inputs": ["sk1"]})
    assert doc.leaf_solid_ids() == ["b", "ex1"], \
        "the base body vanished after extruding its face sketch"
    bodies = [x["id"] for x in c.get("/api/model").json()["bodies"]]
    assert bodies == ["b", "ex1"], bodies


def test_extrude_face_new_body_keeps_the_source(client):
    """Same class of bug via the OTHER face-reference op: pulling a face into
    a separate body must not hide the body the face came from."""
    c = client
    c.post("/api/new", json={"name": "wf2"})
    _add(c, {"id": "b", "op": "plate",
             "params": {"width": 60, "depth": 40, "thickness": 20},
             "inputs": []})
    _add(c, {"id": "boss", "op": "extrude_face",
             "params": {"face_center": [0, 0, 10], "face_normal": [0, 0, 1],
                        "amount": 6},
             "inputs": ["b"]})
    doc = studio._doc()
    assert doc.leaf_solid_ids() == ["b", "boss"], \
        "extrude_face (new body) made the source body vanish"


def test_join_still_consumes_both_parents(client):
    """The fix must not over-reach: a fuse DOES consume its inputs — after a
    Join only the fused body is a leaf."""
    c = client
    c.post("/api/new", json={"name": "wf3"})
    _add(c, {"id": "b", "op": "plate",
             "params": {"width": 60, "depth": 40, "thickness": 20},
             "inputs": []})
    _add(c, {"id": "sk1", "op": "sketch_on_face",
             "params": {"face_center": [0, 0, 10], "face_normal": [0, 0, 1],
                        "entities": [{"kind": "circle", "mode": "add",
                                      "x": 0, "y": 0, "r": 8}]},
             "inputs": ["b"]})
    _add(c, {"id": "ex1", "op": "extrude", "params": {"amount": 5},
             "inputs": ["sk1"]})
    _add(c, {"id": "j1", "op": "fuse", "params": {}, "inputs": ["b", "ex1"]})
    doc = studio._doc()
    assert doc.leaf_solid_ids() == ["j1"], doc.leaf_solid_ids()
