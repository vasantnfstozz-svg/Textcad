"""P1: typing a dimension and having the model follow.

User request (2026-08-27): "we have a circle i am clicking that, we will get
the dia, if i am changing the dia, the actaul dia and design should chnage it".

The rule this file exists to enforce is the DRIVEN/DERIVED split
(MEASURE-PLAN.md). A measurement that maps to one param is editable and exact.
A measurement that is a consequence of two independent literals is NOT, and the
tool must refuse it with a reason rather than guess which side to move — a box
that silently moves the wrong wall is the failure mode this project exists to
prevent.

So the assertions come in pairs: the edit lands AND the geometry really changed
(re-measured, never inferred from the param write), and the un-drivable cases
are refused AND leave the document untouched.
"""
import pytest
from fastapi.testclient import TestClient

import measure
import studio
from document import Document


# --------------------------------------------------------------- fixtures ----

def pocket_doc():
    """80x60x12 plate, ⌀18 pocket 5 deep at x=15, plus a small ⌀8 hole."""
    doc = Document(name="t-drive")
    doc.add("b", "plate", {"width": 80, "depth": 60, "thickness": 12})
    doc.add("sk", "sketch_on_face",
            {"face": "top", "offset": 0,
             "entities": [{"kind": "circle", "mode": "add", "x": 15, "y": 0, "r": 9},
                          {"kind": "circle", "mode": "add", "x": -20, "y": 10, "r": 4}]},
            inputs=["b"])
    doc.add("tool", "extrude", {"amount": -5}, inputs=["sk"])
    doc.add("pk", "cut", {}, inputs=["b", "tool"])
    assert doc.rebuild(), doc.tree()
    return doc


def sel(doc, kind, idx):
    return {"body": doc._result_feature().id, "kind": kind, "id": idx}


def cyl_of(doc, radius):
    """Index of the cylindrical face with this radius."""
    for i, f in enumerate(doc.result().faces()):
        try:
            if "CYLINDER" in str(f.geom_type) and abs(f.radius - radius) < 1e-6:
                return i
        except Exception:
            continue
    raise AssertionError(f"no cylinder of r={radius}")


def flat_of(doc):
    for i, f in enumerate(doc.result().faces()):
        if "PLANE" in str(f.geom_type):
            return i
    raise AssertionError("no planar face")


# ------------------------------------------------------- driver resolution ---

def test_a_hole_reports_the_param_that_drives_it():
    doc = pocket_doc()
    r = measure.measure(doc, sel(doc, "face", cyl_of(doc, 9)))
    d = r["driver"]
    assert d is not None, "a sketched hole must be editable"
    assert d["feature"] == "sk"
    assert d["path"] == ["entities", 0, "r"]
    assert d["current"] == pytest.approx(9.0)
    assert d["transform"] == "half", "a diameter is twice the stored radius"


def test_each_hole_resolves_to_its_own_entity():
    """Two holes of different sizes in ONE sketch must not cross-wire: editing
    the ⌀8 must not reach for the ⌀18's radius."""
    doc = pocket_doc()
    big = measure.measure(doc, sel(doc, "face", cyl_of(doc, 9)))["driver"]
    small = measure.measure(doc, sel(doc, "face", cyl_of(doc, 4)))["driver"]
    assert big["path"] == ["entities", 0, "r"]
    assert small["path"] == ["entities", 1, "r"]


def test_either_rim_of_a_pocket_resolves_the_same_driver():
    """The mouth rim, the bottom rim and the bore wall are three different
    picks of one hole. The user should not have to know which one the tool
    prefers."""
    doc = pocket_doc()
    rims = [i for i, e in enumerate(doc.result().edges())
            if "CIRCLE" in str(e.geom_type) and abs(e.radius - 9) < 1e-6]
    assert len(rims) >= 2, "the pocket has a mouth and a bottom rim"
    paths = {tuple(measure.measure(doc, sel(doc, "edge", i))["driver"]["path"])
             for i in rims}
    assert paths == {("entities", 0, "r")}, paths


def test_a_flat_face_has_no_driver():
    """Read-only is the honest outcome — not an edit box that does nothing."""
    doc = pocket_doc()
    assert measure.measure(doc, sel(doc, "face", flat_of(doc)))["driver"] is None


def test_a_derived_two_face_distance_has_no_driver():
    doc = pocket_doc()
    faces = doc.result().faces()
    flat = [i for i, f in enumerate(faces)
            if "PLANE" in str(f.geom_type)
            and abs(abs(f.normal_at(f.center()).Z) - 1) < 1e-9]
    r = measure.measure(doc, sel(doc, "face", flat[0]),
                        sel(doc, "face", flat[-1]))
    assert r.get("driver") is None


