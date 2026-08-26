"""P1 of VERSION-TREE-PLAN.md — the version-tree storage core.

This is the phase where the feature is either robust or flaky, so the tests are
written against the four invariants in history.py's docstring rather than
against the happy path:

1. a version is only recorded when the content hash changes
2. editing from an old version BRANCHES, it never truncates
3. the snapshot is written before the index
4. a broken index is never overwritten

Plus the failure modes the user asked to be thought through up front: restart,
crash mid-write, a corrupt snapshot, a vanished index, and rename.
"""
import gzip
import json

import pytest

import history
from history import History, HistoryError, INDEX


def design(name="part", n=3, w=10):
    """A stand-in for Document.to_data() — this layer never imports Document."""
    return {"name": name, "spec": {"n_solids": 1},
            "features": [{"id": f"f{i}", "op": "plate",
                          "params": {"w": w + i}, "inputs": []}
                         for i in range(n)]}


@pytest.fixture()
def h(tmp_path):
    return History(tmp_path / "part.history").init("part")


def _chain(h, n, start=1):
    """n sequential versions, each genuinely different."""
    return [h.append(design(w=start + i), label=f"v{i + 1}") for i in range(n)]


# ------------------------------------------------- invariant 1: no-op edits ---

def test_an_identical_snapshot_is_not_recorded_twice(h):
    a = h.append(design(), label="first")
    b = h.append(design(), label="same content")
    assert b.id == a.id, "a no-op edit created a version"
    assert len(h.versions()) == 1
    assert b.label == "first", "the existing version was relabelled"


def test_reopening_the_same_design_ten_times_adds_nothing(h):
    h.append(design(), label="opened")
    for _ in range(10):
        h.append(design(), source="open")
    assert len(h.versions()) == 1


def test_returning_to_an_earlier_STATE_does_record(h):
    """Dedupe is against the PARENT only. A→B→A is real history: the design
    genuinely changed twice, and collapsing it would lose the round trip."""
    h.append(design(w=1))
    h.append(design(w=2))
    v3 = h.append(design(w=1))
    assert v3.id == "v3" and len(h.versions()) == 3


def test_the_hash_ignores_key_order(h):
    v1 = h.append({"name": "p", "spec": {"a": 1, "b": 2}, "features": []})
    v2 = h.append({"spec": {"b": 2, "a": 1}, "features": [], "name": "p"})
    assert v2.id == v1.id, "re-serialisation looked like a change"


# --------------------------------------------------- invariant 2: branching ---

def test_editing_from_an_old_version_branches_and_keeps_the_newer_ones(h):
    """THE core invariant. Go back to v3 of ten and edit: the new version hangs
    off v3, and v4..v10 must all still be reachable."""
    _chain(h, 10)
    assert [v.id for v in h.versions()] == [f"v{i}" for i in range(1, 11)]

    h.set_current("v3")
    new = h.append(design(w=999), label="different idea")

    assert new.id == "v11" and new.parent == "v3"
    for old in ("v4", "v5", "v6", "v7", "v8", "v9", "v10"):
        assert h.get(old) is not None
        assert h.snapshot(old)["features"], f"{old} lost its payload"
    assert sorted(h.children("v3")) == ["v11", "v4"]
    assert h.branch_points() == ["v3"]
    assert sorted(h.leaves()) == ["v10", "v11"]


def test_two_branches_from_one_parent_both_survive(h):
    _chain(h, 2)
    h.set_current("v1")
    a = h.append(design(w=50), label="idea A")
    h.set_current("v1")
    b = h.append(design(w=80), label="idea B")
    assert sorted(h.children("v1")) == sorted(["v2", a.id, b.id])
    assert h.snapshot(a.id) != h.snapshot(b.id)


def test_version_ids_are_monotonic_across_branches(h):
    _chain(h, 3)
    h.set_current("v1")
    assert h.append(design(w=40)).id == "v4"       # not v2 again
    h.set_current("v2")
    assert h.append(design(w=41)).id == "v5"


def test_ancestors_walks_root_first(h):
    _chain(h, 3)
    h.set_current("v1")
    v4 = h.append(design(w=70))
    assert h.ancestors("v3") == ["v1", "v2"]
    assert h.ancestors(v4.id) == ["v1"]
    assert h.ancestors("v1") == []


def test_explicit_parent_overrides_current(h):
    _chain(h, 3)
    v = h.append(design(w=60), parent="v1")
    assert v.parent == "v1" and h.current() == v.id


def test_a_dangling_parent_is_refused(h):
    h.append(design())
    with pytest.raises(HistoryError, match="no version 'v99'"):
        h.append(design(w=5), parent="v99")


# ------------------------------------------------------- restart durability ---

