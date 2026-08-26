"""A cut that runs THROUGH the material instead of stopping inside it.

User, twice (2026-08-26): "if i am increasing or decreasing the extrude value,
it should increase or decrease, it should not create a new body ... i was trying
with pillar, and still its happening again".

Root cause, measured on designs/esp32-remote: `esp_pillar_trim_sketch` sits at
z=7 and its tool extrudes UP. At 6 mm the tool reaches z=13, past the top of the
part, and shaves the pillar tops off — one piece. At 4 mm it reaches only z=11,
so it takes a BAND out of four pillars and leaves their caps floating:

    amount   distance-extent      through-all
      6      1 piece              1 piece
      4      5 pieces  (!)        1 piece
      2      5 pieces  (!)        1 piece
      0.5    5 pieces  (!)        1 piece

A cutting tool has no business ending inside material, so `through` gives it the
standard CAD extent: run past the part, keep the direction. With it ticked, no
value the user types can sever anything.
"""
import pytest

import sketch as sk
from document import Document

REMOTE = "designs/esp32-remote.tcad.json"
TRIM = "esp_pillar_trim_tool"


def fresh_remote():
    """A document with no shared param dicts and its own cache."""
    import json
    d = Document.from_data(json.loads(json.dumps(
        Document.load(REMOTE).to_data())))
    d._cache = {}
    return d


# ------------------------------------------------------------ the op itself ---

def test_through_ignores_the_distance_and_keeps_the_direction():
    profile = sk.make_sketch(plane="XY", entities=[
        {"kind": "circle", "r": 5}])
    up = sk.extrude_sketch(profile, amount=3, through=True)
    bb = up.bounding_box()
    assert bb.max.Z == pytest.approx(sk.THROUGH_MM, rel=1e-6)
    assert bb.min.Z == pytest.approx(0, abs=1e-6)

    down = sk.extrude_sketch(profile, amount=-3, through=True)
    bb = down.bounding_box()
    assert bb.min.Z == pytest.approx(-sk.THROUGH_MM, rel=1e-6)
    assert bb.max.Z == pytest.approx(0, abs=1e-6)


def test_through_is_off_by_default_and_a_no_op_when_false():
    profile = sk.make_sketch(plane="XY", entities=[{"kind": "circle", "r": 5}])
    plain = sk.extrude_sketch(profile, amount=7)
    off = sk.extrude_sketch(profile, amount=7, through=False)
    assert plain.volume == pytest.approx(off.volume)
    assert off.bounding_box().max.Z == pytest.approx(7)


def test_through_ignores_taper_instead_of_collapsing():
    """A 2 m tapered prism collapses; the flag has to win over the taper."""
    profile = sk.make_sketch(plane="XY", entities=[{"kind": "circle", "r": 5}])
    s = sk.extrude_sketch(profile, amount=4, taper=10, through=True)
    assert s.volume > 0
    assert s.bounding_box().max.Z == pytest.approx(sk.THROUGH_MM, rel=1e-6)


def test_the_flag_takes_the_usual_loose_boolean_strings():
    profile = sk.make_sketch(plane="XY", entities=[{"kind": "circle", "r": 5}])
    for truthy in (True, "true", 1, "yes"):
        s = sk.extrude_sketch(profile, amount=2, through=truthy)
        assert s.bounding_box().max.Z > 100, truthy
    for falsy in (False, "false", 0, "no", ""):
        s = sk.extrude_sketch(profile, amount=2, through=falsy)
        assert s.bounding_box().max.Z == pytest.approx(2), falsy


# ------------------------------------------------- the user's actual design ---

@pytest.mark.parametrize("amount", [4, 2, 0.5])
def test_a_short_trim_severs_the_pillars_without_through(amount):
    d = fresh_remote()
    d.edit(TRIM, "amount", amount)
    d.rebuild()
    r = d._result_feature()
    assert r.pieces == 5, "this is the reported bug — it must still reproduce"
    assert d.warnings and TRIM.replace("_tool", "") in " ".join(d.warnings)


@pytest.mark.parametrize("amount", [6, 4, 2, 0.5])
def test_through_keeps_the_part_whole_at_any_distance(amount):
    d = fresh_remote()
    d.edit(TRIM, "amount", amount)
    d.get(TRIM).params["through"] = True
    d._mark_stale()
    assert d.rebuild(), d.tree()
    r = d._result_feature()
    assert r.pieces == 1, f"amount={amount} still broke the part"
    assert not d.warnings


def test_through_gives_the_same_part_the_correct_distance_did():
    """Not just "whole" — the RIGHT shape: identical to the design as authored,
    which cleared the pillar tops with 6 mm."""
    good = fresh_remote()
    good.rebuild()
    want = good._result_feature().volume

    for amount in (6, 3, 1):
        d = fresh_remote()
        d.edit(TRIM, "amount", amount)
        d.get(TRIM).params["through"] = True
        d._mark_stale()
        d.rebuild()
        assert d._result_feature().volume == pytest.approx(want, rel=1e-9), \
            f"through-all at {amount} did not clear the same material"


def test_the_trim_height_is_the_sketch_offset():
    """With `through` on, the distance stops mattering — so the thing that
    raises and lowers the pillars is the SKETCH's offset. Increase it, keep
    more pillar; that is the "increase or decrease" the user wants."""
    vols = {}
    for offset in (5.0, 7.0, 9.0):
        d = fresh_remote()
        d.get(TRIM).params["through"] = True
        d.edit("esp_pillar_trim_sketch", "offset", offset)
        d.rebuild()
        r = d._result_feature()
        assert r.pieces == 1, f"offset {offset} broke the part"
        vols[offset] = r.volume
    assert vols[5.0] < vols[7.0] < vols[9.0], \
        f"a higher trim plane must leave more material: {vols}"


def test_a_through_cut_survives_the_rebuild_cache():
    d = fresh_remote()
    d.get(TRIM).params["through"] = True
    d.edit(TRIM, "amount", 2)
    d.rebuild()
    whole = d._result_feature().volume
    d.get(TRIM).params["through"] = False       # back to a slicing distance
    d._mark_stale()
    d.rebuild()
    assert d._result_feature().pieces == 5
    d.get(TRIM).params["through"] = True        # and back again, from cache
    d._mark_stale()
    d.rebuild()
    assert d._result_feature().pieces == 1
    assert d._result_feature().volume == pytest.approx(whole)
