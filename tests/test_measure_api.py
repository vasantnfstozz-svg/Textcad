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


def test_probe_endpoint_is_read_only(client):
    """A probe fires per pointermove during a drag — it must never snapshot,
    rebuild, or touch the document."""
    model = pocket(client)
    body = body_of(model)
    flat = [f for f in body["faces"]
            if f.get("planar") and f.get("normal")
            and abs(abs(f["normal"][2]) - 1) < 1e-6]
    top = max(flat, key=lambda f: f["center"][2])
    bot = min(flat, key=lambda f: f["center"][2])
    before = client.get("/api/doc").json()["features"]
    hist = len(studio._entry()["history"])
    r = client.post("/api/measure/probe", json={
        "a": {"body": body["id"], "kind": "face", "id": top["id"]},
        "b": {"body": body["id"], "kind": "face", "id": bot["id"]},
        "point": [30, 20, 6], "on": "a"}).json()   # plate is Z-centred: top z=6
    assert r.get("error") is None, r
    assert r["value"] == pytest.approx(12.0, abs=1e-3)
    assert r["from"] and r["to"]
    assert client.get("/api/doc").json()["features"] == before
    assert len(studio._entry()["history"]) == hist


def test_mesh_payload_carries_per_type_dimensions(client):
    """Every surface type reads out its own dimensions in the pick box
    (2026-08-31: "for a selected box surface show the length and width, if i
    am selecting a curve show the radius or dia"). The flat-face extents are
    ORIENTED — a rotated face must report its true size, not its world bbox
    (which reads 23.32 for this 20-wide face at 30 degrees)."""
    client.post("/api/new", json={"name": "dims-payload"})
    _add(client, {"id": "b", "op": "plate",
                  "params": {"width": 80, "depth": 60, "thickness": 10},
                  "inputs": []})
    _add(client, {"id": "sk", "op": "sketch_on_face",
                  "params": {"face": "top", "offset": 0, "entities": [
                      {"kind": "rectangle", "mode": "add", "w": 20, "h": 12,
                       "x": -20, "y": 0, "rotation": 30}]}, "inputs": ["b"]})
    _add(client, {"id": "boss", "op": "extrude", "params": {"amount": 5},
                  "inputs": ["sk"]})
    _add(client, {"id": "j", "op": "fuse", "params": {},
                  "inputs": ["b", "boss"]})
    body = client.get("/api/model").json()["bodies"][-1]
    boss_top = next(f for f in body["faces"]
                    if f.get("planar") and f.get("center")
                    and abs(f["center"][2] - 10) < 1e-6)
    assert boss_top["extents"] == pytest.approx([20.0, 12.0], abs=0.05), \
        boss_top["extents"]
    plate_top = next(f for f in body["faces"]
                     if f.get("planar") and f.get("center")
                     and abs(f["center"][2] - 5) < 0.6)
    assert plate_top["extents"] == pytest.approx([80.0, 60.0], abs=0.05)

    client.post("/api/new", json={"name": "dims-ball"})
    _add(client, {"id": "s", "op": "ball", "params": {"radius": 7},
                  "inputs": []})
    sph = client.get("/api/model").json()["bodies"][-1]["faces"][0]
    assert sph["type"] == "SPHERE"
    assert sph["radius"] == pytest.approx(7.0)

    client.post("/api/new", json={"name": "dims-cone"})
    _add(client, {"id": "c", "op": "cone",
                  "params": {"bottom_radius": 10, "top_radius": 4,
                             "height": 12}, "inputs": []})
    cone = next(f for f in client.get("/api/model").json()["bodies"][-1]["faces"]
                if f["type"] == "CONE")
    assert cone["cone_d"] == pytest.approx([8.0, 20.0], abs=0.05)
    assert cone["cone_angle"] == pytest.approx(26.57, abs=0.05)
    assert cone["height"] == pytest.approx(12.0, abs=0.05)

    client.post("/api/new", json={"name": "dims-disc"})
    _add(client, {"id": "d", "op": "disc",
                  "params": {"radius": 9, "thickness": 14}, "inputs": []})
    cyl = next(f for f in client.get("/api/model").json()["bodies"][-1]["faces"]
               if f["type"] == "CYLINDER")
    assert cyl["radius"] == pytest.approx(9.0)
    assert cyl["height"] == pytest.approx(14.0, abs=0.05)


# ---------------------------------------------------------------------------
# Section 6 review (2026-09-10): the edge id a pick hands back MUST be the
# index measure.resolve() looks up.

def test_edge_ids_stay_part_edges_indices_on_a_big_body(client):
    """F1 (P0). Over 400 faces `_tagged_mesh` switches to mesh mode, and the
    old code handed the viewport `[every rich face's edges]` — each edge once
    per adjacent face, in face order. measure.resolve() indexes part.edges(),
    so on 12 of the 50 saved designs (esp32-remote: 7176 ids for 3588 edges)
    clicking an edge measured a DIFFERENT one, and a circular mismatch even
    opened an edit box driving a hole the user never clicked.

    Built without booleans so the test stays fast: 70 disjoint boxes of
    different sizes = 420 planar faces, every edge length distinctive."""
    import studio as st
    from build123d import Box, Compound, Pos

    part = Compound(children=[Pos(i * 40, 0, 0) * Box(2 + i, 3 + i * 0.5,
                                                      4 + i * 0.25)
                              for i in range(70)])
    assert len(part.faces()) > st.MESH_MODE_FACES, "this body must be mesh mode"
    tm = st._tagged_mesh(part, body_id="b")
    real = part.edges()

    assert tm["edges"], "a CAD body in mesh mode still gets its outlines"
    for e in tm["edges"]:
        i = e["id"]
        assert 0 <= i < len(real), f"edge id {i} is not an index into part.edges()"
        assert float(real[i].length) == pytest.approx(e["length"], abs=1e-6), (
            f"edge id {i} is drawn {e['length']} long but resolves to "
            f"{float(real[i].length)}")
    ids = [e["id"] for e in tm["edges"]]
    assert len(ids) == len(set(ids)), "one edge, one id"


def test_measuring_a_clicked_edge_agrees_with_what_was_drawn(client):
    """The same guarantee end to end: whatever the payload says an edge is,
    /api/measure must say the same. On a mesh-mode body the old code answered
    with another edge entirely and never said so."""
    import studio as st
    from build123d import Box, Compound, Pos

    part = Compound(children=[Pos(i * 40, 0, 0) * Box(2 + i, 3 + i * 0.5,
                                                      4 + i * 0.25)
                              for i in range(70)])
    tm = st._tagged_mesh(part, body_id="b")
    import measure
    from document import Document

    doc = Document(name="t")
    doc._parts = {"b": part}
    for e in tm["edges"][:40]:
        got = measure.resolve(doc, {"body": "b", "kind": "edge", "id": e["id"]})
        assert float(got[0].length) == pytest.approx(e["length"], abs=1e-6)
