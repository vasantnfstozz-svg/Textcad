"""P2 of VERSION-TREE-PLAN.md — the version tree wired into the server.

Two things being pinned here, and they pull in opposite directions:

* versions are minted ONLY when the user pushes one — an explicit save (plus
  the open/reload baseline). Since 2026-09-01 tool commits, imports and AI
  edits no longer mint on their own: they mark the tab DIRTY and ride into
  the next save together. Before that they minted individually, and before
  THAT the user had to rule out minting on every slider drag — same complaint,
  tightened twice;
* nothing is ever silently lost — every unpushed change still rides into the
  next saved version, the dirty flag says the tab is holding some (so the UI
  can ask before a close throws them away), and restore never overwrites the
  saved file.
"""
import json

import pytest
from fastapi.testclient import TestClient

import studio
from history import History

TMP = "_test-versions"


def _design_path(slug=TMP):
    return studio.DESIGNS / f"{slug}.tcad.json"


@pytest.fixture()
def client():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    yield TestClient(studio.app)
    # designs/ is tracked user work; the history root is redirected by the
    # autouse fixture in conftest, but the design FILE is real
    for slug in (TMP, TMP + "-two"):
        p = _design_path(slug)
        if p.exists():
            p.unlink()


@pytest.fixture()
def saved(client):
    """A design in the library, opened in a tab, with v1 already recorded."""
    doc = studio.sample_flange()
    doc.name = TMP
    doc.save(str(_design_path()))
    client.post(f"/api/open/{TMP}")
    return TMP


def _hist(slug=TMP):
    return History.for_design(studio._history_root(), slug)


def _versions(client):
    return client.get("/api/versions").json()


# ------------------------------------------------ versions ARE minted here ---

def test_opening_a_design_records_its_first_version(client, saved):
    d = _versions(client)
    assert d["unsaved"] is False
    assert [v["id"] for v in d["versions"]] == ["v1"]
    assert d["current"] == "v1"
    assert d["versions"][0]["source"] == "open"
    assert TMP in d["versions"][0]["label"]
    assert d["versions"][0]["features"] == 3
    assert d["versions"][0]["rebuildable"] is True
    assert d["versions"][0]["spec"]["volume"] > 0


def test_saving_records_a_version(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    r = client.post("/api/save").json()
    assert r["version"] == "v2"
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1", "v2"]
    # the edit above was made BY HAND, so the version says so rather than the
    # bare "saved" it used to — that is what lets the AI tell the work apart
    assert _hist().get("v2").label == "manual changes (1 edit)"
    assert _hist().get("v2").author == "you"


def test_a_tool_commit_records_NO_version_until_save(client, saved):
    """User (2026-09-01): "whatever i am adding its going as new version, it
    should not be like that ... if i want then i can push those changes into
    new version." A tool commit accumulates in the tab; only SAVE mints."""
    r = client.post("/api/feature/add", json={
        "id": "extra", "op": "with_center_hole", "params": {"radius": 3},
        "inputs": ["bolts"]}).json()
    assert "version" not in r
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1"]

    r = client.post("/api/save").json()
    assert r["version"] == "v2"
    v = _hist().get("v2")
    assert "with_center_hole added" in v.label
    assert v.source == "manual" and v.author == "you"


def test_deleting_a_feature_records_no_version_until_save(client, saved):
    r = client.post("/api/feature/remove",
                    json={"feature_id": "bolts", "mode": "auto"}).json()
    assert "error" not in r, r.get("error")
    assert "version" not in r
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1"]
    r = client.post("/api/save").json()
    assert r["version"] == "v2"
    assert "deleted bolts" in _hist().get("v2").label


def test_an_ai_edit_records_no_version_until_save(client, saved, monkeypatch):
    """AI edits used to mint on their own ("the user asked in words"); the
    user overruled that — NOTHING mints until they push."""
    monkeypatch.setattr(studio, "chat_intent", lambda *a, **k: {
        "action": "edit", "feature_id": "bore", "param": "radius", "value": 9})
    r = client.post("/api/chat", json={"message": "make the bore 9"}).json()
    assert "version" not in r
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1"]
    r = client.post("/api/save").json()
    assert r["version"] == "v2"
    v = _hist().get("v2")
    assert v.source == "ai" and "bore.radius" in v.label


def test_a_first_save_starts_the_history_under_the_new_name(client):
    """A design with no file has no history; saving creates one, keyed to the
    name it was just written as."""
    assert _versions(client)["unsaved"] is True
    studio._doc().name = TMP
    r = client.post("/api/save").json()
    assert r["saved"] == TMP and r["version"] == "v1"
    assert _versions(client)["unsaved"] is False


# -------------------------------------------- and NOT minted for the nudges ---

def test_a_parameter_edit_alone_records_nothing(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 12})
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1"]


