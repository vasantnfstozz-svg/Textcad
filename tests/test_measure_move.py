"""P2: changing a DERIVED distance by moving one side.

The user's own example (2026-08-27): "in esp 32 remote, distanse bewteen a
pillar to wall is 10, and i am changine the it 8, the pillar should move to
wall".

That 10 mm is stored nowhere — the pillar's coordinates live in one sketch, the
wall's in another, and the number is their subtraction. So there is no param to
overwrite; the only honest change is to move ONE side, and the only safe way is
to be explicit about which. These tests pin down three things:

  * the RIGHT side moves by default (the later feature; the earlier one is
    stock or a datum) and the other side is left untouched — asserted, because
    "it moved something" is not the same as "it moved the pillar";
  * the geometry really lands on the requested number, re-measured;
  * a distance that runs along the sketch's DEPTH is refused, because sliding a
    profile sideways would not change it at all.
"""
import pytest

import measure
from document import Document


def cavity_doc():
    """80x60x12 plate, a 60x40 cavity 8 deep, and a 10x10 pillar left standing
    inside it at x=-10.

    Known by construction: the cavity's -X wall sits at x=-30 and the pillar's
    -X wall at x=-15, so the gap is 15 mm. The pillar's sketch is LATER in the
    tree than the cavity's, so the pillar is what should move.

    Note the construction: the pillar tool is cut OUT of the cavity tool and
    that negative is cut from the body. Cutting the pillar back in afterwards
    would not leave an island.
    """
    doc = Document(name="t-move")
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


def sel(doc, i):
    return {"body": doc._result_feature().id, "kind": "face", "id": i}


def x_walls(doc, above_z=4):
    """{rounded x: face index} for the vertical X-facing walls up top."""
    out = {}
    for i, f in enumerate(doc.result().faces()):
        n = f.normal_at(f.center())
        c = f.center()
        if abs(abs(n.X) - 1) < 1e-9 and c.Z > above_z:
            out[round(c.X, 2)] = i
    return out


def the_pair(doc):
    """(cavity -X wall, pillar -X wall) — 15 mm apart by construction."""
    w = x_walls(doc)
    assert -30 in w and -15 in w, f"walls at {sorted(w)}"
    return w[-30], w[-15]


# ------------------------------------------------------------- the measure ---

def test_the_gap_is_measured_and_reported_movable():
    doc = cavity_doc()
    a, b = the_pair(doc)
    r = measure.measure(doc, sel(doc, a), sel(doc, b))
    assert r["kind"] == "gap"
    assert r["value"] == pytest.approx(15.0)
    assert r["driver"] is None, "a derived gap has no single param"
    mv = r["move"]
    assert "error" not in mv, mv
    assert mv["side"] == "b", "the pillar (later in the tree) should move"
    assert mv["feature"] == "isl_sk"
    assert set(mv["movable"]) == {"a", "b"}


# --------------------------------------------------------------- the move ----

def test_reducing_the_gap_moves_the_pillar_not_the_wall():
    """The user's request, end to end."""
    doc = cavity_doc()
    a, b = the_pair(doc)
    cavity_before = dict(doc.get("cav_sk").params["entities"][0])

    plan = measure.plan_set(doc, sel(doc, a), sel(doc, b), 8.0)
    assert "error" not in plan, plan
    assert plan["move"]["feature"] == "isl_sk"
    assert plan["move"]["by"] == pytest.approx([-7.0, 0.0])

    measure.write(doc, plan)
    assert doc.rebuild(), doc.tree()

    assert doc.get("isl_sk").params["entities"][0]["x"] == pytest.approx(-17.0)
    assert doc.get("cav_sk").params["entities"][0] == cavity_before, \
        "the datum wall moved — only the pillar should have"

    # re-measure by GEOMETRY, because face indices shift on a rebuild
    w = x_walls(doc)
    assert -30 in w and -22 in w, f"walls at {sorted(w)}"
    again = measure.measure(doc, sel(doc, w[-30]), sel(doc, w[-22]))
    assert again["value"] == pytest.approx(8.0), again


