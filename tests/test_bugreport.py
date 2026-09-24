"""POST /api/bug — the Studio bug button (LAUNCH-PLAN.md P5b).

One click must leave a folder a later chat can work from, and must not touch
the design: no snapshot, no rebuild, no undo step, no viewport refresh."""
import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import studio
from fixture_docs import flange

ROOT = Path(studio.__file__).parent
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "BUGS", tmp_path / "bugs")
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(flange())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def _folder(d: dict) -> Path:
    p = Path(d["saved"])
    return p if p.is_absolute() else ROOT / p


def test_one_click_files_the_design_the_requests_and_the_screenshot(client):
    before = studio._doc().to_data()
    undo_depth = len(studio._entry()["history"])
    r = client.post("/api/bug", json={
        "note": "the fillet ate the box",
        "screenshot": "data:image/png;base64," + base64.b64encode(PNG_1x1).decode(),
        "requests": [{"method": "POST", "url": "/api/feature/add",
                      "body": '{"op":"fillet"}', "status": 200, "ms": 12}],
        "console": [{"kind": "chat", "text": "⚠ fillet failed"}],
        "ui_build": "ui v197"})
    assert r.status_code == 200
    d = r.json()
    assert "features" not in d, "the answer must not read as a document update"
    folder = _folder(d)
    assert sorted(p.name for p in folder.iterdir()) == [
        "doc.tcad.json", "report.md", "screenshot.png", "state.json"]
    assert json.loads((folder / "doc.tcad.json").read_text(encoding="utf-8")) == before
    assert (folder / "screenshot.png").read_bytes() == PNG_1x1
    state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
    assert state["note"] == "the fillet ate the box"
    assert state["requests"][0]["url"] == "/api/feature/add"
    assert state["console"][0]["text"].endswith("fillet failed")
    assert state["doc"]["features"] and state["ui_build"] == "ui v197"
    report = (folder / "report.md").read_text(encoding="utf-8")
    for needle in ("the fillet ate the box", "/api/feature/add", "--replay", "ui v197"):
        assert needle in report, needle
    # the design is untouched: same intent, no undo step pushed
    assert studio._doc().to_data() == before
    assert len(studio._entry()["history"]) == undo_depth


def test_a_screenshot_that_is_not_a_png_is_skipped_not_fatal(client):
    for junk in ("data:image/png;base64,!!!notbase64", "data:text/plain;base64,aGVsbG8="):
        d = client.post("/api/bug", json={"note": "", "screenshot": junk}).json()
        assert d.get("screenshot_skipped") and "screenshot.png" not in d["files"]
        assert (_folder(d) / "doc.tcad.json").exists()


def test_the_button_works_while_the_ai_is_building():
    """'The AI is stuck' is exactly when the user presses it; the one-writer
    guard must let it through (it only reads)."""
    assert "/api/bug" in studio._JOB_OPEN_POSTS


def test_a_button_folder_replays(client):
    import journeys
    d = client.post("/api/bug", json={"note": "just looking"}).json()
    out = journeys.replay(_folder(d), verbose=False)
    assert out["result"] == "clean"


def test_the_button_is_wired_in_the_ui():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="bugBtn"' in html
    main = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    assert "initBugReport()" in main
    src = (ROOT / "static" / "js" / "bugreport.js").read_text(encoding="utf-8")
    assert "/api/bug" in src and "loadMesh" not in src          # R3: no refresh by hand
    assert "!bugs/**" in (ROOT / ".gitignore").read_text(encoding="utf-8")
