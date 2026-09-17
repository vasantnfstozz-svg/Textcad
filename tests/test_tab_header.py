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


def _no_tabs():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0


@pytest.fixture(autouse=True)
def _tabs_of_our_own():
    """Every test here opens tabs, and `studio.STATE` is a module global that
    the whole fast tier shares.

    Without this the file passes ALONE and fails in the TIER, which is the
    worst way for a test to be wrong. MAX_TABS is 12, so once earlier files
    have filled them `/api/new` is REFUSED - and the refusal still carries
    `active_tab`, so `other` silently becomes the SAME tab as `mine`, and a
    test comparing two designs compares one with itself. Measured 2026-09-17:
    the full tier went red on
    `test_a_mesh_load_without_a_tab_is_served_the_other_windows_body` while
    the file alone was green. `test_tab_reuse.py` and `test_server_layer.py`
    have always cleared it; this file was written tonight and did not.
    """
    _no_tabs()
    yield
    _no_tabs()


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


# ---------------------------------------------------------------------------
# Section 12 ROUND SIX — the page-wide door re-read.
#
# Round five's door claimed a request with `input.startsWith('/api/')`, which
# is only ever true of a root-relative STRING. three.js r160's FileLoader —
# the loader behind BOTH of the viewport's STL calls, the tree-selection
# highlight and the Move/Rotate drag ghost — calls
# `fetch(new Request(url, {...}))`, so those went out bare and the server fell
# back to whichever tab is globally active. Measured
# (probes/section12_round6_fetchdoor.py): with the page on a 20x20x5 plate and
# another window's 60x60x30 block active, /api/feature-mesh/base.stl came back
# as the 60x60x30 — another design's solid, drawn over this one.
#
# Round five's own behaviour change is what makes that permanent rather than a
# three-second window: two browser windows now hold INDEPENDENT tabs, so
# STATE["active"] stays on the other window's tab for as long as both are open.
# ---------------------------------------------------------------------------

_LOC = ("globalThis.location = { href: 'http://127.0.0.1:8123/', "
        "origin: 'http://127.0.0.1:8123' };\n")

# A recording fetch installed BEFORE api.js is imported, so the shipped door
# wraps it — then whatever `cases` asks for, in every header shape a caller
# can legally use.
_RECORDER = """
const seen = [];
globalThis.fetch = async (input, init) => {
  const H = 'X-TextCAD-Tab';
  const url = typeof input === 'string' ? input
            : String((input && input.url) || input);
  const pick = (hh, k) => {
    if (!hh) return null;
    if (typeof Headers !== 'undefined' && hh instanceof Headers) return hh.get(k);
    if (Array.isArray(hh)) {
      const p = hh.find(x => String(x[0]).toLowerCase() === k.toLowerCase());
      return p ? p[1] : null;
    }
    for (const kk of Object.keys(hh)) if (kk.toLowerCase() === k.toLowerCase()) return hh[kk];
    return null;
  };
  const isReq = typeof Request !== 'undefined' && input instanceof Request;
  const h = init && init.headers;
  let tab = pick(h, H), ct = pick(h, 'Content-Type');
  if (tab == null && isReq) tab = input.headers.get(H);
  if (ct == null && isReq) ct = input.headers.get('Content-Type');
  seen.push({ url, tab, ct,
              body: init && init.body != null ? String(init.body) : null,
              signal: !!(init && init.signal) });
  return { ok: true, status: 200, json: async () => ({}) };
};
"""


def _door(tmp_path, cases):
    """Import the shipped api.js over a recording fetch, then run `cases`."""
    return _node(
        tmp_path,
        _STUBS + _LOC + _RECORDER +
        f"await import({json.dumps((JS / 'api.js').as_uri())});\n"
        f"const {{ S }} = await import({json.dumps((JS / 'state.js').as_uri())});\n"
        "S.lastDoc = { active_tab: 't7' };\n"
        + cases +
        "console.log(JSON.stringify(seen));\n")


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_a_request_object_carries_the_tab(tmp_path):
    """The shape three.js r160's FileLoader really sends. Without it the
    viewport's feature highlight and the Move/Rotate drag ghost are served
    whichever design is globally active — another window's, for as long as
    both windows are open."""
    got = _door(tmp_path,
                "await fetch(new Request("
                "'http://127.0.0.1:8123/api/feature-mesh/base.stl', "
                "{ headers: new Headers({}), credentials: 'same-origin' }));\n")
    assert got[0]["tab"] == "t7", got