def test_growing_the_gap_works_too():
    """The sign must follow the request, not only ever shrink."""
    doc = cavity_doc()
    a, b = the_pair(doc)
    plan = measure.plan_set(doc, sel(doc, a), sel(doc, b), 20.0)
    assert "error" not in plan, plan
    assert plan["move"]["by"] == pytest.approx([5.0, 0.0])
    measure.write(doc, plan)
    assert doc.rebuild(), doc.tree()
    w = x_walls(doc)
    assert -30 in w and -10 in w, f"walls at {sorted(w)}"
    again = measure.measure(doc, sel(doc, w[-30]), sel(doc, w[-10]))
    assert again["value"] == pytest.approx(20.0)


def test_the_user_can_move_the_other_side_instead():
    doc = cavity_doc()
    a, b = the_pair(doc)
    pillar_before = dict(doc.get("isl_sk").params["entities"][0])
    plan = measure.plan_set(doc, sel(doc, a), sel(doc, b), 8.0, side="a")
    assert "error" not in plan, plan
    assert plan["move"]["feature"] == "cav_sk"
    assert plan["move"]["by"] == pytest.approx([7.0, 0.0])
    measure.write(doc, plan)
    assert doc.rebuild(), doc.tree()
    assert doc.get("isl_sk").params["entities"][0] == pillar_before, \
        "asked to move the wall, moved the pillar instead"


def test_a_move_writes_both_x_and_y():
    """The write is one list, so an entity can never end up half-moved."""
    doc = cavity_doc()
    a, b = the_pair(doc)
    plan = measure.plan_set(doc, sel(doc, a), sel(doc, b), 8.0)
    paths = [p for p, _ in plan["writes"]]
    assert paths == [["entities", 0, "x"], ["entities", 0, "y"]]


# ------------------------------------------------------------- refusals ------

def test_a_depth_distance_is_refused_not_slid_sideways():
    """A pocket floor to the part's underside is controlled by the extrude
    depth, not by where the profile sits. Sliding the profile in-plane would
    not change the number at all, so it must be refused with the reason."""
    doc = cavity_doc()
    faces = doc.result().faces()
    floor = next(i for i, f in enumerate(faces)
                 if abs(f.normal_at(f.center()).Z - 1) < 1e-9
                 and abs(f.center().Z - 4) < 1e-6)
    bottom = next(i for i, f in enumerate(faces)
                  if abs(f.normal_at(f.center()).Z + 1) < 1e-9)
    r = measure.measure(doc, sel(doc, floor), sel(doc, bottom))
    assert r["kind"] == "thickness"
    before = doc.to_data()
    plan = measure.plan_set(doc, sel(doc, floor), sel(doc, bottom), 6.0)
    assert "error" in plan
    assert "depth" in plan["error"]
    assert doc.to_data() == before, "a refused move must change nothing"


def test_non_parallel_faces_are_refused():
    doc = cavity_doc()
    faces = doc.result().faces()
    top = next(i for i, f in enumerate(faces)
               if abs(f.normal_at(f.center()).Z - 1) < 1e-9)
    side = next(i for i, f in enumerate(faces)
                if abs(abs(f.normal_at(f.center()).X) - 1) < 1e-9)
    plan = measure.plan_set(doc, sel(doc, top), sel(doc, side), 5.0)
    assert "error" in plan
    assert "not parallel" in plan["error"]


def test_a_primitive_wall_is_not_movable():
    """A plate made by the `plate` op has no sketch entity behind its walls, so
    neither side can move and it must say so rather than inventing one."""
    doc = Document(name="t-prim")
    doc.add("b", "plate", {"width": 80, "depth": 60, "thickness": 12})
    assert doc.rebuild(), doc.tree()
    faces = doc.result().faces()
    xs = [i for i, f in enumerate(faces)
          if abs(abs(f.normal_at(f.center()).X) - 1) < 1e-9]
    assert len(xs) >= 2
    r = measure.measure(doc, sel(doc, xs[0]), sel(doc, xs[1]))
    assert r["value"] == pytest.approx(80.0)
    assert r["move"].get("error"), "must explain why nothing can move"
    plan = measure.plan_set(doc, sel(doc, xs[0]), sel(doc, xs[1]), 70.0)
    assert "error" in plan


