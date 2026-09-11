"""P5 review ROUND THREE — round two's own code, and the create tab.

T1: /api/tool/plan is on the one-writer allowlist, and toolplan.plan reads
    doc._parts — which rebuild() CLEARS at the start of every step. What does
    a plan see when it lands between two AI steps?
T2: a "create" job that produces nothing still opens (and keeps) a tab.
T3: the create path opens a tab without the MAX_TABS check /api/new makes.
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
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def reset():
    studio.JOB_THREADS = False
    studio.SESSION_ENABLED = False
    studio.JOBS.clear()
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    return TestClient(studio.app)


print("=" * 70)
print("T1: a plan landing while the job's rebuild has cleared _parts")
c = reset()
d = Document(name="mine")
d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
tid = studio._new_tab(d)
studio._rebuild_and_mesh()
print("  allowlist:", sorted(studio._JOB_OPEN_POSTS))
studio.JOBS["jX"] = {"id": "jX", "done": False, "tab": tid}
r = c.post("/api/tool/plan", json={"tool": "fillet", "feature_id": "base"})
print("  plan during a job -> status", r.status_code)
d._parts.clear()                      # exactly what rebuild() does, step by step
r2 = c.post("/api/tool/plan", json={"tool": "fillet", "feature_id": "base"})
body = r2.json()
print("  with _parts cleared mid-step ->", {k: body.get(k) for k in ("ok", "error")})
studio.JOBS.clear()

print()
print("=" * 70)
print("T2: a create job that produced NOTHING — what is left behind?")
c = reset()
d = Document(name="mine")
d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
studio._new_tab(d)
studio._rebuild_and_mesh()
studio.chat_intent = lambda m: {"action": "create", "description": "a ring"}
bad = {"add": {"id": "x", "op": "torus", "params": {}}}
studio._make_model = lambda: Scripted(bad, bad, bad)
r = c.post("/api/chat", json={"message": "design a ring"}).json()
print("  reply:", (r.get("reply") or "")[:100])
tabs = [(t["id"], t["name"]) for t in r["tabs"]]
print("  tabs after:", tabs)
left = studio.STATE["docs"].get(r.get("new_tab"))
print("  the new tab holds", len(left["doc"].features) if left else "-", "features")
print("  VERDICT:", "an EMPTY 'designing…' tab is left behind (finding)"
      if left and not left["doc"].features else "cleaned up")

print()
print("=" * 70)
print("T3: does the create path honour MAX_TABS the way /api/new does?")
c = reset()
studio._new_tab(Document(name="mine"))
studio._rebuild_and_mesh()
studio.chat_intent = lambda m: {"action": "create", "description": "a ring"}
DISC = {"add": {"id": "body", "op": "disc", "params": {"radius": 20,
                                                       "thickness": 4}}}
DONE = {"done": True, "spec": {"n_solids": 1}}
last = None
for i in range(studio.MAX_TABS + 3):
    studio._make_model = lambda: Scripted(DISC, DONE)
    last = c.post("/api/chat", json={"message": "design a ring"}).json()
print("  the reply once full:", (last.get("reply") or "")[:80])
n = len(studio.STATE["docs"])
print(f"  MAX_TABS={studio.MAX_TABS}; open tabs after {studio.MAX_TABS + 3} "
      f"AI creates: {n}")
print("  /api/new says:", c.post("/api/new", json={"name": "x"}).json().get("error"))
print("  VERDICT:", "the AI path walks past MAX_TABS (finding)"
      if n > studio.MAX_TABS else "bounded")
