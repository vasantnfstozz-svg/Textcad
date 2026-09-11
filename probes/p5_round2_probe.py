"""P5 review ROUND TWO — the guards round one added, probed on their own.

R1: the one-writer middleware sits OUTSIDE _never_die (it is registered
    after it, and Starlette's stack puts the last-registered outermost), so
    anything it raises is a bare 500 the UI cannot read. _job_on iterates
    JOBS live while _start_job deletes from it in a request thread.
R2: what a refused POST actually hands the browser.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import studio
from document import Document
from fastapi.testclient import TestClient

studio.JOB_THREADS = False
studio.SESSION_ENABLED = False
studio.STATE["docs"].clear()
studio.STATE["active"] = None
d = Document(name="mine")
d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
tid = studio._new_tab(d)
studio._rebuild_and_mesh()
c = TestClient(studio.app, raise_server_exceptions=False)

print("=" * 70)
print("R1: _job_on raises (the live-dict race) — what does the browser get?")


class Exploding(dict):
    def values(self):
        raise RuntimeError("dictionary changed size during iteration")


real = studio.JOBS
studio.JOBS = Exploding()
try:
    r = c.post("/api/feature/params",
               json={"feature_id": "base", "params": {"width": 41}})
    print("  status:", r.status_code)
    body = r.text[:120].replace("\n", " ")
    print("  body  :", body)
    try:
        r.json()
        readable = True
    except Exception:
        readable = False
    print("  VERDICT:", "readable JSON" if readable and r.status_code != 500
          else "BARE 500 — the UI cannot read it (finding)")
except Exception as ex:
    print("  the request RAISED out of the app:", type(ex).__name__, str(ex)[:70])
    print("  VERDICT: BARE 500 — the UI cannot read it (finding)")
finally:
    studio.JOBS = real

print()
print("=" * 70)
print("R2: a POST refused while a job runs — what the browser is handed")
studio.STATE["docs"][tid]["doc"] = d
studio.JOBS["jX"] = {"id": "jX", "done": False, "tab": tid}
was = d.get("base").params["width"]
try:
    r = c.post("/api/feature/params",
               json={"feature_id": "base", "params": {"width": 42}})
    print("  status:", r.status_code, "| keys:", sorted(r.json()))
    print("  width:", was, "->", d.get("base").params["width"], "(must not move)")
finally:
    studio.JOBS.pop("jX", None)
