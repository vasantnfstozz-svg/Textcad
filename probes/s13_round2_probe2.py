"""Section 13 ROUND TWO, part two — the questions round one's OWN new code
raises that are not about the lint:

 5. `done`'s new verdict (was_ok | authored): a pre-existing red row FIXED,
    made WORSE, and a `remove` step, which is the one branch with no health
    check at all.
 6. `meanline._check` — does it refuse any duty that is physically legitimate?
 7. what the AI itself habitually writes as a spec (AUTHOR_PROMPT's own
    examples and samples.py), against the new `checked_spec` refusal.

Run:  C:\\Python314\\python.exe probes/s13_round2_probe2.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import author                     # noqa: E402
import meanline                   # noqa: E402
from document import Document     # noqa: E402


class Scripted:
    def __init__(self, *replies):
        import json
        self.replies = [json.dumps(r) for r in replies]

    def generate(self, messages):
        assert self.replies, "over-asked"
        return self.replies.pop(0)


def _half_broken():
    d = Document(name="half-broken")
    d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
    d.add("bad", "with_center_hole", {"radius": 500}, inputs=["base"])
    d.rebuild()
    assert d.get("bad").status != "ok"
    return d


print("=== 5. done's verdict on a row that was red before the job ===")
d = _half_broken()
ok, tr = author.author_steps(d, "fix the bore", Scripted(
    {"edit": {"feature_id": "bad", "param": "radius", "value": 5}},
    {"done": True}), max_fails=1)
print(f"[5a] the job FIXES the pre-existing red row: ok={ok}; "
      f"bad.status={d.get('bad').status}; last={tr[-1][:120]}")

d = _half_broken()
ok, tr = author.author_steps(d, "bigger bore", Scripted(
    {"edit": {"feature_id": "bad", "param": "radius", "value": 900}},
    {"done": True}), max_fails=1)
print(f"[5b] the job makes it WORSE: ok={ok}; "
      f"radius stands at {d.get('bad').params['radius']}; {tr[0][:120]}")

# a `remove` of the model's OWN step: the only branch with no health check
d = Document(name="mine")
d.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
d.rebuild()
ok, tr = author.author_steps(d, "a boss, then take it back", Scripted(
    {"add": {"id": "boss", "op": "disc", "params": {"radius": 6,
                                                    "thickness": 8}}},
    {"add": {"id": "join", "op": "fuse", "inputs": ["base", "boss"]}},
    {"remove": "join"},
    {"done": True}), max_fails=1)
print(f"[5c] remove of its own step: ok={ok}; tree={[f.id for f in d.features]}; "
      f"red={[f.id for f in d.features if f.status != 'ok']}; "
      f"last={tr[-1][:140]}")

print()
print("=== 6. meanline._check against LEGITIMATE duties ===")
LEGIT = [
    ("tiny automotive turbo", dict(mass_flow=0.05, pressure_ratio=2.2,
                                   rpm=180000, backsweep_deg=40)),
    ("micro turbojet", dict(mass_flow=0.012, pressure_ratio=3.0,
                            rpm=240000, backsweep_deg=30)),
    ("industrial blower, LOW ratio", dict(mass_flow=0.30,
                                          pressure_ratio=1.05, rpm=30000,
                                          backsweep_deg=35)),
    ("barely above 1", dict(mass_flow=0.5, pressure_ratio=1.001, rpm=20000,
                            backsweep_deg=35)),
    ("radial-ended (no backsweep)", dict(mass_flow=1.0, pressure_ratio=3.5,
                                         rpm=40000, backsweep_deg=0.0)),
    ("forward-swept", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000,
                           backsweep_deg=-25.0)),
    ("big process compressor", dict(mass_flow=8.0, pressure_ratio=4.0,
                                    rpm=15000, backsweep_deg=45)),
    ("backsweep at the edge", dict(mass_flow=1.0, pressure_ratio=3.0,
                                   rpm=40000, backsweep_deg=89.0)),
]
for label, kw in LEGIT:
    duty = meanline.Duty(**kw)
    try:
        des = meanline.design(duty)
        print(f"[6] OK   {label:30s} r2={des.tip_radius:8.3f} mm  "
              f"b2={des.exit_width:7.3f} mm  Z={des.blade_count}  "
              f"U2={des.tip_speed:7.1f} m/s")
    except ValueError as e:
        print(f"[6] REFUSED {label:30s} -> {e}")

print()
print("=== 7. the specs the AI is TAUGHT to write ===")
for m in re.finditer(r'"spec"\s*:\s*(\{[^{}]*\})', author.AUTHOR_PROMPT + author.TREE_PROMPT):
    print("    prompt example:", m.group(1)[:120])
import samples                          # noqa: E402
bad = []
for name in dir(samples):
    fn = getattr(samples, name)
    if not callable(fn) or name.startswith("_"):
        continue
    try:
        doc = fn()
        spec = getattr(doc, "spec", None)
    except Exception:
        continue
    if not isinstance(spec, dict) or not spec:
        continue
    try:
        author.checked_spec(spec)
    except ValueError as e:
        bad.append((name, spec, str(e)[:90]))
print(f"[7] sample designs whose spec checked_spec refuses: {len(bad)}")
for n, s, e in bad:
    print(f"       {n}: {s} -> {e}")
print("\n--- probe done ---")
