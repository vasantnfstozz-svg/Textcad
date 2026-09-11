"""P5 review probe — what the step loop does to a design that is NOT a blank
sheet. Each block prints MEASURED facts (spec dict, feature ids, volumes).

Run from the repo root.
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import author
from document import Document


class Scripted:
    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]
        self.heard = []

    def generate(self, messages):
        self.heard.append(messages[-1]["content"])
        # repeat the last reply once the script runs out, so a probe block
        # that needs one more step shows the LOOP's verdict, not an assert
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def user_plate():
    """A user's design: a 40x30x5 plate with their OWN spec."""
    d = Document(name="my-plate")
    d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
    d.spec = {"size": [40, 30, 5], "n_solids": 1, "tol": 0.5}
    d.rebuild()
    return d


print("=" * 70)
print("H1: does an AI 'add' job REPLACE the user's own spec?")
d = user_plate()
print("  user spec BEFORE:", d.spec)
m = Scripted({"add": {"id": "boss", "op": "disc",
                      "params": {"radius": 6, "thickness": 8}}},
             {"add": {"id": "joined", "op": "fuse", "inputs": ["base", "boss"]}},
             {"done": True, "spec": {"n_solids": 1}})
ok, tr = author.author_steps(d, "add a 12mm boss", m)
print("  finished:", ok)
print("  user spec AFTER :", d.spec)
print("  VERDICT:", "REPLACED (finding)" if d.spec.get("size") is None else "kept")

print()
print("=" * 70)
print("H1b: a REFUSED done also overwrites the spec?")
d = user_plate()
print("  user spec BEFORE:", d.spec)
m = Scripted({"done": True, "spec": {"n_solids": 1, "volume": 999999}})
ok, tr = author.author_steps(d, "finish it", m, max_fails=1)
print("  finished:", ok, "| transcript:", tr[0][:90])
print("  user spec AFTER :", d.spec)

print()
print("=" * 70)
print("H2: a design that ALREADY has a red feature — can the AI add to it?")
d = Document(name="half-broken")
d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
d.add("bad", "with_center_hole", {"radius": 500}, inputs=["base"])
d.rebuild()
print("  before:", [(f.id, f.status) for f in d.features])
m = Scripted({"add": {"id": "boss", "op": "disc",
                      "params": {"radius": 6, "thickness": 8}}},
             {"edit": {"feature_id": "bad", "param": "radius", "value": 8}},
             {"add": {"id": "join", "op": "fuse", "inputs": ["bad", "boss"]}},
             {"done": True, "spec": {"n_solids": 1}})
ok, tr = author.author_steps(d, "add a boss", m)
print("  finished:", ok)
for t in tr:
    print("   -", t[:140])
print("  tree after:", [(f.id, f.status) for f in d.features])

print()
print("=" * 70)
print("H3: does {'add': ..., 'done': true} finish WITHOUT the spec/lint check?")
d = Document(name="untitled")
m = Scripted({"add": {"id": "a", "op": "plate",
                      "params": {"width": 20, "depth": 20, "thickness": 4}}},
             {"add": {"id": "b", "op": "disc",
                      "params": {"radius": 5, "thickness": 10}}, "done": True})
ok, tr = author.author_steps(d, "two loose bodies", m)
print("  finished:", ok, "| bodies:", d.leaf_solid_ids(), "| spec:", d.spec)
print("  last transcript line:", tr[-1][:120])
print("  VERDICT:", "FINISHED with 2 loose bodies and no spec (finding)"
      if ok and len(d.leaf_solid_ids()) > 1 else "refused / one body")

print()
print("=" * 70)
print("H4: a parked ROLLBACK bar — every step undone?")
d = user_plate()
d.add("boss", "disc", {"radius": 6, "thickness": 8})
d.rollback = "base"
d.rebuild()
print("  rollback:", d.rollback, [(f.id, f.status) for f in d.features])
m = Scripted({"add": {"id": "x", "op": "disc", "params": {"radius": 3, "thickness": 3}}})
ok, tr = author.author_steps(d, "add a pin", m)
print("  finished:", ok)
print("   -", tr[0][:170])
print("  rollback after:", d.rollback)

print()
print("=" * 70)
print("H19: can an AI 'add' job REMOVE one of the user's own features?")
d = user_plate()
d.add("boss", "disc", {"radius": 6, "thickness": 8})
d.rebuild()
before_ids = [f.id for f in d.features]
print("  user tree BEFORE:", before_ids)
m = Scripted({"remove": "boss"},
             {"done": True, "spec": {"n_solids": 1}})
ok, tr = author.author_steps(d, "add a hole", m)
print("  finished:", ok, "| tree AFTER:", [f.id for f in d.features])
print("  VERDICT:", "user feature GONE (finding)"
      if ok and "boss" not in [f.id for f in d.features] else "refused")

print()
print("=" * 70)
print("H6: does a refused step keep the model's doc NAME change?")
d = Document(name="untitled")
m = Scripted({"name": "sports-car", "add": {"id": "a", "op": "nonesuch", "params": {}}},
             {"add": {"id": "a", "op": "plate",
                      "params": {"width": 20, "depth": 20, "thickness": 4}}},
             {"done": True, "spec": {"n_solids": 1}})
ok, tr = author.author_steps(d, "a car", m)
print("  name after a REFUSED name-carrying step:", d.name, "| finished:", ok)
