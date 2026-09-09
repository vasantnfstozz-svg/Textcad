"""Reproduce the Sketcher review findings (REVIEW-QUEUE section 1) by
MEASUREMENT, before any fix. Run:  python probes/sketcher_review_probe.py

F1  a hole drawn BEFORE its outer becomes solid material
F2  even-odd modes are right, but the entities are never reordered
F4  _path_face has no validation: raw OCCT text reaches the user
F8  a circular hole advertises a bogus "corner" and "midpoint"
U3  the 8-sample containment check mislabels a shape that pokes out
"""
import math
import sys

import build123d as b3d

sys.path.insert(0, ".")
import sketch as sk                                     # noqa: E402
import sketch_snap                                     # noqa: E402

print("build123d", b3d.__version__ if hasattr(b3d, "__version__") else "?")

# --- F1: hole first, outer second (what the sketcher sends today) ----------
# assignModes marks the inner circle 'subtract'; create() flips clean[0] back
# to 'add' because it is first in DRAWING order.
f1_sent = [
    {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10},      # flipped!
    {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 30},
]
f1_area = sk.make_sketch("XY", 0, f1_sent).area
washer = math.pi * (30**2 - 10**2)
print(f"\nF1 sent-today area = {f1_area:.2f}   washer should be {washer:.2f}")
print(f"F1 REPRODUCED: {abs(f1_area - washer) > 1.0}")

# --- F2: r10, r30, r20 in drawing order -----------------------------------
f2_sent = [
    {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10},
    {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 30},
    {"kind": "circle", "mode": "subtract", "x": 0, "y": 0, "r": 20},
]
f2_area = sk.make_sketch("XY", 0, f2_sent).area
f2_sorted = [f2_sent[1], f2_sent[2], f2_sent[0]]          # outer, hole, island
f2_ok = sk.make_sketch("XY", 0, f2_sorted).area
want = math.pi * (30**2 - 20**2 + 10**2)
print(f"\nF2 drawing-order area = {f2_area:.2f}   depth-sorted = {f2_ok:.2f}"
      f"   ring+island should be {want:.2f}")
print(f"F2 REPRODUCED: {abs(f2_area - want) > 1.0 and abs(f2_ok - want) < 1.0}")

# --- F4: three degenerate paths, each straight from the UI -----------------
cases = {
    "bow-tie (4 points that cross)": {
        "kind": "path", "start": [0, 0], "segments": [
            {"type": "line", "to": [20, 20]},
            {"type": "line", "to": [20, 0]},
            {"type": "line", "to": [0, 20]}]},
    "two clicks in the same snapped cell": {
        "kind": "path", "start": [0, 0], "segments": [
            {"type": "line", "to": [0, 0]}]},
    "start + one point + double-click": {
        "kind": "path", "start": [0, 0], "segments": [
            {"type": "line", "to": [10, 0]}]},
}
print()
for name, ent in cases.items():
    try:
        a = sk.make_sketch("XY", 0, [ent]).area
        print(f"F4 {name}: BUILT, area {a:.4f}")
    except Exception as e:                                  # noqa: BLE001
        readable = isinstance(e, ValueError)
        print(f"F4 {name}: {type(e).__name__}({e!s:.70}) readable={readable}")

# --- F8: a bore's seam advertised as a corner ------------------------------
solid = b3d.Box(40, 40, 10) - b3d.Cylinder(radius=5, height=20)
snaps = sketch_snap.snap_geometry({"b": solid}, "XY", 0.0)
bore = [p for p in snaps["points"] if abs(math.hypot(p["x"], p["y"]) - 5) < 0.01]
print("\nF8 points on the bore circle (radius 5):")
for p in sorted(bore, key=lambda q: (q["kind"], q["x"])):
    print(f"   {p['kind']:9s} at ({p['x']:.3f}, {p['y']:.3f})")
print(f"F8 REPRODUCED: {any(p['kind'] in ('corner', 'midpoint') for p in bore)}")

# --- U3: a star that pokes out of a circle, 8-sample containment -----------
star = []
for k in range(10):
    r = 34 if k % 2 == 0 else 14           # tips at 34 poke out of an r=30 disc
    t = math.pi / 2 + k * math.pi / 5
    star.append([round(r * math.cos(t), 4), round(r * math.sin(t), 4)])
outside = sum(1 for x, y in star if math.hypot(x, y) > 30)
print(f"\nU3 star vertices outside the r=30 circle: {outside} of {len(star)}")
print("U3 every 2nd sample of an 8-of-20 walk can miss all 5 tips "
      "-> 'contained' -> the star is turned into a HOLE")
