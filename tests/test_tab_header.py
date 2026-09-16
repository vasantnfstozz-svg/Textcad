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


# ---------------------------------------------------------------------------
# Section 12 ROUND FIVE — the browser half re-read.
#
# The pin protects the request that CARRIES the header. Round five measured
# what the RESPONSE then tells the browser
# (probes/section12_round5_hammer.py): the document was the addressed tab's
# but `active_tab` was the LIVE active tab, and tabHeaders() feeds
# `S.lastDoc.active_tab` back as the next request's header — so the pin held
# for exactly ONE request and the one after it went to the design a doorbell
# had made active. Measured: a poll answered about the user's own tab came
# back labelled the arriving design's, and the next edit — made against the
# tree on screen — set the ARRIVING design's base.thickness to 41 while the
# design on screen kept its 5.
# ---------------------------------------------------------------------------

def _two(c):
    """Two tabs, each with a feature called `base` — the ordinary case, and
    the one where a misaddressed edit lands instead of being refused."""
    mine = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/feature/add", json={
        "id": "base", "op": "plate", "inputs": [],
        "params": {"width": 20, "depth": 20, "thickness": 5}})
    other = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/feature/add", json={
        "id": "base", "op": "plate", "inputs": [],
        "params": {"width": 30, "depth": 30, "thickness": 9}})
    return mine, other


def test_the_answer_names_the_tab_it_is_about():
    """A response carrying one design's feature tree must not be labelled
    another design's tab: the browser hands that label straight back."""
    c = TestClient(studio.app)
    mine, other = _two(c)
    studio.STATE["active"] = other                  # the doorbell got there
    r = c.get("/api/doc", headers={"X-TextCAD-Tab": mine}).json()
    assert r["features"][0]["params"]["thickness"] == 5, "wrong document"
    assert r["active_tab"] == mine, \
        "the answer is about `mine` and must say so"


def test_the_tab_strip_marks_the_tab_the_answer_is_about():
    c = TestClient(studio.app)
    mine, other = _two(c)
    studio.STATE["active"] = other
    r = c.get("/api/doc", headers={"X-TextCAD-Tab": mine}).json()
    assert [t["id"] for t in r["tabs"] if t["active"]] == [mine]
    r = c.get("/api/tabs", headers={"X-TextCAD-Tab": mine}).json()
    assert r["active_tab"] == mine


def test_the_next_click_lands_where_the_last_answer_came_from():
    """The whole point, end to end: the browser sends back what the last
    answer called the active tab, so a misaddressed label costs the user the
    NEXT edit — into a design they never opened, under a feature id both
    designs happen to share."""
    c = TestClient(studio.app)
    mine, other = _two(c)
    studio.STATE["active"] = other
    poll = c.get("/api/doc", headers={"X-TextCAD-Tab": mine}).json()
    # exactly what static/js/api.js tabHeaders() does with S.lastDoc
    c.post("/api/edit", headers={"X-TextCAD-Tab": poll["active_tab"]},
           json={"feature_id": "base", "param": "thickness", "value": 41})
    assert studio.STATE["docs"][mine]["doc"].features[0].params[
        "thickness"] == 41, "the edit belonged to the design on screen"
    assert studio.STATE["docs"][other]["doc"].features[0].params[
        "thickness"] == 9, "the other design must be untouched"


def test_a_stale_header_cannot_smuggle_a_write_into_the_busy_tab():
    """The two middlewares must resolve the header by ONE rule. The pin
    ignores a header naming a tab that is not open and falls back to the
    active tab; the one-writer guard took the header as given, so a page one
    poll behind — or one that outlived a restart, where tab ids start again
    at t1 — slipped a write into the very tab the AI was building in."""
    c = TestClient(studio.app)
    mine, other = _two(c)
    studio.STATE["active"] = other
    studio.JOBS.clear()
    studio.JOBS["j-r5"] = {"id": "j-r5", "tab": other, "done": False}
    try:
        r = c.post("/api/edit", headers={"X-TextCAD-Tab": "t-closed-ages-ago"},
                   json={"feature_id": "base", "param": "thickness",
                         "value": 77})
        assert r.status_code == 400, r.json()
        assert studio.STATE["docs"][other]["doc"].features[0].params[
            "thickness"] == 9
    finally:
        studio.JOBS.clear()


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_a_raw_fetch_carries_the_tab_too(tmp_path):
    """Nine call sites under static/js call fetch() directly instead of going
    through api.js — File -> Export, the viewport's /api/model and
    /api/sketch-mesh, the face pick, the two measure calls, the sketcher's
    snap, outline and trim. A write and a read landing on DIFFERENT tabs
    inside one gesture is how a face picked on one body gets applied to
    another, so the header is installed once for the whole page."""
    got = _node(tmp_path,
                _STUBS +
                "let seen = [];\n"
                "globalThis.fetch = async (u, o) => { seen.push([u, (o||{}).headers || null]); "
                "return { ok: true, json: async () => ({}) }; };\n"
                f"await import({json.dumps((JS / 'api.js').as_uri())});\n"
                f"const {{ S }} = await import({json.dumps((JS / 'state.js').as_uri())});\n"
                "S.lastDoc = { active_tab: 't9' };\n"
                "await fetch('/api/export', { method: 'POST' });\n"
                "await fetch('/api/model?t=1');\n"
                "await fetch('/static/js/main.js');\n"
                "console.log(JSON.stringify(seen));\n")
    assert got[0][1]["X-TextCAD-Tab"] == "t9", got
    assert got[1][1]["X-TextCAD-Tab"] == "t9", got
    assert "X-TextCAD-Tab" not in (got[2][1] or {}), \
        "only /api/ calls carry it"


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_arrival_banner_really_loads_what_it_announces(tmp_path):
    """The banner says "loaded it". That used to be true only because the
    server's answer named the ARRIVING tab as active and the browser followed
    the label; now the answer names the tab it is about, so the follow has to
    be a deliberate switch or the sentence is a lie."""
    got = _node(tmp_path,
                _STUBS +
                "let posts = [];\n"
                "globalThis.fetch = async (u, o) => { posts.push(u); "
                "return { ok: true, json: async () => ({ features: [], "
                "ok: true, active_tab: 't4' }) }; };\n"
                f"const api = await import({json.dumps((JS / 'api.js').as_uri())});\n"
                f"const {{ S }} = await import({json.dumps((JS / 'state.js').as_uri())});\n"
                "S.lastDoc = { active_tab: 't1', tabs: [{ id: 't1' }, { id: 't4' }] };\n"
                "await api.noteArrival({ tabs: S.lastDoc.tabs, arrival: "
                "{ tab: 't4', name: 'ring', file: 'ring', at: 123 } });\n"
                "console.log(JSON.stringify(posts));\n")
    assert "/api/tabs/switch" in got, got
    assert "/api/arrival/ack" in got, got