def test_a_spec_change_alone_records_nothing(client, saved):
    client.post("/api/spec", json={"spec": {"n_solids": 1, "tol": 0.5}})
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1"]


def test_a_burst_of_nudges_coalesces_into_one_version(client, saved):
    """The coalescing the user asked for, and the reason not versioning a nudge
    loses nothing: five tweaks then a save is ONE version holding all five."""
    for r in (5, 6, 7, 8, 9):
        client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": r})
    client.post("/api/save")
    vs = _versions(client)["versions"]
    assert [v["id"] for v in vs] == ["v1", "v2"]
    assert _hist().snapshot("v2")["features"][1]["params"]["radius"] == 9


def test_reopening_an_unchanged_design_records_nothing_new(client, saved):
    for _ in range(5):
        client.post(f"/api/open/{saved}")
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1"]


def test_reopening_a_CHANGED_file_records_the_new_state(client, saved):
    data = json.loads(_design_path().read_text(encoding="utf-8"))
    data["features"][1]["params"]["radius"] = 7
    _design_path().write_text(json.dumps(data), encoding="utf-8")
    r = client.post(f"/api/open/{saved}").json()
    assert r["reloaded"] is True and r["version"] == "v2"
    assert _hist().get("v2").label == "reloaded from disk"


# -------------------------------------------------------------- the listing ---

def test_an_unsaved_design_says_so_instead_of_looking_broken(client):
    d = _versions(client)
    assert d["unsaved"] is True and d["versions"] == []
    assert "save it once" in d["note"]
    assert d["problems"] == []


def test_the_listing_carries_the_tree_and_the_markers(client, saved):
    client.post("/api/feature/add", json={
        "id": "x", "op": "with_center_hole", "params": {"radius": 2},
        "inputs": ["bolts"]})
    client.post("/api/save")                                  # push it -> v2
    client.post("/api/versions/star", json={"id": "v1"})
    d = _versions(client)
    assert d["current"] == "v2" and d["starred"] == "v1"
    assert d["design_id"].startswith("d_")
    assert len(d["tree"]) == 2


# ----------------------------------------------------------------- restore ---

def test_restore_puts_the_old_design_back_in_the_same_tab(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")                              # v2
    tabs_before = len(client.get("/api/tabs").json()["tabs"])

    d = client.post("/api/versions/restore", json={"id": "v1"}).json()
    assert d["restored"] == "v1"
    assert d["features"][1]["params"]["radius"] == 15     # v1's value
    assert len(d["tabs"]) == tabs_before, "restore opened a tab"
    assert _versions(client)["current"] == "v1"


def test_restore_does_not_overwrite_the_saved_design(client, saved):
    """The user's decision: .tcad.json is untouched until they explicitly
    save. Restoring v1 must not quietly demote the file to v1."""
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")
    on_disk = _design_path().read_text(encoding="utf-8")

    client.post("/api/versions/restore", json={"id": "v1"})
    assert _design_path().read_text(encoding="utf-8") == on_disk


def test_editing_after_a_restore_BRANCHES(client, saved):
    """The core promise, end to end through HTTP: go back, change something,
    and the versions you came from are still there."""
    for r in (11, 12, 13):
        client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": r})
        client.post("/api/save")
    assert [v["id"] for v in _versions(client)["versions"]] == \
        ["v1", "v2", "v3", "v4"]

    client.post("/api/versions/restore", json={"id": "v2"})
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 99})
    r = client.post("/api/save").json()

    assert r["version"] == "v5"
    h = _hist()
    assert h.get("v5").parent == "v2"
    for old in ("v3", "v4"):
        assert h.snapshot(old)["features"], f"{old} was destroyed"
    assert sorted(h.children("v2")) == ["v3", "v5"]


