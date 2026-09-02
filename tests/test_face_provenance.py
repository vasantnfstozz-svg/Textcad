"""Face -> feature attribution ("which feature made this face?").

User request (2026-08-25): "if i am selecting a surface in the design, it should
highlight the feature tree, which sketch is that and what extrude we have over
there, it should be robust, don't try some simple parts — try the remote and
impeller examples."

So the corpus here is REAL designs, not toy boxes: designs/pump-impeller
(polar-patterned blades, moves, a fuse, a bored hub) and designs/fan-disk /
flange-style trees, plus the pocket-chain shape every AI design has. The
79-feature esp32-remote is verified separately (it rebuilds in 28-40 s, too slow
for the suite) — see MANUAL-DESIGN.md for those numbers.

The invariants matter more than the individual answers, because they hold for
EVERY face of a design:
  * coverage    — every face of the result attributes to some feature;
  * ancestry    — that feature is one the picked body actually descends from;
  * earliest    — no earlier feature also hosts the face (or the walk stopped
                  too late and blamed the wrong feature);
  * determinism — asking twice gives the same answer.
"""
import time

import pytest
from fastapi.testclient import TestClient

import provenance as P
import studio
from document import Document

# frozen copy, never the live library (LAUNCH-PLAN.md R6)
IMPELLER = "tests/fixtures/pump-impeller.tcad.json"


# --------------------------------------------------------------- fixtures ----

def pocket_doc():
    """The shape author.py emits: base body, then sketch -> tool prism -> cut."""
    doc = Document(name="t-prov-pocket")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 80, "h": 60, "x": 0, "y": 0}]})
    doc.add("body", "extrude", {"amount": 12}, inputs=["outline"])
    doc.add("pocket_sketch", "sketch", {"plane": "XY", "offset": 12,
            "entities": [{"kind": "circle", "r": 9, "x": 15, "y": 0}]})
    doc.add("pocket_tool", "extrude", {"amount": -5},
            inputs=["pocket_sketch"])
    doc.add("pocket", "cut", {}, inputs=["body", "pocket_tool"])
    assert doc.rebuild(), doc.tree()
    return doc


def flange_doc():
    doc = Document(name="t-prov-flange")
    doc.add("plate", "disc", {"radius": 50, "thickness": 10})
    doc.add("bore", "with_center_hole", {"radius": 15}, inputs=["plate"])
    doc.add("bolts", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 76},
            inputs=["bore"])
    assert doc.rebuild(), doc.tree()
    return doc


def attribute_all(doc):
    """Attribute EVERY face of the result. Returns (rows, faces, body_id)."""
    rf = doc._result_feature()
    part = doc.result()
    faces = part.faces()
    rows = [P.attribute_face(doc, body_id=rf.id, face_index=i, area=f.area)
            for i, f in enumerate(faces)]
    return rows, faces, rf.id


def face_at(doc, body, pred):
    """Index of the first result face matching a predicate (on the b3d Face)."""
    for i, f in enumerate(doc._parts[body].faces()):
        if pred(f):
            return i
    raise AssertionError("no face matched")


# ------------------------------------------------------- the pocket answer ---

def test_pocket_floor_names_its_sketch_and_extrude():
    """The whole point of the feature: click a pocket, learn where it came
    from."""
    doc = pocket_doc()
    # the floor of the pocket is the plane at z=7 (12 - 5)
    idx = face_at(doc, "pocket",
                  lambda f: abs(f.center().Z - 7) < 1e-6 and f.area < 500)
    r = P.attribute_face(doc, body_id="pocket", face_index=idx)
    assert r["origin"] == "pocket_tool"       # the geometry came from the tool
    assert r["applied_by"] == "pocket"        # the cut put it in this body
    assert r["feature"] == "pocket"           # ...and that is what we reveal
    assert r["sketch"] == "pocket_sketch"     # "which sketch is that"
    assert r["extrude"] == "pocket_tool"      # "what extrude we have there"
    # the chain is deduped: origin IS the extrude here, so it gets ONE row
    assert [c["id"] for c in r["chain"]] == ["pocket_sketch", "pocket_tool",
                                             "pocket"]
    assert [c["role"] for c in r["chain"]] == ["sketch", "extrude", "applied"]
    assert "pocket_sketch" in r["explanation"]


def test_pocket_wall_traces_to_the_same_sketch():
    doc = pocket_doc()
    idx = face_at(doc, "pocket", lambda f: str(f.geom_type).endswith("CYLINDER"))
    r = P.attribute_face(doc, body_id="pocket", face_index=idx)
    assert r["sketch"] == "pocket_sketch" and r["origin"] == "pocket_tool"


