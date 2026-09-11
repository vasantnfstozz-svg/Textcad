"""P5 review probe — what a SLOPPY model reply does to the step loop.
Any traceback here is a crash road out of _apply_step (the loop promises
'never raises for the model's mistakes')."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import author
from document import Document

BAD = [
    ("inputs as a string", {"add": {"id": "c", "op": "cut", "inputs": "base",
                                    "params": {}}}),
    ("params as a list", {"add": {"id": "c", "op": "disc", "params": [1, 2]}}),
    ("params as a string", {"add": {"id": "c", "op": "disc", "params": "r=5"}}),
    ("inputs with a number", {"add": {"id": "c", "op": "cut", "inputs": [1, 2]}}),
    ("id is a number", {"add": {"id": 5, "op": "disc",
                                "params": {"radius": 3, "thickness": 2}}}),
    ("op is a list", {"add": {"id": "c", "op": ["disc"], "params": {}}}),
    ("edit value is a dict", {"edit": {"feature_id": "base", "param": "width",
                                       "value": {"mm": 50}}}),
    ("edit param is 'op'", {"edit": {"feature_id": "base", "param": "op",
                                     "value": "disc"}}),
    ("edit param unknown", {"edit": {"feature_id": "base", "param": "zz",
                                     "value": 1}}),
    ("remove is a list", {"remove": ["base"]}),
    ("done spec is a list", {"done": True, "spec": [1, 2]}),
    ("done spec holes is a list", {"done": True,
                                   "spec": {"holes": ["5"], "n_solids": 1}}),
    ("reply is a list", "[{\"add\": {}}]"),
    ("reply is a number", "42"),
    ("empty object", {}),
    ("add is a list", {"add": [{"id": "c"}]}),
]


class One:
    def __init__(self, reply):
        self.reply = reply if isinstance(reply, str) else json.dumps(reply)
        self.n = 0

    def generate(self, messages):
        self.n += 1
        return self.reply


for label, reply in BAD:
    d = Document(name="probe")
    d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
    d.rebuild()
    try:
        ok, tr = author.author_steps(d, "x", One(reply), max_fails=1)
        tree = [f.id for f in d.features]
        state = "TREE DIRTIED" if tree != ["base"] else "clean"
        print(f"  {label:26s} -> {state:13s} | {tr[0][:78]}")
    except Exception as e:
        print(f"  {label:26s} -> *** RAISED {type(e).__name__}: {str(e)[:70]}")
