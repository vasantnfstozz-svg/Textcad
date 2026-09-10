"""Open tabs survive a server restart (user mandate 2026-08-31: "when you
reload the software, all other designs I am working on close and vanish — do
not do that, open the design tabs that were opened").

The session file holds every open tab's full intent — UNSAVED tabs included —
and startup reopens exactly those tabs, the active one active again."""
import json

import pytest
from fastapi.testclient import TestClient

import studio
from document import Document


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "SESSION_PATH", tmp_path / "session.json")
    monkeypatch.setattr(studio, "SESSION_ENABLED", True)
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    return TestClient(studio.app)


def _build_two_tabs(client):
    """Tab 1: a saved-style plate. Tab 2: an UNSAVED design with real work in
    it — the case that used to vanish. Tab 1 is left active."""
    client.post("/api/new", json={"name": "plate-tab"})
    client.post("/api/feature/add", json={
        "id": "p", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 10}, "inputs": []})
    first = studio.STATE["active"]
    client.post("/api/new", json={"name": "scratch-work"})
    client.post("/api/feature/add", json={
        "id": "d", "op": "disc",
        "params": {"radius": 20, "thickness": 8}, "inputs": []})
    client.post("/api/tabs/switch", json={"id": first})
    return first


def test_every_post_persists_the_session(client):
    _build_two_tabs(client)
    data = json.loads(studio.SESSION_PATH.read_text(encoding="utf-8"))
    names = [t["doc"]["name"] for t in data["tabs"]]
    assert names == ["plate-tab", "scratch-work"]
    actives = [t["active"] for t in data["tabs"]]
    assert actives == [True, False]              # the switch was persisted
    scratch = data["tabs"][1]["doc"]
    assert scratch["features"][0]["op"] == "disc"    # unsaved work IS in there


def test_restart_brings_every_tab_back(client):
    _build_two_tabs(client)
    # the "restart": a fresh empty STATE, then the startup restore
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    assert studio._restore_session() == 2
    tabs = client.get("/api/tabs").json()["tabs"]
    assert [t["name"] for t in tabs] == ["plate-tab", "scratch-work"]
    # only the ACTIVE tab is rebuilt at startup (a heavy session must not
    # keep the port closed for minutes); the other shows "not loaded yet"
    assert [t["ok"] for t in tabs] == [True, None]
    assert [t["active"] for t in tabs] == [True, False]
    # the restored active doc answers with its geometry intact
    doc = client.get("/api/doc").json()
    assert doc["name"] == "plate-tab"
    assert doc["features"][0]["op"] == "plate"
    # switching to the unsaved tab rebuilds it lazily, content intact
    other = next(t["id"] for t in tabs if t["name"] == "scratch-work")
    doc2 = client.post("/api/tabs/switch", json={"id": other}).json()
    assert doc2["features"][0]["params"]["radius"] == 20
    assert doc2["features"][0]["status"] == "ok"     # actually BUILT now
    tabs2 = client.get("/api/tabs").json()["tabs"]
    assert [t["ok"] for t in tabs2] == [True, True]


def test_broken_session_file_is_survived(client):
    studio.SESSION_PATH.write_text("{ not json", encoding="utf-8")
    assert studio._restore_session() == 0            # no crash, fresh start


def test_one_broken_tab_does_not_take_down_the_rest(client):
    good = Document(name="good")
    good.add("p", "plate", {"width": 30, "depth": 30, "thickness": 5}, [])
    studio.SESSION_PATH.write_text(json.dumps({"tabs": [
        {"doc": {"name": "bad", "features": [{"id": "x", "op": "no-such-op",
                                              "params": {}, "inputs": []}]},
         "source": None, "active": True},
        {"doc": good.to_data(), "source": None, "active": False},
    ]}), encoding="utf-8")
    assert studio._restore_session() == 1
    tabs = client.get("/api/tabs").json()["tabs"]
    assert [t["name"] for t in tabs] == ["good"]
    assert tabs[0]["active"] and tabs[0]["ok"]      # fallback active, rebuilt


