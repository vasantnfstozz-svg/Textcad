"""1. A DELIBERATE ordering cycle: C1 contains A1, A1 overlaps C2, C2 contains
   A2, A2 overlaps C1. `_order_from` breaks a cycle by falling back to the
   drawing order — silently. What does the user get?
2. Trim's cost on the biggest sketch in the user's library.
"""
import json, glob, os, time
import sketch as S
import sketch_trim as T


def rect(x, y, w, h, mode="add"):
    return {"kind": "rectangle", "x": x, "y": y, "w": w, "h": h, "mode": mode}


C1 = rect(-10, 0, 40, 20, "subtract")     # x -30..10
A1 = rect(-15, 0, 20, 6)                  # x -25..-5, inside C1, pokes into C2
C2 = rect(10, 0, 40, 20, "subtract")      # x -10..30
A2 = rect(15, 0, 20, 6)                   # x   5..25, inside C2, pokes into C1
CYC = [C1, A1, C2, A2]

print("=== 1. the deliberate cycle ===")
shapes = [S._entity(e) for e in CYC]
modes = [e.get("mode", "add") for e in CYC]
inside = S._containment(shapes)
print("   containment (inside[i][j] = i sits in j):")
for i, r in enumerate(inside):
    print("     ", i, [int(v) for v in r])
needs = [row[:] for row in inside]
for i in range(4):
    if modes[i] != "subtract":
        continue
    for j in range(4):
        if (i == j or modes[j] == "subtract" or needs[i][j] or needs[j][i]
                or inside[i][j] or inside[j][i]):
            continue
        if S._overlaps(shapes[j], shapes[i]):
            needs[i][j] = True
print("   needs (needs[i][j] = j must come before i):")
for i, r in enumerate(needs):
    print("     ", i, [int(v) for v in r])
waiting = [sum(r) for r in needs]
done = [False] * 4
placed = 0
while True:
    nxt = next((i for i in range(4) if not done[i] and not waiting[i]), None)
    if nxt is None:
        break
    done[nxt] = True
    placed += 1
    for i in range(4):
        if needs[i][nxt] and not done[i]:
            waiting[i] -= 1
print(f"   acyclic? {placed == 4}   (placed {placed} of 4)")
order = S.compose_order(CYC)
print("   compose_order ->", order)
S.drain_notes()
try:
    a = S.make_sketch("XY", 0.0, CYC).area
    print(f"   area = {a:.4f}")
except Exception as ex:
    print(f"   RAISED {type(ex).__name__}: {ex}")
print("   notes:", S.drain_notes())
# what SHOULD it be? every add minus every cut that overlaps it, islands kept:
# A1 is inside C1 (island, survives C1) but pokes into C2 -> that bit is cut
# A2 is inside C2 (island, survives C2) but pokes into C1 -> that bit is cut
print("   honest answer: A1 keeps x -25..-10 (15x6=90), A2 keeps x 10..25 "
      "(15x6=90) -> 180.0")
print("   drawing-order answer would be:", end=" ")
r = None
for i in range(4):
    f = shapes[i]
    if modes[i] == "subtract":
        r = r if r is None else r - f
    else:
        r = f if r is None else r + f
print(f"{float(r.area):.4f}" if r is not None else "None")

print()
print("=== 2. Trim's cost on the library's biggest sketch ===")
biggest = None
for path in sorted(glob.glob("designs/*.tcad.json")):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for f in data.get("features", []):
        ents = (f.get("params") or {}).get("entities")
        if ents and (biggest is None or len(ents) > len(biggest[2])):
            biggest = (os.path.basename(path), f.get("id"), ents)
name, fid, ents = biggest
print(f"   {name}/{fid}: {len(ents)} entities, "
      f"{sum(1 for e in ents if e.get('mode') == 'subtract')} of them cuts")
t0 = time.perf_counter()
pieces = T.trim_pieces(ents)
t1 = time.perf_counter()
print(f"   trim_pieces: {len(pieces)} pieces in {t1 - t0:.2f}s")
hit = next((p for p in pieces if not p["whole"]), pieces[0])
t0 = time.perf_counter()
try:
    out = T.trim_apply(ents, hit["id"])
    t1 = time.perf_counter()
    print(f"   trim_apply({hit['id']}): {t1 - t0:.2f}s -> "
          f"{len(out['entities'])} entities; {out['message']}")
except Exception as ex:
    t1 = time.perf_counter()
    print(f"   trim_apply({hit['id']}): {t1 - t0:.2f}s -> REFUSED: {ex}")
t0 = time.perf_counter()
S.compose(ents, note=False)
print(f"   one full compose of that list: {time.perf_counter() - t0:.2f}s")
