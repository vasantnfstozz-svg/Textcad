"""Adversarial probe of the fifth-review composition-order change (3b230b7).

1. COVERAGE: is "zero drift over 50 designs" meaningful? Count the sketches in
   the user's library that actually contain the pair the change is about — a
   cut and an add that OVERLAP without either containing the other. If none
   do, the drift result proves nothing.
2. CYCLES: can the extra ordering edges make a cycle? `_order_from` breaks one
   silently by falling back to drawing order, which would put a cut ahead of
   its material again.
3. THE EMPTY RESET: `_material_at` claims to be pointwise-equivalent to
   `compose`. `compose` resets to None when a cut empties the profile. Grid.
"""
import json, glob, os, itertools
import numpy as np
import sketch as S
import sketch_trim as T


def entities_of(doc_data):
    for f in doc_data.get("features", []):
        ents = (f.get("params") or {}).get("entities")
        if ents:
            yield f.get("id", "?"), ents


print("=== 1. does the library contain the pair this change is about? ===")
hits = total = 0
for path in sorted(glob.glob("designs/*.tcad.json")):
    name = os.path.basename(path)[:-len(".tcad.json")]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for fid, ents in entities_of(data):
        modes = [e.get("mode", "add") for e in ents]
        if not any(m == "subtract" for m in modes):
            continue
        total += 1
        try:
            shapes = [S._entity(e) for e in ents]
        except Exception:
            continue
        inside = S._containment(shapes)
        found = []
        for i, j in itertools.product(range(len(ents)), repeat=2):
            if i == j or modes[i] != "subtract" or modes[j] == "subtract":
                continue
            if inside[i][j] or inside[j][i]:
                continue
            try:
                if S._overlaps(shapes[j], shapes[i]):
                    found.append((i, j))
            except Exception:
                pass
        if found:
            hits += 1
            print(f"   {name}/{fid}: {len(found)} non-nested cut/material "
                  f"overlaps {found[:4]}")
print(f"   -> {hits} of {total} sketches with a subtract contain the pair")

print()
print("=== 2. can the extra edges make a cycle? ===")


def order_and_cycle(ents):
    shapes = [S._entity(e) for e in ents]
    modes = [e.get("mode", "add") for e in ents]
    n = len(shapes)
    inside = S._containment(shapes)
    needs = [row[:] for row in inside]
    for i in range(n):
        if modes[i] != "subtract":
            continue
        for j in range(n):
            if (i == j or modes[j] == "subtract" or needs[i][j] or needs[j][i]
                    or inside[i][j] or inside[j][i]):
                continue
            if S._overlaps(shapes[j], shapes[i]):
                needs[i][j] = True
    # is `needs` acyclic?
    waiting = [sum(r) for r in needs]
    done, placed = [False] * n, 0
    while True:
        nxt = next((i for i in range(n) if not done[i] and not waiting[i]), None)
        if nxt is None:
            break
        done[nxt] = True
        placed += 1
        for i in range(n):
            if needs[i][nxt] and not done[i]:
                waiting[i] -= 1
    return placed < n, needs


def circ(x, y, r, mode="add"):
    return {"kind": "circle", "x": x, "y": y, "r": r, "mode": mode}


def rect(x, y, w, h, mode="add"):
    return {"kind": "rectangle", "x": x, "y": y, "w": w, "h": h, "mode": mode}


# hand-built attempt: A before C1 (overlap), C1 contains A2, A2 before C2
# (overlap), C2 contains A  ->  a 4-cycle
attempts = {
 "hand-built 4-cycle attempt": [
     circ(0, 0, 6),                       # A   (add)
     rect(4, 0, 6, 3, "subtract"),        # C1  overlaps A
     circ(6, 0, 2),                       # A2  inside C1?
     rect(-2, 0, 30, 30, "subtract"),     # C2  contains A
 ],
 "chain of biting cuts": [
     rect(-20, 0, 20, 8), rect(-10, 0, 8, 20, "subtract"),
     rect(0, 0, 20, 8), rect(10, 0, 8, 20, "subtract"),
     rect(20, 0, 20, 8),
 ],
 "concentric ring stack": [
     circ(0, 0, 30), circ(0, 0, 20, "subtract"), circ(0, 0, 10),
     rect(0, 0, 80, 4, "subtract"),
 ],
}
for name, ents in attempts.items():
    try:
        cyc, _ = order_and_cycle(ents)
        print(f"   {name:28s} cycle={cyc}  order={S.compose_order(ents)}")
    except Exception as ex:
        print(f"   {name:28s} RAISED {type(ex).__name__}: {ex}")

# and over the whole library
libcyc = 0
for path in sorted(glob.glob("designs/*.tcad.json")):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for fid, ents in entities_of(data):
        if not any(e.get("mode") == "subtract" for e in ents):
            continue
        try:
            cyc, _ = order_and_cycle(ents)
        except Exception:
            continue
        if cyc:
            libcyc += 1
            print(f"   CYCLE in {os.path.basename(path)}/{fid}")
print(f"   -> cycles in the live library: {libcyc}")

print()
print("=== 3. _material_at vs the builder where the EMPTY RESET fires ===")
RESET_CASES = {
 "cut empties, add restarts":
     [circ(0, 0, 10), circ(0, 0, 10, "subtract"), circ(6, 0, 8)],
 "cut empties, cut, add":
     [circ(0, 0, 10), circ(0, 0, 10, "subtract"),
      circ(4, 0, 6, "subtract"), circ(6, 0, 8)],
 "two adds, one swallowing cut, one biting cut":
     [circ(0, 0, 10), circ(14, 0, 6), circ(0, 0, 11, "subtract"),
      rect(14, 0, 30, 4, "subtract")],
}
bad_total = 0
for name, ents in RESET_CASES.items():
    outlines = [T._outline(e, i) for i, e in enumerate(ents)]
    _, _, crossing = T._pieces_raw(ents)
    try:
        built = S.make_sketch("XY", 0.0, ents)
    except Exception as ex:
        print(f"   {name:42s} builder RAISES ({ex}) — skipped")
        continue
    rings = []
    for f in built.faces():
        ow = f.outer_wire()

        def samp(w):
            n = 300
            return np.array([[(w.position_at(i / n)).X,
                              (w.position_at(i / n)).Y] for i in range(n)])
        rings.append((samp(ow), [samp(w) for w in f.wires()
                                 if not w.is_same(ow)]))

    def in_built(x, y):
        return any(T._inside({"pts": o}, x, y)
                   and not any(T._inside({"pts": h}, x, y) for h in holes)
                   for o, holes in rings)

    clusters = {tuple(T._cluster(ents, outlines, crossing, s))
                for s in range(len(ents))}
    bad = tested = 0
    for x in np.linspace(-26, 34, 61):
        for y in np.linspace(-16, 16, 33):
            if any(np.hypot(o["pts"][:, 0] - x, o["pts"][:, 1] - y).min() < 0.35
                   for o in outlines):
                continue
            tested += 1
            real = in_built(float(x), float(y))
            for cl in clusters:
                if not any(T._inside(outlines[i], float(x), float(y))
                           for i in cl):
                    continue
                if T._material_at(ents, outlines, list(cl),
                                  float(x), float(y)) != real:
                    bad += 1
                    if bad <= 2:
                        print(f"     MISMATCH {cl} ({x:.2f},{y:.2f}) "
                              f"builder={real}")
    bad_total += bad
    print(f"   {name:42s} clusters={sorted(clusters)} tested={tested} bad={bad}")
print(f"   -> reset-case mismatches: {bad_total}")
