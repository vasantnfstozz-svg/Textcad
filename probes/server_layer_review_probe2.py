"""Section 12 (server layer) review probe, part 2.

Run:  C:\\Python314\\python.exe probes/server_layer_review_probe2.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      tempfile.mkdtemp(prefix="textcad-probe-"))

from fastapi.testclient import TestClient      # noqa: E402

import studio                                   # noqa: E402
import blocks                                   # noqa: E402
from document import Document                   # noqa: E402


def fresh():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


print("=" * 70)
print("A. /api/spec with values of the wrong TYPE")
for spec in ({"volume": "big"}, {"size": 5}, {"holes": "six"},
             {"volume": [1, 2]}, {"tol": "loose"}):
    c = fresh()
    r = c.post("/api/spec", json={"spec": spec})
    d = r.json()
    print(f"   {str(spec):24s} -> {r.status_code} ok={d.get('ok')} "
          f"checked={d.get('spec_checked')} err={str(d.get('error'))[:40]} "
          f"problems={str(d.get('spec_problems'))[:70]}")
    # and does it survive a round trip through the file?
    if not d.get("error"):
        again = c.get("/api/doc").json()
        print(f"      stored spec = {again.get('spec')}")

print("=" * 70)
print("B. the ACTIVE tab, and an UNSAVED one, past MAX_TABS")
c = fresh()
studio.STATE["docs"].clear()
studio.STATE["active"] = None
names = []
for i in range(12):
    n = f"_probe-b-{i}"
    d = studio.sample_flange()
    d.name = n
    d.save(str(studio.DESIGNS / f"{n}.tcad.json"))
    names.append(n)
    c.post(f"/api/open/{n}")
# tab 13: the user's own scratch design, never saved, with real work in it
scratch = Document(name="my new bracket")
scratch.add("base", "plate", {"width": 60, "depth": 40, "thickness": 8}, [])
tid = studio._new_tab(scratch)
studio._rebuild_and_mesh()
print("   tabs:", len(studio.STATE["docs"]), " active:", studio.STATE["active"],
      "=", studio._doc().name,
      " dirty:", studio._dirty(studio.STATE["docs"][tid]))
sp = Path(__file__).parent / "_probe-session2.json"
old = studio.SESSION_PATH
studio.SESSION_PATH = sp
studio._persist_session()
studio.STATE["docs"].clear()
studio.STATE["active"] = None
back = studio._restore_session(rebuild=False)
print(f"   restored {back} tabs; is the scratch design back? ",
      any(e["doc"].name == "my new bracket"
          for e in studio.STATE["docs"].values()))
print("   names back:", [e["doc"].name for e in studio.STATE["docs"].values()])
studio.SESSION_PATH = old
sp.unlink(missing_ok=True)
for n in names:
    (studio.DESIGNS / f"{n}.tcad.json").unlink(missing_ok=True)

print("=" * 70)
print("C. what /api/export does to OCCT, and under which lock")
c = fresh()
held = []
real_step = studio.b3d.export_step
real_measure = studio.inspector.measure


def spy_step(shape, path, *a, **k):
    held.append(("export_step", studio._KERNEL_LOCK._is_owned()))
    return real_step(shape, path, *a, **k)


def spy_measure(x, *a, **k):
    held.append(("measure", studio._KERNEL_LOCK._is_owned()))
    return real_measure(x, *a, **k)


studio.b3d.export_step = spy_step
studio.inspector.measure = spy_measure
# park the rollback bar, the way an open editor does
studio._doc().rollback = studio._doc().features[-1].id
real_rebuild = Document.rebuild


def spy_rebuild(self, *a, **k):
    held.append(("rebuild", studio._KERNEL_LOCK._is_owned()))
    return real_rebuild(self, *a, **k)


Document.rebuild = spy_rebuild
c.post("/api/export")
Document.rebuild = real_rebuild
studio.b3d.export_step = real_step
studio.inspector.measure = real_measure
print("   OCCT calls made by /api/export, and whether the kernel lock was held:")
for name, ok in held:
    print(f"      {name:12s} lock held: {ok}")
(studio.DESIGNS / "flange-100.step").unlink(missing_ok=True)

print("=" * 70)
print("D. export over ANOTHER design's .step (save refuses this; export?)")
c = fresh()
a = studio._doc()
a.name = "_probe-collide"
sv = c.post("/api/save").json()
print("   save A ->", {k: sv[k] for k in ("saved",) if k in sv} or sv.get("error"))
ex = c.post("/api/export").json()
first = Path(ex["path"])
size_a = first.stat().st_size if first.exists() else None
vol_a = ex.get("volume")
# a SECOND, different design that happens to carry the same name
c.post("/api/new", json={"name": "_probe-collide"})
b = studio._doc()
b.add("base", "plate", {"width": 10, "depth": 10, "thickness": 2}, [])
studio._rebuild_and_mesh()
sv2 = c.post("/api/save").json()
print("   save B ->", sv2.get("saved") or "REFUSED: "
      + str(sv2.get("error"))[:70])
ex2 = c.post("/api/export").json()
print("   export B ->", ex2.get("path"), " volume:", ex2.get("volume"))
print(f"   A's exported volume was {vol_a} ({size_a} bytes); "
      f"the file now holds {ex2.get('volume')}")
for p in (first, studio.DESIGNS / "_probe-collide.tcad.json"):
    if p.exists():
        p.unlink()

print("=" * 70)
print("E. the crash note: how long does /api/doc keep saying it?")
c = fresh()
studio.RECOVERY = {"code": "0xC0000005", "startup": False, "unbuilt": False,
                   "request": {"path": "/api/edit"}, "at": 1.0}
print("   /api/doc recovery, with at=1970:", c.get("/api/doc").json()["recovery"])
print("   arrival, for comparison (TTL", studio.ARRIVAL_TTL, "s):",
      studio._arrival_json())
studio.RECOVERY = None
print("   is there an ack route for recovery?",
      any("recovery" in r.path for r in studio.app.routes))
print("   blocks loaded:", bool(blocks.EXPORTS))
