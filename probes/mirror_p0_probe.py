"""Mirror — the four P0 "silent wrong geometry" findings of the big P4 review,
each REPRODUCED by measurement before it is fixed (house rule 3: never trust,
always measure).

Run: PYTHONIOENCODING=utf-8 python probes/mirror_p0_probe.py

  §1  A LEGACY copy-only mirror row folds as a DELTA feature, so its "delta"
      is its whole input plus its whole output: mirroring it gouges material
      out of the body somewhere else. It must fold to a BODY seed.
  §2  plan_mirror stamps join:true on every NEW mirror, a seeded one included.
      The op branches on the truthiness of `seed`, so a seed that ever arrives
      empty turns a feature mirror into a whole-body Join at 2x size, silently.
  §3  _body_pattern returns the fused union with NO health gate: a reflection
      tangent to the body is an open shell that is_valid calls fine, handed
      back as a success to MCP / scripts.
  §4  The panel offers the body's mid-planes for a BODY seed, where the
      reflection can never leave the body's own bounding box — on a symmetric
      body it changes nothing at all and still reports "Mirror created".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d

import blocks
import document
import inspector
import pattern
import toolplan


def line(t):
    print(f"\n{'-' * 70}\n{t}\n{'-' * 70}")


# --------------------------------------------------------------- §1 --------
line("§1  a LEGACY copy-only mirror as a seed: the delta is the WHOLE body")

doc = document.Document(name="p0-1")
doc.add("box", "plate", {"width": 40, "depth": 40, "thickness": 10})
# a plane clear of the body, so the copy lands entirely off it — the legacy
# behaviour every saved design uses (`mirror` then `fuse`)
doc.add("copy", "mirror", {"plane": {"origin": (30, 0, 0), "normal": (1, 0, 0)}},
        inputs=["box"])
doc.rebuild()

before_id, after_id = doc.delta_features("copy")
before, after = doc._parts.get(before_id) if before_id else None, doc._parts["copy"]
print(f"delta_features('copy') = {(before_id, after_id)}")
if before is not None:
    removed, added = pattern.delta(before, after)
    rv = float(removed.volume) if removed is not None else 0.0
    av = float(added.volume) if added is not None else 0.0
    print(f"the row's own volume        = {float(after.volume):.1f}")
    print(f"the 'delta' it would repeat = removed {rv:.1f} + added {av:.1f}"
          f"   <-- the whole body twice")
    print("VERDICT: BROKEN — mirroring this row cuts a whole body-sized lump "
          "out of the part")
else:
    print("VERDICT: fixed — it folds to a BODY seed (None, 'copy')")

print("\nthe same row on the user's live design (the review's repro):")
live = "designs/sat-side-panel.tcad.json"
if os.path.exists(live):
    d2 = document.Document.load(live)
    print(f"  delta_features('corner_dimples_diag2') = "
          f"{d2.delta_features('corner_dimples_diag2')}")

print()
print("the SAME class: every op that re-places the whole body")
for op, params in (("rotate", {"axis": "Z", "angle_deg": 30}),
                   ("scale", {"factor": 1.5}),
                   ("mirror", {"plane": {"origin": (30, 0, 0), "normal": (1, 0, 0)}})):
    d = document.Document(name=f"p0-1-{op}")
    d.add("box", "plate", {"width": 40, "depth": 40, "thickness": 10})
    d.add("r", op, params, inputs=["box"])
    d.rebuild()
    bi, ai = d.delta_features("r")
    if bi is None:
        print(f"  {op:8} -> (None, 'r')   a BODY seed (right)")
        continue
    rem, add = pattern.delta(d._parts[bi], d._parts[ai])
    rv = float(rem.volume) if rem is not None else 0.0
    av = float(add.volume) if add is not None else 0.0
    print(f"  {op:8} -> {(bi, ai)}   delta removed {rv:.1f} + added {av:.1f} "
          f"of a {float(d._parts[ai].volume):.1f} mm3 body   <-- WRONG")

# --------------------------------------------------------------- §2 --------
line("§2  a NEW seeded mirror is planned with join:true")

doc = document.Document(name="p0-2")
doc.add("box", "plate", {"width": 60, "depth": 40, "thickness": 12})
doc.add("h", "hole", {"face": "top", "at": (-20, 0), "diameter": 6, "depth": 6},
        inputs=["box"])
doc.rebuild()

plan = toolplan.plan(doc, {"tool": "mirror", "seed_id": "h"})
print(f"plan ok={plan.get('ok')} seed={plan.get('seed')!r} "
      f"params={plan.get('params')}")
if plan.get("params", {}).get("join") and plan.get("seed"):
    print("VERDICT: BROKEN — a FEATURE seed planned as join:true; if the seed "
          "is ever dropped the op silently Joins the whole body")
else:
    print("VERDICT: fixed — join belongs to a body mirror only")

print("\nwhat the op does when the seed goes missing but join stands:")
box = blocks.plate(60, 40, 12)
v0 = float(box.volume)
try:
    out = pattern.mirror(box, plane={"origin": (30, 0, 0), "normal": (1, 0, 0)},
                         seed=None, join=True)
    print(f"  mirror(seed=None, join=True): {v0:.0f} -> {float(out.volume):.0f} "
          f"({len(out.solids())} solids) — a 2x body, no complaint")
except ValueError as e:
    print(f"  refused: {e}")

# --------------------------------------------------------------- §3 --------
line("§3  a body Join tangent to its reflection: no health gate")

# a plate turned 45 deg about Z has a single vertical EDGE at its +x extreme;
# a plane there reflects it onto that edge and nothing else
diamond = blocks.rotate(blocks.plate(30, 30, 10), axis="Z", angle_deg=45)
bb = diamond.bounding_box()
print(f"the turned plate: {float(diamond.volume):.1f} mm3, "
      f"x up to {bb.max.X:.4f}")
tangent = {"origin": (bb.max.X, 0, 0), "normal": (1, 0, 0)}
try:
    out = pattern.mirror(diamond, plane=tangent, seed=None, join=True)
    probs = inspector.health(out, check_valid=False)
    print(f"mirror(join) across that edge -> {len(out.solids())} solid(s), "
          f"{float(out.volume):.1f} mm3")
    print(f"  is_valid = {bool(out.is_valid)}   (it says nothing is wrong)")
    print(f"  inspector.health = {probs if probs else 'OK'}")
    if probs:
        print("VERDICT: BROKEN — this came back as a SUCCESS with "
              f"'{probs[0]}'")
    else:
        print("VERDICT: healthy here — try another tangency")
except ValueError as e:
    print(f"VERDICT: fixed — refused with a sentence:\n  {e}")

# --------------------------------------------------------------- §4 --------
line("§4  a BODY seed offered the body's own mid-planes")

doc = document.Document(name="p0-4")
doc.add("box", "plate", {"width": 40, "depth": 40, "thickness": 12})
doc.rebuild()

plan = toolplan.plan(doc, {"tool": "mirror", "seed_id": "box"})
mids = [a["name"] for a in plan.get("alternatives", [])
        if isinstance(a.get("plane"), dict) and a["plane"].get("mid")]
print(f"seed={plan.get('seed')!r} (a body)   mid-plane choices offered: {mids}")

box = blocks.plate(40, 40, 12)
v0 = float(box.volume)
out = pattern.mirror(box, plane={"mid": "X"}, seed=None, join=True)
print(f"building one of them: {v0:.0f} -> {float(out.volume):.0f} mm3")
if mids and abs(float(out.volume) - v0) < 1e-6:
    print("VERDICT: BROKEN — the panel offers a choice that does nothing and "
          "still says 'Mirror created'")
elif not mids:
    print("VERDICT: fixed — a body seed is not offered its own mid-planes")

print("\nauthor.py's advice for 'model one half':")
import author
for ln in author.AUTHOR_PROMPT.splitlines():
    if "one half" in ln or ("mid" in ln and "mirror" in ln.lower()):
        print(f"  {ln.strip()}")
cat = author.op_catalog()
m = next((e for e in cat if e.get("op") == "mirror"), {})
pl = next((p for p in m.get("params", []) if p.get("name") == "plane"), None)
print()
print(f"what the catalogue tells the AI `mirror.plane` may be: {pl}")
if pl and pl.get("enum"):
    print("VERDICT: BROKEN — the enum hides the face / mid-plane / "
          "{origin, normal} forms the op accepts")
