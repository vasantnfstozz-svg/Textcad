"""Rebuild cost, and the checking that must survive making it cheap.

User report (2026-08-26): "when i am simply changes extrude to little of a part
in that design its also taking really a lot of time, its really irritating".

Measured on esp32-remote (79 features): a rebuild was 22.5 s and ONE parameter
edit 16.7 s. inspector.health() was 14.5 s of that — 65% — because the rebuild
calls it once per feature and health called measure(), which takes a full
topology census (every face's geom_type, cylinder radii, a max-radius scan over
2984 vertices, area, centre of mass, edge and vertex counts) of which health
reads none.

After: health computes only the four facts it judges on, and the rebuild skips
OpenCASCADE's validity analysis (~270 ms a call) on INTERMEDIATE features while
still running it in full on the result.

MEASURED HONESTLY, because the first figures quoted here did not reproduce.
Wall-clock on this machine swings by 3x between runs, so a single before/after
pair means nothing. A controlled A/B — fresh process per run, same design, old
health monkeypatched back in — gives:

    old   cold 69.8 / 65.1 s      one edit 50.2 / 23.6 s
    new   cold 28.5 / 18.9 s      one edit 19.4 / 15.1 s

So roughly 2.5-3.5x, consistently, on both paths. The absolute numbers are
whatever the machine feels like that hour; the RATIO is the claim. What remains
is real geometry: _eval is ~20 s of a 28 s cold rebuild, health ~4 s.

These tests exist so the speed cannot come back as lost checking. They assert
BEHAVIOUR, never wall-clock, for exactly the reason above.
"""

import inspector
from document import Document


def boss_doc(boss_z=5.0):
    d = Document(name="speed")
    d.add("base", "plate", {"width": 100, "depth": 60, "thickness": 10})
    d.add("pil_sk", "sketch", {"plane": "XY", "offset": boss_z,
                               "entities": [{"kind": "circle", "x": 0,
                                             "y": 0, "r": 8}]})
    d.add("pil", "extrude", {"amount": 5}, inputs=["pil_sk"])
    d.add("body", "fuse", {}, inputs=["base", "pil"])
    return d


# ------------------------------------------------- the optimisation itself ---

def test_health_no_longer_pays_for_a_full_topology_census(monkeypatch):
    """REGRESSION GUARD. health() used to call measure(), which costs ~630 ms on
    a large solid while health reads four numbers from it. If someone routes
    health back through measure(), this fails."""
    d = boss_doc()
    d.rebuild()
    called = []
    monkeypatch.setattr(inspector, "measure",
                        lambda *a, **k: called.append(1) or {})
    inspector.health(d.result())
    assert called == [], "health() went back through measure()"


def test_the_cheap_and_full_checks_agree_on_a_healthy_solid():
    d = boss_doc()
    d.rebuild()
    s = d.result()
    assert inspector.health(s) == []
    assert inspector.health(s, check_valid=False) == []


def test_skipping_validity_is_the_only_difference():
    """Everything except the OpenCASCADE validity line must still be reported
    when check_valid is off — otherwise the fast path is a blind path."""
    d = Document(name="empty")
    d.add("a", "plate", {"width": 10, "depth": 10, "thickness": 10})
    d.add("b", "plate", {"width": 10, "depth": 10, "thickness": 10})
    d.add("gone", "cut", {}, inputs=["a", "b"])       # nothing left
    d.rebuild()
    part = d._parts["gone"]
    lean = inspector.health(part, check_valid=False)
    full = inspector.health(part)
    assert lean, "an empty result passed the cheap check"
    assert any("volume" in p or "no solid" in p for p in lean), lean
    assert set(lean) <= set(full)


# ------------------------------------------- what must still be caught ------

def test_a_part_that_falls_into_pieces_is_still_caught(monkeypatch):
    """The cheap path must not lose the check this project cares about most."""
    d = boss_doc(boss_z=5.0)
    assert d.rebuild()
    assert d._result_feature().pieces == 1
    d.edit("pil_sk", "offset", 7.0)                 # boss now floats 2 mm up
    d.rebuild()
    assert d._result_feature().pieces == 2
    assert d.warnings and "pieces" in d.warnings[0]


def test_the_result_still_gets_the_full_validity_check(monkeypatch):
    """Intermediates skip OpenCASCADE validity; the part the user actually gets
    must not. Forced red here, because a genuinely invalid solid is hard to
    produce on purpose."""
    d = boss_doc()
    assert d.rebuild()
    rf = d._result_feature()
    assert rf.status == "ok"

    real = inspector._try

    def fake(fn, default=None):
        try:
            if fn() is True:            # the is_valid probe -> claim invalid
                return False
        except Exception:
            return real(fn, default)
        return real(fn, default)

    monkeypatch.setattr(inspector, "_try", fake)
    d2 = boss_doc()
    ok = d2.rebuild()
    assert ok is False, "an invalid result was reported as fine"
    bad = d2._result_feature()
    assert any("invalid" in p for p in bad.problems), bad.problems
    assert bad.status == "failed"


def test_a_failed_feature_still_fails_the_rebuild():
    d = Document(name="broken")
    d.add("base", "plate", {"width": 10, "depth": 10, "thickness": 10})
    d.add("bad", "with_center_hole", {"radius": 500}, inputs=["base"])
    d.rebuild()
    assert d.get("bad").status == "failed" or d.get("bad").problems


# --------------------------------------------------------------- the speed ---

def test_a_single_edit_does_not_cost_a_full_rebuild():
    """Not a wall-clock assertion (too flaky for CI): it pins the CACHE, which
    is what keeps an edit cheap. Only the edited feature and what depends on it
    may be re-evaluated."""
    d = boss_doc()
    d.rebuild()
    evaluated = []
    real = Document._eval

    def spy(self, f):
        evaluated.append(f.id)
        return real(self, f)

    Document._eval = spy
    try:
        d.edit("pil", "amount", 9)
        d.rebuild()
    finally:
        Document._eval = real
    assert "base" not in evaluated, "an untouched branch was rebuilt"
    assert "pil" in evaluated and "body" in evaluated
