"""P4 of VERSION-TREE-PLAN.md — replaying git history into version trees.

These run against THIS repo's real git history, because that is the thing being
imported and a mock would not have caught either of the two git traps below.
Counts are asserted with >= where new commits could land, and exactly where the
number is a fact about the past.
"""
import shutil

import pytest

import backfill
from backfill import SOURCE, Report
from history import History

pytestmark = pytest.mark.skipif(shutil.which("git") is None
                                and not backfill.Path(
                                    backfill._FALLBACK_GIT).exists(),
                                reason="git not available")


@pytest.fixture()
def repo():
    return backfill.Path(__file__).resolve().parent.parent


@pytest.fixture()
def root(tmp_path):
    d = tmp_path / "hist"
    d.mkdir()
    return d


def _run(slug, repo, root, **kw):
    return backfill.backfill_one(slug, repo=repo, designs_dir=repo / "designs",
                                 history_root=root, **kw)


# ------------------------------------------------------------- git plumbing ---

def test_commits_come_back_oldest_first_with_real_timestamps(repo):
    cs = backfill.commits_for(repo, "rocky-keychain")
    assert len(cs) >= 24
    assert [c.when for c in cs] == sorted(c.when for c in cs), "not oldest-first"
    assert cs[0].when.startswith("2026-08-18"), cs[0].when
    assert "rocky-keychain" in cs[0].subject
    assert all(len(c.sha) == 40 for c in cs)


def test_reverse_and_follow_together_would_have_broken_this(repo):
    """REGRESSION. `--reverse --follow` returns ONE commit for esp32-remote
    where the same query without --reverse returns 16: --follow is a hack in
    the revision walker and does not compose with --reverse. The first version
    of this module used both and would silently have imported 1 of 15."""
    cs = backfill.commits_for(repo, "esp32-remote")
    assert len(cs) >= 15, f"only {len(cs)} commits — the --reverse bug is back"


def test_one_designs_history_never_bleeds_into_another(repo):
    """REGRESSION, and the worse of the two traps. With `--follow`, git's rename
    heuristic walks autonomiq-sat-panel.tcad.json back into
    sat-side-panel.tcad.json and then isogrid-panel.tcad.json — DIFFERENT
    designs, each with their own file, history and tree. Following imported
    another design's commits under this one's name."""
    subjects = [c.subject for c in backfill.commits_for(repo,
                                                        "autonomiq-sat-panel")]
    assert subjects, "no commits at all"
    assert all("autonomiq-sat-panel" in s for s in subjects), subjects
    assert not any("sat-side-panel" in s or "isogrid" in s for s in subjects)
    # and the neighbour keeps its own
    other = [c.subject for c in backfill.commits_for(repo, "sat-side-panel")]
    assert other and all("sat-side-panel" in s for s in other), other


def test_a_blob_reads_back_as_a_design(repo):
    cs = backfill.commits_for(repo, "autonomiq-sat-panel")
    data = backfill.blob_at(repo, cs[0].sha, "autonomiq-sat-panel")
    assert data["name"] and isinstance(data["features"], list)
    assert data["features"]


def test_library_slugs_skips_the_examples_catalogue(repo):
    slugs = backfill.library_slugs(repo / "designs")
    assert "examples" not in slugs and "rocky-keychain" in slugs


# --------------------------------------------------------------- the replay ---

def test_a_design_is_replayed_as_a_linear_chain(repo, root):
    rep = _run("autonomiq-sat-panel", repo, root)
    assert rep.status == "ok"
    h = History.for_design(root, "autonomiq-sat-panel")
    vs = h.versions()
    assert len(vs) == rep.commits - rep.deduped
    assert vs[0].parent is None
    for prev, cur in zip(vs, vs[1:]):
        assert cur.parent == prev.id, "not a chain"
    assert h.branch_points() == [], "a replay invented a branch"
    assert h.current() == vs[-1].id


def test_the_commit_subject_becomes_the_label(repo, root):
    _run("rocky-keychain", repo, root)
    h = History.for_design(root, "rocky-keychain")
    labels = [v.label for v in h.versions()]
    assert len(labels) >= 20
    assert all("rocky" in l.lower() for l in labels), labels[:3]
    # the point of using subjects: the tree arrives readable, not as v1..v24
    assert any("silhouette" in l for l in labels), labels


def test_each_version_records_where_it_came_from(repo, root):
    _run("autonomiq-sat-panel", repo, root)
    h = History.for_design(root, "autonomiq-sat-panel")
    for v in h.versions():
        assert v.source == SOURCE
        assert v.commit and len(v.commit) == 40
        assert v.rebuildable is None, "claimed a build result it never measured"


def test_timestamps_are_the_commits_own_not_todays(repo, root):
    """Every imported version claiming to be from today would make the history
    useless for telling what happened when."""
    _run("rocky-keychain", repo, root)
    h = History.for_design(root, "rocky-keychain")
    made = [v.created for v in h.versions()]
    assert made == sorted(made)
    assert made[0].startswith("2026-08-18"), made[0]
    assert made[0][:10] != made[-1][:10], "all versions share one date"


def test_the_snapshots_are_the_real_old_designs(repo, root):
    """Not just labels: the payloads must differ, or nothing was really saved."""
    _run("rocky-keychain", repo, root)
    h = History.for_design(root, "rocky-keychain")
    vs = h.versions()
    first, last = h.snapshot(vs[0].id), h.snapshot(vs[-1].id)
    assert first["features"] and last["features"]
    assert first != last, "every version stored the same design"
    assert len({v.hash for v in vs}) == len(vs), "duplicate content recorded"


# -------------------------------------------------------------- idempotency ---

