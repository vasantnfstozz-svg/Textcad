"""PROBE - LAUNCH-PLAN s10 P1: "a stored face pick is remembered in WORLD
coordinates, so a body that MOVES can take the pick to a different face".

Round one of the Move review (9e04ff6 -> 4ee5670) turned the direction from a
25 mm2 NUDGE into a GATE, which closed the loud half: the pick can no longer
land on a face pointing the other way. This probe asks the half the plan says
is still open, and asks it of the KERNEL, not of the code reading:

  1. On a STEPPED body - a plate with a boss, so TWO faces point +Z - how far
     can the body move before a pick stored on the boss top resolves to the
     PLATE top instead? Measure the face (area, centre) AND the solid that
     comes out, and check every status the user would see.
  2. Is the answer a TIE anywhere (the queued `resolve_face` shared-centre
     item)? A round pocket with a flush round pad in it has an outer top and a
     pad top that are coplanar, both +Z, and share a centroid exactly.
  3. The fix: `move` is a pure translation and the document knows its delta
     at EDIT time. If the stored pick is carried by that delta, does it name
     the right face at every distance - and does it leave a pure PARAMETER
     change (a thicker plate) resolving exactly as it does today?

WHAT THE ANSWERS WERE (2026-09-16): (1) the pick flips at dz = 2.50 mm, HALF
the boss height, and the design silently becomes 18000.0 mm3 where 14010.62
was asked for, tree green and solid valid; (2) yes - a flush pad in a round
pocket ties exactly, and refusing that tie was measured OUT again because
Shell asks the same question once per lump and two concentric lumps tie too;
(3) yes, correct at every dz including negative, with the parameter path
untouched. Section 4 shows the half that is NOT closed and cannot be: a
thicker plate moves the pick exactly as a move does, and (centre, normal)
carries nothing that could tell the two apart.

Run under the memory cap:
  python probes/memcap.py --gb 4 --timeout 600 -- python probes/face_pick_frame_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blocks                       # noqa: E402
import inspector                    # noqa: E402
from document import Document       # noqa: E402

BOSS_TOP = [0.0, 0.0, 15.0]         # the pick, as the viewport would store it
UP = [0.0, 0.0, 1.0]


def stepped(dz=0.0, plate_t=10.0, boss_h=5.0, riser=5.0):
    """plate 40 x 30 x plate_t, a r8 x boss_h boss fused on top, the whole
    thing MOVED by dz, then a pick on the boss top pulled up by `riser` and
    fused back on. Two faces point +Z, so the pick has a choice."""
    doc = Document(name="p-frame")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": plate_t}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": plate_t, "entities": [
        {"kind": "circle", "r": 8, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": boss_h}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.add("placed", "move", {"x": 0, "y": 0, "z": dz}, inputs=["part"])
    doc.add("riser", "extrude_face",
            {"face_center": list(BOSS_TOP), "face_normal": list(UP),
             "amount": riser}, inputs=["placed"])
    doc.add("final", "fuse", {}, inputs=["placed", "riser"])
    doc._cache = {}
    return doc


def face_line(solid, center, normal):
    try:
        f = blocks.resolve_face(solid, center, normal)
    except ValueError:
        return "REFUSED (the two faces are an exact tie)          ", None
    c = f.center()
    return ("area %8.3f  centre (%6.2f,%6.2f,%6.2f)"
            % (f.area, c.X, c.Y, c.Z)), round(f.area, 3)


print("=" * 78)
print("1. THE PICK ON A STEPPED BODY, AS THE BODY MOVES")
print("=" * 78)
print("""  Plate 40 x 30 x 10 = 12000 mm3.  Boss r8 x 5 = 1005.310 mm3.
  Fused body = 13005.310 mm3.  The pick is the BOSS TOP (0,0,15), +Z:
  disc area 201.062.  The plate top is a RING, area 1200 - 201.062 = 998.938.
  `riser` pulls the picked face up 5 mm and fuses it back, so the design is
  13005.310 + 1005.310 = 14010.620 mm3 WHATEVER dz is - the boss just gets
  taller. Any other number is the pick landing somewhere it was not put.""")
print("")
print("   dz   resolved face on the moved body                    "
      "design mm3   status  health")
truth = None
for dz in (0.0, 1.0, 2.0, 2.4, 2.49, 2.5, 2.51, 3.0, 4.0, 6.0, 10.0):
    doc = stepped(dz=dz)
    ok = doc.rebuild()
    placed = doc._parts["placed"]
    desc, area = face_line(placed, BOSS_TOP, UP)
    part = doc.result()
    vol = None if part is None else round(part.volume, 3)
    if dz == 0.0:
        truth = vol
    h = inspector.health(part) if part is not None else None
    hs = "-" if h is None else ("clean" if not h else ",".join(map(str, h)))
    flag = "" if vol == truth else "   <-- WRONG"
    print("  %4.2f  %s  %11s   %-6s  %s%s"
          % (dz, desc, vol, doc.get("riser").status, hs, flag))
    del doc

print("")
print("  (health is inspector.health on the delivered solid; `status` is the "
      "tree row\n   the user reads. Both stay green on every row above.)")

print("")
print("=" * 78)
print("2. IS IT EVER A TIE?  (the queued shared-centre item)")
print("=" * 78)
print("""  A ROUND POCKET with a FLUSH ROUND PAD in the middle of it - a locating
  pad, an everyday shape. The top surface is then an outer region (square
  minus the pocket) and the pad's own disc. Both are planar, both point +Z,
  both lie on the same plane, and both have their centroid on the axis at
  the SAME point. resolve_face scores them identically - `min` then returns
  whichever the kernel happens to list first.""")
g = Document(name="p-tie")
g.add("o", "sketch", {"plane": "XY", "entities": [
    {"kind": "rectangle", "w": 40, "h": 40}]})
g.add("plate", "extrude", {"amount": 10}, inputs=["o"])
g.add("pocket_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
    {"kind": "circle", "r": 15}]})
g.add("pocket_tool", "extrude", {"amount": -3}, inputs=["pocket_sk"])
g.add("pocketed", "cut", {}, inputs=["plate", "pocket_tool"])
g.add("pad_sk", "sketch", {"plane": "XY", "offset": 7, "entities": [
    {"kind": "circle", "r": 10}]})
g.add("pad", "extrude", {"amount": 3}, inputs=["pad_sk"])
g.add("grooved", "fuse", {}, inputs=["pocketed", "pad"])
g._cache = {}
g.rebuild()
gp = g.result()
print("  grooved plate volume %.3f mm3" % gp.volume)
tops = []
for f in gp.faces():
    try:
        c, n = f.center(), f.normal_at(f.center())
    except Exception:
        continue
    if str(f.geom_type).split(".")[-1] == "PLANE" and n.Z > 0.9:
        tops.append((round(f.area, 3), (round(c.X, 2), round(c.Y, 2),
                                        round(c.Z, 2))))
print("  every planar +Z face (centre ROUNDED to 2dp, which is what the "
      "viewport stores):")
for a, c in tops:
    print("     area %9.3f  centre %s" % (a, c))
seen = {}
for a, c in tops:
    seen.setdefault(c, []).append(a)
tied = {c: v for c, v in seen.items() if len(v) > 1}
print("  centres shared by more than one face: %s" % (tied or "none"))
for c, areas in tied.items():
    try:
        got = blocks.resolve_face(gp, list(c), [0, 0, 1])
        print("     at %s the faces are %s mm2 -> resolve_face answers %.3f "
              "(decided by face ORDER, nothing else)" % (c, areas, got.area))
    except ValueError as e:
        print("     at %s the faces are %s mm2 -> REFUSED: %s" % (c, areas, e))
print("""
  DECIDED 2026-09-16: refusing this tie was built and MEASURED OUT again.
  Shell asks resolve_face once per lump, and a post inside a ring is two
  concentric lumps whose top faces tie EXACTLY, so the refusal turned a shell
  the kernel builds perfectly into a failure (tests/test_shell_tool.py
  ::test_concentric_lumps_a_post_inside_a_ring_still_shell). The tie is also
  not silent - the wrong face shows on the first click and the answer is
  stable across rebuilds - so it stays a LAUNCH-PLAN s10 row for the PICKERS
  to close by saying WHICH face they mean, not a guess for the resolver.""")
print("")
print("  the picks on that body that are NOT tied must still resolve:")
for c in sorted(seen):
    if c in tied:
        continue
    got = blocks.resolve_face(gp, list(c), [0, 0, 1])
    print("     %s -> area %.3f" % (c, got.area))

print("")
print("=" * 78)
print("3. THE FIX AS SHIPPED: CARRY THE PICK WITH THE MOVE, AT EDIT TIME")
print("=" * 78)
print("""  `move` is a pure translation and Document.edit KNOWS the delta. If
  every stored face pick DOWNSTREAM of that move is carried by the same
  delta, the pick stays where the user put it - on the body, not in the
  room. Below: build at dz = 0, then EDIT the move through the REAL code
  path (Document.edit, what /api/edit calls) and measure.""")
print("")
print("   dz   resolved face after the pick is carried               design mm3")
for dz in (0.0, 1.0, 2.5, 4.0, 6.0, 10.0, -7.0):
    doc = stepped(dz=0.0)
    doc.rebuild()
    doc.edit("placed", "z", dz)
    p = doc.get("riser").params
    doc.rebuild()
    desc, _a = face_line(doc._parts["placed"], p["face_center"], UP)
    part = doc.result()
    vol = None if part is None else round(part.volume, 3)
    flag = "" if vol == truth else "   <-- WRONG"
    print("  %5.1f  %s  %11s%s" % (dz, desc, vol, flag))
    del doc

print("")
print("=" * 78)
print("4. WHAT MUST NOT CHANGE: A PURE PARAMETER EDIT")
print("=" * 78)
print("""  Thicken the plate and the picked boss top moves too - but nothing was
  MOVED, so no delta exists and the world rule must go on finding it by
  nearest plane, exactly as it does today.""")
print("")
print("  plate_t   resolved face                                     design mm3")
for t in (10.0, 12.0, 14.0, 8.0, 6.0):
    doc = stepped(dz=0.0, plate_t=t)
    doc.rebuild()
    desc, _a = face_line(doc._parts["placed"], BOSS_TOP, UP)
    part = doc.result()
    want = round(40 * 30 * t + 1005.3096491487338 * 2, 3)
    vol = None if part is None else round(part.volume, 3)
    flag = "" if abs((vol or 0) - want) < 0.01 else "   <-- want %.3f" % want
    print("  %6.1f   %s  %11s%s" % (t, desc, vol, flag))
    del doc
