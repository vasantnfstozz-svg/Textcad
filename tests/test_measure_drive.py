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


def test_a_hole_TOOL_bore_is_driven_by_the_holes_own_diameter():
    """The Hole tool's op EATS its body: there is no sketch circle behind the
    bore, so the sketch walk found nothing and measure said the bore was "a
    primitive, or an imported body" — untrue, and it took measure-and-drive
    away from every hole drilled with the tool. provenance names the feature
    that made the face (probes/hole_review_probe.py §3), and the radius says
    which of the hole's round params it is."""
    doc = Document(name="t-hole-tool")
    doc.add("b", "plate", {"width": 80, "depth": 60, "thickness": 12})
    doc.add("h", "hole", {"face": "top", "at": [15, 0], "diameter": 8, "depth": 5,
                          "kind": "counterbore", "cbore_diameter": 16, "cbore_depth": 2},
            inputs=["b"])
    assert doc.rebuild(), doc.tree()
    bore = measure.measure(doc, sel(doc, "face", cyl_of(doc, 4)))
    assert bore["kind"] == "diameter" and bore["value"] == pytest.approx(8.0)
    d = bore["driver"]
    assert d is not None, "a hole made by the Hole tool must be editable"
    assert d["feature"] == "h" and d["path"] == ["diameter"]
    assert d["current"] == pytest.approx(8.0)
    assert d["transform"] == "value", "a hole stores the DIAMETER, not a radius"
    # the counterbore seat is its own param, not the bore's
    assert measure.measure(doc, sel(doc, "face", cyl_of(doc, 8)))["driver"]["path"] \
        == ["cbore_diameter"]
    # and typing into it really changes the geometry (re-measured, not inferred)
    plan = measure.plan_set(doc, sel(doc, "face", cyl_of(doc, 4)), None, 10.0)
    assert "error" not in plan, plan
    measure.write(doc, plan)
    assert doc.rebuild(), doc.tree()
    assert measure.measure(doc, sel(doc, "face", cyl_of(doc, 5)))["value"] \
        == pytest.approx(10.0)


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
    # The refusal must EXPLAIN itself. Which reason applies depends on what the
    # faces trace back to — here a `plate` primitive, whose walls have no sketch
    # entity at all — so assert that a real reason came back rather than
    # pinning one phrasing (P2 made these messages more specific).
    assert any(bit in r["error"] for bit in (
        "not driven by a single parameter",   # nothing to type into
        "traces back to a sketch entity",     # nothing movable behind it
        "depth",                              # controlled by depth instead
    )), r["error"]
    assert client.get("/api/doc").json()["features"] == before
    # a refusal must not leave an undo entry behind: the user would press
    # Ctrl+Z expecting their last real edit back and get a no-op instead
    assert len(studio._entry()["history"]) == undo_before


def test_api_set_on_a_stale_index_is_an_error_not_a_500(client):
    """A refusal, not a crash -- and it says so in the STATUS. This asserted
    200 while /api/edit and the rest already answered 400, so a script driving
    the API read "face 4242 is not on this body any more" as success."""
    api_pocket(client)
    res = client.post("/api/measure/set", json={
        "a": {"body": "pk", "kind": "face", "id": 4242}, "value": 10.0})
    assert res.status_code == 400, res.text
    assert "error" in res.json()
    assert res.json()["features"], "the unchanged document rides along"


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


def test_verification_checks_the_KIND_not_just_the_number(client):
    """The endpoint re-measures the same face INDICES, and those are array
    positions a rebuild can reorder. Agreeing on a number is therefore not
    enough — if the pick now measures a different kind of thing, the indices
    went stale and the 'verified' claim would be about other geometry.

    Asserted through the honest path: a normal edit verifies AND reports the
    same kind it planned against."""
    model = api_pocket(client)
    r = client.post("/api/measure/set",
                    json={"a": cyl_sel(model, 9.0), "value": 12.0}).json()
    assert r["verified"] is True, r
    # re-reading must still describe a diameter, not something else that
    # happens to measure 12. Re-FETCH the model: `model` above was captured
    # before the edit and still describes the old r=9 bore.
    fresh = client.get("/api/model").json()
    again = client.post("/api/measure",
                        json={"a": cyl_sel(fresh, 6.0)}).json()
    assert again["kind"] == "diameter"
    assert again["value"] == pytest.approx(12.0, abs=1e-3)


