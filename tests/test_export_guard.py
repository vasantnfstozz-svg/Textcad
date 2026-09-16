"""STEP export exports the FINISHED DESIGN — never the transient build state.

Locks in the 2026-08-31 bug: the sketch/extrude editors park the rollback
bar for edit isolation, and /api/export while it was parked wrote whatever
intermediate body was last built (a bare cavity-cutter slab reached the
user's CAM tool instead of their edited part). Also locks the canonical
location (designs/, next to the .tcad.json the MCP builds write) and the
measured-readback contract of the response.
"""
import os

import pytest
from fastapi.testclient import TestClient

import document
import studio

# A test that CHANGES the sample is no longer the library's flange-100, and
# since the section 12 review (2026-09-16) /api/export refuses to write over
# another design's .step exactly as /api/save refuses to write over its
# .tcad.json. Such a test names its own design — which is what the refusal
# tells a user to do too.
OWN_NAME = "_test-export-guard"


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    yield TestClient(studio.app)
    for name in ("flange-100.step", f"{OWN_NAME}.step"):
        step = studio.DESIGNS / name            # keep the library clean
        if step.exists():
            os.remove(step)


def test_export_lands_in_designs_and_is_measured(client):
    d = client.post("/api/export").json()
    assert "error" not in d
    assert d["path"] == str(studio.DESIGNS / "flange-100.step")
    assert os.path.exists(d["path"])
    # the response is measured FROM THE FILE, not assumed from the doc
    assert d["n_solids"] == 1
    assert d["volume"] > 0
    assert d["size"] == pytest.approx([100, 100, 10], abs=0.1)


def test_export_ignores_parked_rollback_bar(client):
    full = client.post("/api/export").json()          # ground truth, bar off
    d = client.post("/api/rollback", json={"feature_id": "body"}).json()
    assert d["rollback"] == "body"                    # bar parked mid-tree
    parked = client.post("/api/export").json()
    # the export contains the WHOLE design, not the body-only build state
    assert "error" not in parked
    assert parked["volume"] == pytest.approx(full["volume"], rel=1e-6)
    # ...and the bar is still parked afterwards (editors depend on it)
    assert client.get("/api/doc").json()["rollback"] == "body"


def test_export_refuses_failed_tail_by_name(client):
    studio._doc().name = OWN_NAME                 # its own design (see above)
    d = client.post("/api/feature/add", json={
        "id": "bad_fillet", "op": "fillet",
        "params": {"radius": 100000, "edges": "all"},
        "inputs": ["bolts"]}).json()
    assert d["features"][-1]["status"] == "failed"    # precondition
    d = client.post("/api/export").json()
    assert "error" in d
    assert "bad_fillet" in d["error"]
    assert "cannot export" in d["error"]


# ---------------------------------------------------------------------------
# EVERY body of the design reaches the file (2026-09-07)
#
# Reported: "when I am exporting step file of a design, and putting into
# another software, i can see only half part of design and rest of them are
# missing". Cause: to_step() exported Document.result() — ONE body, the last
# built leaf — while leaf_solid_ids() (and therefore the viewport) carry ALL
# of them. Measured on the user's designs/my-part-6: four leaf bodies,
# 424161.3 mm3 of design, exported STEP n_solids=1, volume 585.6 (0.14%).
# What you see in the viewport is what the file must contain.
# ---------------------------------------------------------------------------

import inspector
from document import Document


def _measure_export(doc, tmp_path):
    path = str(tmp_path / f"{doc.name}.step")
    doc.to_step(path)
    return inspector.measure(path)


def test_export_writes_every_separate_body(tmp_path):
    """Two disjoint leaf bodies -> two solids in the file, full volume."""
    doc = Document(name="two-bodies")
    doc.add("base", "plate", {"width": 80, "depth": 60, "thickness": 6})
    doc.add("wall_raw", "plate", {"width": 80, "depth": 6, "thickness": 50})
    doc.add("wall", "move", {"x": 0, "y": 0, "z": 28}, inputs=["wall_raw"])
    assert doc.rebuild()
    assert set(doc.leaf_solid_ids()) == {"base", "wall"}      # precondition

    m = _measure_export(doc, tmp_path)
    assert m["n_solids"] == 2, \
        "the STEP dropped a body the viewport shows"
    assert m["volume"] == pytest.approx(80 * 60 * 6 + 80 * 6 * 50, rel=1e-6)
    assert m["size"] == pytest.approx([80, 60, 56], abs=0.01)


