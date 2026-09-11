"""P5 review probe — a job THREAD that dies: does /api/chat/job ever say done?
This is the road the browser's followJob() polls; it has no timeout, and an
'add' job holds the busy overlay while it polls."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import time
import studio
from document import Document
from fastapi.testclient import TestClient


class Scripted:
    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]

    def generate(self, messages):
        assert self.replies, "asked for more steps than scripted"
        return self.replies.pop(0)


studio.JOB_THREADS = True            # PRODUCTION: the job runs in a thread
studio.SESSION_ENABLED = False
studio.STATE["docs"].clear()
studio.STATE["active"] = None
c = TestClient(studio.app)
d = Document(name="mine")
d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
tid = studio._new_tab(d)
studio._rebuild_and_mesh()
studio.chat_intent = lambda m: {"action": "add", "description": "a pin"}
studio._make_model = lambda: Scripted(
    {"add": {"id": "p", "op": "disc", "params": {"radius": 3, "thickness": 3}}},
    {"done": True, "spec": {"n_solids": 2}})
real = studio._pending
studio._pending = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
try:
    r = c.post("/api/chat", json={"message": "a pin"}).json()
    jid = r["job"]
    print("  job:", jid, "| job_done at POST:", r["job_done"])
    for i in range(12):                     # 12 * 0.25 s: the thread is long dead
        time.sleep(0.25)
        s = c.get(f"/api/chat/job/{jid}").json()
        if s["done"]:
            print(f"  finished after {i} polls:", s["reply"][:80])
            break
    else:
        print("  STILL done=False after 3 s — the browser polls for ever and the")
        print("  busy overlay never clears (finding)")
        print("  log so far:", s["log"])
finally:
    studio._pending = real