# ------------------------------------------- same-entity pairs (round 2) -----

def cavity_pillar_doc():
    """The pillar demo: 80x60x12 plate, 60x40 cavity, 10x10 pillar at x=-10."""
    doc = Document(name="t-pair-driver")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 80, "h": 60, "x": 0, "y": 0}]})
    doc.add("body", "extrude", {"amount": 12}, inputs=["outline"])
    doc.add("cav_sk", "sketch_on_face", {"face": "top", "offset": 0,
            "entities": [{"kind": "rectangle", "mode": "add",
                          "w": 60, "h": 40, "x": 0, "y": 0}]}, inputs=["body"])
    doc.add("cav_tool", "extrude", {"amount": -8}, inputs=["cav_sk"])
    doc.add("isl_sk", "sketch_on_face", {"face": "top", "offset": 0,
            "entities": [{"kind": "rectangle", "mode": "add",
                          "w": 10, "h": 10, "x": -10, "y": 0}]}, inputs=["body"])
    doc.add("isl_tool", "extrude", {"amount": -12}, inputs=["isl_sk"])
    doc.add("cav_neg", "cut", {}, inputs=["cav_tool", "isl_tool"])
    doc.add("cavity", "cut", {}, inputs=["body", "cav_neg"])
    assert doc.rebuild(), doc.tree()
    return doc


def wall_at(doc, x, nx):
    for i, f in enumerate(doc.result().faces()):
        n = f.normal_at(f.center())
        c = f.center()
        if (abs(n.Z) < 0.01 and abs(c.X - x) < 1e-6
                and abs(n.X - nx) < 1e-6):
            return i
    raise AssertionError(f"no wall at x={x} nx={nx}")


def test_opposite_walls_of_one_box_drive_its_width():
    """User report (2026-08-27, round 2): "i can measure the distance between
    two seleted face, but the moving option is not working". They had picked
    the two opposite walls of one box - both ends of the tape measure on the
    SAME rectangle entity. The old move path translated the whole box, the
    width stayed 10, verification failed and reverted: "not working".

    That distance IS the rectangle's `w`, so it must be a DRIVEN edit."""
    doc = cavity_pillar_doc()
    a = wall_at(doc, -15, -1)
    b = wall_at(doc, -5, 1)
    r = measure.measure(doc, sel(doc, "face", a), sel(doc, "face", b))
    assert r["kind"] == "thickness"
    d = r["driver"]
    assert d is not None, "opposite walls of one box must be editable"
    assert d["feature"] == "isl_sk"
    assert d["path"] == ["entities", 0, "w"]
    assert d["current"] == pytest.approx(10.0)

    plan = measure.plan_set(doc, sel(doc, "face", a), sel(doc, "face", b), 8.0)
    assert "driver" in plan, plan
    measure.write(doc, plan)
    assert doc.rebuild(), doc.tree()
    ent = doc.get("isl_sk").params["entities"][0]
    assert ent["w"] == pytest.approx(8.0)
    assert ent["x"] == pytest.approx(-10.0), \
        "resizing must keep the box centred, not slide it"
    # the box really is 8 wide now: walls at -14 and -6
    wall_at(doc, -14, -1)
    wall_at(doc, -6, 1)


def test_facing_walls_of_one_cavity_drive_its_width_too():
    """A GAP whose two walls belong to one entity (the inside of a cavity) is
    that entity's dimension as well - same rule, opposite normal sense."""
    doc = cavity_pillar_doc()
    a = wall_at(doc, -30, 1)
    b = wall_at(doc, 30, -1)
    r = measure.measure(doc, sel(doc, "face", a), sel(doc, "face", b))
    assert r["kind"] == "gap"
    assert r["driver"] is not None
    assert r["driver"]["path"] == ["entities", 0, "w"]
    assert r["driver"]["feature"] == "cav_sk"


def test_cross_entity_pairs_still_move():
    """The pair driver must not swallow the move path: cavity wall to pillar
    wall is two different entities and stays a move."""
    doc = cavity_pillar_doc()
    a = wall_at(doc, -30, 1)
    b = wall_at(doc, -15, -1)
    r = measure.measure(doc, sel(doc, "face", a), sel(doc, "face", b))
    assert r["driver"] is None
    assert r["move"]["feature"] == "isl_sk"


