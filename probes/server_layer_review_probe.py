"""Section 12 (server layer) review probe - measurements, not opinions.

Run:  C:\\Python314\\python.exe probes/server_layer_review_probe.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      tempfile.mkdtemp(prefix="textcad-probe-"))

from fastapi.testclient import TestClient      # noqa: E402

import studio                                   # noqa: E402
from document import Document                   # noqa: E402


def fresh():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


print("=" * 70)
print("1. /api/export - the STATUS of a refusal")
c = fresh()
doc = studio._doc()
doc.add("plate2", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
doc.features[-1].status = "failed"
doc.features[-1].problems = ["deliberately broken for the probe"]
doc._parts["plate2"] = None
r = c.post("/api/export")
print("   status:", r.status_code, " body keys:", sorted(r.json()))
print("   error :", str(r.json().get("error"))[:110])

print("=" * 70)
print("2. the file /api/export writes vs the file /api/save writes")
# NEVER name a probe design after one the user owns, and never delete a file
# this probe did not create: the first run of this probe named itself "cam
# cover plaque", had its save REFUSED (that design is in the library), and
# then deleted designs/cam-cover-plaque.tcad.json in its cleanup. Restored
# from HEAD; the lesson is here so it cannot happen again.
c = fresh()
studio._doc().name = "_probe export name"
before = {p.name for p in studio.DESIGNS.iterdir()}
save = c.post("/api/save").json()
exp = c.post("/api/export").json()
print("   saved as :", save.get("saved"))
print("   exported :", Path(exp.get("path", "")).name)
print("   the MCP (_safe_name) would write: _probe-export-name.step")
for p in studio.DESIGNS.iterdir():
    if p.name not in before:
        p.unlink()

print("=" * 70)
print("3. does /api/export hold _KERNEL_LOCK while it rebuilds?")
c = fresh()
seen = []
real = Document.rebuild


def spy(self, *a, **k):
    seen.append(studio._KERNEL_LOCK._is_owned())
    return real(self, *a, **k)


Document.rebuild = spy
c.post("/api/export")
Document.rebuild = real
print("   rebuild() calls inside /api/export:", len(seen),
      " lock held each time:", seen)
seen.clear()
Document.rebuild = spy
c.post("/api/edit", json={"feature_id": "hub", "param": "radius", "value": 11})
Document.rebuild = real
print("   for comparison, /api/edit:", len(seen), "call(s), held:", seen)
(studio.DESIGNS / "flange-100.step").unlink(missing_ok=True)

print("=" * 70)
print("4. how many tabs can be opened, and what survives a restart")
c = fresh()
studio.STATE["docs"].clear()
studio.STATE["active"] = None
names = []
for i in range(14):
    n = f"_probe-tabs-{i}"
    d = studio.sample_flange()
    d.name = n
    d.save(str(studio.DESIGNS / f"{n}.tcad.json"))
    names.append(n)
    c.post(f"/api/open/{n}")
print("   tabs after opening 14 library designs:",
      len(c.get("/api/tabs").json()["tabs"]))
print("   MAX_TABS =", studio.MAX_TABS,
      " /api/new at this point:",
      c.post("/api/new", json={"name": "x"}).json().get("error"))
sp = Path(__file__).parent / "_probe-session.json"
old_path, old_on = studio.SESSION_PATH, studio.SESSION_ENABLED
studio.SESSION_PATH = sp
studio._persist_session()
before = len(studio.STATE["docs"])
studio.STATE["docs"].clear()
studio.STATE["active"] = None
back = studio._restore_session(rebuild=False)
print(f"   persisted {before} tabs -> restored {back}")
studio.SESSION_PATH, studio.SESSION_ENABLED = old_path, old_on
sp.unlink(missing_ok=True)
for n in names:
    (studio.DESIGNS / f"{n}.tcad.json").unlink(missing_ok=True)

print("=" * 70)
print("5. statuses of the other refusals in this section")
c = fresh()
for url, body in (("/api/sample/nope", None),
                  ("/api/tabs/switch", {"id": "t999"}),
                  ("/api/tabs/close", {"id": "t999"})):
    r = c.post(url, json=body) if body else c.post(url)
    print(f"   {url:22s} -> {r.status_code}  {str(r.json().get('error'))[:48]}")

print("=" * 70)
print("6. an unhandled endpoint exception, and a traversal attempt")
c = fresh()
r = c.get("/api/design-preview/..%2F..%2Fstudio")
print("   traversal attempt on design-preview ->", r.status_code)


@studio.app.get("/api/_probe_boom")
def _boom():
    raise RuntimeError("Standard_ConstructionError: kernel says no")


c = fresh()
r = c.get("/api/_probe_boom")
print("   an endpoint that raises ->", r.status_code, json.dumps(r.json())[:150])
