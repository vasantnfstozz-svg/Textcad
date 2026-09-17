"""Sketch shapes as EDITABLE DIMENSIONS, not a JSON dump.

User request (2026-08-25): "when click the feature, we dont need see to
entities, and all, also if i am having sketch of square, i have to see lenth, in
the feature tree, if i want change it i can do it in the feature tree itself,
like that i can edit all shape in the feature tree as well extrude[.] another
examble, lets say we have piller, i can able to change outer diameter and inner
diameter as well, all parameter, i can change it in the feature tree, so it
should be robust."

The tree renders its rows from sketch.ENTITY_FIELDS, so the risk is DRIFT: a new
entity kind lands in _entity() and silently falls back to raw JSON in the UI.
The first test here fails in that case.
"""
import pytest
from fastapi.testclient import TestClient

import sketch as sk
import studio
from document import Document


# ------------------------------------------------------------- the catalog ---

def test_every_entity_kind_has_editable_dimensions_declared():
    """Drift guard: _entity() is the only other place that knows these field
    names. A kind it accepts but the catalog does not know would render as raw
    JSON again — exactly what the user asked us to remove."""
    in_code = sk.entity_kinds_in_code()
    assert in_code, "could not read the kinds out of _entity()"
    missing = in_code - set(sk.ENTITY_FIELDS)
    assert not missing, f"kinds with no dimension rows: {sorted(missing)}"
    extra = set(sk.ENTITY_FIELDS) - in_code
    assert not extra, f"catalog lists kinds _entity() rejects: {sorted(extra)}"


def test_declared_fields_are_the_ones_the_geometry_actually_reads():
    """Each declared key must really drive geometry: change it, and the built
    shape's area must change. A wrong key name would give the user a row that
    silently does nothing."""
    base = {
        "rectangle": {"kind": "rectangle", "w": 20, "h": 10},
        "circle": {"kind": "circle", "r": 8},
        "ellipse": {"kind": "ellipse", "rx": 10, "ry": 6},
        "slot": {"kind": "slot", "length": 30, "height": 8},
        "regular_polygon": {"kind": "regular_polygon", "radius": 10,
                            "sides": 6},
    }
    for kind, ent in base.items():
        area0 = sk.make_sketch(entities=[ent]).area
        for key, label, unit in sk.ENTITY_FIELDS[kind]:
            bumped = dict(ent)
            bumped[key] = (int(ent[key]) + 2 if unit == "count"
                           else ent[key] * 1.5)
            area1 = sk.make_sketch(entities=[bumped]).area
            assert abs(area1 - area0) > 1e-9, \
                f"{kind}.{key} ('{label}') did not change the geometry"


def test_geometry_list_kinds_are_flagged_not_dimensioned():
    """A traced path has no width/height to type — it must be declared as a
    coordinate-list shape so the tree offers a summary + the sketch editor."""
    for kind in ("path", "polygon"):
        assert sk.ENTITY_FIELDS[kind] == []
        assert kind in sk.ENTITY_GEOMETRY


def test_schema_is_json_safe_and_complete():
    sch = sk.entity_schema()
    assert set(sch) == {"fields", "common", "diameter", "geometry", "modes",
                        "strings", "server_outline"}      # text: a word, glyphs from the server
    assert sch["modes"] == ["add", "subtract"]
    assert {f["key"] for f in sch["fields"]["rectangle"]} == {"w", "h"}
    assert sch["diameter"]["circle"] == "r"        # Ø offered for round shapes
    assert {f["key"] for f in sch["common"]} == {"x", "y", "rotation"}
    import json
    json.loads(json.dumps(sch))                    # must survive the wire


# ------------------------------------------------- editing through the API ---

def square_doc():
    doc = Document(name="t-square")
    doc.add("sq", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 40, "x": 0, "y": 0,
         "mode": "add"}]})
    doc.add("block", "extrude", {"amount": 10}, inputs=["sq"])
    assert doc.rebuild(), doc.tree()
    return doc


def pillar_doc():
    """The user's "piller": a tube with an outer and an inner size."""
    doc = Document(name="t-pillar")
    doc.add("post", "tube", {"outer_radius": 20, "inner_radius": 8,
                             "height": 50})
    assert doc.rebuild(), doc.tree()
    return doc


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(square_doc())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def test_kinds_endpoint_serves_the_catalog(client):
    r = client.get("/api/sketch/kinds").json()
    assert {f["label"] for f in r["fields"]["rectangle"]} == {"width", "height"}
    assert r["geometry"]["path"] == "segments"


def test_editing_one_shape_dimension_rebuilds_the_solid(client):
    """What the tree's width row does: send the whole entities array back with
    one field changed."""
    before = client.get("/api/doc").json()
    vol0 = next(f for f in before["features"] if f["id"] == "block")["volume"]
    ents = next(f for f in before["features"]
                if f["id"] == "sq")["params"]["entities"]
    ents[0]["w"] = 80                                   # 40 -> 80 wide
    d = client.post("/api/edit", json={"feature_id": "sq", "param": "entities",
                                       "value": ents}).json()
    assert "error" not in d and d["ok"]
    vol1 = next(f for f in d["features"] if f["id"] == "block")["volume"]
    assert abs(vol1 - vol0 * 2) < 1e-6, f"{vol0} -> {vol1}"
    assert d["can_undo"]


def test_flipping_a_shape_to_subtract_cuts_a_hole(client):
    """The mode dropdown is a real geometry change, not decoration."""
    doc = client.get("/api/doc").json()
    ents = next(f for f in doc["features"]
                if f["id"] == "sq")["params"]["entities"]
    ents.append({"kind": "circle", "r": 10, "x": 0, "y": 0, "mode": "subtract"})
    d = client.post("/api/edit", json={"feature_id": "sq", "param": "entities",
                                       "value": ents}).json()
    assert d["ok"]
    vol = next(f for f in d["features"] if f["id"] == "block")["volume"]
    assert vol < 40 * 40 * 10                       # a hole came out of it


def test_editing_a_radius_by_diameter_halves_correctly(client):
    """What the Ø row does: the user types a diameter, we store the radius."""
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio._new_tab(pillar_doc())
    studio._rebuild_and_mesh()
    c = TestClient(studio.app)
    d = c.post("/api/edit", json={"feature_id": "post",
                                  "param": "outer_radius",
                                  "value": 60 / 2}).json()      # Ø60 -> r30
    assert d["ok"]
    assert next(f for f in d["features"]
                if f["id"] == "post")["params"]["outer_radius"] == 30
    d = c.post("/api/edit", json={"feature_id": "post",
                                  "param": "inner_radius",
                                  "value": 24 / 2}).json()      # Ø24 -> r12
    assert d["ok"] and d["features"][0]["params"]["inner_radius"] == 12


def test_a_bad_dimension_fails_loudly_and_undoes(client):
    """Typing nonsense must land as a feature problem, not a silent no-op."""
    doc = client.get("/api/doc").json()
    ents = next(f for f in doc["features"]
                if f["id"] == "sq")["params"]["entities"]
    ents[0]["w"] = -5
    d = client.post("/api/edit", json={"feature_id": "sq", "param": "entities",
                                       "value": ents}).json()
    assert not d["ok"]
    sq = next(f for f in d["features"] if f["id"] == "sq")
    assert sq["status"] == "failed" and sq["problems"]
    back = client.post("/api/undo").json()
    assert back["ok"]
