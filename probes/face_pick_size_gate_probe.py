"""Does remembering HOW BIG the picked face was find it again after a
parameter change - and does it leave everything else exactly as it was?

LAUNCH-PLAN §10's P1: a stored pick is (centre, normal) in world coordinates,
so on a stepped body a plate thickened from 10 to 14 slides the pick from the
boss top onto the plate top - 22800.0 mm3 where 18810.62 was asked for, every
row `ok` (probes/face_pick_frame_probe.py §4). The move half was closed by
carrying the delta; this one has no delta to carry, because nothing moved.

What the click already knew and threw away is the SIZE of the face. Each
section below is measured both ways - the answer with no stored area (what
every design saved before today has) beside the answer with one - because the
gate must be judged against DOING NOTHING, not only against the bug.
"""
import sys

sys.path.insert(0, ".")
import blocks                          # noqa: E402
from document import Document          # noqa: E402

UP = [0.0, 0.0, 1.0]


def stepped(plate_t=10.0, boss_r=8.0, boss_h=5.0, plate_w=40.0, riser=5.0,
            pick=None, area=None):
    """plate plate_w x 30 x plate_t with a boss_r x boss_h boss on it, then a
    `riser` pulled out of the face the pick names. Two faces point +Z."""
    doc = Document(name="p-size")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": plate_w, "h": 30}]})
    doc.add("base", "extrude", {"amount": plate_t}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": plate_t, "entities": [
        {"kind": "circle", "r": boss_r, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": boss_h}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    params = {"face_center": list(pick), "face_normal": list(UP),
              "amount": riser}
    if area is not None:
        params["face_area"] = area
    doc.add("riser", "extrude_face", params, inputs=["part"])
    doc.add("final", "fuse", {}, inputs=["part", "riser"])
    doc._cache = {}
    return doc


def resolved(part, centre, area):
    """(what resolve_face answers, its area) for a pick with / without a size."""
    try:
        f = blocks.resolve_face(part, centre, UP, area)
    except ValueError as e:
        return f"REFUSED: {e}", None
    a = round(float(f.area), 3)
    c = f.center()
    name = {True: "boss top", False: "plate top"}[a < 500]
    return f"{name} at z={c.Z:6.2f}, {a:9.3f} mm2", a


def volume(doc):
    doc.rebuild()
    p = doc.result()
    return None if p is None else round(p.volume, 3)


def head(n, title):
    print("")
    print("=" * 78)
    print(f"{n}. {title}")
    print("=" * 78)


# ---------------------------------------------------------------------------
head(1, "THE FILED CASE: thicken the plate under a boss-top pick")
print("""  The pick was made on the boss top of a 10 mm plate: centre (0,0,15),
  201.062 mm2. Thicken the plate and the plate top climbs to within 1 mm of
  that stored point while the boss top moves 4 mm away.""")
BOSS_AREA = 201.06
print("")
print("  plate_t  stored area  resolved face                              design mm3")
for t in (10.0, 11.0, 12.0, 14.0, 18.0, 8.0, 6.0):
    want = round(40 * 30 * t + 1005.3096491487338 * 2, 3)
    for area in (None, BOSS_AREA):
        d = stepped(plate_t=t, pick=[0.0, 0.0, 15.0], area=area)
        d.rebuild()
        desc, _ = resolved(d._parts["part"], [0.0, 0.0, 15.0], area)
        vol = volume(d)
        ok = "" if vol is not None and abs(vol - want) < 0.01 else \
             f"   <-- want {want}"
        print("  %6.1f   %-11s  %-42s %11s%s"
              % (t, "-" if area is None else f"{area} mm2", desc, vol, ok))
        del d

# ---------------------------------------------------------------------------
head(2, "FOUR IDENTICAL BOSSES: distance must still decide")
print("""  Every boss top is the same size, so the gate keeps all four and the
  nearest one has to win - one pick per boss, as before.""")


def four_bosses(plate_t=10.0):
    doc = Document(name="p-four")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 80, "h": 60}]})
    doc.add("base", "extrude", {"amount": plate_t}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": plate_t, "entities": [
        {"kind": "circle", "r": 6, "x": x, "y": y}
        for x, y in ((-25, -15), (25, -15), (-25, 15), (25, 15))]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.rebuild()
    return doc


