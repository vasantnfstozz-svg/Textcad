"""The Examples gallery: the designs actually built in this tool.

User request (2026-08-26): "i designed water pump and esp32 remote and some box
company logo with many cuts, like this did many things, collect all those design
put it under in the example tab."

File > Examples used to be three hardcoded code samples (flange, impeller,
compressor) while 27 real designs sat unlisted in File > Open next to scratch
files. The gallery is driven by designs/examples.json, so these tests guard the
things that rot: a catalogued design whose file was renamed, a description that
drifts from the actual feature count, and a thumbnail route that could be talked
into serving something outside designs/.
"""
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

import studio
from document import Document

DESIGNS = pathlib.Path(studio.DESIGNS)
CATALOG = DESIGNS / "examples.json"


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(Document(name="untitled"))
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


# ------------------------------------------------------------- the catalog ---

def test_the_catalog_exists_and_is_grouped():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    groups = data["groups"]
    assert len(groups) >= 5
    for g in groups:
        assert g["group"] and g["designs"]
        for d in g["designs"]:
            assert d["file"] and d["title"] and d["description"]


def test_every_catalogued_design_still_exists_and_loads():
    """A renamed or deleted design must not sit in the gallery as a dead tile.

    The catalog's stored `features` number is NOT compared any more: /api/examples
    derives the count from the file ("so it cannot drift from the catalog"), so
    the stored copy is dead data, and pinning it turned this test red every time
    the user edited a catalogued design in the app (LAUNCH-PLAN.md R6)."""
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    for g in data["groups"]:
        for d in g["designs"]:
            p = DESIGNS / f"{d['file']}.tcad.json"
            assert p.exists(), f"catalogued but missing: {d['file']}"
            doc = json.loads(p.read_text(encoding="utf-8"))
            assert doc.get("features"), f"{d['file']}: no features in the file"


def test_the_user_s_own_projects_are_all_in_there():
    """The designs the user named, plus the families they belong to."""
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    files = {d["file"] for g in data["groups"] for d in g["designs"]}
    for must in ("esp32-remote",                       # "esp32 remote"
                 "pump-housing", "pump-impeller",      # "water pump"
                 "pump-cover", "pump-gasket",
                 "autonomiq-sat-panel",                # the company logo work
                 "autonomiq-panel",
                 "cam-cover-plaque", "isogrid-panel", "wing-rib"):
        assert must in files, f"{must} is missing from the gallery"


def test_scratch_files_are_not_in_the_gallery():
    """t-washer and my-part-3 are test debris, not examples; they stay
    reachable through File > Open."""
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    files = {d["file"] for g in data["groups"] for d in g["designs"]}
    for junk in ("t-washer", "untitled", "my-part", "my-part-2", "my-part-3",
                 "popup-test-washer", "mcp-live-washer"):
        assert junk not in files, f"{junk} should not be an example"


def test_no_design_is_listed_twice():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    files = [d["file"] for g in data["groups"] for d in g["designs"]]
    assert len(files) == len(set(files))


# ------------------------------------------------------------------- API -----

def test_examples_endpoint_serves_the_groups(client):
    r = client.get("/api/examples").json()
    assert "error" not in r
    names = [g["group"] for g in r["groups"]]
    assert len(names) >= 5 and len(set(names)) == len(names)
    total = sum(len(g["designs"]) for g in r["groups"])
    assert total >= 20
    esp = next(d for g in r["groups"] for d in g["designs"]
               if d["file"] == "esp32-remote")
    # NOT a hard-coded count: the point is that the API reports what the
    # FILE says, so a design revision must never make this test fail.
    on_disk = len(json.loads((DESIGNS / "esp32-remote.tcad.json")
                             .read_text(encoding="utf-8"))["features"])
    assert esp["features"] == on_disk and esp["title"] and esp["description"]
    assert esp["name"] == "esp32-remote"          # from the file, not the catalog


def test_every_gallery_tile_has_a_thumbnail(client):
    r = client.get("/api/examples").json()
    for g in r["groups"]:
        for d in g["designs"]:
            assert d["preview"] is True, f"{d['file']} has no preview render"
            img = client.get(f"/api/design-preview/{d['file']}")
            assert img.status_code == 200
            assert img.headers["content-type"] == "image/png"
            assert img.content[:8] == b"\x89PNG\r\n\x1a\n"
            assert len(img.content) < 400_000, \
                f"{d['file']} thumbnail is {len(img.content)//1024} KB"


def test_preview_route_cannot_escape_the_designs_folder(client):
    for evil in ("../studio", "..%2Fstudio", "../../etc/passwd", "a/../../b"):
        r = client.get(f"/api/design-preview/{evil}")
        assert r.status_code == 404, f"{evil} was served!"


def test_opening_a_gallery_design_gives_a_working_tab(client):
    """Clicking a tile calls /api/open — the design must build, not just load."""
    before = len(client.get("/api/doc").json()["tabs"])
    d = client.post("/api/open/pump-impeller").json()
    assert "error" not in d
    assert d["name"] == "pump-impeller" and d["ok"]
    assert len(d["features"]) == 10
    assert len(d["tabs"]) == before + 1           # opens in a NEW tab
    assert all(f["status"] == "ok" for f in d["features"])


def test_a_catalog_entry_for_a_missing_file_is_skipped_not_shown(client, tmp_path,
                                                                 monkeypatch):
    """The gallery must degrade by dropping the tile, not by rendering a tile
    that cannot open."""
    real = json.loads(CATALOG.read_text(encoding="utf-8"))
    real["groups"][0]["designs"].append({
        "file": "no-such-design-xyz", "title": "Ghost",
        "description": "does not exist", "features": 3, "ops": [],
        "preview": False})
    backup = CATALOG.read_text(encoding="utf-8")
    try:
        CATALOG.write_text(json.dumps(real), encoding="utf-8")
        r = client.get("/api/examples").json()
        files = {d["file"] for g in r["groups"] for d in g["designs"]}
        assert "no-such-design-xyz" not in files
    finally:
        CATALOG.write_text(backup, encoding="utf-8")