def test_restore_is_undoable(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")
    client.post("/api/versions/restore", json={"id": "v1"})
    d = client.post("/api/undo").json()
    assert d["features"][1]["params"]["radius"] == 11, \
        "restoring threw away what was on screen"


def test_restoring_an_unknown_version_is_a_clear_error(client, saved):
    d = client.post("/api/versions/restore", json={"id": "v99"}).json()
    assert "no version 'v99'" in d["error"]
    assert d["features"], "the document was disturbed by a failed restore"


def test_restore_needs_an_id(client, saved):
    d = client.post("/api/versions/restore", json={}).json()
    assert "which version" in d["error"]


def test_a_version_this_build_cannot_open_fails_honestly(client, saved):
    """A version recorded before an op was renamed. It must stay in the tree as
    a record and refuse to open with a real explanation — not a 500, and not
    quietly dropped."""
    h = _hist()
    h.append({"name": TMP, "spec": {},
              "features": [{"id": "old", "op": "op_from_a_past_build",
                            "params": {}, "inputs": []}]},
             label="pre-rename", source="test")
    d = client.post("/api/versions/restore", json={"id": "v2"}).json()
    assert "cannot open it" in d["error"] and "still in the history" in d["error"]
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1", "v2"]
    assert d["features"], "the live design was damaged by a failed restore"


def test_restore_on_a_design_with_no_history_says_so(client):
    d = client.post("/api/versions/restore", json={"id": "v1"}).json()
    assert "no history yet" in d["error"]


# -------------------------------------------------------- star and relabel ---

def test_starring_pins_exactly_one_version(client, saved):
    client.post("/api/feature/add", json={
        "id": "x", "op": "with_center_hole", "params": {"radius": 2},
        "inputs": ["bolts"]})
    client.post("/api/save")                                  # push it -> v2
    assert client.post("/api/versions/star",
                       json={"id": "v1"}).json()["starred"] == "v1"
    assert client.post("/api/versions/star",
                       json={"id": "v2"}).json()["starred"] == "v2"
    assert client.post("/api/versions/star",
                       json={"id": None}).json()["starred"] is None


def test_starring_an_unknown_version_is_refused(client, saved):
    d = client.post("/api/versions/star", json={"id": "v42"}).json()
    assert "no version" in d["error"]
    assert _versions(client)["starred"] is None


def test_the_star_survives_a_restore(client, saved):
    """Starring says 'this is the one I mean'; wandering around the tree must
    not un-say it."""
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")
    client.post("/api/versions/star", json={"id": "v2"})
    client.post("/api/versions/restore", json={"id": "v1"})
    d = _versions(client)
    assert d["starred"] == "v2" and d["current"] == "v1"


def test_relabelling_a_version(client, saved):
    r = client.post("/api/versions/label",
                    json={"id": "v1", "label": "the one for the mill"}).json()
    assert r["labelled"] == "v1"
    assert _hist().get("v1").label == "the one for the mill"


def test_relabelling_an_unknown_version_is_refused(client, saved):
    d = client.post("/api/versions/label",
                    json={"id": "v9", "label": "x"}).json()
    assert "no version" in d["error"]


# ---------------------------------------------------- broken history on disk ---

def test_a_corrupt_index_is_reported_and_does_not_break_editing(client, saved):
    """A sidecar file the server cannot write must not make a successful design
    edit look like a failure."""
    idx = _hist().path / "index.json"
    idx.write_text("{ broken", encoding="utf-8")

    d = _versions(client)
    assert d["versions"] == [] and any("unreadable" in p
                                       for p in d["problems"])

    r = client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": 12}).json()
    assert r["features"][1]["params"]["radius"] == 12, "the edit was lost"
    r = client.post("/api/save").json()
    assert r["saved"] == TMP, "the save failed because of a sidecar file"
    assert "history_error" in r and "unreadable" in r["history_error"]
    assert idx.read_text(encoding="utf-8") == "{ broken", \
        "the corrupt index was clobbered"


def test_histories_never_land_in_the_designs_library(client, saved):
    """Guard on the guard: the autouse fixture redirects HISTORY_ROOT, and if it
    ever stops working this test fails instead of a directory silently appearing
    inside tracked user work.

    It checks for THIS TEST'S slug specifically, not for any .history at all —
    since the P4 backfill, designs/ legitimately holds the real designs'
    histories, and a blanket "none may exist" would fail on the user's own
    data."""
    assert studio._history_root() != studio.DESIGNS
    for slug in (TMP, TMP + "-two"):
        assert not (studio.DESIGNS / f"{slug}.history").exists(),             f"a test wrote {slug}.history into the user's library"


# -------------------------------------------------------------- the diff API ---

def _mkchange(client):
    """v1 (opened) -> v2 with a known, checkable difference."""
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/feature/add", json={
        "id": "extra", "op": "with_center_hole", "params": {"radius": 3},
        "inputs": ["bolts"]})
    client.post("/api/save")               # nothing mints until it is pushed