d4 = four_bosses()
part4 = d4._parts["part"]
A4 = round(3.14159265 * 36, 2)
print("")
print("  pick                 no area                       with area %.2f" % A4)
for x, y in ((-25, -15), (25, -15), (-25, 15), (25, 15)):
    c = [float(x), float(y), 15.0]
    f0 = blocks.resolve_face(part4, c, UP)
    f1 = blocks.resolve_face(part4, c, UP, A4)
    p0, p1 = f0.center(), f1.center()
    same = "SAME" if blocks._shape_key(f0) == blocks._shape_key(f1) else "DIFFERENT"
    print("  (%4.0f,%4.0f,15)      (%5.1f,%5.1f,%5.1f)          (%5.1f,%5.1f,%5.1f)  %s"
          % (x, y, p0.X, p0.Y, p0.Z, p1.X, p1.Y, p1.Z, same))

# ---------------------------------------------------------------------------
head(3, "FAIL OPEN: the PICKED face is the one that was resized")
print("""  Widen the plate and the plate top's own area changes. A pick on the
  PLATE top must still land on the plate top - no candidate matches the
  stored size any more, so the gate is skipped and the old answer stands.""")
print("")
print("  plate_w  stored area  resolved face")
for w in (40.0, 60.0, 90.0, 30.0):
    d = four_bosses()
    del d
    doc = Document(name="p-wide")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": w, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.rebuild()
    p = doc._parts["part"]
    # the pick: the PLATE top of the 40 mm plate (40*30 minus the boss disc)
    plate_area = round(40 * 30 - 3.14159265 * 64, 2)
    desc, _ = resolved(p, [0.0, 0.0, 10.0], plate_area)
    print("  %6.1f   %-11s  %s" % (w, f"{plate_area} mm2", desc))
    del doc

# ---------------------------------------------------------------------------
head(4, "THE HALF-STEP MOVE, as a second net")
print("""  The move half is closed by carrying the delta, but a pick that was NOT
  carried (an older file, a hand-written one) used to flip at half the step.
  With a size it does not.""")
print("")
print("  dz     no area                                     with area")
for dz in (0.0, 2.0, 2.49, 2.5, 3.0, 4.0, 6.0):
    doc = Document(name="p-move")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.add("placed", "move", {"x": 0, "y": 0, "z": dz}, inputs=["part"])
    doc.rebuild()
    p = doc._parts["placed"]
    a, _ = resolved(p, [0.0, 0.0, 15.0], None)
    b, _ = resolved(p, [0.0, 0.0, 15.0], BOSS_AREA)
    print("  %4.2f   %-42s %s" % (dz, a, b))
    del doc

# ---------------------------------------------------------------------------
head(5, "COST: the area is measured in the pass the centre already pays for")
import time                                                    # noqa: E402

doc = Document(name="p-cost")
doc.add("outline", "sketch", {"plane": "XY", "entities": [
    {"kind": "rectangle", "w": 120, "h": 80}]})
doc.add("base", "extrude", {"amount": 12}, inputs=["outline"])
doc.add("holes_sk", "sketch", {"plane": "XY", "offset": 12, "entities": [
    {"kind": "circle", "r": 3, "x": -50 + 10 * i, "y": y}
    for i in range(10) for y in (-25, 0, 25)]})
doc.add("holes", "extrude", {"amount": -12}, inputs=["holes_sk"])
doc.add("part", "cut", {}, inputs=["base", "holes"])
doc.rebuild()
big = doc._parts["part"]
t0 = time.perf_counter()
rows = blocks._measure_face_rows(big)
cold = (time.perf_counter() - t0) * 1000
t0 = time.perf_counter()
for _ in range(50):
    blocks._face_rows(big)
warm = (time.perf_counter() - t0) / 50 * 1e6
print("")
print(f"  faces on the test body : {len(rows)}")
print(f"  _measure_face_rows cold: {cold:8.1f} ms  (centre + normal + area)")
print(f"  _face_rows warm (cached): {warm:7.2f} us")
print(f"  areas measured         : {sum(1 for r in rows if r[4] is not None)}"
      f" of {len(rows)}")