# ------------------------------------------------------------- over HTTP -----

def test_api_move_shrinks_a_gap_and_verifies_it():
    """The move path over HTTP, including the verification the endpoint does
    for itself: it re-measures the same pick and reports what it became."""
    from fastapi.testclient import TestClient
    import studio
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    c = TestClient(studio.app)

    c.post("/api/new", json={"name": "move-api"})
    for f in (
        {"id": "outline", "op": "sketch",
         "params": {"plane": "XY", "entities": [
             {"kind": "rectangle", "mode": "add", "w": 80, "h": 60,
              "x": 0, "y": 0}]}, "inputs": []},
        {"id": "body", "op": "extrude", "params": {"amount": 12},
         "inputs": ["outline"]},
        {"id": "cav_sk", "op": "sketch_on_face",
         "params": {"face": "top", "offset": 0, "entities": [
             {"kind": "rectangle", "mode": "add", "w": 60, "h": 40,
              "x": 0, "y": 0}]}, "inputs": ["body"]},
        {"id": "cav_tool", "op": "extrude", "params": {"amount": -8},
         "inputs": ["cav_sk"]},
        {"id": "isl_sk", "op": "sketch_on_face",
         "params": {"face": "top", "offset": 0, "entities": [
             {"kind": "rectangle", "mode": "add", "w": 10, "h": 10,
              "x": -10, "y": 0}]}, "inputs": ["body"]},
        {"id": "isl_tool", "op": "extrude", "params": {"amount": -12},
         "inputs": ["isl_sk"]},
        {"id": "cav_neg", "op": "cut", "params": {},
         "inputs": ["cav_tool", "isl_tool"]},
        {"id": "cavity", "op": "cut", "params": {},
         "inputs": ["body", "cav_neg"]},
    ):
        out = c.post("/api/feature/add", json=f).json()
        got = next(x for x in out["features"] if x["id"] == f["id"])
        assert got["status"] == "ok", (f["id"], got["problems"])

    model = c.get("/api/model").json()
    body = model["bodies"][-1]
    walls = {round(f["center"][0], 2): f["id"] for f in body["faces"]
             if f.get("normal") and abs(abs(f["normal"][0]) - 1) < 1e-6
             and f["center"][2] > 4}
    assert -30 in walls and -15 in walls, sorted(walls)

    r = c.post("/api/measure/set", json={
        "a": {"body": body["id"], "kind": "face", "id": walls[-30]},
        "b": {"body": body["id"], "kind": "face", "id": walls[-15]},
        "value": 8.0}).json()
    assert r.get("error") is None, r
    assert r["move"]["feature"] == "isl_sk", r["move"]
    assert r["verified"] is True, r
    assert r["achieved"] == pytest.approx(8.0, abs=1e-3)

    doc = c.get("/api/doc").json()
    isl = next(f for f in doc["features"] if f["id"] == "isl_sk")
    assert isl["params"]["entities"][0]["x"] == pytest.approx(-17.0)
    # and the datum sketch is untouched
    cav = next(f for f in doc["features"] if f["id"] == "cav_sk")
    assert cav["params"]["entities"][0]["x"] == pytest.approx(0.0)


