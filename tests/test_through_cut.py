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
def test_a_short_trim_is_now_healed_instead_of_severing(amount):
    """This used to assert the bug reproduced (5 pieces). It is now fixed
    automatically: the design has no `through` key, so nobody has decided, and
    the healer proves through-all is the cure before applying it."""
    d = fresh_remote()
    d.edit(TRIM, "amount", amount)
    d.rebuild()
    assert d._result_feature().pieces == 1, "the strand was not healed"
    assert d.get(TRIM).params.get("through") is True
    assert any("Extended" in w for w in d.warnings), d.warnings


@pytest.mark.parametrize("amount", [4, 2, 0.5])
def test_the_underlying_bug_is_still_real_when_through_is_refused(amount):
    """The geometry has not changed — only the default. Say no to through-all
    and the tool still slices the pillars, which is what the healer is for."""
    d = fresh_remote()
    d.get(TRIM).params["through"] = False      # explicit refusal, respected
    d.edit(TRIM, "amount", amount)
    d.rebuild()
    assert d._result_feature().pieces == 5, "the original defect vanished"
    assert not any("Extended" in w for w in d.warnings),         "an explicit refusal was overridden"


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


# ---------------------------------------------------------------------------
# Automatic healing (2026-08-26)
#
# The user reported the same thing a THIRD time: "if i want to increase a
# height of sketch ... if i am changing any of these values, a new body is
# creating, instead of increasing height". R21 warned; f820fe9 added `through`
# as an opt-in cure. Neither helped, because script-generated designs never set
# the flag and a warning is not a fix.
#
# So a cut that strands material now gets `through` ticked automatically — but
# ONLY where that is provably the cure: the cut must have left more pieces than
# it was handed, and through-all must bring the count back. A cut MEANT to
# sever stays severed when its tool is lengthened, so it is never healed.
# ---------------------------------------------------------------------------

def _pillar_doc(trim_amount=6.0):
    """A slab with a cavity and two FREE-STANDING pillars, trimmed from z=7 up.

    The pillars must actually stand alone: cutting a band out of a column that
    is still surrounded by material strands nothing, because the part above the
    band stays joined sideways. That is why this carves a cavity first — an
    earlier version of this fixture skipped it, stranded nothing, and quietly
    tested the wrong thing."""
    d = Document(name="heal")
    d.add("slab_sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 60, "h": 40}]})
    d.add("slab", "extrude", {"amount": 12}, inputs=["slab_sk"])
    d.add("cav_sk", "sketch", {"plane": "XY", "offset": 4.0, "entities": [
        {"kind": "rectangle", "w": 50, "h": 30, "mode": "add"},
        {"kind": "circle", "r": 6, "x": -15, "y": 0, "mode": "subtract"},
        {"kind": "circle", "r": 6, "x": 15, "y": 0, "mode": "subtract"}]})
    d.add("cav_tool", "extrude", {"amount": 20}, inputs=["cav_sk"])
    d.add("hollow", "cut", {}, inputs=["slab", "cav_tool"])
    d.add("trim_sk", "sketch", {"plane": "XY", "offset": 7.0, "entities": [
        {"kind": "circle", "r": 7, "x": -15, "y": 0},
        {"kind": "circle", "r": 7, "x": 15, "y": 0}]})
    d.add("trim_tool", "extrude", {"amount": trim_amount}, inputs=["trim_sk"])
    d.add("part", "cut", {}, inputs=["hollow", "trim_tool"])
    return d


def test_a_cut_that_strands_material_is_healed_automatically():
    good = _pillar_doc(6.0)                 # reaches past the slab: clean
    assert good.rebuild()
    assert good._result_feature().pieces == 1
    right_volume = good.result().volume

    bad = _pillar_doc(2.0)                  # stops inside: would strand caps
    assert bad.rebuild()
    assert bad._result_feature().pieces == 1, "still in pieces"
    assert bad.get("trim_tool").params.get("through") is True
    # the RIGHT shape, not merely a whole one
    assert abs(bad.result().volume - right_volume) < 1e-6


def test_the_heal_is_recorded_in_the_design_not_just_the_geometry():
    """It must survive save/load, or the file and the screen would disagree."""
    d = _pillar_doc(2.0)
    d.rebuild()
    again = Document.from_data(d.to_data())
    assert again.get("trim_tool").params.get("through") is True
    again.rebuild()
    assert again._result_feature().pieces == 1


def test_the_warning_names_the_offset_as_the_real_control():
    """With `through` on, the distance stops doing anything — so the message has
    to say what DOES move the pillar, or the next edit is another dead end."""
    d = _pillar_doc(2.0)
    d.rebuild()
    w = " ".join(d.warnings)
    assert "trim_tool" in w and "through" in w
    assert "OFFSET" in w.upper() and "trim_sk" in w


def test_a_cut_meant_to_sever_is_never_healed():
    d = Document(name="sever")
    d.add("bar", "plate", {"width": 100, "depth": 20, "thickness": 10})
    d.add("slot_sk", "sketch", {"plane": "XY", "offset": -10, "entities": [
        {"kind": "rectangle", "w": 6, "h": 40}]})
    d.add("slot", "extrude", {"amount": 20}, inputs=["slot_sk"])
    d.add("out", "cut", {}, inputs=["bar", "slot"])
    d.rebuild()
    assert d._result_feature().pieces == 2, "the slot did not sever the bar"
    assert d.get("slot").params.get("through") is None, "an intended cut was healed"
    assert any("2 separate pieces" in x for x in d.warnings)


def test_a_pocket_is_left_completely_alone():
    """A pocket is a cut that legitimately stops inside the material. It strands
    nothing, so the healer must never see it."""
    d = Document(name="pocket")
    d.add("blk_sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 60, "h": 40}]})
    d.add("blk", "extrude", {"amount": 10}, inputs=["blk_sk"])
    d.add("pk_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "rectangle", "w": 30, "h": 20}]})
    d.add("pk_tool", "extrude", {"amount": -4}, inputs=["pk_sk"])
    d.add("out", "cut", {}, inputs=["blk", "pk_tool"])
    assert d.rebuild()
    assert d._result_feature().pieces == 1
    assert d.get("pk_tool").params.get("through") is None, "a pocket was healed"
    assert d.result().volume < 60 * 40 * 10, "the pocket was not cut"


def test_healing_does_not_recurse():
    """One retry, not a loop — the guard has to hold even when the heal cannot
    fix everything."""
    d = _pillar_doc(2.0)
    calls = []
    real = Document._heal_stranding_cuts

    def spy(self):
        calls.append(1)
        return real(self)

    Document._heal_stranding_cuts = spy
    try:
        d.rebuild()
    finally:
        Document._heal_stranding_cuts = real
    assert len(calls) == 1, f"healer ran {len(calls)} times"


def test_an_already_through_tool_is_not_re_healed():
    d = _pillar_doc(2.0)
    d.get("trim_tool").params["through"] = True
    d.rebuild()
    assert d._result_feature().pieces == 1
    assert not any("Extended" in w for w in d.warnings), d.warnings
