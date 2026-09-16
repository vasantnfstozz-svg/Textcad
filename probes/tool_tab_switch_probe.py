"""Section 11 probe: what an OPEN tool session writes after the document tab
changes under it.

The tool framework keeps `st.featureId` (and the parked rollback bar) for the
life of its panel and never listens for 'doc-updated'; every write it makes
(`/api/feature/params`, `/api/feature/add`, `/api/rollback`) is addressed to
the ACTIVE tab.  doctabs.js switches tabs with no modalGuard, so the question
is simply: does a write meant for design A land on design B?
"""
import os
import sys

os.environ.setdefault("TEXTCAD_NO_BROWSER", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient            # noqa: E402

import studio                                        # noqa: E402

c = TestClient(studio.app)


def feat(doc, fid):
    return next((f for f in doc["features"] if f["id"] == fid), None)


def make(name, thickness):
    c.post("/api/new", json={"name": name})
    c.post("/api/feature/add", json={
        "id": "b", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
    c.post("/api/feature/add", json={
        "id": "s1", "op": "sketch_on_face",
        "params": {"face": "top", "entities": [{"kind": "circle", "r": 6}]},
        "inputs": ["b"]})
    # both designs get an `extrude1` — uid() hands out the same names everywhere
    c.post("/api/feature/add", json={
        "id": "extrude1", "op": "extrude",
        "params": {"amount": thickness}, "inputs": ["s1"]})
    return c.get("/api/doc").json()


a = make("tab-a", 5)
tabs = a["tabs"]
id_a = a["active_tab"]
b = make("tab-b", 9)
id_b = b["active_tab"]
print(f"design A tab {id_a}: extrude1 amount = "
      f"{feat(a, 'extrude1')['params']['amount']}, volume = "
      f"{feat(a, 'extrude1')['volume']:.3f}")
print(f"design B tab {id_b}: extrude1 amount = "
      f"{feat(b, 'extrude1')['params']['amount']}, volume = "
      f"{feat(b, 'extrude1')['volume']:.3f}")

# --- the user opens Edit on design A's extrude1 (the panel remembers 'extrude1'
#     and parks the rollback bar), then clicks design B's tab, then presses OK
c.post("/api/tabs/switch", json={"id": id_a})
c.post("/api/rollback", json={"feature_id": "extrude1"})     # isolateFor(A)
print("\n-- tool panel open on A.extrude1, rollback bar parked on A --")

c.post("/api/tabs/switch", json={"id": id_b})                # doctabs.js: no guard
print("-- user clicks design B's tab (nothing in the panel notices) --")

# OK / a drag / Cancel: all of them go through /api/feature/params
r = c.post("/api/feature/params",
           json={"feature_id": "extrude1", "params": {"amount": 30}}).json()
print("\nAfter the panel's next write (amount 30):")
print(f"  ACTIVE tab is B; B.extrude1 amount = "
      f"{feat(r, 'extrude1')['params']['amount']}, volume = "
      f"{feat(r, 'extrude1')['volume']:.3f}")
back_a = c.post("/api/tabs/switch", json={"id": id_a}).json()
print(f"  A.extrude1 amount = {feat(back_a, 'extrude1')['params']['amount']}"
      f"  (untouched — the edit went to the wrong design)")
print(f"  A's rollback bar is still parked: rollback_to = "
      f"{back_a.get('rollback_to')!r}")

# --- and a NEW session's first create() adds a feature to whichever tab is active
c.post("/api/tabs/switch", json={"id": id_b})
r2 = c.post("/api/feature/add", json={
    "id": "extrude2", "op": "extrude", "params": {"amount": 4},
    "inputs": ["s1"]}).json()
print(f"\nA new session's create() while B is active: B now has "
      f"{[f['id'] for f in r2['features']]}")
