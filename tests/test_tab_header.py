"""The browser half of "which tab is this request addressed to".

Section 12 round four made the SERVER resolve the tab once per request and
prefer `X-TextCAD-Tab` when it names an open tab, because a design arriving
from outside the browser (an AI over MCP posts /api/open/<slug>?external=1)
can take the active tab between the user's click and the request landing.
Measured there: a traced logo went into another saved design whose undo depth
was 0, so Ctrl+Z on it does nothing.

The server accepting a header nobody sends closes nothing, so these tests are
about the two halves MEETING: the shipped static/js/api.js really puts the tab
on every request, it never invents one, and studio really prefers it.
"""
import json
import shutil
import subprocess
import tempfile
import pathlib

import pytest
from fastapi.testclient import TestClient

import studio

JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "js"


def _node(tmp_path, source):
    harness = tmp_path / "h.mjs"
    harness.write_text(source, encoding="utf-8")
    out = subprocess.run(["node", str(harness)], capture_output=True,
                         text=True, encoding="utf-8",
                         cwd=str(tempfile.gettempdir()))
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


_STUBS = ("globalThis.document = { getElementById: () => "
          "({ style: {}, textContent: '' }) };\n")


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_shipped_postJSON_names_the_tab_it_was_opened_on(tmp_path):
    got = _node(tmp_path,
                f"import {{ postJSON }} from {json.dumps((JS / 'api.js').as_uri())};\n"
                f"import {{ S }} from {json.dumps((JS / 'state.js').as_uri())};\n"
                + _STUBS +
                "S.lastDoc = { active_tab: 't7', features: [], ok: true };\n"
                "let seen = null;\n"
                "globalThis.fetch = async (u, o) => { seen = o.headers; "
                "return { ok: true, json: async () => ({ active_tab: 't7', "
                "features: [], ok: true }) }; };\n"
                "await postJSON('/api/feature/add', { id: 'x' });\n"
                "console.log(JSON.stringify(seen));\n")
    assert got["X-TextCAD-Tab"] == "t7", got
    assert got["Content-Type"] == "application/json", got


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_shipped_getJSON_names_the_tab_too(tmp_path):
    """A read answering about another tab is how a stale highlight or a wrong
    outline reaches the screen, so reads carry it as well as writes."""
    got = _node(tmp_path,
                f"import {{ getJSON }} from {json.dumps((JS / 'api.js').as_uri())};\n"
                f"import {{ S }} from {json.dumps((JS / 'state.js').as_uri())};\n"
                + _STUBS +
                "S.lastDoc = { active_tab: 't3' };\n"
                "let seen = null;\n"
                "globalThis.fetch = async (u, o) => { seen = (o || {}).headers; "
                "return { json: async () => ({}) }; };\n"
                "await getJSON('/api/doc');\n"
                "console.log(JSON.stringify(seen));\n")
    assert got["X-TextCAD-Tab"] == "t3", got


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_a_page_that_has_not_heard_from_the_server_yet_sends_no_tab(tmp_path):
    """The tab id is the SERVER's fact (R1). Before the first /api/doc the
    browser does not know one, and it must not invent one — the server falls
    back to the active tab, which is exactly today's behaviour."""
    got = _node(tmp_path,
                f"import {{ postJSON }} from {json.dumps((JS / 'api.js').as_uri())};\n"
                f"import {{ S }} from {json.dumps((JS / 'state.js').as_uri())};\n"
                + _STUBS +
                "S.lastDoc = null;\n"
                "let seen = null;\n"
                "globalThis.fetch = async (u, o) => { seen = o.headers; "
                "return { ok: true, json: async () => ({ features: [], ok: true }) }; };\n"
                "await postJSON('/api/new', {});\n"
                "console.log(JSON.stringify(seen));\n")
    assert "X-TextCAD-Tab" not in got, got


def test_the_server_honours_the_header_the_browser_now_sends():
    """The two halves meet: a write addressed to the tab the user is looking
    at lands there even though another tab is the active one."""
    c = TestClient(studio.app)
    mine = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/feature/add", json={
        "id": "base", "op": "plate", "inputs": [],
        "params": {"width": 20, "depth": 20, "thickness": 5}})
    other = c.post("/api/new", json={}).json()["active_tab"]
    assert other != mine

    # the active tab is `other` now — exactly what a doorbell leaves behind
    c.post("/api/feature/add",
           json={"id": "boss", "op": "plate", "inputs": [],
                 "params": {"width": 6, "depth": 6, "thickness": 2}},
           headers={"X-TextCAD-Tab": mine})

    got_mine = c.post("/api/tabs/switch", json={"id": mine}).json()
    assert [f["id"] for f in got_mine["features"]] == ["base", "boss"], \
        "the write named a tab and must land in it"
    got_other = c.post("/api/tabs/switch", json={"id": other}).json()
    assert got_other["features"] == [], \
        "the tab that merely happened to be active must be untouched"


def test_a_header_naming_a_tab_that_has_closed_is_ignored_not_refused():
    """A browser one poll behind is not an error (studio.TAB_HEADER's rule)."""
    c = TestClient(studio.app)
    gone = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/tabs/close", json={"id": gone})
    r = c.post("/api/feature/add",
               json={"id": "base", "op": "plate", "inputs": [],
                     "params": {"width": 10, "depth": 10, "thickness": 2}},
               headers={"X-TextCAD-Tab": gone})
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["features"]] == ["base"]