def test_export_keeps_the_base_body_of_a_face_sketch_chain(tmp_path):
    """The user's my-part-6 shape, minimised: a body, a sketch on its face,
    and a plain extrude of that sketch. sketch_on_face does NOT consume the
    body, so the base stays a leaf and the extrude becomes a second one — the
    export used to hand over the extrude alone."""
    doc = Document(name="face-chain")
    doc.add("b", "plate", {"width": 60, "depth": 40, "thickness": 20})
    doc.add("sk", "sketch_on_face",
            {"face_center": [0, 0, 10], "face_normal": [0, 0, 1],
             "entities": [{"kind": "circle", "mode": "add",
                           "x": 0, "y": 0, "r": 8}]},
            inputs=["b"])
    doc.add("boss", "extrude", {"amount": 5}, inputs=["sk"])
    assert doc.rebuild()
    assert doc.leaf_solid_ids() == ["b", "boss"]              # precondition
    base_vol = doc._parts["b"].volume
    boss_vol = doc._parts["boss"].volume

    m = _measure_export(doc, tmp_path)
    assert m["n_solids"] == 2
    assert m["volume"] == pytest.approx(base_vol + boss_vol, rel=1e-6)
    # the whole part, not the 8mm boss on its own
    assert m["size"] == pytest.approx([60, 40, 25], abs=0.01)


def test_export_of_one_body_is_unchanged(tmp_path):
    """The everyday case must not gain an assembly wrapper or a solid."""
    doc = Document(name="one-body")
    doc.add("disc1", "disc", {"radius": 50, "thickness": 12})
    doc.add("bore", "with_center_hole", {"radius": 12}, inputs=["disc1"])
    assert doc.rebuild()
    assert doc.leaf_solid_ids() == ["bore"]                   # precondition

    m = _measure_export(doc, tmp_path)
    assert m["n_solids"] == 1
    assert m["volume"] == pytest.approx(doc._parts["bore"].volume, rel=1e-6)


def test_export_refuses_a_failed_body_that_is_not_the_tail(tmp_path):
    """A failed branch EARLIER than the tail is still a body of the design.
    Exporting the tail alone would silently ship a part with a piece missing
    — the very shape of this bug — so it is refused BY NAME instead."""
    doc = Document(name="failed-branch")
    doc.add("b1", "plate", {"width": 40, "depth": 40, "thickness": 10})
    doc.add("bad", "fillet", {"radius": 100000, "edges": "all"}, inputs=["b1"])
    doc.add("b2", "plate", {"width": 20, "depth": 20, "thickness": 5})
    doc.rebuild()
    assert doc.get("bad").status == "failed"                # precondition
    assert doc._result_feature().id == "b2"                   # ...and not the tail

    with pytest.raises(RuntimeError) as e:
        doc.to_step(str(tmp_path / "nope.step"))
    assert "bad" in str(e.value)
    assert "cannot export" in str(e.value)


def test_striking_the_failed_body_lets_the_rest_export(tmp_path):
    """The escape hatch: strike the broken feature and the design's remaining
    bodies export whole (b1 comes back as a leaf once 'bad' stops consuming
    it)."""
    doc = Document(name="struck-branch")
    doc.add("b1", "plate", {"width": 40, "depth": 40, "thickness": 10})
    doc.add("bad", "fillet", {"radius": 100000, "edges": "all"}, inputs=["b1"])
    doc.add("b2_raw", "plate", {"width": 20, "depth": 20, "thickness": 5})
    doc.add("b2", "move", {"x": 0, "y": 0, "z": 40}, inputs=["b2_raw"])
    doc.get("bad").suppressed = True
    assert doc.rebuild()
    assert set(doc.leaf_solid_ids()) == {"b1", "b2"}          # precondition

    m = _measure_export(doc, tmp_path)
    assert m["n_solids"] == 2
    assert m["volume"] == pytest.approx(40 * 40 * 10 + 20 * 20 * 5, rel=1e-6)


def test_export_response_measures_the_WHOLE_design(client):
    """/api/export's proof line is what the user reads to trust the file, so
    it must describe every body — the frontend only echoes these fields."""
    c = client
    studio._doc().name = OWN_NAME                 # its own design (see above)
    c.post("/api/feature/add", json={
        "id": "sk", "op": "sketch_on_face",
        "params": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                   "entities": [{"kind": "circle", "mode": "add",
                                 "x": 0, "y": 0, "r": 6}]},
        "inputs": ["bolts"]})
    r = c.post("/api/feature/add", json={
        "id": "boss", "op": "extrude", "params": {"amount": 9},
        "inputs": ["sk"]}).json()
    assert next(f for f in r["features"] if f["id"] == "boss")["status"] == "ok"
    doc = studio._doc()
    assert doc.leaf_solid_ids() == ["bolts", "boss"]          # precondition
    whole = sum(doc._parts[f].volume for f in doc.leaf_solid_ids())

    d = c.post("/api/export").json()
    assert "error" not in d, d
    assert d["n_solids"] == 2
    assert d["volume"] == pytest.approx(whole, rel=1e-6)


