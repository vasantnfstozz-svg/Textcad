"""Section 13 ROUND THREE, part 3 — the BLOB rule after round two.

Round one's blob rule carried `and all(mine(f.id) for f in features)`, so on a
design the USER already owns it could never fire: every feature of a two-
feature user design is outside `authored`. Round two deleted that clause and
leaned on the baseline instead — which forgives only a blob the tree ALREADY
had, at the entity count it already had.

So: the user hand-draws a sketch and asks the AI to extrude it, or asks it to
put three more holes in their one-sketch plate. Does `done` refuse?

Run:  C:\\Python314\\python.exe probes/s13_round3_probe3.py
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


def circles(n, y=0.0):
    return [{"kind": "circle", "r": 2, "x": -((n - 1) * 5) / 2 + i * 5, "y": y}
            for i in range(n)]


# --------------------------------------------------------------------------
head("A. THE USER DREW A SKETCH BY HAND AND ASKS THE AI TO EXTRUDE IT")
for n in (1, 3, 4, 5, 6, 9):
    doc = Document(name="hand-drawn")
    doc.add("plate_sketch", "sketch",
            {"plane": "XY", "offset": 0,
             "entities": [{"kind": "rectangle", "w": 60, "h": 40}] + circles(n - 1)
             if n > 1 else [{"kind": "rectangle", "w": 60, "h": 40}]})
    doc.rebuild()
    base = author.lint_baseline(doc.features)
    m = Scripted({"add": {"id": "plate", "op": "extrude",
                          "params": {"amount": 5}, "inputs": ["plate_sketch"]}},
                 {"done": True}, {"done": True}, {"done": True})
    before = doc.to_data()
    ok, tr = author.author_steps(doc, "extrude this 5 mm", m, max_fails=3)
    kept = [f.id for f in doc.features]
    print(f"  the user's sketch has {n} entit{'y' if n == 1 else 'ies'}; "
          f"baseline={list(base)}")
    print(f"     finished={ok}   tree after = {kept}")
    if not ok:
        print(f"     >>> {tr[1][:150]}")
        print(f"     >>> studio would now restore: {before == doc.to_data()} "
              f"(the loop itself left the extrude in place: "
              f"{'plate' in kept})")

# --------------------------------------------------------------------------
head("B. THE USER'S ONE-SKETCH PLATE, AND THE AI IS ASKED FOR MORE HOLES")
doc = Document(name="hand-drawn")
doc.add("plate_sketch", "sketch",
        {"plane": "XY", "offset": 0,
         "entities": [{"kind": "rectangle", "w": 60, "h": 40},
                      {"kind": "circle", "r": 2, "x": -20, "y": 0,
                       "mode": "subtract"}]})
doc.add("plate", "extrude", {"amount": 5}, inputs=["plate_sketch"])
doc.rebuild()
print(f"  their design: {[f.id for f in doc.features]}, "
      f"{len(doc.get('plate_sketch').params['entities'])} entities, "
      f"baseline={list(author.lint_baseline(doc.features))}")
ents = [{"kind": "rectangle", "w": 60, "h": 40}] + [
    {"kind": "circle", "r": 2, "x": -20 + i * 10, "y": 0, "mode": "subtract"}
    for i in range(5)]
m = Scripted({"edit": {"feature_id": "plate_sketch", "param": "entities",
                       "value": ents}},
             {"done": True}, {"done": True}, {"done": True})
before = doc.to_data()
ok, tr = author.author_steps(doc, "put four more holes in it", m, max_fails=3)
print(f"  finished={ok}")
for t in tr:
    print(f"     {t[:150]}")
print(f"  the loop left the edit in place: "
      f"{len(doc.get('plate_sketch').params['entities'])} entities")

# --------------------------------------------------------------------------
head("C. WHAT ROUND ONE DID WITH THE SAME TWO JOBS")
print("""  Round one's blob rule read:
      if (final and len(features) == 2 and len(sketches) == 1
              and all(mine(f.id) for f in features)):
  `mine` is `fid in (authored | {fid})`, and the USER's sketch is in neither,
  so `all(...)` was False and the rule could not fire on a design the user
  already owned. Round two deleted the clause.""")

# --------------------------------------------------------------------------
head("D. HOW MANY OF THE SAVED DESIGNS ARE ONE SKETCH + ONE CONSUMER?")
lib = Path(__file__).resolve().parent.parent / "designs"
hits, total = [], 0
for p in sorted(lib.glob("*.tcad.json")):
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                           # noqa: BLE001
        continue
    total += 1
    fs = data.get("features") or []
    sk = [f for f in fs if f.get("op") == "sketch"]
    if len(fs) == 2 and len(sk) == 1:
        n = len((sk[0].get("params") or {}).get("entities") or [])
        hits.append((p.stem.replace(".tcad", ""), n))
print(f"  {len(hits)} of {total} saved designs are exactly one sketch + one "
      f"consumer: {hits}")
# ...and how many are ONE sketch alone, waiting to be extruded
alone = []
for p in sorted(lib.glob("*.tcad.json")):
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                           # noqa: BLE001
        continue
    fs = data.get("features") or []
    if len(fs) == 1 and fs[0].get("op") == "sketch":
        alone.append((p.stem, len((fs[0].get("params") or {}).get("entities") or [])))
print(f"  {len(alone)} are a lone sketch: {alone}")