def test_history_survives_being_reopened_from_disk(h, tmp_path):
    """The old undo stack was in memory and died with the server. This must
    not."""
    _chain(h, 3)
    h.set_current("v2")
    h.star("v2")
    h.relabel("v3", "the good one")
    before_id, before_snap = h.design_id, h.snapshot("v3")

    again = History(tmp_path / "part.history")
    assert [v.id for v in again.versions()] == ["v1", "v2", "v3"]
    assert again.current() == "v2" and again.starred() == "v2"
    assert again.get("v3").label == "the good one"
    assert again.design_id == before_id
    assert again.snapshot("v3") == before_snap
    assert not again.problems()


def test_a_snapshot_round_trips_exactly(h):
    payload = design(n=6, w=3)
    payload["spec"] = {"n_solids": 1, "holes": {"4.0": 6}, "tol": 0.5}
    v = h.append(payload)
    assert h.snapshot(v.id) == payload
    assert v.features == 6


# ---------------------------------------------- invariant 3+4: crash safety ---

def test_a_crash_writing_the_index_leaves_the_previous_one_intact(
        h, tmp_path, monkeypatch):
    """Snapshot first, index second, and the index write is atomic — so a crash
    can leave an orphaned snapshot but never a half-written index nor an entry
    pointing at a payload that is not there."""
    _chain(h, 2)
    real = history.os.replace

    def boom(src, dst):
        if str(dst).endswith(INDEX):
            raise OSError("simulated crash mid-write")
        return real(src, dst)

    monkeypatch.setattr(history.os, "replace", boom)
    with pytest.raises(OSError):
        h.append(design(w=77), label="never landed")
    monkeypatch.setattr(history.os, "replace", real)

    # the live object must not be ahead of its own disk
    assert [v.id for v in h.versions()] == ["v1", "v2"]
    assert h.current() == "v2"

    again = History(tmp_path / "part.history")
    assert [v.id for v in again.versions()] == ["v1", "v2"]
    assert again.current() == "v2"
    assert not again.problems(), "an orphan snapshot was reported as a fault"


def test_a_crash_writing_the_SNAPSHOT_leaves_no_dangling_index_entry(
        h, tmp_path, monkeypatch):
    """This is what pins the ORDER (invariant 3). Crash while writing the
    payload: because the index is written second, it must not yet mention the
    version. The other order would leave the tree advertising a version whose
    snapshot never landed — an entry that can never be opened."""
    _chain(h, 2)
    real = history.os.replace

    def boom(src, dst):
        if str(dst).endswith(".json.gz"):
            raise OSError("simulated crash writing the snapshot")
        return real(src, dst)

    monkeypatch.setattr(history.os, "replace", boom)
    with pytest.raises(OSError):
        h.append(design(w=77), label="payload never landed")
    monkeypatch.setattr(history.os, "replace", real)

    again = History(tmp_path / "part.history")
    assert [v.id for v in again.versions()] == ["v1", "v2"],         "the index recorded a version whose snapshot was never written"
    assert not again.problems()
    for v in again.versions():                    # every entry is openable
        assert again.snapshot(v.id)["features"]


def test_the_id_of_a_never_indexed_version_is_reused(h, monkeypatch):
    """Deliberate: v3 was never RECORDED, so the number is free. Ids are
    monotonic over real versions, not over failed write attempts."""
    _chain(h, 2)
    real = history.os.replace
    monkeypatch.setattr(history.os, "replace", lambda s, d: (
        real(s, d) if not str(d).endswith(INDEX) else
        (_ for _ in ()).throw(OSError("crash"))))
    with pytest.raises(OSError):
        h.append(design(w=77))
    monkeypatch.setattr(history.os, "replace", real)
    assert h.append(design(w=88)).id == "v3"


def test_a_corrupt_index_is_reported_and_never_overwritten(h, tmp_path):
    _chain(h, 2)
    idx = tmp_path / "part.history" / INDEX
    idx.write_text("{ this is not json", encoding="utf-8")

    broken = History(tmp_path / "part.history")
    assert not broken.exists()
    assert any("unreadable" in p for p in broken.problems())
    assert any("repair()" in p for p in broken.problems())

    with pytest.raises(HistoryError, match="unreadable"):
        broken.append(design(w=9))
    assert idx.read_text(encoding="utf-8") == "{ this is not json", \
        "a corrupt index was clobbered — the snapshots are the only copy left"
    assert (tmp_path / "part.history" / "v1.json.gz").exists()


def test_init_does_not_paper_over_a_corrupt_index(h, tmp_path):
    _chain(h, 1)
    (tmp_path / "part.history" / INDEX).write_text("nope", encoding="utf-8")
    broken = History(tmp_path / "part.history").init("part")
    assert not broken.exists(), "init() started a fresh index over a broken one"


