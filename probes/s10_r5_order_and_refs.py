r"""Round FIVE, part 1: the ORDER of the doors, and the new REF signature.

Nothing here builds a design file; every document is made in memory, so this
probe is read-only with respect to designs/.

  1  ORDER OF CHECKS  -- when two things are wrong at once, which sentence
     does the user read?  `_eval` runs `_check_modifier_input` (the KIND of
     the input, the more basic fact) BEFORE `_check_numeric_params` (which is
     where `_params_dict` says "its settings are damaged in the file").  So a
     modifier whose params are not a table at all reaches the kind check
     first, and the kind check reads `params.get(...)`.

  2  THE REF SIGNATURE  -- round four folded `param_refs` into `_signature`.
     Attack it: a ref that points FORWARD, a ref to a feature that is not
     there, a ref to a suppressed feature, a ref chain, a ref cycle, and
     `sweep_face`.

Run: C:\Python314\python.exe probes/s10_r5_order_and_refs.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blocks                                                       # noqa: E402
import document as D                                                # noqa: E402
from document import Document                                       # noqa: E402


CIRCLE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]


def _rail(mm):
    return [{"kind": "path", "closed": False, "start": [0, 0],
             "segments": [{"kind": "line", "to": [0, mm]}]}]


def line(t):
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


# ---------------------------------------------------------------------------
line("1. ORDER OF CHECKS: params that are not a table, on every modifier")
# ---------------------------------------------------------------------------
# One box, then the modifier under test with a LIST where its params should
# be.  What does the feature row say?
bad_rows = []
for op in sorted(set(D.MODIFIERS) | {"move"}):
    doc = Document(name="order")
    doc.add("body", "plate", {"width": 20, "depth": 20, "thickness": 10})
    doc.add("m", op, inputs=["body"])
    doc.get("m").params = [1, 2]            # what a foreign file held
    doc._cache = {}
    doc.rebuild()
    msg = (doc.get("m").problems or ["(none)"])[0]
    flag = ""
    if "settings are damaged" not in msg:
        flag = "  <-- NOT the file-damage sentence"
        bad_rows.append((op, msg))
    print(f"  {op:18s} {msg}{flag}")

print(f"\n  rows that do NOT read the file-damage sentence: {len(bad_rows)}")
for op, msg in bad_rows:
    print(f"    {op}: {msg}")

# ...and the same for a CREATOR and a COMBINER, for the record
for op, mk in (("plate", None), ("loft", None)):
    doc = Document(name="order2")
    if op == "loft":
        doc.add("s1", "sketch", {"entities": CIRCLE, "offset": 0.0})
        doc.add("s2", "sketch", {"entities": CIRCLE, "offset": 10.0})
        doc.add("m", "loft", inputs=["s1", "s2"])
    else:
        doc.add("m", "plate")
    doc.get("m").params = [1, 2]
    doc._cache = {}
    doc.rebuild()
    print(f"  {op:18s} {(doc.get('m').problems or ['(none)'])[0]}")

# ---------------------------------------------------------------------------
line("2. THE NEW REF SIGNATURE")
# ---------------------------------------------------------------------------


def sweep_doc(rail_len=20.0, path_id="rail", order="path_first",
              op="sweep", suppress_path=False):
    """profile circle r=5 swept along a straight rail of `rail_len`."""
    doc = Document(name="s")
    doc._cache = {}                      # its OWN cache: measure one document
    if order == "path_first":
        doc.add("rail", "sketch",
                {"entities": _rail(rail_len), "plane": "XZ", "offset": 0.0})
        doc.add("prof", "sketch",
                {"entities": CIRCLE, "plane": "XY", "offset": 0.0})
        doc.add("sw", op, {"path": path_id, "full": True}, inputs=["prof"])
    else:                                # the sweep BEFORE its path
        doc.add("prof", "sketch",
                {"entities": CIRCLE, "plane": "XY", "offset": 0.0})
        doc.add("sw", op, {"path": path_id, "full": True}, inputs=["prof"])
        doc.add("rail", "sketch",
                {"entities": _rail(rail_len), "plane": "XZ", "offset": 0.0})
    if suppress_path:
        doc.get("rail").suppressed = True
    return doc


print("\n-- 2a. the baseline round four fixed (edit the rail, same cache) --")
doc = sweep_doc(20.0)
doc.rebuild()
print(f"   rail 20  -> {doc.get('sw').volume}  {doc.get('sw').status}")
doc.edit("rail", "entities", _rail(40))
doc.rebuild()
print(f"   rail 40  -> {doc.get('sw').volume}  {doc.get('sw').status}"
      "   (3141.59 is right)")

print("\n-- 2b. TWO documents, ONE shared cache, different rails --")
shared: dict = {}
a = sweep_doc(20.0)
a._cache = shared
a.rebuild()
b = sweep_doc(40.0)
b._cache = shared
b.rebuild()
print(f"   A rail 20 -> {a.get('sw').volume}")
print(f"   B rail 40 -> {b.get('sw').volume}   (3141.59 is right)")

print("\n-- 2c. the sweep BEFORE its path (a forward reference) --")
shared2: dict = {}
c = sweep_doc(20.0, order="sweep_first")
c._cache = shared2
c.rebuild()
print(f"   A rail 20 -> {c.get('sw').volume} {c.get('sw').status}"
      f" :: {(c.get('sw').problems or [''])[0]}")
print(f"   sig refs  -> {c._sigs.get('sw')[:12]}")
d = sweep_doc(40.0, order="sweep_first")
d._cache = shared2
d.rebuild()
print(f"   B rail 40 -> {d.get('sw').volume} {d.get('sw').status}"
      f" :: {(d.get('sw').problems or [''])[0]}")
print(f"   sig refs  -> {d._sigs.get('sw')[:12]}"
      f"   SAME KEY? {c._sigs.get('sw') == d._sigs.get('sw')}")

print("\n-- 2d. a ref that names nothing --")
e = sweep_doc(20.0, path_id="ghost")
e.rebuild()
print(f"   {e.get('sw').status} :: {(e.get('sw').problems or [''])[0]}")

print("\n-- 2e. a suppressed path --")
g = sweep_doc(20.0, suppress_path=True)
g.rebuild()
print(f"   {g.get('sw').status} :: {(g.get('sw').problems or [''])[0]}")

print("\n-- 2f. a ref CYCLE: a sweep whose path is itself --")
h = Document(name="cyc")
h._cache = {}
h.add("prof", "sketch", {"entities": CIRCLE, "plane": "XY", "offset": 0.0})
h.add("sw", "sweep", {"path": "sw", "full": True}, inputs=["prof"])
try:
    h.rebuild()
    print(f"   {h.get('sw').status} :: {(h.get('sw').problems or [''])[0]}")
except Exception as ex:                                            # noqa: BLE001
    print(f"   RAISED {type(ex).__name__}: {ex}")

print("\n-- 2g. sweep_face carries `path` in REF_PARAMS? --")
print(f"   REF_PARAMS['sweep']      = {D.REF_PARAMS.get('sweep')}")
print(f"   REF_PARAMS['sweep_face'] = {D.REF_PARAMS.get('sweep_face')}")
print(f"   SWEEP_OPS                = {getattr(D, 'SWEEP_OPS', '(none)')}")

print("\n-- 2h. every op whose params can name another feature --")
import inspect                                                      # noqa: E402
suspects = []
for name, fn in list(D.CREATORS.items()) + list(D.MODIFIERS.items()):
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        continue
    for p in inspect.signature(fn).parameters:
        if p.startswith("_"):
            continue
        if p in ("seed", "path") and name not in D.REF_PARAMS:
            suspects.append((name, p))
print(f"   ops with a seed/path parameter that REF_PARAMS does not list:"
      f" {suspects}")

print("\nplain_cause of an AttributeError, for the record:")
print("   ", blocks.plain_cause(
    AttributeError("'list' object has no attribute 'get'")))
