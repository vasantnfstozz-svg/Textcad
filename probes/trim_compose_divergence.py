"""Probe: does sketch_trim.py's own composition rule disagree with sketch.py?

LAUNCH-PLAN section 10, P1 (4th sketch review 2026-09-09). Measured, not argued.
"""
import sys, traceback
import sketch as sk
import sketch_trim as tr

def circ(x, y, r, mode="add"):
    return {"kind": "circle", "x": x, "y": y, "r": r, "mode": mode}

def rect(x, y, w, h, mode="add"):
    return {"kind": "rectangle", "x": x, "y": y, "w": w, "h": h, "mode": mode}

BOSS   = circ(0, 0, 5)
BAR    = rect(0, 0, 80, 6, "subtract")
POCKET = rect(0, 0, 40, 20, "subtract")
FAR    = circ(200, 0, 5)

def area(ents):
    try:
        return round(float(sk.make_sketch("XY", 0.0, ents).area), 4)
    except Exception as e:
        return f"RAISED {type(e).__name__}: {e}"

def trim_area(ents, idxs):
    try:
        return round(float(tr._compose_faces(ents, idxs).area), 4)
    except Exception as e:
        return f"RAISED {type(e).__name__}: {e}"

print("=== 1. builder vs trim composition on the boss/bar/pocket cluster ===")
ents = [BOSS, BAR, POCKET]
print("  sketch.py  _compose :", area(ents))
print("  trim _compose_faces :", trim_area(ents, [0, 1, 2]))

print()
print("=== 2. _material_at vs the builder, pointwise ===")
outlines = [tr._outline(e, i) for i, e in enumerate(ents)]
built = sk.make_sketch("XY", 0.0, ents)
for (x, y) in [(0.0, 0.0), (0.0, 4.0), (0.0, -4.0), (4.5, 0.0), (15.0, 0.0)]:
    trim_says = tr._material_at(ents, outlines, [0, 1, 2], x, y)
    # ground truth: is the point in the built profile?
    faces = [f for f in built.faces()]
    real = any(tr._face_contains(f, x, y) for f in faces)
    flag = "" if trim_says == real else "   <-- DISAGREE"
    print(f"  ({x:5.1f},{y:5.1f})  trim={trim_says!s:5}  builder={real!s:5}{flag}")

print()
print("=== 3. a whole trim click on that cluster ===")
try:
    pieces = tr.trim_pieces(ents)
    print("  pieces:", [(p["id"], p["ent"], p["whole"]) for p in pieces])
    # click a piece of the bar inside the boss region
    for p in pieces:
        try:
            out = tr.trim_apply(ents, p["id"])
            print(f"  apply {p['id']}: OK -> area {area(out['entities'])}  ({out['message']})")
        except Exception as e:
            print(f"  apply {p['id']}: RAISED {e}")
except Exception as e:
    traceback.print_exc()

print()
print("=== 4. the guard at l.372: deleting a bar from the three-bar sketch ===")
bars = [rect(0, 0, 40, 20, "subtract"), rect(-12, 0, 6, 12),
        rect(0, 0, 6, 12), rect(12, 0, 6, 12)]
print("  builder area, all four      :", area(bars))
print("  builder area, bar 1 removed :", area([bars[0], bars[2], bars[3]]))
ps = tr.trim_pieces(bars)
print("  pieces:", [(p["id"], p["ent"], p["whole"]) for p in ps])
for p in ps:
    if p["ent"] == 1:
        try:
            out = tr.trim_apply(bars, p["id"])
            print(f"  trim delete bar 1 -> OK, area {area(out['entities'])}")
        except Exception as e:
            print(f"  trim delete bar 1 -> RAISED: {e}")

print()
print("=== 5. LATENT: does sketch.py itself lose the bar behind an unrelated add? ===")
print("  [BOSS,BAR,POCKET]      :", area([BOSS, BAR, POCKET]), " (expect 22.3648)")
print("  [FAR,BOSS,BAR,POCKET]  :", area([FAR, BOSS, BAR, POCKET]),
      " (expect 22.3648 + 78.5398 = 100.9046)")
print("  [BOSS,BAR,POCKET,FAR]  :", area([BOSS, BAR, POCKET, FAR]))