def test_rotated_rectangle_maps_the_right_dimension():
    """sketch._entity rotates a shape about its centre, so a 90-degree
    rectangle's `w` runs along local Y. Un-rotating the wall normal must pick
    w, not h (probed 2026-08-27)."""
    doc = Document(name="t-rot")
    doc.add("b", "plate", {"width": 100, "depth": 80, "thickness": 10})
    doc.add("sk", "sketch_on_face", {"face": "top", "offset": 0,
            "entities": [{"kind": "rectangle", "mode": "add", "w": 20,
                          "h": 12, "x": 0, "y": 0, "rotation": 90}]},
            inputs=["b"])
    doc.add("boss", "extrude", {"amount": 5}, inputs=["sk"])
    doc.add("j", "fuse", {}, inputs=["b", "boss"])
    assert doc.rebuild(), doc.tree()
    # after 90 deg, w=20 spans WORLD Y: the boss walls at y=+-10 face +-Y
    walls = [i for i, f in enumerate(doc.result().faces())
             if abs(abs(f.normal_at(f.center()).Y) - 1) < 1e-6
             and f.center().Z > 6]
    assert len(walls) == 2
    r = measure.measure(doc, sel(doc, "face", walls[0]),
                        sel(doc, "face", walls[1]))
    assert r["value"] == pytest.approx(20.0)
    d = r["driver"]
    assert d is not None
    assert d["path"] == ["entities", 0, "w"], \
        f"rotation was not unwound: {d['path']}"


def test_same_entity_without_a_dimension_is_blocked_with_a_reason():
    """Two walls of one POLYGON have no single stored dimension, and moving the
    polygon slides both walls together. The tool must say so - not offer a
    move that can only ever no-op and revert."""
    doc = Document(name="t-poly-pair")
    doc.add("b", "plate", {"width": 100, "depth": 80, "thickness": 10})
    doc.add("sk", "sketch_on_face", {"face": "top", "offset": 0,
            "entities": [{"kind": "polygon", "mode": "add",
                          "points": [[-10, -8], [10, -8], [12, 8], [-12, 8]]}]},
            inputs=["b"])
    doc.add("boss", "extrude", {"amount": 5}, inputs=["sk"])
    doc.add("j", "fuse", {}, inputs=["b", "boss"])
    assert doc.rebuild(), doc.tree()
    walls = [i for i, f in enumerate(doc.result().faces())
             if abs(abs(f.normal_at(f.center()).Y) - 1) < 1e-6
             and f.center().Z > 6]
    assert len(walls) == 2, walls
    r = measure.measure(doc, sel(doc, "face", walls[0]),
                        sel(doc, "face", walls[1]))
    assert r["driver"] is None
    assert "same" in (r.get("move") or {}).get("error", ""), r.get("move")
    before = doc.to_data()
    plan = measure.plan_set(doc, sel(doc, "face", walls[0]),
                            sel(doc, "face", walls[1]), 12.0)
    assert "error" in plan
    assert doc.to_data() == before


def test_api_box_width_edit_verifies(client):
    """The user's exact gesture over HTTP: two opposite walls, type 8, and the
    box IS 8 wide - verified by the endpoint's own re-measure."""
    c = client
    c.post("/api/new", json={"name": "width-api"})
    _add(c, {"id": "b", "op": "plate",
             "params": {"width": 80, "depth": 60, "thickness": 12},
             "inputs": []})
    _add(c, {"id": "sk", "op": "sketch_on_face",
             "params": {"face": "top", "offset": 0,
                        "entities": [{"kind": "rectangle", "mode": "add",
                                      "w": 10, "h": 10, "x": -10, "y": 0}]},
             "inputs": ["b"]})
    _add(c, {"id": "boss", "op": "extrude", "params": {"amount": 5},
             "inputs": ["sk"]})
    _add(c, {"id": "j", "op": "fuse", "params": {}, "inputs": ["b", "boss"]})
    model = c.get("/api/model").json()
    body = model["bodies"][-1]
    walls = [f["id"] for f in body["faces"]
             if f.get("normal") and abs(abs(f["normal"][0]) - 1) < 1e-6
             and f["center"][2] > 6]
    assert len(walls) == 2, walls
    r = c.post("/api/measure/set", json={
        "a": {"body": body["id"], "kind": "face", "id": walls[0]},
        "b": {"body": body["id"], "kind": "face", "id": walls[1]},
        "value": 8.0}).json()
    assert r.get("error") is None, r
    assert r["verified"] is True, r
    assert r["achieved"] == pytest.approx(8.0, abs=1e-3)
    doc = c.get("/api/doc").json()
    sk = next(f for f in doc["features"] if f["id"] == "sk")
    assert sk["params"]["entities"][0]["w"] == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Section 6 review (2026-09-10), F2: a rebuild RENUMBERS faces, so verifying