def test_an_unknown_schema_is_refused_rather_than_guessed(h, tmp_path):
    _chain(h, 1)
    idx = tmp_path / "part.history" / INDEX
    data = json.loads(idx.read_text(encoding="utf-8"))
    data["schema"] = 99
    idx.write_text(json.dumps(data), encoding="utf-8")

    future = History(tmp_path / "part.history")
    assert not future.exists()
    assert any("schema 99" in p for p in future.problems())
    with pytest.raises(HistoryError, match="schema"):
        future.append(design())


# ------------------------------------------------------- corrupt SNAPSHOTS ---

def test_one_corrupt_snapshot_does_not_take_the_others_with_it(h, tmp_path):
    _chain(h, 3)
    (tmp_path / "part.history" / "v2.json.gz").write_bytes(b"not gzip at all")

    reread = History(tmp_path / "part.history")
    assert reread.exists()                       # the tree itself is fine
    assert [v.id for v in reread.versions()] == ["v1", "v2", "v3"]
    assert reread.snapshot("v1")["features"]
    assert reread.snapshot("v3")["features"]
    with pytest.raises(HistoryError, match="corrupt"):
        reread.snapshot("v2")
    probs = reread.problems()
    assert len(probs) == 1 and "v2" in probs[0]
    assert "unaffected" in probs[0]


def test_a_missing_snapshot_is_named_not_guessed(h, tmp_path):
    _chain(h, 2)
    (tmp_path / "part.history" / "v1.json.gz").unlink()
    reread = History(tmp_path / "part.history")
    assert any("v1" in p and "missing" in p for p in reread.problems())
    with pytest.raises(HistoryError, match="gone"):
        reread.snapshot("v1")
    assert reread.snapshot("v2")["features"]      # still usable


def test_a_vanished_index_over_real_snapshots_is_not_reported_as_empty(
        h, tmp_path):
    """'You have no versions' and 'your index disappeared' must never read the
    same — the second is recoverable and the user has to be told."""
    _chain(h, 3)
    (tmp_path / "part.history" / INDEX).unlink()
    lost = History(tmp_path / "part.history")
    assert not lost.exists()
    assert any("missing" in p and "3 version" in p for p in lost.problems())


def test_repair_rebuilds_an_index_from_the_snapshots(h, tmp_path):
    _chain(h, 3)
    keep = h.snapshot("v2")
    (tmp_path / "part.history" / INDEX).unlink()

    lost = History(tmp_path / "part.history")
    notes = lost.repair()
    assert [v.id for v in lost.versions()] == ["v1", "v2", "v3"]
    assert lost.snapshot("v2") == keep
    assert lost.current() == "v3"
    assert not lost.problems()
    # honest about what it could not know
    assert any("linear" in n and "branch" in n for n in notes)
    assert all(v.label == "(recovered)" for v in lost.versions())


def test_repair_skips_a_corrupt_snapshot_and_says_so(h, tmp_path):
    _chain(h, 3)
    (tmp_path / "part.history" / "v2.json.gz").write_bytes(b"junk")
    (tmp_path / "part.history" / INDEX).unlink()

    lost = History(tmp_path / "part.history")
    notes = lost.repair()
    assert [v.id for v in lost.versions()] == ["v1", "v3"]
    assert any("v2" in n and "left out" in n for n in notes)


def test_repair_with_nothing_to_recover_refuses(tmp_path):
    empty = History(tmp_path / "gone.history")
    with pytest.raises(HistoryError, match="nothing to repair"):
        empty.repair()


# ------------------------------------------------------------------ rename ---

def test_renaming_moves_the_history_and_keeps_its_identity(h, tmp_path):
    """A rename must not fork history — same design_id, same versions, and the
    old directory gone rather than left as a decoy."""
    _chain(h, 3)
    h.star("v2")
    did = h.design_id

    h.rename("part-mk2")
    assert h.path.name == "part-mk2.history"
    assert not (tmp_path / "part.history").exists()

    moved = History(tmp_path / "part-mk2.history")
    assert moved.design_id == did
    assert [v.id for v in moved.versions()] == ["v1", "v2", "v3"]
    assert moved.starred() == "v2" and moved.name == "part-mk2"
    assert moved.snapshot("v3")["features"]


def test_renaming_onto_an_existing_history_is_refused(h, tmp_path):
    _chain(h, 1)
    other = History(tmp_path / "taken.history").init("taken")
    other.append(design(name="taken"))
    with pytest.raises(HistoryError, match="refusing to merge"):
        h.rename("taken")
    assert h.path.name == "part.history", "the move half-happened"