def test_the_body_count_still_describes_the_file_with_the_bar_parked(client):
    """`bodies` is what the browser's "this design has N separate bodies and
    all of them are in the file" sentence reads. It was counted AFTER to_step
    returned — and to_step RE-PARKS the rollback bar on its way out, so with an
    editor open (the very case the parked-bar guard exists for) the count
    described the isolated build state, not the file: 2 solids written, one
    body reported, and the sentence the multi-body export was written for never
    appeared (review 2026-09-07)."""
    c = client
    studio._doc().name = OWN_NAME                 # its own design (see above)
    c.post("/api/feature/add", json={
        "id": "sk", "op": "sketch_on_face",
        "params": {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                   "entities": [{"kind": "circle", "mode": "add",
                                 "x": 0, "y": 0, "r": 6}]},
        "inputs": ["bolts"]})
    c.post("/api/feature/add", json={
        "id": "boss", "op": "extrude", "params": {"amount": 9}, "inputs": ["sk"]})
    d = c.post("/api/export").json()
    assert d["n_solids"] == 2 and d["bodies"] == 2, d       # bar off: both agree
    assert c.post("/api/rollback", json={"feature_id": "bolts"}).json()["rollback"] == "bolts"
    assert len(studio._doc().result_bodies()) == 1, "precondition: the parked state is ONE body"
    d = c.post("/api/export").json()
    assert d["n_solids"] == 2, "the FILE holds every body"
    assert d["bodies"] == 2, "and the count the sentence reads must describe the file"


def test_export_response_proves_the_file_is_sound(client):
    """is_valid / is_manifold are measured from the WRITTEN FILE, so they
    cover every body in it. rebuild() validates each body separately; this
    readback proves the thing that was actually handed over."""
    d = client.post("/api/export").json()
    assert d["is_valid"] is True
    assert d["is_manifold"] is True
    assert d["bodies"] == 1


def test_mcp_report_measures_the_whole_design():
    """The MCP hands its measurements to an AI, which then believes them: a
    multi-body design measured through result() reported one body."""
    import mcp_server

    doc = Document(name="mcp-two-bodies")
    doc.add("base", "plate", {"width": 50, "depth": 50, "thickness": 8})
    doc.add("post_raw", "disc", {"radius": 6, "thickness": 20})
    doc.add("post", "move", {"x": 0, "y": 0, "z": 14}, inputs=["post_raw"])
    ok = doc.rebuild()
    assert set(doc.leaf_solid_ids()) == {"base", "post"}      # precondition

    rep = mcp_server._report(doc, ok)
    assert rep["bodies"] == 2
    assert rep["measured"]["n_solids"] == 2
    assert rep["measured"]["volume"] == pytest.approx(
        sum(doc._parts[f].volume for f in doc.leaf_solid_ids()), rel=1e-6)


def test_spec_is_checked_against_every_body(tmp_path):
    """The spec is the anti-hallucination guarantee, so it must describe the
    DESIGN. Checked against result() it measured the tail body alone: a 60x40
    plate with a small boss reported the boss's size as the part's size."""
    doc = Document(name="spec-two-bodies")
    doc.add("b", "plate", {"width": 60, "depth": 40, "thickness": 20})
    doc.add("post_raw", "disc", {"radius": 5, "thickness": 6})
    doc.add("post", "move", {"x": 0, "y": 0, "z": 13}, inputs=["post_raw"])
    doc.spec = {"size": [60, 40, 26], "tol": 0.3}
    assert doc.rebuild(), doc.spec_problems
    assert doc.spec_problems == []          # the WHOLE design is 60x40x26

    # ...and a spec that describes only the tail body is now REFUSED
    doc.spec = {"size": [10, 10, 6], "tol": 0.3}
    doc._spec_cache = None
    assert not doc.rebuild()
    assert any("dimension" in p for p in doc.spec_problems), doc.spec_problems


def test_spec_cache_notices_a_change_to_a_body_that_is_not_the_tail():
    """The cache key spans every leaf: signing only the tail's signature made
    an edit to another body hand back the previous verdict."""
    doc = Document(name="spec-cache")
    doc.add("b", "plate", {"width": 60, "depth": 40, "thickness": 20})
    doc.add("post_raw", "disc", {"radius": 5, "thickness": 6})
    doc.add("post", "move", {"x": 0, "y": 0, "z": 13}, inputs=["post_raw"])
    doc.spec = {"size": [60, 40, 26], "tol": 0.3}
    assert doc.rebuild(), doc.spec_problems

    # widen the BASE (not the tail) — the verdict must be recomputed
    doc.get("b").params["width"] = 90
    assert not doc.rebuild(), "a stale cached spec verdict was reused"
    assert any("X dimension is 90" in p for p in doc.spec_problems), \
        doc.spec_problems


