"""Third review of the sketch composition order (2026-09-09) — measurement
first, per REVIEW-QUEUE.md's fix pass.

The claim under test: `_compose`'s DEFERRAL of a leading subtraction cancels
`_compose_order`. The order hoists a subtraction in FRONT of the add nested
inside it precisely so that add survives as an island; the deferral then
subtracts it from exactly that add.

Ground truth for what a sketch means: the sketcher paints every entity on its
own — `add` fills GREEN, `subtract` fills RED (sketcher.js:1611). A green
region the kernel builds away is the F1 class of bug.

Run: C:\\Python314\\python.exe probes/sketcher_review3_probe.py
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sketch as S


def compose_area(entities, rule):
    """Area of the composed profile under a named rule, without touching
    sketch.py. 'defer' is what ships today; 'skip' is a leading subtraction
    cutting nothing; 'draw' is the pre-556a611 drawing order."""
    shapes = [S._entity(e) for e in entities]
    order = list(range(len(shapes)))
    if rule != "draw" and any(e.get("mode", "add") == "subtract"
                              for e in entities):
        order = S._compose_order(shapes)
    result, waiting = None, []
    try:
      for i in order:
        mode = entities[i].get("mode", "add")
        if result is None:
            if mode == "subtract":
                if rule == "defer":
                    waiting.append(i)
                continue                      # 'skip': cuts nothing
            result = shapes[i]
            for j in waiting:
                result = result - shapes[j]
            waiting.clear()
        else:
            result = (result - shapes[i] if mode == "subtract"
                      else result + shapes[i])
    except Exception as exc:                                  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    if result is None:
        return None, "every entity subtracts"
    try:
        return round(result.area, 4), None
    except Exception as exc:                                  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def rect(x, y, w, h, mode="add"):
    return {"kind": "rectangle", "x": x, "y": y, "w": w, "h": h, "mode": mode}


def circ(x, y, r, mode="add"):
    return {"kind": "circle", "x": x, "y": y, "r": r, "mode": mode}


print("=" * 72)
print("1. THE USER'S OWN DESIGN — esp32-remote/logo_1_sketch")
print("=" * 72)
doc = json.load(open("designs/esp32-remote.tcad.json"))
for feat in doc["features"]:
    if feat["id"] not in ("logo_0_sketch", "logo_1_sketch"):
        continue
    ents = feat["params"]["entities"]
    shapes = [S._entity(e) for e in ents]
    order = S._compose_order(shapes)
    modes = [e.get("mode", "add")[:3] for e in ents]
    print(f"\n{feat['id']}: {len(ents)} entities, modes {modes}")
    print(f"  _compose_order -> {order}")
    inside = S._containment(shapes)
    for i in range(len(ents)):
        holders = [j for j in range(len(ents)) if inside[i][j]]
        if holders:
            print(f"  ent {i} ({modes[i]}, {shapes[i].area:.4f} mm2) sits "
                  f"inside {holders} ({[modes[j] for j in holders]})")
    for rule in ("draw", "defer", "skip"):
        area, err = compose_area(ents, rule)
        print(f"  {rule:>5}: {area if err is None else err}")

print()
print("=" * 72)
print("2. THE REVIEWER'S SYNTHETIC CASES")
print("=" * 72)
cases = {
    "island, outer drawn first  [r30 add, r20 sub, r10 add]":
        [circ(0, 0, 30), circ(0, 0, 20, "subtract"), circ(0, 0, 10)],
    "island, NO outer           [r20 sub, r10 add, r5@100 add]":
        [circ(0, 0, 20, "subtract"), circ(0, 0, 10), circ(100, 0, 5)],
    "leading sub eats the add   [r20 sub, r10 add]":
        [circ(0, 0, 20, "subtract"), circ(0, 0, 10)],
    "two leading subs           [r20 sub, r15 sub, r10 add]":
        [circ(0, 0, 20, "subtract"), circ(0, 0, 15, "subtract"),
         circ(0, 0, 10)],
    "3 bars in a subtract blob":
        [rect(0, 0, 40, 20, "subtract"), rect(-12, 0, 6, 12),
         rect(0, 0, 6, 12), rect(12, 0, 6, 12)],
}
for name, ents in cases.items():
    print(f"\n{name}")
    shapes = [S._entity(e) for e in ents]
    print(f"  order {S._compose_order(shapes)}   "
          f"entity areas {[round(s.area, 2) for s in shapes]}")
    for rule in ("draw", "defer", "skip"):
        area, err = compose_area(ents, rule)
        print(f"  {rule:>5}: {area if err is None else err}")

print()
print("=" * 72)
print("3. THE EMPTY RESULT — what reaches the user (P1/P2 claims)")
print("=" * 72)
for name, ents in {
    "add r10 then subtract the SAME r10 (mutual pair, order untouched)":
        [circ(0, 0, 10), circ(0, 0, 10, "subtract")],
    "leading sub eats the first add, a second add follows":
        [circ(0, 0, 20, "subtract"), circ(0, 0, 10), circ(100, 0, 5)],
    "emptied, then ANOTHER subtraction":
        [circ(0, 0, 10), circ(0, 0, 10, "subtract"),
         circ(0, 0, 3, "subtract")],
}.items():
    print(f"\n{name}")
    try:
        sk = S.make_sketch("XY", 0.0, ents)
        print(f"  make_sketch OK: area {sk.area:.4f}, "
              f"{len(sk.faces())} face(s)")
    except Exception as exc:                                  # noqa: BLE001
        print(f"  make_sketch raised {type(exc).__name__}: {exc}")

print()
print("=" * 72)
print("4. THE ARC MESSAGE — a malformed 'via' (P3 claim)")
print("=" * 72)
bad = {"kind": "path", "start": [0, 0], "segments": [
    {"type": "line", "to": [10, 0]},
    {"type": "arc", "to": [0, 10]},              # no 'via' at all
    {"type": "line", "to": [0, 0]}]}
try:
    S.make_sketch("XY", 0.0, [bad])
    print("  built (no error)")
except Exception as exc:                                      # noqa: BLE001
    print(f"  {type(exc).__name__}: {exc}")

print()
print("=" * 72)
print("5. LIBRARY SWEEP — which committed designs change, and by how much")
print("=" * 72)
import glob
changed = []
malformed = []
for path in sorted(glob.glob("designs/*.tcad.json")):
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except Exception as exc:                                  # noqa: BLE001
        print(f"  {path}: unreadable ({exc})")
        continue
    for feat in doc.get("features", []):
        ents = (feat.get("params") or {}).get("entities")
        if not ents:
            continue
        for i, e in enumerate(ents):
            if e.get("kind") == "path" and not e.get("start"):
                malformed.append(f"{path}::{feat['id']} ent {i}: path, no start")
        if not any(e.get("mode", "add") == "subtract" for e in ents):
            continue
        try:
            a_now, e_now = compose_area(ents, "defer")
            a_fix, e_fix = compose_area(ents, "skip")
        except Exception as exc:                              # noqa: BLE001
            print(f"  {path}::{feat['id']}: probe failed {exc}")
            continue
        if (a_now, e_now) != (a_fix, e_fix):
            changed.append((path, feat["id"], a_now or e_now, a_fix or e_fix))
print(f"\nsketches whose area or verdict MOVES: {len(changed)}")
for path, fid, now, fix in changed:
    print(f"  {path}::{fid}\n      today {now}  ->  fixed {fix}")
print(f"\npath entities with no start: {len(malformed)}")
for m in malformed:
    print("  " + m)