def test_renaming_to_the_same_slug_is_a_no_op(h):
    _chain(h, 1)
    h.rename("part")
    assert h.path.name == "part.history" and len(h.versions()) == 1


# -------------------------------------------------------------------- star ---

def test_exactly_one_version_can_be_starred(h):
    """Recency does not answer 'which is my intended design', so the star is
    the answer — and only one thing can hold it."""
    _chain(h, 3)
    assert h.starred() is None
    h.star("v1")
    assert h.starred() == "v1"
    h.star("v3")
    assert h.starred() == "v3", "starring did not move the pin"
    h.star(None)
    assert h.starred() is None


def test_starring_an_unknown_version_is_refused(h):
    _chain(h, 1)
    with pytest.raises(HistoryError, match="no version"):
        h.star("v42")
    assert h.starred() is None


def test_the_star_and_current_are_independent(h):
    _chain(h, 3)
    h.star("v1")
    h.set_current("v2")
    assert h.starred() == "v1" and h.current() == "v2"


# ------------------------------------------------------------ book-keeping ---

def test_a_fresh_history_is_empty_but_valid(tmp_path):
    fresh = History(tmp_path / "new.history")
    assert not fresh.exists() and not fresh.problems()
    assert fresh.versions() == [] and fresh.current() is None
    with pytest.raises(HistoryError, match="init"):
        fresh.append(design())
    fresh.init("new")
    assert fresh.exists() and fresh.design_id.startswith("d_")


def test_init_is_idempotent(tmp_path):
    a = History(tmp_path / "x.history").init("x")
    a.append(design())
    did = a.design_id
    b = History(tmp_path / "x.history").init("x")
    assert b.design_id == did and len(b.versions()) == 1


def test_for_design_builds_the_sidecar_path(tmp_path):
    hh = History.for_design(tmp_path, "esp32-remote")
    assert hh.path == tmp_path / "esp32-remote.history"


def test_backfill_can_supply_its_own_timestamps_and_commits(h):
    """P4 replays git history, so `created` and `commit` have to be injectable
    — otherwise every imported version would claim to be from today."""
    v = h.append(design(), label="esp32-remote v9", source="backfill:git",
                 commit="0926b52", created="2026-08-25T14:41:03+00:00")
    assert v.created == "2026-08-25T14:41:03+00:00"
    assert v.commit == "0926b52" and v.source == "backfill:git"


def test_metadata_the_caller_measured_is_stored_verbatim(h):
    v = h.append(design(), spec={"volume": 107260.0, "size": [200, 90, 12]},
                 rebuildable=True)
    assert h.get(v.id).spec["volume"] == 107260.0
    assert h.get(v.id).rebuildable is True


def test_a_version_that_no_longer_rebuilds_is_still_recorded(h):
    """An op renamed since v2 means v2 cannot build. It must stay in the tree
    as a record — losing the snapshot would be far worse than showing a version
    the current build cannot open."""
    v = h.append(design(), rebuildable=False, label="pre-rename")
    assert h.get(v.id).rebuildable is False
    assert h.snapshot(v.id)["features"], "the payload was dropped"


def test_tree_lines_shows_shape_current_and_star(h):
    _chain(h, 2)
    h.set_current("v1")
    h.append(design(w=30), label="branch")
    h.star("v2")
    lines = h.tree_lines()
    assert len(lines) == 3
    assert lines[0].strip().startswith("v1")
    assert "★" in [l for l in lines if "v2" in l][0]
    assert [l for l in lines if "v3" in l][0].startswith("*")


def test_a_hundred_versions_stay_cheap(h, tmp_path):
    """Sizes were measured, not assumed: feature-tree JSON gzips 12-19x, so a
    long history must not blow up on disk."""
    for i in range(100):
        h.append(design(n=20, w=i))
    assert len(h.versions()) == 100
    assert h.versions()[-1].id == "v100"
    total = sum(p.stat().st_size
                for p in (tmp_path / "part.history").glob("v*.json.gz"))
    assert total < 200_000, f"100 versions cost {total} bytes"
    assert History(tmp_path / "part.history").snapshot("v50")["features"]


def test_snapshots_are_actually_compressed(h, tmp_path):
    payload = design(n=200)
    v = h.append(payload)
    raw = len(json.dumps(payload).encode("utf-8"))
    on_disk = (tmp_path / "part.history" / f"{v.id}.json.gz").stat().st_size
    assert on_disk < raw / 4, f"{on_disk} vs raw {raw} — not compressed"
    with gzip.open(tmp_path / "part.history" / f"{v.id}.json.gz",
                   "rt", encoding="utf-8") as fh:
        assert json.load(fh) == payload
