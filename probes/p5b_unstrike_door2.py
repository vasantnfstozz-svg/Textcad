"""P5b review, second door into the same defect: unstrike() puts back the
DELETE PLAN, so a dependent the user had struck INDEPENDENTLY earlier also
comes back when its ancestor is restored.

  strike 'fillet1'            (the user turns the rounding off)
  strike 'base'               (its plan sweeps fillet1 up - already struck)
  restore 'base'  (the row's up-arrow)
  -> fillet1 is un-struck too

And the case the fix must NOT break: restoring a cut whose TOOL prism is
struck has to bring the prism back, because a suppressed extrude passes a
SKETCH down and a cut cannot take one.

Run:  C:\\Python314\\python.exe probes/p5b_unstrike_door2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from document import Document  # noqa: E402


def struck(doc):
    return sorted(f.id for f in doc.features if f.suppressed)


def reds(doc):
    return [f"{f.id} ({f.op}): {'; '.join(f.problems)}" for f in doc.features
            if f.status != "ok" and not f.suppressed]


def door2():
    print("== door 2: a dependent struck on purpose comes back with its ancestor ==")
    doc = Document(name="d2")
    doc.add("base", "plate", {"width": 40, "depth": 30, "thickness": 6}, [])
    doc.add("fillet1", "fillet", {"radius": 2, "edges": "all"}, ["base"])
    doc.rebuild()
    doc.strike("fillet1")
    doc.rebuild()
    print(f"  user struck the fillet:      struck={struck(doc)}")
    plan = doc.strike("base")
    doc.rebuild()
    print(f"  then struck the plate:       struck={struck(doc)}  plan deleted={plan['deleted']}")
    plan = doc.unstrike("base")
    doc.rebuild()
    print(f"  restored the plate:          struck={struck(doc)}  plan restored={plan.get('restored')}")
    if "fillet1" not in struck(doc):
        print("  *** the fillet the user turned off is back on")


def tool_prism_must_come_back():
    print("\n== the case the fix must not break: a cut whose tool prism is struck ==")
    doc = Document(name="d3")
    doc.add("plate", "plate", {"width": 40, "depth": 30, "thickness": 6}, [])
    doc.add("sk", "sketch", {"plane": "XY", "offset": 0,
                             "entities": [{"kind": "circle", "mode": "add",
                                           "x": 0, "y": 0, "r": 5}]}, [])
    doc.add("tool", "extrude", {"amount": 20}, ["sk"])
    doc.add("pocket", "cut", {}, ["plate", "tool"])
    doc.rebuild()
    v0 = round(float(doc.result().volume), 3)
    doc.strike("pocket")
    doc.rebuild()
    print(f"  struck the cut:   struck={struck(doc)}")
    doc.unstrike("pocket")
    doc.rebuild()
    print(f"  restored the cut: struck={struck(doc)}  red={reds(doc) or 'none'}")
    v1 = round(float(doc.result().volume), 3)
    print(f"  volume {v0} -> {v1}  ({'same' if v0 == v1 else 'CHANGED'})")


def esp32_restore_the_logo_itself():
    print("\n== and restoring the struck logo itself must still work ==")
    p = ROOT / "tests" / "fixtures" / "esp32-remote.tcad.json"
    doc = Document.from_data(json.loads(p.read_text(encoding="utf-8")))
    doc.rebuild()
    before = round(float(doc.result().volume), 3)
    plan = doc.unstrike("logo_0")
    doc.rebuild()
    print(f"  unstrike('logo_0') restored {plan.get('restored')}")
    print(f"  red={reds(doc) or 'none'}")
    print(f"  volume {before} -> {round(float(doc.result().volume), 3)}")


if __name__ == "__main__":
    door2()
    tool_prism_must_come_back()
    esp32_restore_the_logo_itself()
