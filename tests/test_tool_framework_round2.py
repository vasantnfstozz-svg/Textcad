"""Section 11, ROUND TWO — the fix commit a3d6b03 re-read.

Round one closed a P0, so the queue's step 8 made this round mandatory. Its
three findings, each reproduced by measurement first (probes/
tool_framework_round2_probe.py, tool_tab_moves_itself_probe.py,
tool_limits_blast_radius_probe.py, tool_wire_order_probe.py):

  R1  P0 — round one guarded the tab BAR, but the active tab also moves with
           NO tab click at all: a design arriving over MCP
           (/api/open/<slug>?external=1) takes it, and tool.js has no
           'doc-updated' listener, so the open panel never hears.
  R2  P1 — the Spec dialog's holes box was guarded; its six NUMBER boxes were
           not. `Number('two')` is NaN, JSON.stringify writes null, /api/spec
           keeps only `v is not None` — so the requirement is deleted and the
           next line says the design verifies against the new requirements.
  R3  P2 — planRequest's new non-200 branch reads `detail` only. This
           project's own refusal shape is `{"error": <sentence>}` with status
           400 (studio._refused, and the one-writer middleware that answers
           /api/tool/plan while the AI builds), so the sentence the server
           wrote is thrown away and the panel says "the server said 400".

The JS half is pinned by reading the source, the way test_tool_framework.py
and test_launch_rules.py do — plus, where node is on PATH, by RUNNING the
shipped module against the server's real answer.
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import studio

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"


def _src(name):
    return (JS / name).read_text(encoding="utf-8")


def _slice(src, start, end):
    a = src.index(start)
    return src[a:src.index(end, a)]


def _block(src, start):
    i = src.index("{", src.index(start))
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise AssertionError(f"unbalanced block after {start!r}")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TEXTCAD_HISTORY_ROOT", str(tmp_path))
    # The doorbell test SAVES a design and reopens it as if it had arrived
    # from outside, and conftest isolates only the version histories — a code
    # test must never write into the user's library (REVIEW-QUEUE, shared
    # rule 1). Give this one its own designs folder.
    lib = tmp_path / "designs"
    lib.mkdir()
    monkeypatch.setattr(studio, "DESIGNS", lib)
    return TestClient(studio.app)


def _design(client, name, amount):
    """A design that holds an `extrude1` — the name `uid()` hands out in every
    design, which is why a write meant for one lands squarely in another."""
    client.post("/api/new", json={"name": name})
    client.post("/api/feature/add", json={
        "id": "b", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
    client.post("/api/feature/add", json={
        "id": "s1", "op": "sketch_on_face",
        "params": {"face": "top", "entities": [{"kind": "circle", "r": 6}]},
        "inputs": ["b"]})
    client.post("/api/feature/add", json={
        "id": "extrude1", "op": "extrude",
        "params": {"amount": amount}, "inputs": ["s1"]})
    return client.get("/api/doc").json()["active_tab"]


# ---------------------------------------------------------------------------
# R1 — the P0's other door: the active tab moves with no tab-bar click
# ---------------------------------------------------------------------------

def test_a_design_arriving_from_outside_takes_the_active_tab(client):
    """The damage round one's tab-bar guard does not reach. An AI over MCP
    posts /api/open/<slug>?external=1; studio makes that tab active; the open
    panel's next write lands in the arriving design, which is untouched by
    the user and green. doctabs.js's own closeTab comment has recorded this
    door since 2026-09-01 ("the MCP doorbell auto-loads arriving designs")."""
    mine = _design(client, "panel-design", 5)
    _design(client, "arrives-from-mcp", 9)
    slug = client.post("/api/save", json={}).json()["saved"]
    client.post("/api/tabs/close",
                json={"id": client.get("/api/doc").json()["active_tab"]})
    client.post("/api/tabs/switch", json={"id": mine})       # the panel is here

    client.post(f"/api/open/{slug}?external=1", json={})     # no tab click
    now = client.get("/api/doc").json()
    assert now["active_tab"] != mine, "the doorbell no longer moves the tab"
    assert now["arrival"], "the doorbell owes a banner"

    doc = client.post("/api/feature/params",
                      json={"feature_id": "extrude1",
                            "params": {"amount": 30}}).json()
    assert doc["name"] == "arrives-from-mcp"
    got = next(f for f in doc["features"] if f["id"] == "extrude1")
    assert got["params"]["amount"] == 30          # the arriving design took it
    back = client.post("/api/tabs/switch", json={"id": mine}).json()
    ours = next(f for f in back["features"] if f["id"] == "extrude1")
    assert ours["params"]["amount"] == 5          # and the panel's own never moved


def test_an_open_tool_panel_hears_when_the_active_tab_moves_under_it():
    """So the panel must LET GO when the document on screen becomes another
    design — the same let-go a kernel crash gets, because the session's next
    write would land in a design the user never opened a tool on."""
    src = _src("tool.js")
    assert re.search(r"bus\.on\(\s*'doc-updated'", src), \
        "tool.js still never listens for 'doc-updated' (a3d6b03's own diagnosis)"
    body = _block(src, "function tabMoved")
    assert "active_tab" in body, "the let-go does not compare the ACTIVE TAB"
    assert "releaseModal" in body, \
        "the let-go leaves the one-command-at-a-time lock held"
    assert "hide()" in body, "the let-go leaves the panel on screen"


def test_a_tool_sessions_own_posts_never_move_the_active_tab(client):
    """The other half of the let-go: it must not FALSE-FIRE. Every request an
    open session makes — the plan, parking and releasing the rollback bar, the
    preview feature, its parameter pushes, its combiner and the strict removes
    — has to come back on the tab it went out on, or the panel would shut
    itself in the middle of an ordinary Extrude."""
    tab = _design(client, "one-design", 5)
    seen = []

    def post(url, body):
        r = client.post(url, json=body).json()
        if "active_tab" in r:
            seen.append((url, r["active_tab"]))
        return r

    post("/api/tool/plan", {"tool": "extrude", "sketch_id": "s1"})
    post("/api/rollback", {"feature_id": "extrude1"})        # isolateFor
    post("/api/feature/params", {"feature_id": "extrude1",
                                 "params": {"amount": 7}})
    post("/api/feature/add", {"id": "extrude2", "op": "extrude",
                              "params": {"amount": 3}, "inputs": ["s1"]})
    post("/api/feature/add", {"id": "extrude2_cut", "op": "cut",
                              "inputs": ["b", "extrude2"], "params": {}})
    post("/api/feature/remove", {"feature_id": "extrude2_cut",
                                 "mode": "strict"})
    post("/api/feature/remove", {"feature_id": "extrude2", "mode": "strict"})
    post("/api/rollback", {"feature_id": None})              # releaseIso
    assert seen, "no answer carried an active_tab at all"
    assert all(t == tab for _, t in seen), seen


def test_the_session_records_the_tab_it_was_opened_on():
    """It has to know which design it belongs to before it can notice it is
    no longer the one in front."""
    src = _src("tool.js")
    session = _slice(src, "const session = input =>", "/* -------- open on")
    assert "S.lastDoc" in session and "active_tab" in session, session


# ---------------------------------------------------------------------------
# R2 — the Spec dialog's NUMBER boxes, not just its holes box
# ---------------------------------------------------------------------------

def _spec_form():
    return _slice(_src("dialogs.js"), "getElementById('specForm').onsubmit",
                  "export function actionSpec")


def test_a_spec_number_that_is_not_a_number_deletes_that_requirement(client):
    """Why: /api/spec keeps only `v is not None`, and a box holding text goes
    out as null (Number('two') is NaN; JSON.stringify writes null). The
    requirement is gone, doc.ok flips green, and the handler's very next line
    says "design verifies against the new requirements"."""
    client.post("/api/new", json={"name": "spec-nan"})
    client.post("/api/feature/add", json={
        "id": "b", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
    d = client.post("/api/spec", json={"spec": {"n_solids": 2}}).json()
    assert d["spec"]["n_solids"] == 2 and d["ok"] is False

    d2 = client.post("/api/spec", json={"spec": {
        "n_solids": None, "symmetry": None, "tip_radius": None,
        "tol": None}}).json()
    assert "n_solids" not in d2["spec"]
    assert d2["ok"] is True          # "✓ design verifies against the new..."


def test_the_spec_dialog_stops_on_a_number_box_that_is_not_a_number():
    """The holes box was guarded in round one; the six number boxes share the
    handler and the same consequence."""
    form = _spec_form()
    assert "Number.isFinite" in form, \
        "a spec number box that is not a number still goes out as null"
    assert form.index("Number.isFinite") < form.index("specDialog().close()"), \
        "the spec dialog closes before its numbers are checked"


def test_the_spec_dialog_names_the_box_that_is_wrong():
    """Rule 7: a refusal is a sentence, and a sentence that does not say WHICH
    of seven boxes is wrong sends the user hunting."""
    form = _spec_form()
    for label in ("solid bodies", "symmetry", "tip radius", "tolerance", "size"):
        assert label in form, f"no box is named '{label}' in the refusal"


# ---------------------------------------------------------------------------
# R3 — planRequest must speak the sentence the server wrote
# ---------------------------------------------------------------------------

def _plan_request_src():
    return _slice(_src("api.js"), "export async function planRequest",
                  "A read-only QUESTION")


def test_the_plan_route_answers_400_with_this_projects_refusal_shape(client):
    """/api/tool/plan is NOT in studio._JOB_OPEN_POSTS, so while the AI builds
    in the active tab the one-writer middleware answers it 400 — with
    `error`, never `detail`. It is the commonest non-200 this route has, and
    its sentence is the one that tells the user what to do next."""
    assert "/api/tool/plan" not in studio._JOB_OPEN_POSTS
    tab = _design(client, "plan-400", 5)
    studio.JOBS["t-round2"] = {"done": False, "tab": tab}
    try:
        r = client.post("/api/tool/plan",
                        json={"tool": "extrude", "sketch_id": "s1"})
    finally:
        studio.JOBS.pop("t-round2", None)
    assert r.status_code == 400
    body = r.json()
    assert "detail" not in body
    assert "the AI is still building" in body["error"]


def test_plan_request_reads_the_servers_own_error_sentence():
    fn = _plan_request_src()
    assert "data.error" in fn or ".error" in fn, \
        "planRequest reads `detail` only, so a 400 with `error` is lost"
    assert fn.index("error") < fn.index("the server said"), fn


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_shipped_planRequest_speaks_the_refusal(tmp_path):
    """The proof, not the promise: the real static/js/api.js, run in node
    against the exact body studio answers, must produce the server's own
    sentence — not "the server said 400"."""
    body = {"error": "the AI is still building in this design — wait for it to "
                     "finish, or switch to another tab to keep working"}
    harness = tmp_path / "h.mjs"
    harness.write_text(
        "import { planRequest } from "
        f"{json.dumps((JS / 'api.js').as_uri())};\n"
        "globalThis.document = { getElementById: () => "
        "({ style: {}, textContent: '' }) };\n"
        f"const body = {json.dumps(body)};\n"
        "globalThis.fetch = async () => ({ ok: false, status: 400, "
        "json: async () => body });\n"
        "console.log(JSON.stringify(await planRequest({ tool: 'extrude' })));\n",
        encoding="utf-8")
    out = subprocess.run(["node", str(harness)], capture_output=True,
                         text=True, encoding="utf-8",
                         cwd=str(tempfile.gettempdir()))
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip())
    assert got["ok"] is False
    assert got["error"] == body["error"], got


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_shipped_planRequest_still_takes_a_plain_refusal_and_a_plan(tmp_path):
    """The 200 paths round one had right must stay right: a real plan comes
    back whole, and a 200 carrying `ok: false` keeps its own error."""
    cases = [
        (200, {"ok": True, "origin": [1, 2, 3]}),
        (200, {"ok": False, "error": "no plan for tool 'nope'"}),
        (422, {"detail": [{"loc": ["body", "chain"],
                           "msg": "Input should be a valid boolean"}]}),
    ]
    harness = tmp_path / "h2.mjs"
    harness.write_text(
        "import { planRequest } from "
        f"{json.dumps((JS / 'api.js').as_uri())};\n"
        "globalThis.document = { getElementById: () => "
        "({ style: {}, textContent: '' }) };\n"
        f"const cases = {json.dumps(cases)};\n"
        "const out = [];\n"
        "for (const [status, body] of cases) {\n"
        "  globalThis.fetch = async () => ({ ok: status < 300, status, "
        "json: async () => body });\n"
        "  out.push(await planRequest({ tool: 'extrude' }));\n"
        "}\n"
        "console.log(JSON.stringify(out));\n",
        encoding="utf-8")
    out = subprocess.run(["node", str(harness)], capture_output=True,
                         text=True, encoding="utf-8",
                         cwd=str(tempfile.gettempdir()))
    assert out.returncode == 0, out.stderr
    a, b, c = json.loads(out.stdout.strip())
    assert a == {"ok": True, "origin": [1, 2, 3]}          # a plan is untouched
    assert b == {"ok": False, "error": "no plan for tool 'nope'"}
    assert c["ok"] is False and "chain" in c["error"]      # 422 still reads detail
