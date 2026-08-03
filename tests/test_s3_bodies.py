"""S3: every visible body is a REAL, face-tagged, pickable body.

The bug: /api/model only face-tagged the RESULT solid and shipped the other
leaf bodies as bare silhouettes, which the viewport drew as translucent grey
ghosts. Extruding a second sketch made the second body the result — so the
FIRST body turned into a ghost, which users read as "my box went blank /
disappeared". Fusion shows every body in the Bodies folder as a real solid.
"""
import pytest
from fastapi.testclient import TestClient

import studio
from document import Document


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(Document(name="s3"))
    return TestClient(studio.app)


def two_bodies(client):
    """Two separate solids, exactly like sketch->extrude done twice."""
    doc = studio._doc()
    doc.add("plate1", "plate", {"width": 60, "depth": 40, "thickness": 10})
    doc.add("plate2", "plate", {"width": 30, "depth": 20, "thickness": 8})
    doc.add("shift", "move", {"x": 120, "y": 0, "z": 0}, inputs=["plate2"])
    studio._rebuild_and_mesh()
    return client.get("/api/model").json()


def test_every_leaf_body_is_returned_and_face_tagged(client):
    m = two_bodies(client)
    ids = {b["id"] for b in m["bodies"]}
    assert ids == {"plate1", "shift"}, ids
    for b in m["bodies"]:
        assert b["positions"] and b["indices"], b["id"]
        # face tagging is what makes a body pickable — ghosts had none
        assert len(b["faceId"]) * 3 == len(b["positions"]), b["id"]
        assert len(b["faces"]) == 6, b["id"]          # a box
        assert b["edges"], b["id"]
        assert all(f.get("body") == b["id"] for f in b["faces"])
        assert all(f.get("planar") for f in b["faces"])


def test_exactly_one_body_is_flagged_as_the_result(client):
    m = two_bodies(client)
    flagged = [b["id"] for b in m["bodies"] if b["result"]]
    assert len(flagged) == 1
    # top-level keys still describe the result body (older callers)
    res = next(b for b in m["bodies"] if b["result"])
    assert m["positions"] == res["positions"]
    assert m["faceId"] == res["faceId"]
    assert [f["id"] for f in m["faces"]] == [f["id"] for f in res["faces"]]


def test_non_result_body_faces_carry_their_own_body_id(client):
    """Picking a face must say WHICH body it came from, so tools act on that
    body instead of on whatever happens to be the tip."""
    m = two_bodies(client)
    other = next(b for b in m["bodies"] if not b["result"])
    assert other["faces"], other["id"]
    assert {f["body"] for f in other["faces"]} == {other["id"]}
    assert {e["body"] for e in other["edges"]} == {other["id"]}


def test_single_body_still_reports_itself_as_result(client):
    doc = studio._doc()
    doc.add("disc1", "disc", {"radius": 25, "thickness": 6})
    studio._rebuild_and_mesh()
    m = client.get("/api/model").json()
    assert len(m["bodies"]) == 1
    assert m["bodies"][0]["result"] and m["bodies"][0]["id"] == "disc1"
    assert m["positions"]


def test_face_outline_resolves_on_the_PICKED_body_not_the_result(client):
    """The regression this guards: two bodies, ask for a face of the NON-result
    one. Without feature_id the face resolves on the RESULT solid, so you get
    the wrong body's outline — the sketch/extrude then acts on the wrong body.

    Here the result is `shift` (plate2 30x20, moved), so the non-result leaf is
    plate1 at 60x40. Asserted explicitly rather than assumed, because "which
    body is the result" is exactly the thing under test."""
    m = two_bodies(client)
    other = next(b for b in m["bodies"] if not b["result"])
    assert other["id"] == "plate1"
    top = max((f for f in other["faces"] if f.get("center")),
              key=lambda f: f["center"][2])

    out = client.post("/api/face-outline", json={
        "face_center": top["center"], "face_normal": top.get("normal"),
        "feature_id": other["id"]}).json()
    assert out["planar"] and out["outer"], out
    xs = [p[0] for p in out["outer"]]
    ys = [p[1] for p in out["outer"]]
    assert max(xs) - min(xs) == pytest.approx(60, abs=1e-3)   # plate1, picked
    assert max(ys) - min(ys) == pytest.approx(40, abs=1e-3)

    # same face WITHOUT feature_id: falls back to the result body (30x20) and
    # therefore cannot return plate1's 60x40 outline
    fallback = client.post("/api/face-outline", json={
        "face_center": top["center"], "face_normal": top.get("normal")}).json()
    fxs = [p[0] for p in fallback.get("outer") or [[0, 0]]]
    assert max(fxs) - min(fxs) != pytest.approx(60, abs=1e-3)


def test_sketches_still_reported_alongside_bodies(client):
    doc = studio._doc()
    doc.add("sk", "sketch", {"plane": "XY", "offset": 0,
                             "entities": [{"kind": "circle", "mode": "add",
                                           "r": 10}]})
    doc.add("solid", "plate", {"width": 20, "depth": 20, "thickness": 5})
    studio._rebuild_and_mesh()
    m = client.get("/api/model").json()
    assert len(m["sketches"]) == 1
    assert [b["id"] for b in m["bodies"]] == ["solid"]
