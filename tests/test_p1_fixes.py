"""P1 regression tests — the manual-design friction fixes from dogfooding
round 1 (2026-07-28):

  P1-a  viewport showed only the last body -> leaf_solid_ids() exposes all
  P1-c  fillet could not target vertical edges -> "vertical"/"horizontal" rules
  P1-d  dialogs lacked units/enums/conventions -> op_catalog metadata
  P1-e  empty server 500'd -> _entry() auto-creates an untitled doc
  P1-b  committed sketches were uneditable -> /api/feature/params (multi-set)
"""
import pytest

import build123d as b3d
import blocks
import author
from document import Document


# -------------------------------------------------- P1-a: all leaf bodies

def test_leaf_solids_lists_every_unconsumed_body():
    """Base + wall before a fuse: BOTH are leaves and must both be visible."""
    doc = Document(name="two-bodies")
    doc.add("base", "plate", {"width": 80, "depth": 60, "thickness": 6})
    doc.add("wall", "plate", {"width": 80, "depth": 6, "thickness": 50})
    assert doc.rebuild()
    assert set(doc.leaf_solid_ids()) == {"base", "wall"}


def test_leaf_solids_single_after_fuse():
    doc = Document(name="fused")
    doc.add("base", "plate", {"width": 80, "depth": 60, "thickness": 6})
    doc.add("wall", "plate", {"width": 80, "depth": 6, "thickness": 50})
    doc.add("joined", "fuse", inputs=["base", "wall"])
    assert doc.rebuild()
    assert doc.leaf_solid_ids() == ["joined"]     # base+wall consumed


def test_linear_chain_single_leaf_no_warning():
    doc = Document(name="flange")
    doc.add("disc1", "disc", {"radius": 50, "thickness": 12})
    doc.add("bore", "with_center_hole", {"radius": 12}, inputs=["disc1"])
    assert doc.rebuild()
    assert doc.leaf_solid_ids() == ["bore"]
    assert doc.warnings == []


# -------------------------------------------------- P1-c: fillet edge rules

def test_fillet_vertical_edges_rounds_box_corners():
    box = blocks.plate(100, 70, 40)
    out = blocks.fillet_edges(box, 5, edges="vertical")
    assert out.volume < box.volume            # material removed at 4 corners
    # only the 4 vertical edges rounded: bounding box unchanged in Z
    assert out.bounding_box().size.Z == pytest.approx(40, abs=1e-6)


def test_fillet_horizontal_edges():
    box = blocks.plate(100, 70, 40)
    out = blocks.fillet_edges(box, 3, edges="horizontal")
    assert out.volume < box.volume


def test_fillet_bad_edge_rule_lists_options():
    box = blocks.plate(20, 20, 20)
    with pytest.raises(ValueError, match="vertical"):
        blocks.fillet_edges(box, 2, edges="sideways")


def test_chamfer_vertical_edges():
    box = blocks.plate(40, 40, 20)
    out = blocks.chamfer_edges(box, 3, edges="vertical")
    assert out.volume < box.volume


# -------------------------------------------------- P1-d: catalog metadata

def test_op_catalog_marks_enums_and_units():
    cat = {c["op"]: c for c in author.op_catalog()}
    fillet = cat["fillet"]
    edges_p = next(p for p in fillet["params"] if p["name"] == "edges")
    assert edges_p["enum"] == ["all", "top", "bottom", "vertical", "horizontal"]
    disc = cat["disc"]
    radius_p = next(p for p in disc["params"] if p["name"] == "radius")
    assert radius_p["unit"] == "mm"
    assert disc["note"]                       # positioning convention present
    rot = cat["rotate"]
    axis_p = next(p for p in rot["params"] if p["name"] == "axis")
    assert axis_p["enum"] == ["X", "Y", "Z"]
    ang_p = next(p for p in rot["params"] if p["name"] == "angle_deg")
    assert ang_p["unit"] == "deg"


def test_op_catalog_extrude_both_still_boolean():
    cat = {c["op"]: c for c in author.op_catalog()}
    both = next(p for p in cat["extrude"]["params"] if p["name"] == "both")
    assert both["default"] is False           # stays a real bool -> checkbox


# -------------------------------------------------- P1-e / P1-b: Studio API

@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import studio
    studio.STATE = {"docs": {}, "active": None, "seq": 0}   # truly empty
    return TestClient(studio.app)


def test_empty_server_doc_does_not_500(client):
    """Fresh server with no tab open must degrade gracefully, not KeyError."""
    r = client.get("/api/doc")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "untitled"
    assert body["features"] == []


def test_docked_2d_sketch_editor_stays_deleted():
    """S4 (SKETCH-MODE-PLAN): the docked 2D SVG sketch editor was a separate
    flat screen — the model vanished and orbiting was impossible, violating
    fusion-parity rule 9 ('a mode is never a separate screen'). It was deleted:
    EVERY sketch (origin plane or picked face) runs in the 3D viewport. This
    locks the deletion in — none of its markup/hooks may come back."""
    from pathlib import Path
    static = Path(__file__).resolve().parents[1] / "static"
    banned = ["sketchDialog", "sketchCanvas", "skFaceExtrude", "skPlaneRow"]
    for rel in ["index.html", "css/studio.css", "js/sketcher.js"]:
        text = (static / rel).read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{token!r} resurfaced in static/{rel}"


def test_feature_params_sets_multiple_in_one_rebuild(client):
    client.post("/api/new", json={"name": "sk-edit"})
    client.post("/api/feature/add", json={
        "id": "s1", "op": "sketch",
        "params": {"plane": "XY", "offset": 0,
                   "entities": [{"kind": "circle", "r": 5}]}, "inputs": []})
    # edit the sketch's entities + offset at once (the sketch-editor path)
    r = client.post("/api/feature/params", json={
        "feature_id": "s1",
        "params": {"plane": "XY", "offset": 2,
                   "entities": [{"kind": "rectangle", "w": 30, "h": 20}]}})
    assert r.status_code == 200
    doc = r.json()
    s1 = next(f for f in doc["features"] if f["id"] == "s1")
    assert s1["params"]["offset"] == 2
    assert s1["params"]["entities"][0]["kind"] == "rectangle"
    assert s1["status"] == "ok"
