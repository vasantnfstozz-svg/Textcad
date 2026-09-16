"""Section 13 ROUND THREE, part 4 — the last two doors into the baseline.

(1) `lint_baseline` collapses `_lint_items` into a dict, so two features with
    the SAME key would forgive each other. Can a tree ever hold two features
    with one id?
(2) `lint_baseline(doc.features)` is the FIRST thing `author_steps` does and it
    is not inside any try — and it calls `float(params["offset"])`. Can a
    design carry an offset `float()` refuses, and what does the user see?
(3) the blob fix, re-measured.

Run:  C:\\Python314\\python.exe probes/s13_round3_probe4.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import author                                                    # noqa: E402
from document import Document                                    # noqa: E402


class Scripted:
    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r)
                        for r in replies]

    def generate(self, messages):
        if not self.replies:
            return json.dumps({"done": True})
        return self.replies.pop(0)


def head(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


head("1. TWO FEATURES, ONE ID — CAN A TREE HOLD THEM?")
data = {"name": "corrupt", "features": [
    {"id": "sk", "op": "sketch",
     "params": {"plane": "XY", "offset": 0,
                "entities": [{"kind": "rectangle", "w": 40, "h": 30}]},
     "inputs": []},
    {"id": "ex", "op": "extrude", "params": {"amount": 5}, "inputs": ["sk"]},
    {"id": "dup", "op": "sketch",
     "params": {"plane": "XY", "offset": 7.0,
                "entities": [{"kind": "circle", "r": 3}]}, "inputs": []},
    {"id": "dup", "op": "sketch",
     "params": {"plane": "XY", "offset": 7.0,
                "entities": [{"kind": "circle", "r": 4}]}, "inputs": []},
], "spec": {}}
try:
    d = Document.from_data(data)
    ids = [f.id for f in d.features]
    print(f"  Document.from_data kept: {ids}")
    items = author._lint_items(d.features)
    print(f"  _lint_items yields {len(items)} problems; "
          f"lint_baseline holds {len(author.lint_baseline(d.features))}")
    if len(items) != len(author.lint_baseline(d.features)):
        print("  *** a key COLLAPSED: one feature's problem forgives another's")
except Exception as e:                                          # noqa: BLE001
    print(f"  Document.from_data refused: {type(e).__name__}: {e}")


head("2. AN OFFSET `float()` CANNOT READ")
doc = Document(name="plate")
doc.add("base_sketch", "sketch", {"plane": "XY", "offset": 0,
                                  "entities": [{"kind": "rectangle",
                                                "w": 40, "h": 30}]})
doc.add("base", "extrude", {"amount": 5}, inputs=["base_sketch"])
doc.add("boss_sketch", "sketch", {"plane": "XY", "offset": 0,
                                  "entities": [{"kind": "circle", "r": 4}]})
doc.rebuild()
for value in ("12mm", "", None, "8", float("nan")):
    d2 = Document.from_data(doc.to_data())
    try:
        d2.edit("boss_sketch", "offset", value)
        took = repr(d2.get("boss_sketch").params.get("offset"))
    except Exception as e:                                      # noqa: BLE001
        print(f"  offset={value!r:12} -> Document.edit refused: "
              f"{type(e).__name__}: {str(e)[:60]}")
        continue
    try:
        base = author.lint_baseline(d2.features)
        print(f"  offset={value!r:12} -> stored {took:12} "
              f"lint_baseline ok, keys {list(base)}")
    except Exception as e:                                      # noqa: BLE001
        print(f"  offset={value!r:12} -> stored {took:12} "
              f"*** lint_baseline raised {type(e).__name__}: {e}")
        m = Scripted({"edit": {"feature_id": "base", "param": "amount",
                               "value": 6}}, {"done": True})
        try:
            author.author_steps(d2, "thicker", m, max_fails=1)
            print("       author_steps survived")
        except Exception as e2:                                 # noqa: BLE001
            print(f"       author_steps raises out: "
                  f"{type(e2).__name__}: {e2}")


head("3. THE BLOB FIX, RE-MEASURED")
for n in (1, 4, 5, 9, 30):
    doc = Document(name="hand-drawn")
    doc.add("plate_sketch", "sketch",
            {"plane": "XY", "offset": 0,
             "entities": [{"kind": "rectangle", "w": 90, "h": 60}]
             + [{"kind": "circle", "r": 1.5, "x": -40 + (i % 12) * 7,
                 "y": -20 + (i // 12) * 12, "mode": "subtract"}
                for i in range(n - 1)]})
    doc.rebuild()
    m = Scripted({"add": {"id": "plate", "op": "extrude",
                          "params": {"amount": 5}, "inputs": ["plate_sketch"]}},
                 {"done": True}, {"done": True}, {"done": True})
    ok, tr = author.author_steps(doc, "extrude this 5 mm", m, max_fails=3)
    print(f"  the user's hand-drawn sketch, {n:2} entities -> finished={ok}"
          f"   {'' if ok else tr[-1][:90]}")

print("\n  ...and the rules the fix must NOT touch:")
# the model creating a blob from nothing
doc = Document(name="untitled")
six = [{"kind": "circle", "r": 3 + i, "x": i * 10, "y": 0} for i in range(6)]
m = Scripted({"add": {"id": "art_sketch", "op": "sketch",
                      "params": {"plane": "XY", "offset": 0, "entities": six}}},
             {"add": {"id": "art", "op": "extrude", "params": {"amount": 3},
                      "inputs": ["art_sketch"]}},
             {"done": True}, {"done": True}, {"done": True})
ok, tr = author.author_steps(doc, "a plate", m, max_fails=3)
print(f"   the MODEL's own one-sketch design: finished={ok}  {tr[-2][:80]}")
# the whole-tree MCP door
try:
    author._to_document({"name": "blob", "features": [
        {"id": "art_sketch", "op": "sketch",
         "params": {"plane": "XY", "offset": 0, "entities": six}},
        {"id": "art", "op": "extrude", "params": {"amount": 3},
         "inputs": ["art_sketch"]}]})
    print("   *** build_design ACCEPTED a blob tree")
except ValueError as e:
    print(f"   build_design still refuses a blob tree: {str(e)[:70]}")
# the AI's own absolute-offset sketch, on the user's tree
doc = Document(name="hand-drawn")
doc.add("plate_sketch", "sketch", {"plane": "XY", "offset": 0,
                                   "entities": [{"kind": "rectangle",
                                                 "w": 60, "h": 40}]})
doc.add("plate", "extrude", {"amount": 5}, inputs=["plate_sketch"])
doc.rebuild()
m = Scripted({"add": {"id": "boss_sketch", "op": "sketch",
                      "params": {"plane": "XY", "offset": 5.0,
                                 "entities": [{"kind": "circle", "r": 4}]}}},
             {"done": True})
ok, tr = author.author_steps(doc, "a boss", m, max_fails=1)
print(f"   the AI's own absolute-offset sketch: refused={not ok}  "
      f"{tr[0][:70]}")
# an 11-entity sketch of the AI's own
m = Scripted({"add": {"id": "art_sketch", "op": "sketch",
                      "params": {"plane": "XY", "offset": 0,
                                 "entities": [{"kind": "circle", "r": 1,
                                               "x": -25 + i * 4, "y": 0}
                                              for i in range(11)]}}},
             {"done": True})
doc = Document(name="hand-drawn")
doc.add("plate_sketch", "sketch", {"plane": "XY", "offset": 0,
                                   "entities": [{"kind": "rectangle",
                                                 "w": 60, "h": 40}]})
doc.add("plate", "extrude", {"amount": 5}, inputs=["plate_sketch"])
doc.rebuild()
ok, tr = author.author_steps(doc, "art", m, max_fails=1)
print(f"   the AI's own 11-entity sketch:      refused={not ok}  "
      f"{tr[0][:70]}")
