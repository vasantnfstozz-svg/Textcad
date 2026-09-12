"""E2E: the bug button (LAUNCH-PLAN.md P5b) — one click, one folder, design untouched.

The user presses it while something looks wrong and keeps working. What must
land in the folder without them describing anything: the design as it stands,
the requests this tab made (the fetch ring has to have seen the add that came
BEFORE the click), which UI build the tab runs, and a real frame of the
viewport — not a blank canvas, which is what toDataURL returns when nobody
rendered first.
"""
import json

import pytest

from conftest import ask_text

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add', { id: 'p', op: 'plate',
    params: { width: 60, depth: 40, thickness: 5 }, inputs: [] }, 'add');
}
"""


def test_one_click_saves_a_repro_folder(page, fresh_doc, tmp_path, monkeypatch):
    import studio                    # the e2e server runs in THIS process
    monkeypatch.setattr(studio, "BUGS", tmp_path / "bugs")
    page.evaluate(BUILD)
    page.wait_for_timeout(1000)      # the plate is on screen
    before = studio._doc().to_data()

    page.click("#bugBtn")
    assert "What went wrong" in ask_text(page)
    page.fill("#askInput", "the plate looks wrong")
    page.click("#askOk")
    page.wait_for_function(
        "() => document.getElementById('chatLog').innerText.includes('Saved to')", timeout=15000)

    folders = list((tmp_path / "bugs").iterdir())
    assert len(folders) == 1, folders
    f = folders[0]
    state = json.loads((f / "state.json").read_text(encoding="utf-8"))
    assert state["note"] == "the plate looks wrong"
    assert any(r["url"].endswith("/api/feature/add") for r in state["requests"]), \
        "the fetch ring missed the add made before the click"
    assert state["ui_build"].startswith("ui v")
    assert json.loads((f / "doc.tcad.json").read_text(encoding="utf-8")) == before
    png = (f / "screenshot.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 5000, f"{len(png)} bytes: a blank canvas, not the rendered viewport"
    assert studio._doc().to_data() == before and not page.errors
