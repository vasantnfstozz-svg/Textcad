"""P0 of the version-tree work (VERSION-TREE-PLAN.md): opening a design must
reuse ITS tab instead of cloning one.

Before this, /api/open/{file} and /api/sample/{name} called _new_tab()
unconditionally. The design loop is "regenerate the script -> POST
/api/open/<name> -> look at it in 3D", so ten iterations left ten
identically-named tabs (user, 2026-08-26: "we do not know which is my
intended design").
"""
import json

import pytest
from fastapi.testclient import TestClient

import studio

TMP_NAME = "_test-tab-reuse"
TMP_NAME_2 = "_test-tab-reuse-two"


def _tab_count(c, name=None):
    tabs = c.get("/api/tabs").json()["tabs"]
    return len([t for t in tabs if name is None or t["name"] == name])


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    yield TestClient(studio.app)
    # designs/ is the user's tracked library — never leave test files in it
    for n in (TMP_NAME, TMP_NAME_2):
        p = studio.DESIGNS / f"{n}.tcad.json"
        if p.exists():
            p.unlink()


@pytest.fixture()
def saved(client):
    """A real design file in the library, cleaned up afterwards."""
    doc = studio.sample_flange()
    doc.name = TMP_NAME
    doc.save(str(studio.DESIGNS / f"{TMP_NAME}.tcad.json"))
    return TMP_NAME


# ----------------------------------------------------------------- the fix ---

def _ai_designs_a_flange(monkeypatch, name):
    """Stand in for the P5 step loop: the job fills the new tab's document
    with the flange, verified, without a model or a thread."""
    def steps(doc, request, model, on_step=None, guard=None, **kw):
        for f in studio.sample_flange().features:
            doc.add(f.id, f.op, f.params, f.inputs)
        doc.name = name
        ok = doc.rebuild()
        if on_step:
            on_step({"kind": "done", "text": "verified", "id": None, "ok": ok})
        return True, ["verified"]
    monkeypatch.setattr(studio, "JOB_THREADS", False)
    monkeypatch.setattr(studio, "chat_intent",
                        lambda *a, **k: {"action": "create",
                                         "description": "a flange"})
    monkeypatch.setattr(studio, "_make_model", lambda *a, **k: object())
    monkeypatch.setattr(studio.author, "author_steps", steps)


def test_opening_the_same_design_twice_reuses_one_tab(client, saved):
    before = _tab_count(client)
    a = client.post(f"/api/open/{saved}").json()
    assert a["tab_reused"] is False                    # first open: a real tab
    assert _tab_count(client) == before + 1
    b = client.post(f"/api/open/{saved}").json()
    assert b["tab_reused"] is True
    assert _tab_count(client) == before + 1, "second open cloned the tab"
    assert _tab_count(client, TMP_NAME) == 1


def test_ten_opens_still_leave_one_tab(client, saved):
    """The user's actual loop, ten iterations deep."""
    before = _tab_count(client)
    for _ in range(10):
        client.post(f"/api/open/{saved}")
    assert _tab_count(client) == before + 1
    assert _tab_count(client, TMP_NAME) == 1


def test_two_different_designs_still_get_two_tabs(client, saved):
    doc = studio.sample_flange()
    doc.name = TMP_NAME_2
    doc.save(str(studio.DESIGNS / f"{TMP_NAME_2}.tcad.json"))
    before = _tab_count(client)
    client.post(f"/api/open/{saved}")
    client.post(f"/api/open/{TMP_NAME_2}")
    assert _tab_count(client) == before + 2, "reuse must not merge designs"


# ------------------------------------------------- staleness is the danger ---

def test_reopening_after_the_file_changed_refreshes_the_tab(client, saved):
    """The whole point of the loop: the file on disk has moved on. Reusing the
    tab must NOT mean showing the old design."""
    client.post(f"/api/open/{saved}")
    path = studio.DESIGNS / f"{saved}.tcad.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    bore = next(f for f in data["features"] if f["id"] == "bore")
    bore["params"]["radius"] = 7
    path.write_text(json.dumps(data), encoding="utf-8")

    d = client.post(f"/api/open/{saved}").json()
    assert d["tab_reused"] is True and d["reloaded"] is True
    got = next(f for f in d["features"] if f["id"] == "bore")
    assert got["params"]["radius"] == 7, "tab was reused but left stale"
    assert _tab_count(client, TMP_NAME) == 1


