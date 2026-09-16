"""Does the new pick-carry rule hold when a NON-RIGID placement op sits
between the `move` and the pick?

`Document._carry_face_picks` (2026-09-16) calls a feature RIGID when the move
reaches it and every one of its inputs is rigid, and then adds the move's own
delta to every stored `face_center` on it.  Three reachable ops break that:

  * `mirror` (the legacy COPY, and the `join` half that is a reflection)
    maps a delta (dx,0,0) to (-dx,0,0)
  * `rotate` with the DEFAULT world-origin pivot turns the body as it moves
  * `polar_pattern` turns every copy by that copy's own angle

The question this probe answers is not "is the world-frame pick fragile"
(known, LAUNCH-PLAN §10) but "does the CARRY make a correct answer wrong".
So every case is measured twice: with the pick carried (today) and with the
pick left where it was (the behaviour before 6b4c494/31684d1).
"""
import math
import sys

sys.path.insert(0, ".")
import blocks                                    # noqa: E402
from document import Document                    # noqa: E402

R = 6.0
UP = [0.0, 0.0, 1.0]
BOSS_TOP_AREA = 12.0 * 12.0   # square bosses: every competing face is PLANAR,
#                              so resolve_face's direction gate really applies


def build(place_op, place_params, move_x):
    """plate 60 x 30 x 10, two r6 x 5 bosses 30 mm apart, MOVED +x, then
    placed by `place_op`."""
    doc = Document(name="t-nonrigid")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 60, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "rectangle", "w": 12, "h": 12, "x": -15, "y": 0},
        {"kind": "rectangle", "w": 12, "h": 12, "x": 15, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.add("placed", "move", {"x": move_x, "y": 0, "z": 0}, inputs=["part"])
    doc.add("flip", place_op, dict(place_params), inputs=["placed"])
    doc._cache = {}
    assert doc.rebuild(), doc.tree()
    return doc


def boss_tops(part):
    out = []
    for f in part.faces():
        try:
            n = f.normal_at(f.center())
        except Exception:
            continue
        if abs(n.Z - 1.0) < 1e-6 and abs(f.area - BOSS_TOP_AREA) < 1e-3:
            out.append(round(f.center().X, 4))
    return sorted(out)


def where(part, pick):
    f = blocks.resolve_face(part, pick, UP)
    return round(f.center().X, 4), round(f.area, 3)


def run(label, place_op, place_params, d, pick_index=0):
    print(f"\n=== {label} (move.x 30 -> {30 + d}) ===")
    doc = build(place_op, place_params, 30.0)
    tops = boss_tops(doc._parts["flip"])
    print(f"  boss tops before: x = {tops}")
    picked_x = tops[pick_index]
    pick = [picked_x, 0.0, 15.0]
    print(f"  user picks the boss top at x = {picked_x}")

    after = build(place_op, place_params, 30.0 + d)
    tops_after = boss_tops(after._parts["flip"])
    print(f"  boss tops after:  x = {tops_after}")
    truth = tops_after[pick_index]
    print(f"  that same boss top is now at x = {truth}")

    doc.edit("placed", "x", 30.0 + d)
    carried = list(doc.get("riser").params["face_center"]) if doc.has("riser") \
        else list(doc.get("probe_pick").params["face_center"])
    del carried


def measure(label, place_op, place_params, d, pick_index=0):
    print(f"\n=== {label}: move.x 30 -> {30 + d} ===")
    doc = build(place_op, place_params, 30.0)
    tops = boss_tops(doc._parts["flip"])
    picked_x = tops[pick_index]
    pick = [picked_x, 0.0, 15.0]
    doc.add("riser", "extrude_face",
            {"face_center": list(pick), "face_normal": list(UP), "amount": 5},
            inputs=["flip"])
    doc._cache = {}
    assert doc.rebuild(), doc.tree()
    v_before = doc.result().volume

    after = build(place_op, place_params, 30.0 + d)
    tops_after = boss_tops(after._parts["flip"])
    truth = tops_after[pick_index]
    print(f"  boss tops {tops} -> {tops_after}; picked one now at x = {truth}")

    doc.edit("placed", "x", 30.0 + d)
    assert doc.rebuild(), doc.tree()
    carried = list(doc.get("riser").params["face_center"])
    cx, ca = where(doc._parts["flip"], carried)
    ux, ua = where(doc._parts["flip"], pick)
    ok_c = abs(cx - truth) < 1e-6 and abs(ca - BOSS_TOP_AREA) < 1e-3
    ok_u = abs(ux - truth) < 1e-6 and abs(ua - BOSS_TOP_AREA) < 1e-3
    print(f"  CARRIED   pick x={carried[0]:>8} -> face x={cx:>9} area={ca:>10}"
          f"  {'OK' if ok_c else 'WRONG'}")
    print(f"  UNCARRIED pick x={pick[0]:>8} -> face x={ux:>9} area={ua:>10}"
          f"  {'OK' if ok_u else 'WRONG'}")
    print(f"  volume {v_before:.3f} -> {doc.result().volume:.3f}"
          f"   tree all-ok = {all(f.status == 'ok' for f in doc.features)}")
    if ok_u and not ok_c:
        print("  >>> REGRESSION: the carry turned a CORRECT pick into a wrong one")


measure("mirror across YZ (legacy copy)", "mirror", {"plane": "YZ"}, d=6.0)
measure("mirror across YZ, join=True (reflected half)", "mirror",
        {"plane": "YZ", "join": True}, d=6.0, pick_index=0)
measure("rotate 180 about Z, default world-origin pivot", "rotate",
        {"axis": "Z", "angle_deg": 180}, d=6.0)