def test_tests_never_touch_the_real_session(tmp_path, monkeypatch):
    """The gate itself: with SESSION_ENABLED False (the import-time default),
    POSTs must not write the session file."""
    monkeypatch.setattr(studio, "SESSION_PATH", tmp_path / "session.json")
    monkeypatch.setattr(studio, "SESSION_ENABLED", False)
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    c = TestClient(studio.app)
    c.post("/api/new", json={"name": "x"})
    assert not (tmp_path / "session.json").exists()


# ---------------------------------------------------------------------------
# Section 3 code review, 2026-09-10 (F2, P1). A restored tab's dirty baseline
# is taken from the design's CURRENT VERSION -- "otherwise a dirty tab would
# read clean after every restart and the close prompt would let those edits
# vanish silently". Two doors were left open in the fallbacks: a design with
# no (or a broken) .history/ never entered the `if cur:` branch, and a
# `sample:` tab never entered the block at all. In both the baseline stayed
# the ALREADY-EDITED restored content, so the tab read clean, showed no dot,
# and closing it threw the edits away without asking. Measured with three
# restored tabs all holding radius 99: True / False / False.
# ---------------------------------------------------------------------------

def _session_with(client, tabs):
    studio.SESSION_PATH.write_text(json.dumps({"tabs": tabs}), encoding="utf-8")
    studio.STATE = {"docs": {}, "active": None, "seq": 0}
    return studio._restore_session()


def _disc(name, radius):
    d = Document(name=name)
    d.add("body", "disc", {"radius": radius, "thickness": 5})
    return d


def _dirty_by_name(name):
    for e in studio.STATE["docs"].values():
        if e["doc"].name == name:
            return studio._dirty(e)
    raise AssertionError(f"no restored tab called {name}")


def test_a_restored_tab_with_no_history_still_reads_dirty(client, tmp_path):
    """A design that has never been versioned: the file on disk is the only
    baseline there is, and the restored tab has moved away from it."""
    (studio.DESIGNS / "_test-nohist.tcad.json").write_text(
        json.dumps(_disc("_test-nohist", 10).to_data()), encoding="utf-8")
    try:
        assert _session_with(client, [
            {"doc": _disc("_test-nohist", 99).to_data(),
             "source": "file:_test-nohist", "active": True}]) == 1
        assert _dirty_by_name("_test-nohist") is True, \
            "unsaved edits read as clean, so closing the tab discards them"
    finally:
        (studio.DESIGNS / "_test-nohist.tcad.json").unlink(missing_ok=True)


def test_a_restored_tab_matching_its_file_reads_clean(client):
    """...and the guard must not cry wolf on an untouched one."""
    (studio.DESIGNS / "_test-nohist.tcad.json").write_text(
        json.dumps(_disc("_test-nohist", 10).to_data()), encoding="utf-8")
    try:
        _session_with(client, [
            {"doc": _disc("_test-nohist", 10).to_data(),
             "source": "file:_test-nohist", "active": True}])
        assert _dirty_by_name("_test-nohist") is False
    finally:
        (studio.DESIGNS / "_test-nohist.tcad.json").unlink(missing_ok=True)


def test_a_restored_sample_tab_keeps_its_unsaved_edits_visible(client):
    pristine = studio.SAMPLES["flange"]()
    edited = studio.SAMPLES["flange"]()
    edited.edit(edited.features[1].id, "radius", 99)
    assert _session_with(client, [
        {"doc": edited.to_data(), "source": "sample:flange", "active": True}]) == 1
    assert _dirty_by_name(pristine.name) is True, \
        "an edited sample read as clean after a restart"


def test_an_untouched_restored_sample_reads_clean(client):
    pristine = studio.SAMPLES["flange"]()
    _session_with(client, [
        {"doc": pristine.to_data(), "source": "sample:flange", "active": True}])
    assert _dirty_by_name(pristine.name) is False
