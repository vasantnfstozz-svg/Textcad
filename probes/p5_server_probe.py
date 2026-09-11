"""P5 review probe — the SERVER side of a chat job (studio.py).

Runs the job inline (JOB_THREADS=False) against a TestClient, so every check
is a measured fact about STATE, not a guess.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import studio
from document import Document
from fastapi.testclient import TestClient


class Scripted:
    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]

    def generate(self, messages):
        assert self.replies, "asked for more steps than scripted"
        return self.replies.pop(0)


def fresh(monkey_model, intent):
    studio.JOB_THREADS = False
    studio.SESSION_ENABLED = False
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.chat_intent = lambda msg: intent
    studio._make_model = lambda: monkey_model
    return TestClient(studio.app)


print("=" * 70)
print("S1: an 'add' job that GIVES UP — is the user's rollback bar kept?")
c = fresh(Scripted({"add": {"id": "x", "op": "disc", "params": {"radius": 3, "thickness": 3}}},
                   {"add": {"id": "x", "op": "disc", "params": {"radius": 3, "thickness": 3}}},
                   {"add": {"id": "x", "op": "disc", "params": {"radius": 3, "thickness": 3}}}),
          {"action": "add", "description": "add a pin"})
d = Document(name="parked")
d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
d.add("boss", "disc", {"radius": 6, "thickness": 8})
d.rollback = "base"
tid = studio._new_tab(d)
studio._rebuild_and_mesh()
print("  rollback BEFORE:", studio.STATE["docs"][tid]["doc"].rollback)
r = c.post("/api/chat", json={"message": "add a pin"}).json()
print("  reply:", (r.get("reply") or "")[:90])
after = studio.STATE["docs"][tid]["doc"]
print("  rollback AFTER :", after.rollback, "| same doc object:", after is d)
print("  VERDICT:", "ROLLBACK BAR LOST (finding)" if after.rollback is None else "kept")

print()
print("=" * 70)
print("S2: does an 'add' job that REMOVES a user feature report it honestly?")
c = fresh(Scripted({"remove": "boss"}, {"done": True, "spec": {"n_solids": 1}}),
          {"action": "add", "description": "add a hole"})
d = Document(name="my-plate")
d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
d.add("boss", "disc", {"radius": 6, "thickness": 8})
tid = studio._new_tab(d)
studio._rebuild_and_mesh()
r = c.post("/api/chat", json={"message": "add a hole"}).json()
print("  reply:", (r.get("reply") or "")[:160])
print("  tree after:", [f.id for f in studio.STATE["docs"][tid]["doc"].features])

print()
print("=" * 70)
print("S3: a user EDIT landing mid-job — does 'one Undo takes it all back' hold?")
studio.JOB_THREADS = False
c = fresh(None, {"action": "answer", "text": "x"})
d = Document(name="interleave")
d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
tid = studio._new_tab(d)
studio._rebuild_and_mesh()


class Meddling:
    """A model whose second step is interrupted by the user's own edit."""
    def __init__(self, client):
        self.client, self.n = client, 0

    def generate(self, messages):
        self.n += 1
        if self.n == 1:
            return json.dumps({"add": {"id": "p1", "op": "disc",
                                       "params": {"radius": 3, "thickness": 3}}})
        if self.n == 2:
            rr = self.client.post("/api/feature/params",
                                  json={"feature_id": "base", "params": {"width": 99}})
            print("  user edit mid-job ->", rr.status_code, rr.json().get("error"))
            return json.dumps({"add": {"id": "p2", "op": "disc",
                                       "params": {"radius": 4, "thickness": 3}}})
        return json.dumps({"done": True, "spec": {"n_solids": 3}})


studio.chat_intent = lambda msg: {"action": "add", "description": "two pins"}
studio._make_model = lambda: Meddling(c)
r = c.post("/api/chat", json={"message": "two pins"}).json()
e = studio.STATE["docs"][tid]
print("  reply:", (r.get("reply") or "")[:110])
print("  history depth:", len(e["history"]))
c.post("/api/undo", json={})
print("  after ONE undo — tree:", [f.id for f in e["doc"].features],
      "| base width:", e["doc"].get("base").params.get("width"))
rr = c.post("/api/feature/params", json={"feature_id": "base", "params": {"width": 99}})
print("  edit AFTER the job ->", rr.status_code,
      "| width:", e["doc"].get("base").params.get("width"))
