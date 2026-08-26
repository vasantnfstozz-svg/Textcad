"""The rebuild cache must be fast AND never stale.

User report (2026-08-25): "when did some changes or even no changes in the
sketch tab, when i am pressing finish or cancel sketch, why does it take so much
time to rebuilding it, most of the times, it takes a lot of times to load as
well."

Measured on designs/esp32-remote (73 features): opening a sketch and closing it
again without editing anything cost ~10 s of pure recomputation, because every
rebuild re-evaluated all 73 features and re-ran the health check on each. A
feature's output is a pure function of (op, params, input geometry), so it is
content-addressed now.

The speed is the easy half. These tests are mostly about the other half: a
cache that hands back geometry the parameters no longer describe would be the
worst bug this project could ship.
"""
import time

import pytest

from document import Document


def chain_doc(w=40.0, cut_r=6.0):
    """base plate -> pocket cut -> a second pocket, so there is something
    downstream of everything."""
    doc = Document(name="t-cache")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": w, "h": 30}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("p1_sketch", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": cut_r, "x": -10, "y": 0}]})
    doc.add("p1_tool", "extrude", {"amount": -4}, inputs=["p1_sketch"])
    doc.add("p1", "cut", {}, inputs=["body", "p1_tool"])
    doc.add("p2_sketch", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 3, "x": 10, "y": 0}]})
    doc.add("p2_tool", "extrude", {"amount": -4}, inputs=["p2_sketch"])
    doc.add("p2", "cut", {}, inputs=["p1", "p2_tool"])
    # The rebuild cache is process-wide, so every test here takes a PRIVATE one:
    # otherwise a test that measures a "cold" build silently measures a warm one
    # that an earlier test filled in (this failed exactly that way in the full
    # suite while passing when the file ran alone).
    doc._cache = {}
    return doc


# ------------------------------------------------------------- correctness ---

def test_an_upstream_edit_changes_everything_downstream():
    """The whole risk in one test: edit the BASE sketch and the final solid must
    change. If inputs were keyed by name instead of by content, the downstream
    cuts would be served from cache and the part would silently stay wrong."""
    doc = chain_doc()
    assert doc.rebuild()
    v0 = doc.result().volume
    doc.edit("outline", "entities", [{"kind": "rectangle", "w": 80, "h": 30}])
    assert doc.rebuild()
    v1 = doc.result().volume
    assert v1 > v0 * 1.9, f"downstream did not follow the base edit: {v0}->{v1}"


def test_editing_a_middle_feature_is_reflected_in_the_result():
    doc = chain_doc()
    assert doc.rebuild()
    v0 = doc.result().volume
    doc.edit("p1_tool", "amount", -9)          # deeper pocket
    assert doc.rebuild()
    assert doc.result().volume < v0


def test_the_same_document_rebuilt_twice_gives_the_same_volume():
    doc = chain_doc()
    assert doc.rebuild()
    v0 = doc.result().volume
    assert doc.rebuild()
    assert doc.result().volume == pytest.approx(v0)


def test_a_cached_rebuild_matches_an_uncached_one_exactly():
    """Belt and braces: build the same design in a FRESH document (no cache at
    all) and demand identical volumes, feature by feature."""
    warm = chain_doc()
    warm.rebuild()
    warm.edit("p2_sketch", "offset", 10)        # touch it, rebuild with cache
    warm.rebuild()
    cold = chain_doc()
    cold._cache = {}
    cold.rebuild()
    for f in cold.features:
        a = warm.get(f.id).volume
        b = f.volume
        assert (a is None and b is None) or a == pytest.approx(b), \
            f"{f.id}: cached {a} vs fresh {b}"


def test_undo_style_restore_reuses_the_cache_but_stays_correct():
    doc = chain_doc()
    doc.rebuild()
    before = doc.to_data()
    v0 = doc.result().volume
    doc.edit("p1_sketch", "entities", [{"kind": "circle", "r": 12, "x": -10,
                                        "y": 0}])
    doc.rebuild()
    assert doc.result().volume < v0
    restored = Document.from_data(before)
    restored._cache = doc._cache               # what /api/undo carries across
    assert restored.rebuild()
    assert restored.result().volume == pytest.approx(v0)


