"""Round FOUR: the catalogue the AI reads, and the last 14 rows of the census.

Two jobs, neither of them geometry:

  1. `author.op_catalog` / `_catalog_text` against the registry itself — is
     every op in the catalogue, is every note about an op that exists, does
     every parameter carry the right unit, and does the `unit: "count"` /
     "any NUMERIC param may be a formula" promise hold for every parameter the
     catalogue marks as a number?
  2. the 14 rows the census leaves, spelled out exactly, plus the one class of
     sketch-entity damage the census's value list cannot reach (an entity dict
     that is missing a key), so whoever takes sketch.py can close them in one
     pass.

Run: C:\\Python314\\python.exe probes/s10_r4_catalogue_audit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import author                                                      # noqa: E402
from document import KNOWN_OPS, Document                           # noqa: E402

print("=" * 78)
print("1. the catalogue against the registry")
print("=" * 78)
cat = author.op_catalog()
ops = {c["op"] for c in cat}
print(f"  KNOWN_OPS {len(KNOWN_OPS)}, catalogue {len(ops)}")
print(f"  in KNOWN_OPS, not in the catalogue: {sorted(KNOWN_OPS - ops) or 'none'}")
print(f"  in the catalogue, not in KNOWN_OPS: {sorted(ops - KNOWN_OPS) or 'none'}")
print(f"  OP_NOTES about an op that does not exist: "
      f"{sorted(set(author.OP_NOTES) - KNOWN_OPS) or 'none'}")

print()
print("  a parameter the catalogue calls a NUMBER but the document does not")
print("  (the prompt says every numeric param may hold a formula):")
bad = []
for c in cat:
    numeric = Document.numeric_params(c["op"])
    for p in c["params"]:
        unit = p.get("unit")
        if unit in ("mm", "deg", "count") and p["name"] not in numeric:
            bad.append((c["op"], p["name"], unit, "catalogue only"))
        if p["name"] in numeric and unit not in ("mm", "deg", "count"):
            bad.append((c["op"], p["name"], unit, "document only"))
for b in bad:
    print("   ", b)
print("   ", "none" if not bad else f"{len(bad)} rows")

print()
print("  the REQUIRED sentinel, in the JSON the API and MCP serve:")
import json                                                        # noqa: E402
blob = json.dumps(cat)
print(f"    {len(blob)} bytes, 'REQUIRED' in it: {'REQUIRED' in blob}")
print(f"    parameters marked required: "
      f"{sum(1 for c in cat for p in c['params'] if p.get('required'))}")
txt = author._catalog_text()
for op in ("sweep", "loft", "move"):
    for line in txt.splitlines():
        if line.strip().startswith(op + "("):
            print(f"    {line.strip()}")

print()
print("=" * 78)
print("2. what the census leaves — all of it in sketch.py, NOT edited here")
print("=" * 78)
CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
rows = []
for op, key, bads in (
        ("sketch", "entities", ["abc", True, [1, 2], {"a": 1}, [[1, 2]]]),
        ("sketch", "plane", [[1, 2], {"a": 1}, [], [[1, 2]]]),
        ("sketch_on_face", "entities", ["abc", True, [1, 2], {"a": 1}, [[1, 2]]]),
):
    for bad in bads:
        d = Document(name="n")
        if op == "sketch":
            base = {"entities": CIRC, "plane": "XY", "offset": 0.0}
            d.add("p1", op, {**base, key: bad}, [])
        else:
            d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
            base = {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
                    "entities": CIRC, "offset": 0.0}
            d.add("p1", op, {**base, key: bad}, ["b1"])
        d.rebuild()
        rows.append((op, key, bad, " | ".join(d.get("p1").problems)))

print("  the 14 the census counts:")
for op, key, bad, msg in rows:
    print(f"    {op}.{key} = {bad!r:12s} -> {msg}")

print()
print("  and the class the census's value list cannot reach — an ENTITY that")
print("  is a dict but is missing a key, or holds a value that is not one:")
for ents in ([{"kind": "slot", "x": 0, "y": 0, "height": 4}],
             [{"kind": "circle", "x": 0, "y": 0}],
             [{"kind": "rectangle", "x": 0, "y": 0, "w": 5}],
             [{"x": 0, "y": 0, "r": 5}],
             [{"kind": "circle", "x": "a", "y": 0, "r": 5}],
             [{"kind": "circle", "x": 0, "y": 0, "r": ""}],
             [{"kind": "polygon", "points": "abc"}],
             [{"kind": "text", "text": 5, "size": 4, "x": 0, "y": 0}]):
    d = Document(name="n")
    d.add("p1", "sketch", {"entities": ents, "plane": "XY", "offset": 0.0}, [])
    d.rebuild()
    print(f"    {str(ents)[:58]:<60} -> {' | '.join(d.get('p1').problems)}")