def test_the_three_js_loader_really_builds_a_request():
    """The test above is only as true as this: it hand-rolls the loader's call
    shape, so the shipped three.js must still make it that way. r160's
    FileLoader has no XMLHttpRequest at all — it is fetch, with a Request."""
    src = (pathlib.Path(__file__).resolve().parents[1] / "static" / "vendor"
           / "three" / "0.160.0" / "three.module.js").read_text(
               encoding="utf-8", errors="ignore")
    assert "const req = new Request( url, {" in src
    assert "fetch( req )" in src


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_every_shape_of_a_same_origin_api_url_carries_the_tab(tmp_path):
    """A URL object and an absolute same-origin string are the same request as
    '/api/doc'; only a plain root-relative string used to be recognised."""
    got = _door(tmp_path,
                "await fetch(new URL('/api/doc', 'http://127.0.0.1:8123'));\n"
                "await fetch('http://127.0.0.1:8123/api/doc');\n"
                "await fetch('/api/model?t=1');\n")
    assert [g["tab"] for g in got] == ["t7", "t7", "t7"], got


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_tab_id_never_leaves_this_origin(tmp_path):
    """The door is same-origin by TEST now, not by the accident of a path that
    has to start with a slash: a cross-origin URL whose path happens to be
    /api/ must not be told which tab this user is working in."""
    got = _door(tmp_path,
                "await fetch('https://example.com/api/doc');\n"
                "await fetch('//example.com/api/doc');\n"
                "await fetch('/static/js/main.js');\n"
                "await fetch(new Request("
                "'http://127.0.0.1:8123/static/js/main.js'));\n")
    assert [g["tab"] for g in got] == [None, None, None, None], got


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_headers_given_as_pairs_keep_their_content_type(tmp_path):
    """An array of pairs is legal fetch input, and spreading one into an
    object (`{ ...[['Content-Type', 'application/json']] }`) throws the
    Content-Type away and invents a `0:` header — a POST the server reads as
    having no JSON body at all."""
    got = _door(tmp_path,
                "await fetch('/api/x', { method: 'POST', "
                "headers: [['Content-Type', 'application/json']], "
                "body: '{}' });\n")
    assert got[0]["tab"] == "t7", got
    assert got[0]["ct"] == "application/json", got
    assert got[0]["body"] == "{}", got


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_door_passes_the_rest_of_the_request_through(tmp_path):
    """Adding a header must not rebuild the request around it: an abort
    signal and a body belong to the caller."""
    got = _door(tmp_path,
                "const ac = new AbortController();\n"
                "await fetch('/api/s', { signal: ac.signal, method: 'POST', "
                "body: 'x' });\n")
    assert got[0]["tab"] == "t7", got
    assert got[0]["signal"] is True, got
    assert got[0]["body"] == "x", got


def _stl_bbox(body: bytes) -> list[float]:
    """The binary STL's own bounding box, read from its triangles."""
    import struct
    n = struct.unpack("<I", body[80:84])[0]
    lo, hi = [1e30] * 3, [-1e30] * 3
    for i in range(n):
        off = 84 + i * 50 + 12
        for v in range(3):
            p = struct.unpack("<3f", body[off + v * 12:off + v * 12 + 12])
            for k in range(3):
                lo[k], hi[k] = min(lo[k], p[k]), max(hi[k], p[k])
    return [round(hi[k] - lo[k], 3) for k in range(3)]


def test_a_mesh_load_without_a_tab_is_served_the_other_windows_body():
    """What the missing header COSTS, in millimetres. The header decides which
    design /api/feature-mesh answers about; a loader that sends none gets the
    globally active tab, which after round five is the other browser window's
    for as long as both are open."""
    c = TestClient(studio.app)
    mine = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/feature/add", json={
        "id": "base", "op": "plate", "inputs": [],
        "params": {"width": 20, "depth": 20, "thickness": 5}})
    other = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/feature/add", json={
        "id": "base", "op": "plate", "inputs": [],
        "params": {"width": 60, "depth": 60, "thickness": 30}})
    assert studio.STATE["active"] == other

    named = c.get("/api/feature-mesh/base.stl", headers={"X-TextCAD-Tab": mine})
    bare = c.get("/api/feature-mesh/base.stl")
    assert named.status_code == 200 and bare.status_code == 200
    assert _stl_bbox(named.content) == [20.0, 20.0, 5.0], "the page's own design"
    assert _stl_bbox(bare.content) == [60.0, 60.0, 30.0], \
        "no header means the active tab — which is why the loader must send one"
