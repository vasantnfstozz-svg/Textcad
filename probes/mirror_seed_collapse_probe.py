"""Mirror — the two ways a stored `seed` STOPS RESOLVING, each REPRODUCED by
measurement (house rule 3: never trust, always measure). The P0 of the
/code-review of c4d5961 + 85821be, closed in 072aa95; this is the proof the
regression test in tests/test_mirror_tool.py stands on.

Run: PYTHONIOENCODING=utf-8 python probes/mirror_seed_collapse_probe.py

An EDIT reads `join` from what was SAVED, and a seeded mirror saves join:false
(a feature mirror may never become a whole-body Join at twice the size). So a
row whose stored seed no longer resolves to a feature came back as "no seed,
no join" — the LEGACY COPY form, which REPLACES the body with a detached
reflection and leaves no Join row to undo from.

  §1  The stored seed names a whole BODY.
  §2  The stored seed names a PLACEMENT row (rotate / scale / a legacy
      copy-only mirror). Those fold to a BODY seed — delta_features' own P0,
      probes/mirror_p0_probe.py §1 — so the plan finds no feature where the
      stored params claim one.

Both must come back as a body JOIN. Printed for each: what the tree folds the
seed to, what the row's own rebuild says, what the plan returns, and how much
of the body each form leaves where the body actually is.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pattern
import toolplan
from document import Document

# an explicit plane resolves on ANY body — a rotated one has no axis-aligned
# face, and {"face": "+x"} is refused there (rule 7) before `join` is reached
OFFSET_PLANE = {"origin": [40, 0, 0], "normal": [1, 0, 0]}

CASES = [
    ("§1  a stored seed that names a whole BODY", "hole1", "box1", {"face": "+x"}),
    ("§2  a stored seed that names a PLACEMENT row (rotate)", "rot", "rot", OFFSET_PLANE),
]


def a_doc():
    """an 80 mm plate, a ⌀6 hole, and a rotate row on top of it"""
    d = Document("t")
    d.add("box1", "plate", {"width": 80, "depth": 80, "thickness": 12})
    d.add("hole1", "hole", {"face": "top", "at": [20, 10], "diameter": 6,
                            "through": True, "depth": 1}, inputs=["box1"])
    d.add("rot", "rotate", {"axis": "Z", "angle_deg": 30}, inputs=["hole1"])
    return d


for title, tip, seed, plane in CASES:
    print(f"\n{title}")
    doc = a_doc()
    doc.add("m", "mirror", {"seed": seed, "plane": plane, "join": False}, inputs=[tip])
    doc.rebuild()
    f = doc.get("m")
    print(f"  the tree folds {seed!r} to  {doc.delta_features(seed)}   (before, after)")
    print(f"  the row's rebuild:         {f.status} - {(f.problems or ['-'])[0][:72]}")

    plan = toolplan.plan(doc, {"tool": "mirror", "feature_id": "m"})
    print(f"  the plan for an EDIT:      ok={plan['ok']} seed={plan['seed']!r} "
          f"join={plan['params']['join']!r} ({plan['seed_words']!r})")

    body = doc._parts[tip]
    v0 = float(body.volume)
    copy = pattern.mirror(body, plan["params"]["plane"], seed=None, join=False)
    join = pattern.mirror(body, plan["params"]["plane"], seed=None, join=True)
    print(f"  the body is {v0:.1f} mm3")
    print(f"    the COPY form (join:false): {float((body & copy).volume):8.1f} mm3 of it left "
          f"where the body is, total {float(copy.volume):.1f}")
    print(f"    the JOIN form (join:true):  {float((body & join).volume):8.1f} mm3 of it left "
          f"where the body is, total {float(join.volume):.1f}")

    if plan["params"]["join"] is True:
        print("  VERDICT: fixed - a body JOIN; the part stays where it is")
    else:
        lost = v0 - float((body & copy).volume)
        print(f"  VERDICT: BROKEN - the legacy COPY: {lost:.1f} mm3 of the part silently "
              f"relocated, with no Join row to undo from")