def test_the_diff_defaults_to_comparing_against_the_parent(client, saved):
    _mkchange(client)
    d = client.get("/api/versions/diff?target=v2").json()
    assert d["base"] == "v1" and d["target"] == "v2"
    assert [a["id"] for a in d["added"]] == ["extra"]
    assert d["added"][0]["op"] == "with_center_hole"
    ch = next(c for c in d["changed"] if c["id"] == "bore")
    p = next(p for p in ch["params"] if p["param"] == "radius")
    assert p["from"] == "15" and p["to"] == "11" and p["scalar"] is True
    assert "+1 feature" in d["summary"] and "1 changed" in d["summary"]


def test_the_diff_accepts_an_explicit_base(client, saved):
    _mkchange(client)
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 12})
    client.post("/api/save")                                  # v3
    d = client.get("/api/versions/diff?target=v3&base=v1").json()
    assert d["base"] == "v1"
    ch = next(c for c in d["changed"] if c["id"] == "bore")
    assert next(p for p in ch["params"] if p["param"] == "radius")["to"] == "12"


def test_the_first_version_says_there_is_nothing_to_compare(client, saved):
    d = client.get("/api/versions/diff?target=v1").json()
    assert d["base"] is None
    assert "nothing before it" in d["summary"]
    assert d["added"] == [] and d["changed"] == []


def test_diffing_an_unknown_version_is_a_clear_error(client, saved):
    d = client.get("/api/versions/diff?target=v99").json()
    assert "no version 'v99'" in d["error"]


def test_the_diff_on_a_design_with_no_history_says_so(client):
    d = client.get("/api/versions/diff?target=v1").json()
    assert "no history yet" in d["error"]


# ------------------------------------------------- who made it, and undo/redo ---

def test_manual_edits_are_recorded_as_the_users_own_work(client, saved):
    """User (2026-08-26): "if there is a design v5 and i am doing manually some
    changes over there, it should be saved as a manual change ... so ai can
    recognize the manual changes"."""
    for r in (11, 12, 13):
        client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": r})
    client.post("/api/save")
    v = _hist().get("v2")
    assert v.author == "you"
    assert v.source == "manual"
    assert v.label == "manual changes (3 edits)"


def test_an_ai_change_is_recorded_as_the_ais(client, saved, monkeypatch):
    monkeypatch.setattr(studio, "chat_intent", lambda *a, **k: {
        "action": "edit", "feature_id": "bore", "param": "radius", "value": 4})
    client.post("/api/chat", json={"message": "set the bore to 4"})
    client.post("/api/save")
    v = _hist().get("v2")
    assert v.author == "ai" and v.source == "ai"
    assert "AI" in v.label


def test_a_mixed_batch_saves_as_the_users_work_with_a_composite_label(
        client, saved, monkeypatch):
    """An AI edit plus a tool commit plus a hand nudge, pushed together: ONE
    version, attributed to the user (a mixed batch is their curation), the
    label saying what rode in."""
    monkeypatch.setattr(studio, "chat_intent", lambda *a, **k: {
        "action": "edit", "feature_id": "bore", "param": "radius", "value": 4})
    client.post("/api/chat", json={"message": "set the bore to 4"})
    client.post("/api/feature/add", json={
        "id": "extra", "op": "with_center_hole", "params": {"radius": 3},
        "inputs": ["bolts"]})
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 5})
    r = client.post("/api/save").json()
    assert r["version"] == "v2"
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1", "v2"]
    v = _hist().get("v2")
    assert v.source == "manual" and v.author == "you"
    assert "AI set bore.radius = 4" in v.label
    assert "with_center_hole added" in v.label
    assert "1 tweak" in v.label


def test_backfilled_versions_are_marked_as_coming_from_git():
    from history import _author_of
    assert _author_of("backfill:git") == "git"
    assert _author_of("ai") == "ai"
    for s in ("save", "manual", "open", "tool:extrude", ""):
        assert _author_of(s) == "you", s


def test_the_hand_edit_count_resets_after_it_is_recorded(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 12})
    client.post("/api/save")
    assert _hist().get("v3").label == "manual changes (1 edit)", \
        "the counter kept accumulating across versions"


