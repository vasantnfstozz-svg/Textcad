"""Does the new pattern kind gate refuse something that BUILT before it?

`polar_pattern` and `linear_pattern` both hand the input straight back when
the pattern asks for no copies at all (`if n == 1: return feature`, and
`if not offsets: return feature`). Fed a SKETCH that is a pass-through with
status ok — and the gate in `document._check_modifier_input` now runs BEFORE
the op, so it never gets there.

Run:  C:\\Python314\\python.exe probes/s10_pattern_gate_count1_probe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pattern                                  # noqa: E402
import sketch as sk                             # noqa: E402
from document import Document                   # noqa: E402

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]

CASES = [
    ("linear_pattern", {"count": 1, "dx": 20}),
    ("linear_pattern", {"count": 1, "direction": [1, 0, 0], "distance": 20}),
    ("polar_pattern", {"count": 1}),
    ("polar_pattern", {"count": 1, "axis": "+z", "angle": 90}),
]

print("=" * 72)
print("A: the OP itself, called directly on a sketch (the gate bypassed)")
print("=" * 72)
s = sk.make_sketch("XY", 0.0, CIRC)
for op, kw in CASES:
    fn = getattr(pattern, op)
    try:
        out = fn(s, **kw)
        same = out is s
        print(f"  {op:16s} {kw} -> BUILT  identical-object={same} "
              f"area={getattr(out, 'area', None)}")
    except Exception as e:
        print(f"  {op:16s} {kw} -> refused: {e}")

print()
print("=" * 72)
print("B: the same through the document (the gate in front of it)")
print("=" * 72)
for op, kw in CASES:
    d = Document(name="c1")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add("p1", op, kw, ["s1"])
    d.rebuild()
    f = d.get("p1")
    print(f"  {op:16s} {kw} -> {f.status}: {f.problems}")

print()
print("=" * 72)
print("C: and a whole design that USED to rebuild — does it still?")
print("=" * 72)
d = Document(name="c2")
d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
d.add("p1", "linear_pattern", {"count": 1, "dx": 20}, ["s1"])
d.add("e1", "extrude", {"amount": 4}, ["p1"])
ok = d.rebuild()
print("  rebuild ok:", ok)
for fid in ("s1", "p1", "e1"):
    f = d.get(fid)
    print(f"    {fid}: {f.status} vol={f.volume} {f.problems}")