def test_suppression_and_rollback_still_work_with_the_cache():
    doc = chain_doc()
    assert doc.rebuild()
    full = doc.result().volume

    doc.get("p2").suppressed = True
    doc._mark_stale()
    assert doc.rebuild()
    p2 = doc.get("p2")
    assert p2.status == "ok" and p2.problems == ["(suppressed)"]
    # a suppressed node passes its first input through untouched
    assert doc._parts["p2"] is doc._parts["p1"]
    assert doc._parts["p1"].volume > full      # p1 has one pocket, not two
    # NOTE (pre-existing, not the cache): result() walks back past the
    # suppressed cut and lands on `p2_tool`, because a tool prism is a solid
    # too. Filed in BACKLOG.md; asserted here so a change to it is deliberate.
    assert doc._result_feature().id == "p2_tool"

    doc.get("p2").suppressed = False
    doc._mark_stale()
    assert doc.rebuild()
    assert doc.result().volume == pytest.approx(full)

    doc.rollback = "p1"                        # build only up to the first cut
    assert doc.rebuild()
    assert doc.get("p2").status == "stale"
    doc.rollback = None
    assert doc.rebuild()
    assert doc.result().volume == pytest.approx(full)


def test_a_failure_is_cached_without_becoming_permanent():
    doc = chain_doc()
    assert doc.rebuild()
    doc.edit("outline", "entities", [{"kind": "rectangle", "w": -5, "h": 30}])
    assert not doc.rebuild()
    assert doc.get("outline").status == "failed"
    assert not doc.rebuild()                   # still failed, from cache
    doc.edit("outline", "entities", [{"kind": "rectangle", "w": 40, "h": 30}])
    assert doc.rebuild(), doc.tree()           # and it recovers
    assert doc.get("outline").status == "ok"


def test_renaming_does_not_invalidate_anything():
    """Inputs are keyed by CONTENT, so a rename must be free — and correct."""
    doc = chain_doc()
    assert doc.rebuild()
    v0 = doc.result().volume
    doc.rename("p1_tool", "first_pocket_tool")
    assert doc.rebuild()
    assert doc.result().volume == pytest.approx(v0)


def test_geometry_version_moves_only_when_geometry_does():
    doc = chain_doc()
    doc.rebuild()
    v1 = doc._geom_version
    doc.rebuild()
    assert doc._geom_version == v1             # nothing changed
    doc.rollback = "p1"
    doc.rebuild()
    assert doc._geom_version != v1             # different bodies are drawable
    doc.rollback = None
    doc.rebuild()
    assert doc._geom_version == v1             # ...and back again
    doc.edit("p2_tool", "amount", -6)
    doc.rebuild()
    assert doc._geom_version != v1


# ------------------------------------------------------------------- speed ---

def test_a_no_change_rebuild_is_effectively_free():
    """Pressing Cancel in the sketch editor: the rollback bar goes on and off
    and nothing else happens. This is the user's complaint, as a test."""
    doc = chain_doc()
    doc.rebuild()
    t0 = time.perf_counter()
    doc.rollback = "p1_sketch"
    doc.rebuild()
    doc.rollback = None
    doc.rebuild()
    round_trip = time.perf_counter() - t0

    cold = chain_doc()
    t0 = time.perf_counter()
    cold.rebuild()
    cold_build = time.perf_counter() - t0

    assert round_trip < cold_build / 2, \
        f"open+close a sketch took {round_trip*1000:.0f} ms vs a cold build of " \
        f"{cold_build*1000:.0f} ms — the cache is not being used"


def test_editing_the_last_feature_does_not_rebuild_the_first_ones():
    doc = chain_doc()
    doc.rebuild()
    built = []
    real = doc._eval
    doc._eval = lambda f: (built.append(f.id), real(f))[1]
    doc.edit("p2_tool", "amount", -7)
    doc.rebuild()
    assert "p2_tool" in built and "p2" in built      # the tail rebuilds
    assert "body" not in built and "p1" not in built  # the head does not
    assert "outline" not in built


def test_the_cache_does_not_grow_without_bound():
    import document as D
    doc = chain_doc()
    for i in range(D.CACHE_MAX + 40):
        doc.edit("p2_tool", "amount", -(1 + (i % 7) * 0.001) * 3)
        doc.rebuild()
    assert len(doc._cache) <= D.CACHE_MAX