def test_only_one_movable_side_still_works():
    """A `plate` primitive has no sketch behind its walls, but a sketched boss
    standing on it does. Exactly one side can move, so there is nothing to
    choose — the tool must just move it rather than refusing or asking."""
    doc = Document(name="t-one-side")
    doc.add("b", "plate", {"width": 80, "depth": 60, "thickness": 12})
    doc.add("boss_sk", "sketch_on_face", {"face": "top", "offset": 0,
            "entities": [{"kind": "rectangle", "mode": "add",
                          "w": 20, "h": 20, "x": 10, "y": 0}]}, inputs=["b"])
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("j", "fuse", {}, inputs=["b", "boss"])
    assert doc.rebuild(), doc.tree()

    faces = doc.result().faces()
    # the plate's -X outer wall (x=-40) and the boss's -X wall (x=0): 40 apart
    plate_w = next(i for i, f in enumerate(faces)
                   if abs(f.normal_at(f.center()).X + 1) < 1e-9
                   and abs(f.center().X + 40) < 1e-6)
    boss_w = next(i for i, f in enumerate(faces)
                  if abs(f.normal_at(f.center()).X + 1) < 1e-9
                  and abs(f.center().X) < 1e-6 and f.center().Z > 6)

    r = measure.measure(doc, sel(doc, plate_w), sel(doc, boss_w))
    assert r["value"] == pytest.approx(40.0), r
    assert r["move"]["movable"] == ["b"], "only the boss can move"
    assert r["move"]["side"] == "b"

    plan = measure.plan_set(doc, sel(doc, plate_w), sel(doc, boss_w), 30.0)
    assert "error" not in plan, plan
    measure.write(doc, plan)
    assert doc.rebuild(), doc.tree()
    assert doc.get("boss_sk").params["entities"][0]["x"] == pytest.approx(0.0)


def test_a_move_that_wrecks_the_part_reverts_itself():
    """User report 2026-08-27: "i tried to move the box … i chnages but, still
    it was not moving".

    Found by clicking every wall pair a user can reach from one iso view. From
    a single view the two facing walls of a gap are never both visible, so the
    natural pick is two walls pointing the SAME way — a step. Asking for a
    small step there translates the whole profile far enough to leave the part,
    which changes the topology: the old code wrote it, failed its own
    verification, and left the wrecked part behind with only a warning.

    A dimension the user asked for and did not get must put the design back."""
    from fastapi.testclient import TestClient
    import studio
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    c = TestClient(studio.app)
    c.post("/api/new", json={"name": "revert-demo"})
    for f in (
        {"id": "outline", "op": "sketch",
         "params": {"plane": "XY", "entities": [
             {"kind": "rectangle", "mode": "add", "w": 80, "h": 60,
              "x": 0, "y": 0}]}, "inputs": []},
        {"id": "body", "op": "extrude", "params": {"amount": 12},
         "inputs": ["outline"]},
        {"id": "cav_sk", "op": "sketch_on_face",
         "params": {"face": "top", "offset": 0, "entities": [
             {"kind": "rectangle", "mode": "add", "w": 60, "h": 40,
              "x": 0, "y": 0}]}, "inputs": ["body"]},
        {"id": "cav_tool", "op": "extrude", "params": {"amount": -8},
         "inputs": ["cav_sk"]},
        {"id": "cavity", "op": "cut", "params": {},
         "inputs": ["body", "cav_tool"]},
    ):
        out = c.post("/api/feature/add", json=f).json()
        got = next(x for x in out["features"] if x["id"] == f["id"])
        assert got["status"] == "ok", (f["id"], got["problems"])

    model = c.get("/api/model").json()
    body = model["bodies"][-1]
    # the plate's -Y outer wall and the cavity's +Y wall BOTH point -Y, so they
    # are a step of 50 mm — and both are visible from one iso view, which is
    # exactly why a user picks them
    ys = {round(f["center"][1], 1): f["id"] for f in body["faces"]
          if f.get("normal") and abs(f["normal"][1] + 1) < 1e-6}
    assert -30.0 in ys and 20.0 in ys, sorted(ys)

    before = c.get("/api/doc").json()["features"]
    r = c.post("/api/measure/set", json={
        "a": {"body": body["id"], "kind": "face", "id": ys[-30.0]},
        "b": {"body": body["id"], "kind": "face", "id": ys[20.0]},
        "value": 5.0}).json()

    assert r.get("verified") is False, r
    assert r.get("reverted") is True, r
    assert "nothing was changed" in r.get("warning", ""), r
    assert c.get("/api/doc").json()["features"] == before, \
        "a failed move left the design changed"