def test_running_twice_adds_nothing(repo, root):
    a = _run("autonomiq-sat-panel", repo, root)
    b = _run("autonomiq-sat-panel", repo, root)
    assert a.added and b.added == []
    h = History.for_design(root, "autonomiq-sat-panel")
    assert len(h.versions()) == len(a.added)


def test_a_partly_filled_history_is_extended_not_restarted(repo, root):
    """The forward-looking case: more commits land, re-run, only the new ones
    are imported."""
    cs = backfill.commits_for(repo, "rocky-keychain")
    h = History.for_design(root, "rocky-keychain").init("rocky-keychain")
    h.append(backfill.blob_at(repo, cs[0].sha, "rocky-keychain"),
             label=cs[0].subject, source=SOURCE, commit=cs[0].sha,
             created=cs[0].when)
    rep = _run("rocky-keychain", repo, root)
    h = History.for_design(root, "rocky-keychain")
    assert len(rep.added) == len(cs) - 1 - rep.deduped
    assert [v.id for v in h.versions()][0] == "v1", "existing version renumbered"
    assert len({v.commit for v in h.versions()}) == len(h.versions())


# --------------------------------------------------------- safety and dry run ---

def test_dry_run_writes_nothing(repo, root):
    rep = _run("rocky-keychain", repo, root, dry_run=True)
    assert len(rep.added) >= 24
    assert not list(root.iterdir()), "dry run touched the disk"


def test_a_history_with_live_versions_is_left_alone(repo, root):
    """Non-destructive by default: git commits are OLDER than anything recorded
    live, so appending them would build a chain that lies about the order."""
    h = History.for_design(root, "autonomiq-sat-panel").init("x")
    h.append({"name": "x", "spec": {}, "features": [{"id": "a", "op": "plate",
                                                     "params": {}}]},
             label="edited in the app", source="save")
    rep = _run("autonomiq-sat-panel", repo, root)
    assert rep.status == "skipped"
    assert "live editing" in rep.reason and "--reset" in rep.reason
    h = History.for_design(root, "autonomiq-sat-panel")
    assert len(h.versions()) == 1 and h.get("v1").label == "edited in the app"


def test_reset_makes_git_the_only_source(repo, root):
    h = History.for_design(root, "autonomiq-sat-panel").init("x")
    h.append({"name": "x", "spec": {}, "features": [{"id": "a", "op": "plate",
                                                     "params": {}}]},
             label="edited in the app", source="save")
    rep = _run("autonomiq-sat-panel", repo, root, reset=True)
    assert rep.status == "ok" and rep.added
    h = History.for_design(root, "autonomiq-sat-panel")
    assert all(v.source == SOURCE for v in h.versions())
    assert not any(v.label == "edited in the app" for v in h.versions())


def test_reset_in_a_dry_run_still_writes_nothing(repo, root):
    h = History.for_design(root, "autonomiq-sat-panel").init("x")
    h.append({"name": "x", "spec": {}, "features": [{"id": "a", "op": "plate",
                                                     "params": {}}]},
             label="keep me", source="save")
    _run("autonomiq-sat-panel", repo, root, dry_run=True, reset=True)
    h = History.for_design(root, "autonomiq-sat-panel")
    assert [v.label for v in h.versions()] == ["keep me"], "dry run deleted work"


def test_a_design_with_no_git_history_is_reported_not_invented(repo, root):
    """A synthetic slug rather than a real untracked scratch file: this test
    once used esp32-remote-live-t2 and broke the moment that file got committed,
    which made the test a hostage to what happens to be tracked."""
    rep = _run("_no-such-design-has-ever-existed", repo, root)
    assert rep.status == "empty"
    assert "2026-08-05" in rep.reason, "the real limit is not explained"
    assert not list(root.iterdir()), "an empty design got a history dir"


def test_an_unhealthy_history_is_not_written_over(repo, root):
    h = History.for_design(root, "autonomiq-sat-panel").init("x")
    h.append({"name": "x", "spec": {}, "features": []}, label="a", source="save")
    (h.path / "index.json").write_text("{ broken", encoding="utf-8")
    rep = _run("autonomiq-sat-panel", repo, root)
    assert rep.status == "skipped" and "unhealthy" in rep.reason
    assert (h.path / "index.json").read_text(encoding="utf-8") == "{ broken"


# --------------------------------------------------------------- whole sweep ---

def test_the_whole_library_replays(repo, root):
    reps = backfill.backfill_all(repo=repo, designs_dir=repo / "designs",
                                 history_root=root)
    ok = [r for r in reps if r.status == "ok"]
    assert len(ok) >= 30, f"only {len(ok)} designs replayed"
    assert sum(len(r.added) for r in ok) >= 100
    assert not any(r.unreadable for r in reps), \
        [u for r in reps for u in r.unreadable]
    # the designs the user named must all be in there
    by = {r.slug: r for r in reps}
    for must in ("rocky-keychain", "esp32-remote", "autonomiq-sat-panel",
                 "pump-housing", "cam-cover-upper", "wing-rib"):
        assert by[must].status == "ok", (must, by[must].reason)
    assert len(by["rocky-keychain"].added) >= 24
    assert len(by["esp32-remote"].added) >= 15


def test_only_limits_the_sweep(repo, root):
    reps = backfill.backfill_all(repo=repo, designs_dir=repo / "designs",
                                 history_root=root, only=["wing-rib"])
    assert [r.slug for r in reps] == ["wing-rib"]
    assert [p.name for p in root.iterdir()] == ["wing-rib.history"]


def test_a_report_line_reads_like_a_sentence(repo, root):
    rep = _run("wing-rib", repo, root)
    assert "wing-rib" in rep.line() and "version(s)" in rep.line()
    skipped = Report(slug="x", status="skipped", reason="because")
    assert "SKIPPED: because" in skipped.line()