# by the index the pick was made on threw away correct edits.

def shuffling_doc():
    """Four ⌀8 bores in a plate that also has a rectangular pocket.

    Changing one bore's diameter reorders `part.faces()` here, so the index the
    pick carried lands on a different face after the rebuild. That is not
    exotic: it happens on 7 of the 81 editable diameters across eight saved
    designs (x-frame, hole-box, bit-tray, pump-housing, gear-case)."""
    doc = Document(name="t-shuffle")
    doc.add("b", "plate", {"width": 120, "depth": 80, "thickness": 10})
    doc.add("sk", "sketch_on_face",
            {"face": "top", "offset": 0,
             "entities": [{"kind": "circle", "mode": "add", "x": x, "y": y, "r": 4}
                          for x, y in ((-40, -25), (-40, 25), (40, -25), (40, 25))]},
            inputs=["b"])
    doc.add("tool", "extrude", {"amount": -12}, inputs=["sk"])
    doc.add("cut", "cut", {}, inputs=["b", "tool"])
    doc.add("psk", "sketch_on_face",
            {"face": "top", "offset": 0,
             "entities": [{"kind": "rectangle", "mode": "add",
                           "x": 0, "y": 0, "w": 50, "h": 40}]},
            inputs=["cut"])
    doc.add("ptool", "extrude", {"amount": -4}, inputs=["psk"])
    doc.add("pk", "cut", {}, inputs=["cut", "ptool"])
    assert doc.rebuild(), doc.tree()
    return doc


def _shuffling_bore(doc):
    """The bore whose face index does NOT survive its own edit."""
    rid = doc._result_feature().id
    for i, f in enumerate(doc.result().faces()):
        if "CYLINDER" not in str(f.geom_type) or abs(f.radius - 4) > 1e-9:
            continue
        a = {"body": rid, "kind": "face", "id": i}
        if not measure.measure(doc, a).get("driver"):
            continue
        probe = shuffling_doc()
        plan = measure.plan_set(probe, a, None, 8.5)
        if "error" in plan:
            continue
        measure.write(probe, plan)
        probe._mark_stale()
        probe.rebuild()
        if abs(float(measure.measure(probe, a).get("value") or 0) - 8.5) > 1e-4:
            return a
    raise AssertionError("no bore in this fixture reorders on its own edit")


def test_relocate_finds_the_same_bore_after_the_indices_move():
    """The mechanism: the pick's geometry is still there, at another index."""
    doc = shuffling_doc()
    a = _shuffling_bore(doc)
    shape, body = measure.resolve(doc, a)
    sig = measure._signature(shape)
    assert sig and sig["kind"] == "axis"

    plan = measure.plan_set(doc, a, None, 8.5)
    measure.write(doc, plan)
    doc._mark_stale()
    doc.rebuild()

    moved = measure._relocate(doc, a, sig)
    assert moved["id"] != a["id"], "this fixture is supposed to renumber"
    got = measure.measure(doc, moved)
    assert got["kind"] == "diameter"
    assert got["value"] == pytest.approx(8.5, abs=1e-6)


def test_a_correct_diameter_edit_is_not_reverted_when_the_indices_move(client):
    """F2 end to end. Measured on the user's own x-frame: asking a Ø8 pad hole
    for 8.5 really made it 8.5 (volume 116961.18 -> 116896.39) and the tool
    then reverted it with 'the model came out at 8 mm — nothing was changed'.
    Seven of eight designs' editable diameters lost a correct edit this way."""
    doc = shuffling_doc()
    a = _shuffling_bore(doc)
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    studio._entry()["doc"] = doc
    studio._rebuild_and_mesh()

    r = client.post("/api/measure/set", json={"a": a, "value": 8.5}).json()
    assert r.get("error") is None, r.get("error")
    assert r["verified"] is True, r.get("warning")
    assert r.get("reverted") in (None, False)
    assert r["achieved"] == pytest.approx(8.5, abs=1e-6)
    ents = studio._doc().get("sk").params["entities"]
    assert sorted(e["r"] for e in ents) == pytest.approx([4, 4, 4, 4.25])


