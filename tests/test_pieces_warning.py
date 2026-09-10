"""A part that quietly falls into two pieces.

User report (2026-08-26): "i was editing the extrude feature in the design, when
i reduced extrude, it created a new body, it should not be like that".

Reproduced: shorten the plate under a boss and the boss floats. The fuse still
returns ONE Part — a compound holding two disjoint solids — so `inspector.health`
called it clean, the tree stayed green, and the viewport showed a part plus a
mystery lump. Same for a cut that severs a plate.

Nothing here makes it an error: two pieces is sometimes exactly what you meant.
It must simply never be silent.
"""
from fastapi.testclient import TestClient

import studio
from document import Document, n_solids


def boss_doc(base=10.0):
    """A plate with a boss standing on its top face at z=10."""
    d = Document(name="t-boss")
    d.add("base_sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 60, "h": 40}]})
    d.add("base", "extrude", {"amount": base}, inputs=["base_sk"])
    d.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8, "x": -15, "y": 0}]})
    d.add("boss_tool", "extrude", {"amount": 12}, inputs=["boss_sk"])
    d.add("boss", "fuse", {}, inputs=["base", "boss_tool"])
    return d


def test_a_whole_part_reports_one_piece():
    d = boss_doc(10)
    assert d.rebuild()
    assert d.get("boss").pieces == 1
    assert not d.warnings


def test_shortening_the_base_until_the_boss_floats_is_reported():
    """THE user's case: reduce an extrude, and a piece detaches."""
    d = boss_doc(5)
    assert d.rebuild()                      # still "valid" geometry
    assert d.get("boss").pieces == 2
    assert d.warnings, "the part is in two pieces and nothing said so"
    note = " ".join(d.warnings)
    assert "boss" in note and "2 separate pieces" in note
    assert "fuse" in note                   # names the operation that did it


def test_a_cut_that_severs_the_part_is_reported():
    d = Document(name="t-sever")
    d.add("sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 60, "h": 40}]})
    d.add("plate", "extrude", {"amount": 10}, inputs=["sk"])
    d.add("slot_sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 6, "h": 60}]})
    d.add("slot_tool", "extrude", {"amount": 10}, inputs=["slot_sk"])
    d.add("cut1", "cut", {}, inputs=["plate", "slot_tool"])
    assert d.rebuild()
    assert d.get("cut1").pieces == 2
    assert any("cut1" in w for w in d.warnings)


def test_a_tool_of_many_prisms_is_not_a_complaint():
    """An extrude of a sketch holding 8 pilot circles is 8 prisms BY DESIGN.
    Warning about those buried the real signal (esp32-remote produced a dozen
    such notes, every one of them a tool doing its job)."""
    d = Document(name="t-pilots")
    d.add("plate_sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 60, "h": 40}]})
    d.add("plate", "extrude", {"amount": 10}, inputs=["plate_sk"])
    d.add("pilots_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 1.5, "x": -20 + 5 * i, "y": 0}
        for i in range(8)]})
    d.add("pilots_tool", "extrude", {"amount": -4}, inputs=["pilots_sk"])
    d.add("pilots", "cut", {}, inputs=["plate", "pilots_tool"])
    assert d.rebuild(), d.tree()
    assert d.get("pilots_tool").pieces == 8      # counted...
    assert not d.warnings                        # ...but not complained about
    assert d.get("pilots").pieces == 1


def test_the_count_survives_the_rebuild_cache():
    d = boss_doc(10)
    assert d.rebuild() and d.get("boss").pieces == 1
    d.edit("base", "amount", 5)
    assert d.rebuild()
    assert d.get("boss").pieces == 2 and d.warnings
    d.edit("base", "amount", 10)                 # back — served from cache
    assert d.rebuild()
    assert d.get("boss").pieces == 1 and not d.warnings


def test_pieces_reaches_the_api():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(boss_doc(5))
    studio._rebuild_and_mesh()
    c = TestClient(studio.app)
    d = c.get("/api/doc").json()
    assert d["result_pieces"] == 2
    assert d["bodies"] == 1                      # one body, in two lumps
    boss = next(f for f in d["features"] if f["id"] == "boss")
    assert boss["pieces"] == 2 and boss["status"] == "ok"
    assert d["warnings"]


def test_body_count_is_counted_not_guessed():
    """The badge used to read "warnings + 1 bodies", so an unrelated note made
    it claim 13 bodies on a single-body part."""
    d = Document(name="t-two")
    d.add("a", "plate", {"width": 30, "depth": 30, "thickness": 5})
    d.add("b", "disc", {"radius": 8, "thickness": 20})
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(d)
    studio._rebuild_and_mesh()
    j = TestClient(studio.app).get("/api/doc").json()
    assert j["bodies"] == 2                      # two real, separate bodies
    assert j["result_pieces"] == 1               # each of which is one lump


# ---------------------------------------------------------------------------
# Section 2 code review, 2026-09-10: a STRUCK feature kept its last piece
# count. Two consequences, both measured:
#   * its row went on saying "pieces 2" about geometry that is gone (the same
#     class the fourth sketcher review fixed for `notes` and `volume`);
#   * _check_pieces took that stale count as the BASELINE for the feature
#     below it, so a part genuinely in two pieces was reported by nothing at
#     all (measured n_solids(result) == 2 with doc.warnings == []).
# ---------------------------------------------------------------------------

def _two_severing_cuts():
    """A bar cut clean through in two places — each cut adds a piece."""
    d = Document(name="t-two-severs")
    d.add("base", "plate", {"width": 60, "depth": 10, "thickness": 5})
    d.add("sk1", "sketch", {"plane": "XY", "offset": -3, "entities": [
        {"kind": "rectangle", "x": -15, "y": 0, "w": 4, "h": 40}]})
    d.add("tool1", "extrude", {"amount": 20, "through": False}, inputs=["sk1"])
    d.add("cut1", "cut", {}, inputs=["base", "tool1"])
    d.add("sk2", "sketch", {"plane": "XY", "offset": -3, "entities": [
        {"kind": "rectangle", "x": 15, "y": 0, "w": 4, "h": 40}]})
    d.add("tool2", "extrude", {"amount": 20, "through": False}, inputs=["sk2"])
    d.add("cut2", "cut", {}, inputs=["cut1", "tool2"])
    return d


def test_a_struck_feature_reports_no_piece_count():
    """Its geometry is not in the model, so it has nothing to say about it."""
    d = _two_severing_cuts()
    assert d.rebuild()
    assert d.get("cut1").pieces == 2
    d.strike("cut1")
    assert d.rebuild()
    assert d.get("cut1").pieces is None, \
        "a struck-out row still claims the part is in 2 lumps"
    assert d.get("cut1").volume is None and d.get("cut1").notes == []


def test_a_struck_cut_does_not_silence_the_piece_warning_below_it():
    """THE measured bug: strike the first sever and the second one's warning
    disappeared, because the struck row's stale count was its baseline."""
    d = _two_severing_cuts()
    assert d.rebuild()
    d.strike("cut1")
    assert d.rebuild()
    assert n_solids(d.result()) == 2, "the bar should still be cut in two"
    note = " ".join(d.warnings)
    assert "cut2" in note and "2 separate pieces" in note, \
        f"the part is in two pieces and nothing said so: {d.warnings!r}"
    assert "its input was 1" in note, \
        "the baseline came from the struck row, not from what cut2 was built on"