def test_undo_and_redo_walk_both_ways(client, saved):
    def radius():
        return client.get("/api/doc").json()["features"][1]["params"]["radius"]

    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 9})
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 7})
    assert radius() == 7
    client.post("/api/undo")
    assert radius() == 9
    client.post("/api/undo")
    assert radius() == 15
    d = client.post("/api/redo").json()
    assert d["features"][1]["params"]["radius"] == 9
    assert d["can_redo"] is True and d["can_undo"] is True
    client.post("/api/redo")
    assert radius() == 7
    assert "nothing to redo" in client.post("/api/redo").json()["error"]


def test_a_new_edit_after_undo_ends_the_redo_line(client, saved):
    """Standard editor behaviour: undo, then do something else, and the branch
    you undid is gone. The VERSION tree is what keeps that recoverable."""
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 9})
    client.post("/api/undo")
    assert client.get("/api/doc").json()["can_redo"] is True
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 22})
    d = client.get("/api/doc").json()
    assert d["can_redo"] is False
    assert "nothing to redo" in client.post("/api/redo").json()["error"]


def test_redo_is_per_tab(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 9})
    client.post("/api/undo")
    client.post("/api/new", json={"name": "_test-versions-two"})
    assert client.get("/api/doc").json()["can_redo"] is False
    assert "nothing to redo" in client.post("/api/redo").json()["error"]


# --------------------------- dirty: changes waiting to be pushed as a version ---
# User (2026-09-01): edits must NOT auto-version; the tab shows it holds
# unpushed changes, the user pushes when they choose, and closing a dirty tab
# asks first (the ask lives in the UI — the flag here is what it runs on).

def _dirty_of(client):
    d = client.get("/api/doc").json()
    active = next(t for t in d["tabs"] if t["active"])
    assert d["dirty"] == active["dirty"], "doc and tab bar disagree on dirty"
    return d["dirty"]


def test_a_freshly_opened_design_is_clean(client, saved):
    assert _dirty_of(client) is False
    assert _versions(client)["dirty"] is False


def test_every_kind_of_edit_marks_the_tab_dirty_and_save_cleans_it(client, saved):
    client.post("/api/feature/add", json={
        "id": "extra", "op": "with_center_hole", "params": {"radius": 3},
        "inputs": ["bolts"]})
    assert _dirty_of(client) is True
    assert _versions(client)["dirty"] is True
    client.post("/api/save")
    assert _dirty_of(client) is False

    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    assert _dirty_of(client) is True
    client.post("/api/save")
    assert _dirty_of(client) is False


def test_undoing_every_edit_reads_clean_again(client, saved):
    """Dirty is a HASH comparison, not a flag: edit + undo = nothing to push,
    so the close prompt never cries wolf."""
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    assert _dirty_of(client) is True
    client.post("/api/undo")
    assert _dirty_of(client) is False


def test_restoring_a_version_reads_clean(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")
    client.post("/api/versions/restore", json={"id": "v1"})
    assert _dirty_of(client) is False


def test_a_never_saved_design_with_features_is_dirty(client):
    """No file means closing the tab loses the work — that must read dirty so
    the UI asks, even though there is no version to compare against."""
    assert _dirty_of(client) is True          # the flange sample tab, no file
    client.post("/api/new", json={"name": "_test-versions-two"})
    assert _dirty_of(client) is False         # empty scratch design — nothing to lose


def test_closing_a_dirty_tab_discards_without_touching_the_design(client, saved):
    """The server side of "Discard & close": the file and its versions stay
    exactly as they were; only the tab's unpushed edits die with it."""
    on_disk = _design_path().read_text(encoding="utf-8")
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 55})
    tid = studio.STATE["active"]
    client.post("/api/tabs/close", json={"id": tid})
    assert _design_path().read_text(encoding="utf-8") == on_disk
    assert [v.id for v in _hist().versions()] == ["v1"]

    client.post(f"/api/open/{saved}")          # reopen: the saved state, clean
    d = client.get("/api/doc").json()
    assert d["features"][1]["params"]["radius"] != 55
    assert _dirty_of(client) is False


def test_stale_pending_notes_do_not_leak_into_a_later_versions_label(
        client, saved):
    """Add a feature, restore v1 (the addition goes to the undo stack), then
    hand-nudge and save: the label must describe the nudge, not the feature
    that is no longer part of the pushed design."""
    client.post("/api/feature/add", json={
        "id": "extra", "op": "with_center_hole", "params": {"radius": 3},
        "inputs": ["bolts"]})
    client.post("/api/versions/restore", json={"id": "v1"})
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    r = client.post("/api/save").json()
    assert r["version"] == "v2"
    assert "with_center_hole" not in _hist().get("v2").label
    assert _hist().get("v2").label == "manual changes (1 edit)"