def test_the_panel_is_told_where_its_picks_went(client):
    """The frontend re-reads the SAME selection after a Set, so the response
    must hand back the relocated ids — otherwise the readout goes on showing
    the neighbouring bore's ⌀8 right after the user set 8.5."""
    doc = shuffling_doc()
    a = _shuffling_bore(doc)
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    studio._entry()["doc"] = doc
    studio._rebuild_and_mesh()

    r = client.post("/api/measure/set", json={"a": a, "value": 8.5}).json()
    assert "picks" in r, "the relocated picks come back with the answer"
    assert r["picks"]["a"]["id"] != a["id"]
    again = client.post("/api/measure", json={"a": r["picks"]["a"]}).json()
    assert again["value"] == pytest.approx(8.5, abs=1e-6)


def test_an_inch_size_typed_in_full_is_not_reverted(client):
    """F3 of the section 6 review (P2). The readout is rounded to 3 dp for
    display, and the verification compared that rounded number against the RAW
    request, so every dimension with more than three decimals was written
    perfectly and then thrown away: 5/16" = 7.9375, 7/16" = 11.1125.
    Measured: 18.0 kept; 7.9375, 11.1125 and 12.3456 all reverted with
    "asked for 7.9375 mm but the model came out at 7.938 mm"."""
    doc = pocket_doc()
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    studio._entry()["doc"] = doc
    studio._rebuild_and_mesh()
    a = sel(doc, "face", cyl_of(doc, 9))

    for want, param in ((7.9375, 3.96875), (11.1125, 5.55625)):
        r = client.post("/api/measure/set", json={"a": a, "value": want}).json()
        assert r.get("error") is None, r["error"]
        assert r["verified"] is True, r.get("warning")
        assert r.get("reverted") in (None, False)
        assert r["param"] == pytest.approx(param, abs=1e-9)
        # and the geometry really is that size, not just the param
        got = studio._doc().result()
        assert any(abs(float(f.radius) - param) < 1e-9
                   for f in got.faces() if "CYLINDER" in str(f.geom_type)), \
            f"no bore of r={param} in the rebuilt body"
        a = r["picks"]["a"]


def test_a_diameter_that_breaks_a_later_feature_is_put_back(client):
    """The safety net the section 6 review had to make EXPLICIT.

    Reverting a wrecked edit used to happen only because a wreck also
    renumbered the faces, and remeasure now sees through that renumbering. So
    the real question is asked directly: did a feature that built a moment ago
    stop building? Measured: a ⌀8 hole in a 60×40 plate grown to ⌀38 leaves the
    2 mm rim fillet nowhere to sit ("radius 2 mm does not fit on 15 edges")."""
    doc = Document(name="t-break")
    doc.add("b", "plate", {"width": 60, "depth": 40, "thickness": 10})
    doc.add("sk", "sketch_on_face",
            {"face": "top", "offset": 0,
             "entities": [{"kind": "circle", "mode": "add", "x": 0, "y": 0,
                           "r": 4}]}, inputs=["b"])
    doc.add("tool", "extrude", {"amount": -12}, inputs=["sk"])
    doc.add("cut", "cut", {}, inputs=["b", "tool"])
    doc.add("fl", "fillet", {"radius": 2, "edges": "all"}, inputs=["cut"])
    assert doc.rebuild(), doc.tree()
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    studio._entry()["doc"] = doc
    studio._rebuild_and_mesh()

    a = sel(doc, "face", cyl_of(doc, 4))
    before = client.get("/api/doc").json()["features"]
    r = client.post("/api/measure/set", json={"a": a, "value": 38.0}).json()

    assert r["verified"] is False, r
    assert r["reverted"] is True, r
    assert "stop fl from building" in r["warning"], r["warning"]
    assert client.get("/api/doc").json()["features"] == before, \
        "a dimension that breaks a feature left the design changed"
    # _revert_last swaps in a fresh Document, so ask the SERVER, not the
    # local reference this test happens to still hold
    assert studio._doc().get("sk").params["entities"][0]["r"] == 4
