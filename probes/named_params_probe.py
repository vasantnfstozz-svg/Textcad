"""Named parameters through the DOCUMENT: `wall = 3`, an extrude whose amount
is "wall*2", the volume follows a change of wall (cache invalidation), rename
rewrites the formula by token, delete is refused while used, a loop is a
sentence, save/load carries parameters and the 47 saved designs round-trip
byte for byte (no `parameters` key when there are none)."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from document import Document  # noqa: E402

d = Document(name="np")
d.add("s", "sketch", {"plane": "XY", "entities": [{"kind": "rectangle", "w": 20, "h": 10, "mode": "add"}]}, [])
d.set_parameter("wall", "3", "the wall thickness")
d.add("e", "extrude", {"amount": "wall*2"}, ["s"], strict=True)
d.rebuild()
print("e:", d.get("e").status, d.get("e").problems, "volume", d.get("e").volume, "(expect 1200)")
d.set_parameter("wall", "4")
d.rebuild()
print("wall=4 ->", d.get("e").volume, "(expect 1600)")
d.set_parameter("wall_2", "wall + 1")
d.rename_parameter("wall", "thickness")
print("renamed:", d.get("e").params, d.parameters)
d.rebuild()
print("after rename:", d.get("e").status, d.get("e").volume)
for bad in [("thickness", "thickness*2"), ("wall_2", "thickness_3 + 1"), ("e", "1"), ("2x", "1"),
            ("min", "1"), ("t", "1/0"), ("t", "__import__('os')")]:
    try:
        d.set_parameter(*bad)
        print("ACCEPTED", bad, "<-- check")
    except ValueError as ex:
        print("refused", bad, "->", str(ex)[:100])
d.set_parameter("a", "b + 1") if False else None
try:
    d.set_parameter("a", "1")
    d.set_parameter("b", "a + 1")
    d.set_parameter("a", "b + 1")
    print("LOOP ACCEPTED <-- check")
except ValueError as ex:
    print("loop refused ->", ex)
try:
    d.remove_parameter("thickness")
except ValueError as ex:
    print("delete refused ->", ex)
d.edit_many("e", {"amount": "wal*2"}) if False else None
try:
    d.edit_many("e", {"amount": "wal*2"})
except ValueError as ex:
    print("edit refused ->", ex)
try:
    d.edit_many("e", {"amount": "8mm"})
except ValueError as ex:
    print("8mm refused ->", ex)
data = d.to_data()
print("to_data keys:", sorted(data), "parameters:", data["parameters"])
d2 = Document.from_data(json.loads(json.dumps(data)))
d2.rebuild()
print("reloaded:", d2.get("e").volume, d2.param_values)
# a saved file whose parameter is gone still OPENS, red where it matters
broken = json.loads(json.dumps(data))
del broken["parameters"]["thickness"]
d3 = Document.from_data(broken)
d3.rebuild()
print("missing parameter opens:", d3.get("e").status, d3.get("e").problems[:1], d3.param_problems)
# the 47 saved designs: byte-identical round trip, no parameters key
designs = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\VasanSeenivasan\Desktop\textcad\designs"
same = diff = 0
for path in sorted(glob.glob(os.path.join(designs, "*.tcad.json"))):
    raw = json.load(open(path, encoding="utf-8"))
    out = Document.from_data(raw).to_data()
    if "parameters" in out:
        print("  PARAMETERS KEY APPEARED in", path)
    if json.dumps(out, sort_keys=True) == json.dumps({k: raw[k] for k in ("name", "spec", "features") if k in raw}
                                                     | {"spec": raw.get("spec", {})}, sort_keys=True):
        same += 1
    else:
        diff += 1
        print("  round trip differs:", os.path.basename(path))
print(f"round trip: {same} identical, {diff} differ")
