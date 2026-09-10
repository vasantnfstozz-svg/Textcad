"""Section 3 FIX-PASS review probe (2026-09-10, range 4b0ca40..f63ba5a).

Measures three suspected gaps in the section-3 fixes themselves:

  A  /api/save's "content is identical" escape hatch binds a SECOND tab to a
     file another tab already owns -- the very state the F1 test forbids.
  B  History.can_repair() says yes on a SCHEMA-mismatched index that _load
     deliberately refused to touch, so the new panel button overwrites it.
  C  can_repair() says yes on a stray v*.json.gz that is not v<N>, and
     repair() then dies with an AttributeError whose text reaches the user.
  D  the guard checks the design FILE only, so a design whose .tcad.json was
     deleted by hand leaves its version tree open to the same graft.

Run:  C:\Python314\python.exe probes/version_review_probe.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(tempfile.mkdtemp(prefix="probe-hist-"))
os.environ["TEXTCAD_HISTORY_ROOT"] = str(ROOT)

from fastapi.testclient import TestClient   # noqa: E402
import studio                               # noqa: E402
from history import History, content_hash   # noqa: E402

TMP = "_probe-sec3"
DP = studio.DESIGNS / f"{TMP}.tcad.json"


def fresh_client():
    DP.unlink(missing_ok=True)
    import shutil
    shutil.rmtree(ROOT, ignore_errors=True)
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


def hist():
    return History.for_design(studio._history_root(), TMP)


def probe_a():
    print("\n=== A. the equal-content escape hatch binds a SECOND tab ===")
    c = fresh_client()
    studio._doc().name = TMP
    r = c.post("/api/save").json()
    print(f"tab A saved: {r['saved']} {r.get('version')}")
    a_tid = studio.STATE["active"]

    # tab B: a fresh tab holding EXACTLY what the file holds (a sample tab
    # writing itself into the library is the case the comment names)
    c.post("/api/new", json={"name": TMP})
    b_tid = studio.STATE["active"]
    studio.STATE["docs"][b_tid]["doc"] = studio.Document.load(str(DP))
    r = c.post("/api/save").json()
    print(f"tab B save allowed: {not r.get('error')}")
    srcs = [e.get("source") for e in studio.STATE["docs"].values()]
    n = srcs.count(f"file:{TMP}")
    print(f"tabs bound to file:{TMP} -> {n}   (the F1 test asserts == 1)")

    # now the two tabs diverge
    studio.STATE["active"] = a_tid
    c.post("/api/edit", json={"feature_id": "bore", "param": "radius",
                              "value": 11})
    va = c.post("/api/save").json().get("version")
    a_file = json.loads(DP.read_text(encoding="utf-8"))
    print(f"tab A pushed {va}; file bore.radius = "
          f"{[f for f in a_file['features'] if f['id'] == 'bore'][0]['params']['radius']}")

    studio.STATE["active"] = b_tid
    c.post("/api/edit", json={"feature_id": "bore", "param": "radius",
                              "value": 44})
    rb = c.post("/api/save").json()
    vb = rb.get("version")
    b_file = json.loads(DP.read_text(encoding="utf-8"))
    print(f"tab B save allowed: {not rb.get('error')} -> {vb}")
    rad = [f for f in b_file['features'] if f['id'] == 'bore'][0]['params']['radius']
    print(f"file bore.radius is now {rad} (11 = tab A's save survived, "
          f"44 = it was overwritten with no warning)")
    h = hist()
    tree = {v.id: v.parent for v in h.versions()}
    print(f"version parents: {tree}")
    print(f"A: {'PASS' if n == 1 and rad == 11 and vb is None else 'FAIL'} "
          f"— one binding, tab A's file intact, no version grafted")
    return n


def probe_b():
    print("\n=== B. a SCHEMA-mismatched index: refused by _load, offered by "
          "can_repair ===")
    c = fresh_client()
    studio._doc().name = TMP
    c.post("/api/save")
    c.post("/api/edit", json={"feature_id": "bore", "param": "radius",
                              "value": 12})
    c.post("/api/save")
    h = hist()
    idx = h.path / "index.json"
    before = json.loads(idx.read_text(encoding="utf-8"))
    # real labels, a real branch, a star -- the information repair() destroys
    h.relabel("v2", "the one that machines")
    h.star("v2")
    before = json.loads(idx.read_text(encoding="utf-8"))
    print(f"healthy: design_id={before['design_id']} starred={before['starred']} "
          f"labels={[v['label'] for v in before['versions']]}")

    # a NEWER build wrote this index (schema 2). _load: 'Refusing to touch it
    # rather than risk mangling it.'
    before["schema"] = 2
    idx.write_text(json.dumps(before, indent=2), encoding="utf-8")
    h2 = hist()
    print(f"exists()      = {h2.exists()}")
    print(f"problems()    = {h2.problems()}")
    print(f"can_repair()  = {h2.can_repair()}   <-- the panel shows the button")

    d = c.get("/api/versions").json()
    print(f"/api/versions can_repair = {d.get('can_repair')}")
    r = c.post("/api/versions/repair").json()
    print(f"POST /api/versions/repair -> {r}")
    try:                             # what the button does, measured directly
        print(f"History.repair() notes -> {hist().repair()}")
    except Exception as e:
        print(f"History.repair() refused: {type(e).__name__}: {e}")
    after = json.loads(idx.read_text(encoding="utf-8"))
    print(f"AFTER: schema={after['schema']} design_id={after['design_id']} "
          f"starred={after['starred']} labels={[v['label'] for v in after['versions']]}")
    kept = (after == before)
    print(f"B: {'PASS' if kept else 'FAIL'} — the schema-2 index is "
          f"{'untouched' if kept else 'GONE'}")
    return r


def probe_c():
    print("\n=== C. a stray v*.json.gz that is not v<N> ===")
    c = fresh_client()
    studio._doc().name = TMP
    c.post("/api/save")
    h = hist()
    (h.path / "index.json").unlink()
    (h.path / "v.json.gz").write_bytes(b"not gzip")
    h2 = hist()
    print(f"can_repair() = {h2.can_repair()}   <-- the button is offered")
    try:                             # the endpoint FIRST, on the broken state
        r = c.post("/api/versions/repair")
        body = r.json()
        print(f"POST -> {r.status_code} {body}")
        ok = not body.get("error") and body.get("recovered") == 1
    except Exception as e:
        print(f"POST raised {type(e).__name__}: {e}  (not a sentence)")
        ok = False
    left = [p.name for p in h2.path.glob("*.json.gz")]
    print(f"C: {'PASS' if ok else 'FAIL'} — the real snapshot was rebuilt and "
          f"the stray file left alone ({left})")


def probe_d():
    print("\n=== D. the FILE is gone but the version tree is not ===")
    c = fresh_client()
    studio._doc().name = TMP
    c.post("/api/save")
    c.post("/api/edit", json={"feature_id": "bore", "param": "radius",
                              "value": 11})
    c.post("/api/save")
    h = hist()
    print(f"design A: {[(v.id, v.parent, v.features) for v in h.versions()]} "
          f"design_id={h.design_id}")
    DP.unlink()                       # the user deletes it in Explorer
    print(f"file deleted; index still there: "
          f"{(h.path / 'index.json').exists()}")
    # ...and closes the tab, so nothing but the version tree is left. Door 1
    # must not be the thing that catches this; door 3 must.
    c.post("/api/tabs/close", json={"id": studio.STATE["active"]})
    print(f"tab closed; tabs bound to file:{TMP} -> "
          f"{sum(1 for e in studio.STATE['docs'].values() if e.get('source') == f'file:{TMP}')}")
    c.post("/api/new", json={"name": TMP})
    c.post("/api/feature/add", json={"id": "other", "op": "disc",
                                     "params": {"radius": 3, "thickness": 1},
                                     "inputs": []})
    r = c.post("/api/save").json()
    print(f"unrelated 1-feature design's save allowed: {not r.get('error')}")
    if r.get("error"):
        print(f"  refusal: {r['error']}")
    h2 = hist()
    print(f"tree now: {[(v.id, v.parent, v.features, v.label) for v in h2.versions()]}")


if __name__ == "__main__":
    try:
        probe_a()
        probe_b()
        probe_c()
        probe_d()
    finally:
        DP.unlink(missing_ok=True)
        print(f"\n(history root was {ROOT})")
