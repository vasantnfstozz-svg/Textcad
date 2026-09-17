"""probes/s10_required_census.py — WHICH parameters are actually required.

The fix for the §10 P2 row adds a sentinel; this is the census it has to cover,
plus the exact Python a user sees today when each one is left out. Run it
BEFORE and AFTER the fix.

Run:  C:\\Python314\\python.exe probes\\s10_required_census.py
"""
import inspect
import sys

sys.path.insert(0, ".")

import blocks                                             # noqa: E402
import document                                           # noqa: E402
from document import CREATORS, MODIFIERS, Document, op_params   # noqa: E402

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]

print("=" * 70)
print("every op whose function has a parameter with NO default")
print("=" * 70)
required = {}
for name in list(CREATORS) + list(MODIFIERS):
    fn = CREATORS.get(name) or MODIFIERS.get(name)
    sig = list(inspect.signature(fn).parameters.values())
    if name in MODIFIERS:
        sig = sig[1:]
    need = [p.name for p in sig
            if p.default is inspect._empty
            and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
            and not p.name.startswith("_")]
    if need:
        required[name] = need
        print(f"  {name:18s} {need}")
print(f"\n  {len(required)} of {len(CREATORS) + len(MODIFIERS)} ops")

print("\n" + "=" * 70)
print("parameters whose default IS None (look identical in the catalogue today)")
print("=" * 70)
for name in list(CREATORS) + list(MODIFIERS):
    nones = [n for n, d in op_params(name) if d is None]
    if nones:
        print(f"  {name:18s} {nones}")

print("\n" + "=" * 70)
print("the row a user sees when a required parameter is omitted")
print("=" * 70)


def _row(op, params, inputs, pre=None):
    d = Document(name="r")
    for fid, fop, fpar, fin in (pre or []):
        d.add(fid, fop, fpar, fin)
    d.add("x1", op, params, inputs)
    d.rebuild()
    f = d.get("x1")
    print(f"  {op:18s} status={f.status}  {f.problems}")


sketch_pre = [("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])]
_row("extrude", {}, ["s1"], sketch_pre)
_row("revolve", {}, ["s1"], sketch_pre)
_row("sweep", {}, ["s1"], sketch_pre)

print("\n  and directly, with no document in the way:")
d = Document(name="d")
d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
d.rebuild()
for op in sorted(required):
    fn = CREATORS.get(op) or MODIFIERS.get(op)
    try:
        if op in MODIFIERS:
            fn(d._parts["s1"])
        else:
            fn()
    except Exception as e:                             # noqa: BLE001
        print(f"    {op:18s} {type(e).__name__}: {str(e).splitlines()[0][:90]}")
        print(f"    {'':18s} plain_cause -> {blocks.plain_cause(e)!r}")

print("\n" + "=" * 70)
print("REF_PARAMS / underscored: what op_params already hides")
print("=" * 70)
print(" ", document.REF_PARAMS)
