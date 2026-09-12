"""P5b review probe: what the random-journey oracles do and do not see.

1. `unhandled()` decides "a kernel exception leaked" from the wording
   `_never_die` writes (`f"{type(e).__name__}: {e}"`). Which class names does
   it actually recognise?
2. A leak staged through the REAL barrier: does Journey.call raise Bug?
3. The two round-trips move_misc plays with no oracle at all: rename there and
   back, suppress and back. Do they really land on the same document?
4. The dry run in move_remove is sent with mutating=True but nothing compares
   the document across it.

Run:  C:\\Python314\\python.exe probes/p5b_oracle_gaps.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import journeys  # noqa: E402

NAMES = [
    # what _never_die writes for the OCCT families build123d raises
    "Standard_Failure: There are no suitable edges for chamfer or fillet",
    "Standard_ConstructionError: BRep_API: command not done",
    "Standard_DomainError: ",
    "StdFail_NotDone: BRep_API: command not done",
    "StdFail_Undefined: ",
    "StdFail_InfiniteSolution: ",
    "StdFail_UndefinedDerivative: ",
    # python
    "KeyError: 'face'",
    "TypeError: unsupported operand",
    "StopIteration: ",
    "RecursionError: maximum recursion depth exceeded",
    # sentences the product means to say
    "the radius must be smaller than half the wall",
    "Extrude needs a sketch profile or a picked flat face",
]


def part1_classifier():
    print("== 1. unhandled() against what _never_die writes ==")
    for n in NAMES:
        print(f"  {'FLAGGED' if journeys.unhandled(n) else 'MISSED ':7s}  {n[:70]}")
    print()


def part2_staged_leak():
    """Make a real route leak StdFail_NotDone and ask the runner about it."""
    print("== 2. a real leak through _never_die: does the journey see it? ==")
    from OCP.StdFail import StdFail_NotDone

    j = journeys.Journey("empty", None, seed=1, steps=0, verbose=False)
    j.run()
    import document

    orig = document.Document.rebuild

    def boom(self, *a, **k):
        raise StdFail_NotDone("BRep_API: command not done")

    document.Document.rebuild = boom
    try:
        resp = j.call("add", "POST", "/api/feature/add",
                      {"id": "leak", "op": "plate",
                       "params": {"width": 20, "depth": 10, "thickness": 4}, "inputs": []})
        print(f"  no Bug raised. the server answered: {resp.get('error')!r}")
        print("  -> the runner logged it as the product working")
    except journeys.Bug as b:
        print(f"  Bug raised: {b.kind}: {b.detail[:80]}")
    finally:
        document.Document.rebuild = orig
    print()


def part3_roundtrips(fixture: str = "pump-impeller"):
    """move_misc renames a feature and back, suppresses and un-suppresses, and
    checks NOTHING. Do those two round-trips really land where they started?"""
    print(f"== 3. move_misc's unchecked round-trips on {fixture} ==")
    path = dict(journeys.sources())[fixture]
    j = journeys.Journey(fixture, path, seed=1, steps=0, verbose=False)
    j.run()
    bad = 0
    for f in list(j.doc.features):
        fid = f.id
        before, vols = j.data(), j.volumes()
        r1 = j.client.post("/api/feature/rename", json={"feature_id": fid, "name": fid + "_r"})
        if (r1.json() or {}).get("error"):
            continue
        j.client.post("/api/feature/rename", json={"feature_id": fid + "_r", "name": fid})
        if j.data() != before:
            bad += 1
            d0 = {x["id"]: x for x in before["features"]}
            d1 = {x["id"]: x for x in j.data()["features"]}
            print(f"  RENAME drift on '{fid}': ids {list(d0) != list(d1)}, "
                  f"params differ for {[k for k in d0 if k in d1 and d0[k] != d1[k]]}")
        if j.volumes() != vols:
            bad += 1
            print(f"  RENAME volume drift on '{fid}': {vols} -> {j.volumes()}")
        before, vols = j.data(), j.volumes()
        j.client.post("/api/feature/suppress", json={"feature_id": fid, "suppressed": True})
        j.client.post("/api/feature/suppress", json={"feature_id": fid, "suppressed": False})
        if j.data() != before:
            bad += 1
            print(f"  SUPPRESS drift on '{fid}'")
        if j.volumes() != vols:
            bad += 1
            print(f"  SUPPRESS volume drift on '{fid}': {vols} -> {j.volumes()}")
    print(f"  {len(j.doc.features)} features, {bad} drift(s)")
    print()


def part4_dry_run():
    """A dry run that wrote would be silent data loss with no undo entry.
    Stage one and ask the runner."""
    print("== 4. a dry run that changes the document: does the journey see it? ==")
    j = journeys.Journey("empty", None, seed=1, steps=0, verbose=False)
    j.run()
    j.call("add", "POST", "/api/feature/add",
           {"id": "b1", "op": "plate", "params": {"width": 20, "depth": 10, "thickness": 4},
            "inputs": []})
    j.call("add", "POST", "/api/feature/add",
           {"id": "b2", "op": "disc", "params": {"radius": 8, "thickness": 3}, "inputs": []})
    import document

    orig = document.Document.remove_plan

    def sneaky(self, fid, mode="auto"):
        plan = orig(self, fid, mode)
        self.features[0].params["width"] = 999.0     # a dry run that wrote
        return plan

    document.Document.remove_plan = sneaky
    try:
        before = j.data()
        j.call("remove-plan", "POST", "/api/feature/remove",
               {"feature_id": "b2", "mode": "auto", "dry_run": True}, mutating=True)
        after = j.data()
        print(f"  no Bug raised. width before={before['features'][0]['params']['width']} "
              f"after={after['features'][0]['params']['width']}")
        print("  -> a dry run that rewrote the design passed the checks")
    except journeys.Bug as b:
        print(f"  Bug raised: {b.kind}: {b.detail[:90]}")
    finally:
        document.Document.remove_plan = orig
    print()


if __name__ == "__main__":
    part1_classifier()
    part2_staged_leak()
    part3_roundtrips("pump-impeller")
    part4_dry_run()
    print(json.dumps({"done": True}))