def test_export_refuses_a_body_that_built_but_is_not_a_solid(tmp_path):
    """A cut that swallows its own body returns an EMPTY shape, not an
    exception, so rebuild() keeps the part and the old `part is None` gate let
    it through: the STEP held zero solids and the UI called that a successful
    export. (The user's 'mirror of a mirror = empty solid' lands here too.)"""
    doc = Document(name="empty-body")
    doc.add("small", "plate", {"width": 10, "depth": 10, "thickness": 4})
    doc.add("big", "plate", {"width": 40, "depth": 40, "thickness": 20})
    doc.add("gone", "cut", inputs=["small", "big"])
    doc.rebuild()
    assert doc.get("gone").status == "failed"                 # precondition
    assert doc._parts["gone"] is not None, "built a shape, just not a solid"

    with pytest.raises(RuntimeError) as e:
        doc.to_step(str(tmp_path / "nope.step"))
    assert "gone" in str(e.value)


def test_export_refuses_when_one_of_several_bodies_is_unhealthy(tmp_path):
    """The multi-body form: the healthy bodies must NOT be shipped on their
    own with plausible-looking measurements while a body is missing."""
    doc = Document(name="one-bad-body")
    doc.add("good", "plate", {"width": 40, "depth": 40, "thickness": 10})
    doc.add("small", "plate", {"width": 10, "depth": 10, "thickness": 4})
    doc.add("big", "plate", {"width": 40, "depth": 40, "thickness": 20})
    doc.add("gone", "cut", inputs=["small", "big"])
    doc.rebuild()
    assert doc.get("gone").status == "failed"                 # precondition

    with pytest.raises(RuntimeError) as e:
        doc.to_step(str(tmp_path / "nope.step"))
    assert "gone" in str(e.value)


def _two_body_doc():
    from document import Document
    doc = Document(name="two-bodies")
    doc.add("base", "plate", {"width": 40, "depth": 40, "thickness": 10})
    doc.add("boss", "plate", {"width": 10, "depth": 10, "thickness": 4})
    return doc


def test_the_deep_validity_check_sees_every_body_not_just_the_tail(monkeypatch):
    """rebuild()'s deep pass — OpenCASCADE's validity analysis, the one check
    the per-feature pass skips for speed — ran on the tree's TAIL only. A design
    legitimately has SEVERAL bodies (that is the whole point of the multi-body
    export), so an invalid body that was not the tail was never validated: its
    row stayed green and _export_blockers, which trusts `status`, let it into
    the file. An invalid solid reported as ok is the second of the two banned
    failures (house rule 5).

    A genuinely invalid solid cannot be built to order, so the check itself is
    stood in for — what is under test is WHICH bodies it is run on."""
    doc = _two_body_doc()
    seen = []

    def spy(part):
        seen.append(round(part.volume, 2))
        return len(seen) != 1              # the FIRST body (not the tail) is invalid

    monkeypatch.setattr(document, "_deep_valid", spy)
    assert doc.rebuild() is False, "an invalid body must fail the rebuild"
    assert doc.leaf_solid_ids() == ["base", "boss"]        # precondition: two bodies
    assert len(seen) == 2, f"only {len(seen)} body validated, not every body"
    assert doc.get("base").status == "failed"
    assert any("invalid" in p for p in doc.get("base").problems), doc.get("base").problems
    assert doc.get("boss").status == "ok", "the sound body is untouched"


def test_the_deep_check_is_paid_once_per_body_per_change(monkeypatch):
    """~270 ms a body: checking every body instead of one must not mean paying
    it again on every rebuild. The verdict rides the body's content signature,
    so a rebuild that changes nothing pays nothing — which also removes the
    repeat the TAIL used to pay on every single rebuild."""
    doc = _two_body_doc()
    calls = []
    monkeypatch.setattr(document, "_deep_valid", lambda part: calls.append(1) or True)
    assert doc.rebuild() is True
    assert len(calls) == 2, "one per body"
    assert doc.rebuild() is True
    assert len(calls) == 2, "nothing changed: no body is validated again"
    doc.get("base").params["width"] = 55
    assert doc.rebuild() is True
    assert len(calls) == 3, "only the body that changed is validated again"
