"""Round FOUR: `move` is the ONE op left outside the numeric door, and round
three's P0 was exactly a flag in a placement number.

Round three fixed `sketch {"offset": true}` building silently at Z = 1 — "a
silent wrong PLACEMENT is the worst class there is". `move` was deliberately
left out of the same door because it reads a MISSING offset as 0 on purpose
(`_move_offsets`). A missing offset and a `true` one are not the same thing,
and `float(True)` is 1.0.

The census cannot see this: a move does not change a volume. This measures
WHERE THE BODY IS.

Run: C:\\Python314\\python.exe probes/s10_r4_move_door.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document import Document, _move_offsets                       # noqa: E402

PLATE = {"width": 20, "depth": 20, "thickness": 5}


def centre(params):
    d = Document(name="m")
    d.add("b1", "plate", PLATE, [])
    d.add("m1", "move", params, ["b1"])
    ok = d.rebuild()
    f = d.get("m1")
    part = d._parts.get("m1")
    if part is None:
        return ok, f.status, None, f.problems
    bb = part.bounding_box()
    return ok, f.status, (round(bb.center().X, 4), round(bb.center().Y, 4),
                          round(bb.center().Z, 4)), f.problems


print("the body's centre after `move`, for every value a file can hold")
print("-" * 78)
base = centre({})
print(f"  {'{}':<22} -> {base[2]}   (nothing moved)")
for params in ({"x": 0}, {"x": None}, {"x": 7}, {"x": -4}, {"x": "7"},
               {"x": True}, {"x": False}, {"y": True}, {"z": True},
               {"x": True, "y": True, "z": True},
               {"x": ""}, {"x": "abc"}, {"x": [1, 2]}, {"x": {"a": 1}}):
    ok, status, c, probs = centre(params)
    note = ""
    if c is not None and c != base[2]:
        note = "  <-- THE BODY MOVED"
    print(f"  {str(params):<22} -> {c} {status:<7}{probs or ''}{note}")

print()
print("_move_offsets directly")
print("-" * 78)
for v in (None, True, False, 0, 7, "7", "", "abc", [1, 2]):
    try:
        print(f"  x={v!r:<10} -> {_move_offsets({'x': v})}")
    except ValueError as e:
        print(f"  x={v!r:<10} -> {e}")

print()
print("and the edit path, which reads the SAME params (_move_delta)")
print("-" * 78)
d = Document(name="m")
d.add("b1", "plate", PLATE, [])
d.add("m1", "move", {"x": True}, ["b1"])
d.rebuild()
print("  a move of x=True, then edit x to 7:")
d.edit("m1", "x", 7)
d.rebuild()
bb = d._parts["m1"].bounding_box()
print(f"    centre now {round(bb.center().X, 4)} (a plate centred on 0 moved "
      f"to 7 means the True was read as 1)")