# ------------------------------------------------------------ deleting one ---

def test_deleting_a_version_removes_it_from_the_listing(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")                                  # v2 (current)
    r = client.post("/api/versions/delete", json={"id": "v1"}).json()
    assert r == {"deleted": "v1", "rewired": ["v2"], "parent": None}
    d = _versions(client)
    assert [v["id"] for v in d["versions"]] == ["v2"]
    assert d["versions"][0]["parent"] is None
    assert d["problems"] == []


def test_deleting_the_current_version_is_refused(client, saved):
    r = client.post("/api/versions/delete", json={"id": "v1"}).json()
    assert "version you are on" in r["error"]
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1"]


def test_deleting_the_starred_version_is_refused(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")                                  # v2 (current)
    client.post("/api/versions/star", json={"id": "v1"})
    r = client.post("/api/versions/delete", json={"id": "v1"}).json()
    assert "starred" in r["error"]
    assert _versions(client)["starred"] == "v1"


def test_deleting_with_no_history_or_no_id_says_so(client, saved):
    r = client.post("/api/versions/delete", json={}).json()
    assert "which version" in r["error"]
    client.post("/api/new", json={"name": "_test-versions-two"})
    r = client.post("/api/versions/delete", json={"id": "v1"}).json()
    assert "no history yet" in r["error"]


# --------------------------------------- update-in-place vs push-as-new-version ---

def test_amend_updates_the_current_version_instead_of_minting(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    r = client.post("/api/versions/amend").json()
    assert r.get("amended") == "v1" and r["saved"] == TMP, r
    assert r["dirty"] is False
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1"]
    assert _hist().snapshot("v1")["features"][1]["params"]["radius"] == 11
    # the design FILE holds the amended state too — "save those changes"
    on_disk = json.loads(_design_path().read_text(encoding="utf-8"))
    assert on_disk["features"][1]["params"]["radius"] == 11


def test_amend_refuses_when_newer_versions_hang_off_the_current(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")                                  # v2
    client.post("/api/versions/restore", json={"id": "v1"})
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 12})
    r = client.post("/api/versions/amend").json()
    assert "branched from it" in r["error"], r
    assert r["dirty"] is True, "a refused amend still marked the tab clean"
    assert _hist().snapshot("v1")["features"][1]["params"]["radius"] == 15


def test_the_listing_says_what_the_next_push_would_be(client, saved):
    assert _versions(client)["next_id"] == "v2"
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")
    assert _versions(client)["next_id"] == "v3"


def test_delete_after_trims_the_tail_and_the_numbering(client, saved):
    """The user's esp32 flow end to end: versions pile up after v1, they go
    back to v1, trim the tail in one call, and the next push counts on from
    where they stand — not from where the junk left off."""
    for r in (11, 12, 13):
        client.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": r})
        client.post("/api/save")                              # v2, v3, v4
    client.post("/api/versions/restore", json={"id": "v1"})
    r = client.post("/api/versions/delete_after", json={"id": "v1"}).json()
    assert r["deleted"] == ["v2", "v3", "v4"] and r["next"] == "v2", r
    assert [v["id"] for v in _versions(client)["versions"]] == ["v1"]
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 99})
    assert client.post("/api/save").json()["version"] == "v2"


def test_delete_after_refuses_from_below_the_cut(client, saved):
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")                                  # current v2
    r = client.post("/api/versions/delete_after", json={"id": "v1"}).json()
    assert "open v1 first" in r["error"]
    assert len(_versions(client)["versions"]) == 2


# ------------------------------------ restoring what is already on screen ---

def test_restoring_the_version_you_are_on_does_not_rebuild(client, saved):
    """Clicking v16 while v16 is on screen used to reload the whole design —
    ~30 s on the esp32 case, to arrive exactly where you already are."""
    r = client.post("/api/versions/restore", json={"id": "v1"}).json()
    assert r.get("already") is True and r["restored"] == "v1"
    assert r["can_undo"] is False, \
        "a no-op restore pushed an undo entry (so it rebuilt)"
    assert _versions(client)["current"] == "v1"


def test_restoring_the_current_version_while_DIRTY_really_restores(
        client, saved):
    """With unsaved edits the same click is meaningful again: it puts the
    pristine version back, and the edits go to the undo stack."""
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    r = client.post("/api/versions/restore", json={"id": "v1"}).json()
    assert "already" not in r
    assert r["features"][1]["params"]["radius"] == 15    # v1's value is back
    assert r["dirty"] is False
    d = client.post("/api/undo").json()
    assert d["features"][1]["params"]["radius"] == 11, "the edits were lost"


