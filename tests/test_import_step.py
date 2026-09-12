"""import_step: STEP files come in as exact BREP solids.

User request (2026-08-31): "i can able to import step as well, becasue, i have
exported a compressor design here, but, if i want to open it again the same
file here, its not working". The defining test is therefore the ROUND TRIP:
a design exported from this app must come back in losslessly — same volume,
no meshing, no repair.
"""
import base64

import pytest
from fastapi.testclient import TestClient

import build123d as b3d
from build123d import Box, Compound, Pos

import blocks
import studio
from document import Document


# ------------------------------------------------------------- the block -----

def step_of(shape, tmp_path, name="t.step"):
    p = tmp_path / name
    b3d.export_step(shape, str(p))
    return str(p)


def test_roundtrip_preserves_the_exact_volume(tmp_path):
    """BREP in, BREP out: no faceting, so the volume is exact, not an
    approximation the way an STL round trip is."""
    part = blocks.with_center_hole(blocks.disc(30, 10), 8)
    p = step_of(part, tmp_path)
    back = blocks.import_step(p)
    assert back.volume == pytest.approx(part.volume, rel=1e-9)
    # still a real BREP: the bore is a CYLINDER face, not triangles
    assert any("CYLINDER" in str(f.geom_type) for f in back.faces())


def test_multi_solid_step_becomes_a_compound_not_a_fuse(tmp_path):
    two = Compound(children=[Box(10, 10, 10), Pos(30, 0, 0) * Box(5, 5, 5)])
    p = step_of(two, tmp_path)
    back = blocks.import_step(p)
    assert len(back.solids()) == 2
    assert back.volume == pytest.approx(1125.0)


def test_scale_resizes_on_import(tmp_path):
    p = step_of(Box(10, 10, 10), tmp_path)
    back = blocks.import_step(p, scale=2.0)
    assert back.volume == pytest.approx(8000.0)


def test_errors_are_friendly_valueerrors(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        blocks.import_step("no-such-file.step")
    junk = tmp_path / "junk.step"
    junk.write_text("this is not a STEP file")
    with pytest.raises(ValueError):
        blocks.import_step(str(junk))
    notstep = tmp_path / "box.stl"
    notstep.write_text("solid x endsolid x")
    with pytest.raises(ValueError, match="not a STEP"):
        blocks.import_step(str(notstep))
    p = step_of(Box(1, 1, 1), tmp_path)
    with pytest.raises(ValueError, match="scale"):
        blocks.import_step(p, scale=0)


def test_import_step_works_inside_a_document_tree(tmp_path):
    """The op must be a first-class tree citizen: buildable, healthy, and a
    valid input to a boolean like any other body."""
    p = step_of(Box(40, 30, 10), tmp_path)
    doc = Document(name="t-step-tree")
    doc.add("imp", "import_step", {"file": p, "scale": 1.0}, [])
    doc.add("hole_sk", "sketch_on_face", {"face": "top", "offset": 0,
            "entities": [{"kind": "circle", "mode": "add",
                          "x": 0, "y": 0, "r": 4}]}, inputs=["imp"])
    doc.add("hole_tool", "extrude", {"amount": -10}, inputs=["hole_sk"])
    doc.add("hole", "cut", {}, inputs=["imp", "hole_tool"])
    assert doc.rebuild(), doc.tree()
    vol = doc.result().volume
    import math
    assert vol == pytest.approx(40 * 30 * 10 - math.pi * 16 * 10, rel=1e-6)


# ------------------------------------------------------------- the API -------

@pytest.fixture
def client():
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    return TestClient(studio.app)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_api_upload_creates_the_feature(client, tmp_path):
    p = step_of(Box(20, 10, 5), tmp_path)
    client.post("/api/new", json={"name": "step-api"})
    r = client.post("/api/import-step", json={
        "step_base64": _b64(open(p, "rb").read()),
        "feature_id": "my-box"}).json()
    assert r.get("error") is None, r
    info = r["import_info"]
    assert info["feature_id"] == "my-box"
    assert info["bodies"] == 1
    assert info["volume_mm3"] == pytest.approx(1000.0)
    feats = {f["id"]: f for f in r["features"]}
    assert feats["my-box"]["op"] == "import_step"
    assert feats["my-box"]["status"] == "ok"
    # the file landed in imports/ so the tree rebuilds from disk
    assert (blocks.IMPORTS_DIR / info["file"]).is_file()


def test_api_garbage_leaves_no_feature_and_no_stray_file(client):
    client.post("/api/new", json={"name": "step-bad"})
    before = set(f.name for f in blocks.IMPORTS_DIR.glob("*.step"))
    r = client.post("/api/import-step", json={
        "step_base64": _b64(b"not a step at all"),
        "feature_id": "bad-step"}).json()
    assert "error" in r
    assert all(f["id"] != "bad-step" for f in r["features"])
    after = set(f.name for f in blocks.IMPORTS_DIR.glob("*.step"))
    assert after == before, "a rejected upload left its file behind"


def test_the_users_own_export_reimports(client):
    """The exact reported flow: design something HERE, export it, then bring
    the produced .step back in — in a fresh tab — and get the same solid."""
    client.post("/api/new", json={"name": "roundtrip-src"})
    r = client.post("/api/feature/add", json={
        "id": "b", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 9}, "inputs": []}).json()
    assert next(f for f in r["features"] if f["id"] == "b")["status"] == "ok"
    src_vol = 60 * 40 * 9

    exp = client.post("/api/export").json()
    assert exp.get("error") is None, exp
    data = open(exp["path"], "rb").read()

    client.post("/api/new", json={"name": "roundtrip-dst"})
    r = client.post("/api/import-step", json={
        "step_base64": _b64(data), "feature_id": "roundtrip"}).json()
    assert r.get("error") is None, r
    assert r["import_info"]["volume_mm3"] == pytest.approx(src_vol, rel=1e-6)
    assert r["ok"] is True


def test_a_file_that_is_not_step_is_named_as_such(tmp_path):
    """Measured 2026-09-12 (section 8 review): OCCT's STEP reader does not
    raise on a file that is not STEP — it prints its own parse error to the
    server console and hands back an empty shape, so every such file was
    diagnosed as "the file contains no solid bodies — surfaces or curves
    alone cannot be used here", sending the user to look for surfaces in a
    file that was never STEP."""
    p = tmp_path / "notstep.step"
    p.write_bytes(b"hello world")
    with pytest.raises(ValueError, match="not a STEP file"):
        blocks.import_step(str(p))

    q = tmp_path / "really_an_stl.stp"
    q.write_bytes(b"\0" * 80 + b"\x00\x00\x00\x00")
    with pytest.raises(ValueError, match="not a STEP file"):
        blocks.import_step(str(q))


def test_a_real_step_still_opens(tmp_path):
    """The guard must not cost the round trip it exists for."""
    p = tmp_path / "ok.step"
    b3d.export_step(b3d.Box(10, 10, 10), str(p))
    part = blocks.import_step(str(p))
    assert part.volume == pytest.approx(1000, rel=1e-6)
