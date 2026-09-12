"""P5b review ROUND TWO, risk 2: can `_struck_by` go STALE and be believed?

The record is written by `strike` and popped by `unstrike`. But
/api/feature/suppress sets `Feature.suppressed` directly, behind both of
them — no UI button does, but the AI and the MCP can, and the journey
runner's move_misc does. So:

  strike 'base'                      -> record: base took 'round' with it
  suppress base = False              -> base is live again, record untouched
  suppress base = True               -> base is struck again, by another hand
  restore 'base' (the tree's arrow)  -> the STALE record brings 'round' back

which is round one's door 2 again, through a third door.

Run:  C:\\Python314\\python.exe probes/p5b_r2_stale_record.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from document import Document  # noqa: E402


def struck(doc):
    return sorted(f.id for f in doc.features if f.suppressed)


def build():
    d = Document(name="stale")
    d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 6}, [])
    d.add("round", "fillet", {"radius": 2, "edges": "all"}, ["base"])
    d.rebuild()
    return d


def main():
    print("== the stale-record shape ==")
    d = build()
    d.strike("base")
    d.rebuild()
    print(f"  strike('base')            struck={struck(d)}  record={dict(d._struck_by)}")

    d.get("base").suppressed = False          # what /api/feature/suppress does
    d._mark_stale()
    d.rebuild()
    print(f"  suppress base=False       struck={struck(d)}  record={dict(d._struck_by)}")

    d.get("base").suppressed = True
    d._mark_stale()
    d.rebuild()
    print(f"  suppress base=True        struck={struck(d)}  record={dict(d._struck_by)}")

    plan = d.unstrike("base")
    d.rebuild()
    print(f"  restore('base')           struck={struck(d)}  restored={plan.get('restored')}")
    if "round" not in struck(d):
        print("  *** 'round' was never struck by THIS gesture and came back anyway")
    else:
        print("  clean: only 'base' came back")

    print("\n== and the plain case still works (no other hand on the flag) ==")
    d = build()
    d.strike("base")
    d.rebuild()
    plan = d.unstrike("base")
    d.rebuild()
    print(f"  strike + restore          struck={struck(d)}  restored={plan.get('restored')}")


if __name__ == "__main__":
    main()