def test_restoring_an_identical_TWIN_version_only_moves_the_marker(
        client, saved):
    """A->B->A: v3 holds the same content as v1. Standing on v3, clicking v1
    must not rebuild — but it MUST move `current`, so the next edit branches
    off v1 as asked."""
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")                              # v2
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 15})
    client.post("/api/save")                              # v3 == v1's content
    r = client.post("/api/versions/restore", json={"id": "v1"}).json()
    assert r.get("already") is True
    assert _versions(client)["current"] == "v1"


# ---------------------------------------------------------------------------
# Section 3 code review, 2026-09-10.
#
# F1 (P0): File > New, type a name that already exists, Save -- and that
# design's .tcad.json was OVERWRITTEN while the new content was appended to
# its version tree as a child of its latest version. Measured: tab A saved 1
# feature as v1, a second tab of the same name saved 0 features as v2 and the
# file on disk went to 0 features. Both tabs then carried the same `source`,
# so two tabs wrote one file and one history. The slug rule does it without
# any exact typing: "cam cover plaque" -> cam-cover-plaque.
#
# F3 (P2): when index.json is lost the panel says "History.repair() rebuilds
# an index from them" -- a Python method with no button, endpoint or CLI.
# ---------------------------------------------------------------------------

def test_saving_over_another_designs_name_is_refused(client):
    studio._doc().name = TMP
    r = client.post("/api/save").json()
    assert r["saved"] == TMP and r.get("version") == "v1"
    original = json.loads(_design_path().read_text(encoding="utf-8"))
    assert original["features"], "the first design must have content"

    # a SECOND tab, named the same -- /api/new does not object
    client.post("/api/new", json={"name": TMP})
    client.post("/api/feature/add", json={
        "id": "other", "op": "disc",
        "params": {"radius": 3, "thickness": 1}, "inputs": []})
    r = client.post("/api/save").json()
    assert r.get("error"), "saving over another design was allowed"
    assert TMP in r["error"]

    # nothing moved: not the file, not the tree, not the tab binding
    assert json.loads(_design_path().read_text(encoding="utf-8")) == original
    h = History.for_design(studio._history_root(), TMP)
    assert [v.id for v in h.versions()] == ["v1"]
    assert h.current() == "v1"
    sources = [e.get("source") for e in studio.STATE["docs"].values()]
    assert sources.count(f"file:{TMP}") == 1, \
        "two tabs ended up bound to one design"


def test_a_design_can_still_be_saved_over_its_own_file(client):
    """The guard must not block the everyday case: saving the design you
    opened, over and over."""
    studio._doc().name = TMP
    assert client.post("/api/save").json()["saved"] == TMP
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    r = client.post("/api/save").json()
    assert r["saved"] == TMP and not r.get("error")
    assert r.get("version") == "v2"


def test_a_lost_index_can_be_rebuilt_from_the_panel(client):
    studio._doc().name = TMP
    client.post("/api/save")
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 12})
    client.post("/api/save")
    h = History.for_design(studio._history_root(), TMP)
    assert len(h.versions()) == 2
    (h.path / "index.json").unlink()                # the index is gone

    d = client.get("/api/versions").json()
    assert d["problems"] and "rebuild the list" in " ".join(d["problems"])
    assert d.get("can_repair") is True, \
        "the panel is told to run repair() with no way to run it"

    r = client.post("/api/versions/repair").json()
    assert not r.get("error"), r
    assert r["recovered"] == 2
    back = History.for_design(studio._history_root(), TMP)
    assert [v.id for v in back.versions()] == ["v1", "v2"]
    assert not back.problems()


def test_repair_refuses_a_healthy_history(client):
    """It rebuilds a LINEAR chain with '(recovered)' labels and no star, so
    running it on a working tree would throw away real information."""
    studio._doc().name = TMP
    client.post("/api/save")
    r = client.post("/api/versions/repair").json()
    assert r.get("error") and "nothing to repair" in r["error"].lower()


def test_saving_content_the_file_already_holds_is_still_allowed(client):
    """A sample tab writing itself into the library, or a second save of an
    unchanged design: nothing can be lost, so the guard must not fire.

    No OTHER tab may own the file, though — see the next test."""
    studio._doc().name = TMP
    assert client.post("/api/save").json()["saved"] == TMP
    owner = studio.STATE["active"]
    client.post("/api/new", json={"name": TMP})           # a fresh, unbound tab
    studio.STATE["docs"][studio.STATE["active"]]["doc"] = studio.Document.load(
        str(_design_path()))
    client.post("/api/tabs/close", json={"id": owner})    # ...and A is closed
    r = client.post("/api/save").json()
    assert r["saved"] == TMP and not r.get("error")