def test_a_reload_can_be_undone(client, saved):
    """Reloading replaces what the tab held, so that state goes on the undo
    stack — a refresh must never silently discard unsaved work."""
    client.post(f"/api/open/{saved}")
    d = client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": 11}).json()
    assert d["features"][1]["params"]["radius"] == 11
    d = client.post(f"/api/open/{saved}").json()       # reload, discarding 11
    assert d["reloaded"] is True and d["can_undo"]
    assert d["features"][1]["params"]["radius"] == 15  # back to the file
    d = client.post("/api/undo").json()
    assert d["features"][1]["params"]["radius"] == 11, "the edit was lost"


def test_reopening_an_unchanged_file_only_switches(client, saved):
    """A 97-feature design costs ~45 s to rebuild; re-opening an identical file
    must not pay that for nothing."""
    client.post(f"/api/open/{saved}")
    client.post("/api/tabs/switch", json={"id": "t1"})
    d = client.post(f"/api/open/{saved}").json()
    assert d["tab_reused"] is True and d["reloaded"] is False
    assert d["name"] == TMP_NAME, "switched to the wrong tab"


# ---------------------------------------------------------------- samples ---

def test_a_sample_opened_twice_reuses_its_tab(client):
    before = _tab_count(client)
    a = client.post("/api/sample/flange").json()
    assert a["tab_reused"] is False
    b = client.post("/api/sample/flange").json()
    assert b["tab_reused"] is True
    assert _tab_count(client) == before + 1


def test_reopening_a_sample_keeps_your_edits(client):
    """A sample has no file that can move on, so switching back must return the
    design as the user left it, not a fresh copy."""
    client.post("/api/sample/flange")
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 12})
    client.post("/api/tabs/switch", json={"id": "t1"})
    d = client.post("/api/sample/flange").json()
    assert d["tab_reused"] is True
    assert d["features"][1]["params"]["radius"] == 12


# ------------------------------------------------------------ book-keeping ---

def test_closing_the_tab_then_opening_makes_a_fresh_one(client, saved):
    """A closed tab must not leave a ghost that later opens switch to."""
    d = client.post(f"/api/open/{saved}").json()
    tid = d["active_tab"]
    client.post("/api/tabs/close", json={"id": tid})
    d = client.post(f"/api/open/{saved}").json()
    assert d["tab_reused"] is False
    assert d["active_tab"] != tid
    assert _tab_count(client, TMP_NAME) == 1


def test_saving_binds_the_tab_so_a_later_open_comes_back_to_it(client):
    """Save under a name, then open that name: it must land in the tab you were
    already working in rather than cloning it."""
    doc = studio._doc()
    doc.name = TMP_NAME
    before = _tab_count(client)
    r = client.post("/api/save").json()
    assert r["saved"] == TMP_NAME
    d = client.post(f"/api/open/{TMP_NAME}").json()
    assert d["tab_reused"] is True
    assert _tab_count(client) == before


def test_opening_a_missing_design_still_errors(client):
    d = client.post("/api/open/no-such-design-at-all").json()
    assert "error" in d and "no saved design" in d["error"]


# ------------------------------------------------ the AI must not steal focus ---

def test_an_ai_design_opens_in_its_own_tab_without_stealing_the_current_one(
        client, monkeypatch):
    """User (2026-08-26): "when an ai is working a design and loading it ... even
    my current tab is being taken for that design ... it should take a new tab
    and that should not disturb other tabs".

    Authoring takes a while, so yanking the viewport away mid-edit loses the
    user's place. The design still gets its own tab — it just does not become
    the active one."""
    _ai_designs_a_flange(monkeypatch, "ai-part")

    mine = client.get("/api/doc").json()["active_tab"]
    before = _tab_count(client)

    d = client.post("/api/chat", json={"message": "design a flange"}).json()

    assert _tab_count(client) == before + 1, "the AI design got no tab"
    assert d["active_tab"] == mine, "the AI stole the tab I was working in"
    assert d["new_tab"] != mine
    assert "ai-part" in [t["name"] for t in d["tabs"]]
    assert "own tab" in d["reply"] and "untouched" in d["reply"]


def test_the_ai_tab_is_built_and_ready_when_you_switch_to_it(
        client, monkeypatch):
    """Handing the tab back must not leave the new design unbuilt — switching
    to it should show geometry, not an empty viewport."""
    _ai_designs_a_flange(monkeypatch, "ai-built")
    d = client.post("/api/chat", json={"message": "design a flange"}).json()
    tid = d["new_tab"]
    switched = client.post("/api/tabs/switch", json={"id": tid}).json()
    assert switched["name"] == "ai-built"
    assert switched["ok"] is True and len(switched["features"]) == 3
