"""Section 13 ROUND THREE, part 2 — the key's id half, and the MCP digest.

Part 1 (probes/s13_round3_probe.py) showed the lint key carries the feature
id for every rule but `blob`. This part attacks the two ways an id can be
made to COLLIDE with a baseline entry, and then measures `_digest`'s
stability across the loop the doorbell exists for.

Run:  C:\\Python314\\python.exe probes/s13_round3_probe2.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import author                                                    # noqa: E402
from document import Document                                    # noqa: E402


class Scripted:
    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r)
                        for r in replies]

    def generate(self, messages):
        if not self.replies:
            return json.dumps({"done": True})
        return self.replies.pop(0)


def run(label, doc, *replies, max_fails=1):
    return author.author_steps(doc, label, Scripted(*replies),
                               max_fails=max_fails)


def head(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


def _base(name="hand-built"):
    d = Document(name=name)
    d.add("base_sketch", "sketch",
          {"plane": "XY", "offset": 0,
           "entities": [{"kind": "rectangle", "w": 60, "h": 40}]})
    d.add("base", "extrude", {"amount": 10}, inputs=["base_sketch"])
    return d


ENTS = [{"kind": "circle", "r": 1, "x": -25 + i * 4, "y": 0} for i in range(11)]

# ---------------------------------------------- 1. cram, op "sketch" this time
head("1. THE AI'S OWN 11-ENTITY `sketch` WHILE THE USER ALREADY CRAMS ONE")
doc = Document(name="hand-built")
doc.add("art_sketch", "sketch", {"plane": "XY", "offset": 0, "entities": ENTS})
doc.add("art", "extrude", {"amount": 3}, inputs=["art_sketch"])
doc.add("pad_sketch", "sketch", {"plane": "XY", "offset": 0,
                                 "entities": [{"kind": "rectangle",
                                               "w": 60, "h": 40}]})
doc.add("pad", "extrude", {"amount": 2}, inputs=["pad_sketch"])
doc.rebuild()
print("  baseline:", list(author.lint_baseline(doc.features)))
ok, tr = run("more art", doc,
             {"add": {"id": "ai_art_sketch", "op": "sketch",
                      "params": {"plane": "XY", "offset": 0,
                                 "entities": [dict(e, y=14) for e in ENTS]}}},
             {"done": True})
print(f"  AI's OWN 11-entity `sketch`: finished={ok}")
print(f"    {tr[0][:150]}")

# ------------------------------------------ 2. can a baseline id be re-used? --
head("2. CAN THE AI GET ITS OWN FEATURE UNDER A BASELINE KEY?")
doc = _base()
doc.add("recess_sketch", "sketch", {"plane": "XY", "offset": 10.0,
                                    "entities": [{"kind": "circle", "r": 5}]})
doc.add("recess_tool", "extrude", {"amount": -3}, inputs=["recess_sketch"])
doc.add("recess", "cut", {}, inputs=["base", "recess_tool"])
doc.rebuild()
base_keys = list(author.lint_baseline(doc.features))
print("  baseline:", base_keys)
ok, tr = run("move the recess", doc,
             {"remove": "recess_sketch"},
             {"add": {"id": "recess_sketch", "op": "sketch",
                      "params": {"plane": "XY", "offset": 10.0,
                                 "entities": [{"kind": "circle", "r": 9}]}}},
             {"done": True}, max_fails=1)
print(f"  remove the USER's floating sketch then re-add it under the same "
      f"id + offset: finished={ok}")
for t in tr[:3]:
    print(f"    {t[:140]}")

# does `remove` cascade past the id it was given (taking a protected one)?
doc = _base()
doc.add("boss_sketch", "sketch_on_face",
        {"face": "top", "offset": 0, "entities": [{"kind": "circle", "r": 6}]},
        inputs=["base"])
doc.rebuild()
try:
    plan = doc.remove("base", mode="strict")
    print(f"  strict remove of a feature with a dependant: {plan}")
except Exception as e:                                          # noqa: BLE001
    print(f"  strict remove of a feature with a dependant: refused — {e}")

# ------------------------------------------------ 3. _digest stability --------
head("3. `_digest` — WHAT MOVES IT THAT IS NOT A USER EDIT?")
import mcp_server                                                # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="s13r3-"))
mcp_server.OUT = tmp
mcp_server._MINE = {}
rung = []
mcp_server._notify_studio = rung.append

TREE = {"name": "my-widget", "features": [
    {"id": "base_sketch", "op": "sketch",
     "params": {"plane": "XY", "offset": 0,
                "entities": [{"kind": "rectangle", "w": 40, "h": 30}]}},
    {"id": "base", "op": "extrude", "params": {"amount": 5},
     "inputs": ["base_sketch"]},
], "spec": {"n_solids": 1}}

rep = mcp_server.build_design(dict(TREE), export_name="my-widget")
recipe = tmp / "my-widget.tcad.json"
d1 = hashlib.sha256(recipe.read_bytes()).hexdigest()
print(f"  build_design wrote {rep['design_name']}, digest {d1[:16]}")
print(f"  _MINE now: {{k: v[:12] for ...}} = "
      f"{ {k: v[:12] for k, v in mcp_server._MINE.items()} }")

# (a) save -> load -> save, the cycle Studio's File > Save performs
loaded = Document.load(str(recipe))
loaded.rebuild()
again = tmp / "roundtrip.tcad.json"
loaded.save(str(again))
d2 = hashlib.sha256(again.read_bytes()).hexdigest()
print(f"  (a) load + rebuild + save is byte-identical: {d1 == d2}")
if d1 != d2:
    a = recipe.read_text(encoding="utf-8").splitlines()
    b = again.read_text(encoding="utf-8").splitlines()
    import difflib
    print("      " + "\n      ".join(
        list(difflib.unified_diff(a, b, "mcp", "studio", lineterm=""))[:24]))

# (b) the same file saved straight back over itself
loaded.save(str(recipe))
d3 = hashlib.sha256(recipe.read_bytes()).hexdigest()
print(f"  (b) an untouched Studio save over the AI's file keeps it ours: "
      f"{mcp_server._still_mine('my-widget')}  (digest moved: {d1 != d3})")

# (c) the iterate-in-one-file loop after that save
rep2 = mcp_server.build_design(dict(TREE), export_name="my-widget")
print(f"  (c) the next build_design lands in: {rep2['design_name']}"
      f"   renamed: {rep2.get('renamed', '-')[:80]}")

# (d) a real USER edit
mcp_server._MINE = {}
rep3 = mcp_server.build_design(dict(TREE), export_name="w2")
theirs = json.loads((tmp / "w2.tcad.json").read_text(encoding="utf-8"))
theirs["features"][1]["params"]["amount"] = 9
(tmp / "w2.tcad.json").write_text(json.dumps(theirs), encoding="utf-8")
rep4 = mcp_server.build_design(dict(TREE), export_name="w2")
print(f"  (d) after a real user edit: {rep4['design_name']}  "
      f"(their edit survived: "
      f"{json.loads((tmp / 'w2.tcad.json').read_text())['features'][1]['params']['amount'] == 9})")

# (e) the file deleted under us
mcp_server._MINE = {}
mcp_server.build_design(dict(TREE), export_name="w3")
(tmp / "w3.tcad.json").unlink()
rep5 = mcp_server.build_design(dict(TREE), export_name="w3")
print(f"  (e) with the .tcad.json deleted (the .step still there): "
      f"{rep5['design_name']}")

# (f) cost of the digest on a big recipe
big = {"name": "big", "features": [
    {"id": "base_sketch", "op": "sketch",
     "params": {"plane": "XY", "offset": 0,
                "entities": [{"kind": "circle", "r": 0.5, "x": i % 90,
                              "y": i // 90} for i in range(4000)]}}]}
(tmp / "big.tcad.json").write_text(json.dumps(big), encoding="utf-8")
mcp_server._MINE["big"] = ""
t0 = time.perf_counter()
for _ in range(20):
    mcp_server._digest("big")
ms = (time.perf_counter() - t0) / 20 * 1000
print(f"  (f) _digest of a {len(json.dumps(big)) // 1024} KB recipe: "
      f"{ms:.2f} ms")

# (g) design_part's rename line vs build_design's
print(f"  (g) build_design renamed wording: {rep4.get('renamed', '-')[:110]}")

shutil.rmtree(tmp, ignore_errors=True)

# ------------------------------------------------ 4. meanline's window --------
head("4. meanline._check — THE BOUNDARY")
import math                                                      # noqa: E402

import meanline                                                  # noqa: E402

for phi in (0.20, 0.28, 0.40):
    lim = math.degrees(math.atan(1.0 / phi))
    inside, outside = lim - 0.01, lim + 0.01
    for beta, want in ((inside, "designed"), (outside, "refused")):
        try:
            d = meanline.design(meanline.Duty(mass_flow=1.0, pressure_ratio=3.0,
                                              rpm=40000, backsweep_deg=beta),
                                flow_coeff=phi)
            got = f"designed r2={d.tip_radius} mm, U2={d.tip_speed:.0f} m/s"
        except ValueError as e:
            got = f"refused: {str(e)[:60]}"
        except Exception as e:                                   # noqa: BLE001
            got = f"*** {type(e).__name__}: {e}"
        print(f"  phi={phi}  limit={lim:.3f}  beta={beta:8.3f} "
              f"want {want:9} -> {got}")

for phi in (0.0, -0.1):
    try:
        d = meanline.design(meanline.Duty(mass_flow=1.0, pressure_ratio=3.0,
                                          rpm=40000, backsweep_deg=35.0),
                            flow_coeff=phi)
        print(f"  phi={phi}: designed r2={d.tip_radius}, b2={d.exit_width}, "
              f"shroud={d.inducer_shroud_radius}")
    except ValueError as e:
        print(f"  phi={phi}: refused: {str(e)[:70]}")
    except Exception as e:                                       # noqa: BLE001
        print(f"  phi={phi}: *** {type(e).__name__}: {e}")