# ---------------------------------------------------------------------------
# Section 3 FIX-PASS review, 2026-09-10: three doors the F1 guard left open,
# all measured first in probes/version_review_probe.py.
# ---------------------------------------------------------------------------

def test_a_second_tab_cannot_take_over_an_open_designs_file(client):
    """The identical-content escape hatch bound a SECOND tab to the file, and
    from then on either tab's save silently overwrote the other's and hung its
    version off the other's latest. Measured: bore.radius 11 -> 44, with v3
    parented to a v2 it never came out of."""
    studio._doc().name = TMP
    assert client.post("/api/save").json()["saved"] == TMP
    a_tid = studio.STATE["active"]

    # tab B holds EXACTLY what the file holds, so the content check passes
    client.post("/api/new", json={"name": TMP})
    studio.STATE["docs"][studio.STATE["active"]]["doc"] = studio.Document.load(
        str(_design_path()))
    r = client.post("/api/save").json()
    assert r.get("error"), "a second tab took over an open design's file"
    assert "another tab" in r["error"]
    sources = [e.get("source") for e in studio.STATE["docs"].values()]
    assert sources.count(f"file:{TMP}") == 1

    # ...and the tab that DOES own it keeps saving over it
    studio.STATE["active"] = a_tid
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    assert client.post("/api/save").json().get("version") == "v2"


def test_the_owner_tab_is_matched_case_insensitively(client):
    """This filesystem is case-insensitive, so file:Flange-Case and
    file:flange-case are ONE file and must not be owned by two tabs."""
    studio._doc().name = TMP
    client.post("/api/save")
    studio.STATE["docs"][studio.STATE["active"]]["source"] = f"file:{TMP.upper()}"
    client.post("/api/new", json={"name": TMP})
    studio.STATE["docs"][studio.STATE["active"]]["doc"] = studio.Document.load(
        str(_design_path()))
    r = client.post("/api/save").json()
    assert r.get("error") and "another tab" in r["error"]


def test_saving_onto_a_deleted_designs_version_tree_is_refused(client):
    """The design FILE is not the only thing a save lands on. There is no
    in-app delete, so a design removed in Explorer leaves <slug>.history/
    behind -- and an unrelated design of the same name appended itself to that
    tree as a child of its last version, under its design_id and its name
    (measured: a 1-feature disc became v3 of a 3-feature flange)."""
    studio._doc().name = TMP
    client.post("/api/save")
    client.post("/api/edit", json={"feature_id": "bore",
                                   "param": "radius", "value": 11})
    client.post("/api/save")
    h = _hist()
    assert [v.id for v in h.versions()] == ["v1", "v2"]
    design_id = h.design_id

    _design_path().unlink()                       # deleted in Explorer...
    client.post("/api/tabs/close", json={"id": studio.STATE["active"]})

    client.post("/api/new", json={"name": TMP})   # ...and the name reused
    client.post("/api/feature/add", json={
        "id": "other", "op": "disc",
        "params": {"radius": 3, "thickness": 1}, "inputs": []})
    r = client.post("/api/save").json()
    assert r.get("error"), "an unrelated design was grafted onto that tree"
    assert f"{TMP}.history" in r["error"]
    back = _hist()
    assert [v.id for v in back.versions()] == ["v1", "v2"]
    assert back.design_id == design_id
    assert not _design_path().exists()


def test_repair_says_the_real_reason_it_cannot_rebuild(client):
    """An index from a NEWER build is unusable here and still holds every
    parent, label and star a rebuild would guess away. Answering that with
    "your version list is readable" was the opposite of the truth."""
    studio._doc().name = TMP
    client.post("/api/save")
    h = _hist()
    idx = h.path / "index.json"
    data = json.loads(idx.read_text(encoding="utf-8"))
    data["schema"] = 999
    idx.write_text(json.dumps(data), encoding="utf-8")

    d = client.get("/api/versions").json()
    assert d.get("can_repair") is False, "the panel offered to overwrite it"
    r = client.post("/api/versions/repair").json()
    assert r.get("error") and "schema" in r["error"]
    # and the index is exactly as it was
    assert json.loads(idx.read_text(encoding="utf-8")) == data