def test_a_block_op_hole_is_not_editable():
    """with_center_hole makes a bore with no sketch entity behind it, so there
    is no single param to type into. It must say so, not invent one."""
    doc = Document(name="t-block-hole")
    doc.add("plate", "disc", {"radius": 40, "thickness": 10})
    doc.add("bore", "with_center_hole", {"radius": 12}, inputs=["plate"])
    assert doc.rebuild(), doc.tree()
    r = measure.measure(doc, sel(doc, "face", cyl_of(doc, 12)))
    assert r["kind"] == "diameter"
    assert r["value"] == pytest.approx(24.0)
    assert r["driver"] is None


# ----------------------------------------------------------- the edit loop ---

def test_setting_a_diameter_changes_the_geometry():
    """The whole point: type 12, and the hole IS ⌀12 afterwards — re-measured
    from the rebuilt solid, not inferred from the param write."""
    doc = pocket_doc()
    plan = measure.plan_set(doc, sel(doc, "face", cyl_of(doc, 9)), None, 12.0)
    assert "error" not in plan, plan
    assert plan["param"] == pytest.approx(6.0), "12 mm diameter = 6 mm radius"
    measure.write(doc, plan)
    assert doc.rebuild(), doc.tree()
    assert doc.get("sk").params["entities"][0]["r"] == pytest.approx(6.0)
    again = measure.measure(doc, sel(doc, "face", cyl_of(doc, 6)))
    assert again["value"] == pytest.approx(12.0)


def test_plan_set_does_not_mutate_on_refusal():
    """A refused edit must leave the design byte-identical — the endpoint pops
    its undo snapshot on failure, which is only safe if nothing was written."""
    doc = pocket_doc()
    before = doc.to_data()
    for bad in (0, -5, "wide"):
        assert "error" in measure.plan_set(
            doc, sel(doc, "face", cyl_of(doc, 9)), None, bad)
    assert "error" in measure.plan_set(doc, sel(doc, "face", flat_of(doc)),
                                       None, 5)
    assert doc.to_data() == before


def test_a_zero_or_negative_diameter_is_refused_with_the_arithmetic():
    doc = pocket_doc()
    r = measure.plan_set(doc, sel(doc, "face", cyl_of(doc, 9)), None, -3)
    assert "must be positive" in r["error"]
    assert "-1.5" in r["error"], "say what the param would have become"


# ------------------------------------------------------------- over HTTP -----

@pytest.fixture
def client():
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    return TestClient(studio.app)


def _add(c, payload):
    r = c.post("/api/feature/add", json=payload).json()
    f = next(x for x in r["features"] if x["id"] == payload["id"])
    assert f["status"] == "ok", (payload["id"], f["problems"])
    return r


def api_pocket(c):
    c.post("/api/new", json={"name": "drive-api"})
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


def cyl_sel(model, radius=None):
    body = model["bodies"][-1]
    for f in body["faces"]:
        if f["type"] == "CYLINDER" and (
                radius is None or abs(f.get("radius", 0) - radius) < 1e-2):
            return {"body": body["id"], "kind": "face", "id": f["id"]}
    raise AssertionError("no cylinder face in the payload")


def test_api_set_drives_the_model_and_verifies_it(client):
    model = api_pocket(client)
    r = client.post("/api/measure/set",
                    json={"a": cyl_sel(model, 9.0), "value": 12.0}).json()
    assert r.get("error") is None, r
    assert r["verified"] is True, r
    assert r["achieved"] == pytest.approx(12.0, abs=1e-3)
    assert r["was"] == pytest.approx(9.0)
    assert r["param"] == pytest.approx(6.0)
    assert "warning" not in r
    # and the document really changed
    doc = client.get("/api/doc").json()
    sk = next(f for f in doc["features"] if f["id"] == "sk")
    assert sk["params"]["entities"][0]["r"] == pytest.approx(6.0)


def test_api_set_is_undoable(client):
    """A driven edit is a normal hand edit: it snapshots, so Ctrl+Z restores
    the old dimension."""
    model = api_pocket(client)
    client.post("/api/measure/set",
                json={"a": cyl_sel(model, 9.0), "value": 12.0})
    assert client.post("/api/undo").json().get("error") is None
    doc = client.get("/api/doc").json()
    sk = next(f for f in doc["features"] if f["id"] == "sk")
    assert sk["params"]["entities"][0]["r"] == pytest.approx(9.0), \
        "undo did not restore the diameter"


