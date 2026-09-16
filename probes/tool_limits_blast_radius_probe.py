"""Section 11 round two — checking round one's "gizmo placement only" claim.

a3d6b03 replaced `_limits`' centre (the average of the sampled boundary
POINTS) with the AREA centroid, and claimed it changes nothing but where the
extrude arrow and the taper ring sit.  Verified here, not taken on trust:
the OLD `_limits` is restored by monkeypatch and the WHOLE plan dict is
diffed, key by key, over a corpus of profiles — plus the adversarial ones the
round-two brief names (a reversed wire, holes wound the same way as the
outer, a sliver, an unordered point list, a figure eight).

Run:  C:\\Python314\\python.exe probes/tool_limits_blast_radius_probe.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", tempfile.mkdtemp())

import sketch as sk  # noqa: E402
import toolplan  # noqa: E402
from document import Document  # noqa: E402

NEW = toolplan._limits


def OLD(loops):
    """_limits exactly as it stood at ca01a62 (the fix commit's parent)."""
    cx = cy = 0.0
    n = 0
    for L in loops:
        pts = L["outer"]
        if len(pts) < 3:
            continue
        for p in pts:
            cx += p[0]
            cy += p[1]
            n += 1
    base = {"has_holes": any(L["holes"] for L in loops),
            "max_taper": sk.MAX_TAPER_DEG, "apex_fraction": sk.APEX_FRACTION}
    if not n:
        return ({**base, "outer_radius": 0.0}, None)
    cx /= n
    cy /= n
    outer_r = max(math.hypot(p[0] - cx, p[1] - cy)
                  for L in loops for p in L["outer"])
    return ({**base, "outer_radius": round(outer_r, 4)}, (cx, cy))


PROFILES = {
    "circle": [{"kind": "circle", "r": 10}],
    "rect": [{"kind": "rectangle", "w": 30, "h": 20}],
    "washer": [{"kind": "circle", "r": 15},
               {"kind": "circle", "r": 5, "mode": "subtract"}],
    "hex": [{"kind": "regular_polygon", "radius": 12, "sides": 6}],
    "slot": [{"kind": "slot", "length": 40, "height": 10}],
    "L": [{"kind": "polygon", "points": [[0, 0], [40, 0], [40, 10],
                                         [10, 10], [10, 30], [0, 30]]}],
    "circle+square": [{"kind": "circle", "r": 10, "x": -20},
                      {"kind": "rectangle", "w": 20, "h": 20, "x": 20}],
    "plate+4 holes": [{"kind": "rectangle", "w": 60, "h": 40},
                      {"kind": "circle", "r": 3, "x": -20, "y": -12,
                       "mode": "subtract"},
                      {"kind": "circle", "r": 3, "x": 20, "y": -12,
                       "mode": "subtract"},
                      {"kind": "circle", "r": 3, "x": -20, "y": 12,
                       "mode": "subtract"},
                      {"kind": "circle", "r": 3, "x": 20, "y": 12,
                       "mode": "subtract"}],
    "thin ring": [{"kind": "circle", "r": 10},
                  {"kind": "circle", "r": 9.6, "mode": "subtract"}],
    "sliver": [{"kind": "rectangle", "w": 60, "h": 0.05}],
}

print("=" * 76)
print("A. what the WHOLE plan looks like, old centre vs new, key by key")
print("=" * 76)
changed_keys = set()
for name, ents in PROFILES.items():
    d = Document(name="t")
    d.add("s", "sketch", {"plane": "XY", "entities": ents}, [])
    d.rebuild()
    toolplan._limits = NEW
    new = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s",
                            "measure_collapse": True})
    toolplan._limits = OLD
    old = toolplan.plan(d, {"tool": "extrude", "sketch_id": "s",
                            "measure_collapse": True})
    toolplan._limits = NEW
    if not (new.get("ok") and old.get("ok")):
        print(f"  {name:<16} old ok={old.get('ok')} new ok={new.get('ok')}  "
              f"{new.get('error') or old.get('error')}")
        continue
    diff = []
    for k in sorted(set(old) | set(new)):
        if k == "limits":
            for lk in sorted(set(old[k]) | set(new[k])):
                if old[k].get(lk) != new[k].get(lk):
                    diff.append(f"limits.{lk}")
                    changed_keys.add(f"limits.{lk}")
            continue
        if old.get(k) != new.get(k):
            diff.append(k)
            changed_keys.add(k)
    shift = math.dist(old["origin"], new["origin"])
    print(f"  {name:<16} moved {shift:7.3f} mm   differs in: {diff or '(nothing)'}")

print(f"\n  EVERY key that ever differs, over the corpus: {sorted(changed_keys)}")

print()
print("=" * 76)
print("B. the adversarial shapes the round-two brief names")
print("=" * 76)

sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
cases = {
    "square, CCW": [{"outer": sq, "holes": []}],
    "square, CW (reversed wire)": [{"outer": list(reversed(sq)), "holes": []}],
    "hole wound the SAME way as the outer": [
        {"outer": [[0, 0], [30, 0], [30, 30], [0, 30]],
         "holes": [[[10, 10], [20, 10], [20, 20], [10, 20]]]}],
    "hole wound the OTHER way": [
        {"outer": [[0, 0], [30, 0], [30, 30], [0, 30]],
         "holes": [[[10, 10], [10, 20], [20, 20], [20, 10]]]}],
    "figure eight (self-crossing)": [
        {"outer": [[0, 0], [10, 0], [0, 10], [10, 10]], "holes": []}],
    "unordered point list": [
        {"outer": [[0, 0], [10, 10], [10, 0], [0, 10]], "holes": []}],
    "sliver (1e-7 mm2)": [
        {"outer": [[0, 0], [1, 0], [1, 1e-7], [0, 1e-7]], "holes": []}],
    "zero area (a line back on itself)": [
        {"outer": [[0, 0], [10, 0], [10, 0], [0, 0]], "holes": []}],
    "outer under 3 points, a hole with area": [
        {"outer": [[0, 0], [5, 5]],
         "holes": [[[10, 10], [20, 10], [20, 20], [10, 20]]]}],
}
for name, loops in cases.items():
    try:
        lim, centre = NEW(loops)
        print(f"  {name:<38} centre={centre}  outer_radius={lim['outer_radius']}")
    except Exception as e:             # noqa: BLE001 — that IS the finding
        print(f"  {name:<38} RAISED {type(e).__name__}: {e}")