def test_untouched_top_face_belongs_to_the_base_extrude():
    """A face that SURVIVED 1..n later cuts still belongs to the feature that
    made it — not to the last feature that trimmed it."""
    doc = pocket_doc()
    idx = face_at(doc, "pocket",
                  lambda f: abs(f.center().Z - 12) < 1e-6 and f.area > 1000)
    r = P.attribute_face(doc, body_id="pocket", face_index=idx)
    assert r["origin"] == "body" and r["sketch"] == "outline"


def test_bolt_hole_belongs_to_the_bolt_circle_not_the_disc():
    doc = flange_doc()
    idx = face_at(doc, "bolts",
                  lambda f: str(f.geom_type).endswith("CYLINDER")
                  and abs(f.radius - 4) < 1e-6)
    r = P.attribute_face(doc, body_id="bolts", face_index=idx)
    assert r["origin"] == "bolts"
    idx = face_at(doc, "bolts",
                  lambda f: str(f.geom_type).endswith("CYLINDER")
                  and abs(f.radius - 15) < 1e-6)
    assert P.attribute_face(doc, body_id="bolts",
                            face_index=idx)["origin"] == "bore"


# ----------------------------------------------------------- invariants ------

def _check_invariants(doc, label):
    rows, faces, body = attribute_all(doc)
    n = len(faces)
    assert n, f"{label}: no faces"
    missed = [i for i, r in enumerate(rows) if not r.get("origin")]
    assert not missed, f"{label}: {len(missed)}/{n} faces unattributed: " \
                       f"{[(i, rows[i].get('reason')) for i in missed[:4]]}"

    anc = P._ancestors(doc, body)
    for i, r in enumerate(rows):
        assert r["origin"] in anc, \
            f"{label}: face {i} blamed on '{r['origin']}', not an ancestor"

    for i in range(0, n, max(1, n // 12)):      # determinism
        again = P.attribute_face(doc, body_id=body, face_index=i,
                                 area=faces[i].area)
        assert again["origin"] == rows[i]["origin"]

    order = [f for f in P._solid_features(doc, upto=body) if f in anc]
    for i in range(0, n, max(1, n // 12)):      # earliest
        o = rows[i]["origin"]
        if o not in order:
            continue
        tf = faces[i].wrapped
        key, bb = P.surface_key(tf), P._bbox(tf)
        pt = P.interior_point(faces[i])
        if pt is None:
            continue
        for earlier in order[:order.index(o)]:
            assert not P._hosts(P.feature_index(doc, earlier),
                                P._surface_type(tf), key, bb, pt,
                                len(key) > 1), \
                f"{label}: face {i} blamed on '{o}' but '{earlier}' has it too"
    return rows, n


def test_invariants_hold_for_every_face_of_a_pocket_chain():
    _check_invariants(pocket_doc(), "pocket")


def test_invariants_hold_for_every_face_of_a_flange():
    _check_invariants(flange_doc(), "flange")


@pytest.mark.parametrize("path", [IMPELLER])
def test_invariants_hold_for_every_face_of_the_impeller(path):
    """The user's own example: patterned blades, moved bodies, a fuse, a bore."""
    doc = Document.load(path)
    assert doc.rebuild(), doc.tree()
    rows, n = _check_invariants(doc, "impeller")
    # the blades must trace back to the blade sketch, not to the hub
    blades = [r for r in rows if r.get("sketch") == "blade_sketch"]
    assert len(blades) > n // 3, \
        f"only {len(blades)}/{n} faces traced to blade_sketch"
    assert any(r["origin_op"] == "polar_pattern" for r in rows), \
        "no face attributed to the pattern that created the blade copies"


# --------------------------------------------------- staying correct later ---

def test_attribution_survives_a_rename():
    doc = pocket_doc()
    doc.rename("pocket_sketch", "name_of_the_pocket")
    assert doc.rebuild()
    idx = face_at(doc, "pocket",
                  lambda f: str(f.geom_type).endswith("CYLINDER"))
    r = P.attribute_face(doc, body_id="pocket", face_index=idx)
    assert r["sketch"] == "name_of_the_pocket"


def test_cache_is_invalidated_by_a_rebuild():
    """The index is cached per feature part; an edit must not serve stale
    geometry (this cache was silently rebuilt on every query once — 22.8 ms a
    click — and the fix must not swing the other way into staleness)."""
    doc = pocket_doc()
    idx = face_at(doc, "pocket", lambda f: abs(f.center().Z - 7) < 1e-6
                  and f.area < 500)
    assert P.attribute_face(doc, body_id="pocket",
                            face_index=idx)["origin"] == "pocket_tool"
    doc.edit("pocket_tool", "amount", -8)        # floor moves to z=4
    assert doc.rebuild()
    idx2 = face_at(doc, "pocket", lambda f: abs(f.center().Z - 4) < 1e-6
                   and f.area < 500)
    r = P.attribute_face(doc, body_id="pocket", face_index=idx2)
    assert r["origin"] == "pocket_tool" and r["applied_by"] == "pocket"


def test_a_warm_query_is_fast_enough_to_feel_instant():
    doc = pocket_doc()
    attribute_all(doc)                            # warm the index
    faces = doc.result().faces()
    t0 = time.perf_counter()
    for i in range(len(faces)):
        P.attribute_face(doc, body_id="pocket", face_index=i,
                         area=faces[i].area)
    per = (time.perf_counter() - t0) / len(faces)
    assert per < 0.15, f"{per*1000:.0f} ms per query is too slow for a click"


def test_stale_face_index_falls_back_to_geometry():
    """The viewport's face ids come from the mesh it was sent; if the document
    was rebuilt since, the index can point at a different face. center+area
    catch that instead of confidently answering about the wrong face."""
    doc = pocket_doc()
    faces = doc.result().faces()
    idx = face_at(doc, "pocket", lambda f: abs(f.center().Z - 7) < 1e-6
                  and f.area < 500)
    want = faces[idx]
    c = want.center()
    r = P.attribute_face(doc, body_id="pocket",
                         face_index=(idx + 3) % len(faces),   # wrong index
                         center=[c.X, c.Y, c.Z], area=want.area)
    assert r["origin"] == "pocket_tool"        # resolved by geometry instead


def test_unknown_body_and_empty_doc_answer_honestly():
    empty = Document(name="t-empty")
    assert P.attribute_face(empty, body_id=None, face_index=0)["feature"] is None
    doc = pocket_doc()
    r = P.attribute_face(doc, body_id="no_such_body", face_index=0)
    assert r.get("origin") or r.get("reason")   # falls back to the result body
    bad = P.attribute_face(doc, body_id="pocket", face_index=9999)
    assert bad["feature"] is None and "resolve" in bad["reason"]


# ------------------------------------------- tessellation must not matter ----

def test_attribution_is_the_same_after_the_body_has_been_meshed():
    """THE bug this test exists for: BRepBndLib.Add_s(..., useTriangulation=
    True) quietly measures a face's bounding box from its TRIANGULATION once one
    exists. The viewport tessellates every body it draws, so in the real app —
    and only there — face boxes shifted, the containment rule started failing,
    and attribution slid onto much later features (42 of the impeller's 65 faces
    collapsed onto the final fuse). Every unit test stayed green because tests
    never mesh. So: mesh first, then demand the same answers."""
    doc = Document.load(IMPELLER)
    assert doc.rebuild()
    rf = doc._result_feature()
    faces = doc.result().faces()
    before = [P.attribute_face(doc, body_id=rf.id, face_index=i)["origin"]
              for i in range(len(faces))]

    studio._tagged_mesh(doc.result(), body_id=rf.id)      # what the viewport does
    for f in faces[:12]:
        f.tessellate(0.1)
    doc._prov_index = {}                                  # forget the cache too

    after = [P.attribute_face(doc, body_id=rf.id, face_index=i)["origin"]
             for i in range(len(faces))]
    drift = [(i, a, b) for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert not drift, f"{len(drift)} faces changed feature after meshing: " \
                      f"{drift[:5]}"


def test_pocket_attribution_survives_meshing_too():
    doc = pocket_doc()
    rf = doc._result_feature()
    faces = doc.result().faces()
    before = [P.attribute_face(doc, body_id=rf.id, face_index=i)["origin"]
              for i in range(len(faces))]
    studio._tagged_mesh(doc.result(), body_id=rf.id)
    doc._prov_index = {}
    after = [P.attribute_face(doc, body_id=rf.id, face_index=i)["origin"]
             for i in range(len(faces))]
    assert before == after
    assert "pocket_tool" in after       # the pocket is still traceable


# ---------------------------------------------------------------- HTTP API ---

@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(pocket_doc())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def test_api_face_feature_returns_the_chain(client):
    doc = studio._doc()
    idx = face_at(doc, "pocket", lambda f: abs(f.center().Z - 7) < 1e-6
                  and f.area < 500)
    r = client.post("/api/face-feature",
                    json={"body": "pocket", "face": idx}).json()
    assert r["feature"] == "pocket" and r["sketch"] == "pocket_sketch"
    assert [c["id"] for c in r["chain"]][:2] == ["pocket_sketch", "pocket_tool"]
    assert "pocket_sketch" in r["explanation"]


def test_api_face_feature_never_mutates_the_document(client):
    before = client.get("/api/doc").json()
    client.post("/api/face-feature", json={"body": "pocket", "face": 0})
    after = client.get("/api/doc").json()
    assert after["features"] == before["features"]
    assert after["can_undo"] == before["can_undo"]      # no snapshot pushed


def test_api_face_feature_survives_garbage(client):
    r = client.post("/api/face-feature", json={}).json()
    assert "feature" in r                       # answers, does not 500
    r = client.post("/api/face-feature",
                    json={"body": "pocket", "face": -5}).json()
    assert r["feature"] is None and r["reason"]