def test_api_set_refuses_a_derived_measurement_without_touching_the_doc(client):
    model = api_pocket(client)
    body = model["bodies"][-1]
    flat = [f for f in body["faces"]
            if f.get("planar") and f.get("normal")
            and abs(abs(f["normal"][2]) - 1) < 1e-6]
    top = max(flat, key=lambda f: f["center"][2])
    bot = min(flat, key=lambda f: f["center"][2])
    before = client.get("/api/doc").json()["features"]
    undo_before = len(studio._entry()["history"])
    r = client.post("/api/measure/set", json={
        "a": {"body": body["id"], "kind": "face", "id": top["id"]},
        "b": {"body": body["id"], "kind": "face", "id": bot["id"]},
        "value": 20.0}).json()
    assert "error" in r
    assert "not driven by a single parameter" in r["error"]
    assert client.get("/api/doc").json()["features"] == before
    # a refusal must not leave an undo entry behind: the user would press
    # Ctrl+Z expecting their last real edit back and get a no-op instead
    assert len(studio._entry()["history"]) == undo_before


def test_api_set_on_a_stale_index_is_an_error_not_a_500(client):
    api_pocket(client)
    res = client.post("/api/measure/set", json={
        "a": {"body": "pk", "kind": "face", "id": 4242}, "value": 10.0})
    assert res.status_code == 200, res.text
    assert "error" in res.json()


def test_every_bore_of_a_polar_pattern_is_editable():
    """A patterned copy sits nowhere near the entity that seeded it, so
    position matching alone found only the seed: 5 of 6 bores in a ring were
    read-only while the 6th was editable (probed 2026-08-27) — same hole, same
    diameter, different answer depending on which one you clicked.

    Provenance has already proved the face came from this sketch, so one circle
    of that radius in it is unambiguous wherever the copy landed. Editing it
    moves the whole ring, which is what patterning a seed means.

    NOTE the construction: the TOOL is patterned and then cut once. Unioning
    six copies of an already-holed disc fills every hole back in, because each
    copy is solid where the others are not."""
    doc = Document(name="t-pattern-drive")
    doc.add("b", "disc", {"radius": 60, "thickness": 10})
    doc.add("sk", "sketch_on_face",
            {"face": "top", "offset": 0,
             "entities": [{"kind": "circle", "mode": "add",
                           "x": 40, "y": 0, "r": 5}]}, inputs=["b"])
    doc.add("tool", "extrude", {"amount": -10}, inputs=["sk"])
    doc.add("ring", "polar_pattern", {"count": 6}, inputs=["tool"])
    doc.add("hole", "cut", {}, inputs=["b", "ring"])
    assert doc.rebuild(), doc.tree()

    bores = [i for i, f in enumerate(doc.result().faces())
             if "CYLINDER" in str(f.geom_type) and abs(f.radius - 5) < 1e-6]
    assert len(bores) == 6, f"expected 6 bores, got {len(bores)}"
    drivers = [measure.measure(doc, sel(doc, "face", i)).get("driver")
               for i in bores]
    assert all(d is not None for d in drivers), \
        f"only {sum(d is not None for d in drivers)}/6 bores were editable"
    assert {tuple(d["path"]) for d in drivers} == {("entities", 0, "r")}


def test_two_holes_of_the_SAME_radius_still_resolve_separately():
    """The pattern fallback must not blur two distinct entities together: with
    two r=5 circles in one sketch, position is what tells them apart, and each
    must drive its own."""
    doc = Document(name="t-same-radius")
    doc.add("b", "plate", {"width": 120, "depth": 60, "thickness": 10})
    doc.add("sk", "sketch_on_face",
            {"face": "top", "offset": 0,
             "entities": [{"kind": "circle", "mode": "add", "x": -30, "y": 0, "r": 5},
                          {"kind": "circle", "mode": "add", "x": 30, "y": 0, "r": 5}]},
            inputs=["b"])
    doc.add("tool", "extrude", {"amount": -10}, inputs=["sk"])
    doc.add("holes", "cut", {}, inputs=["b", "tool"])
    assert doc.rebuild(), doc.tree()

    faces = doc.result().faces()
    bores = [i for i, f in enumerate(faces)
             if "CYLINDER" in str(f.geom_type) and abs(f.radius - 5) < 1e-6]
    assert len(bores) == 2
    paths = {}
    for i in bores:
        d = measure.measure(doc, sel(doc, "face", i))["driver"]
        assert d is not None
        # which entity did it pick? key it by the bore's X so we can compare
        paths[round(faces[i].axis_of_rotation.position.X)] = tuple(d["path"])
    assert paths[-30] == ("entities", 0, "r"), paths
    assert paths[30] == ("entities", 1, "r"), paths
