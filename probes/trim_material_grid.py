"""Probe: does trim's pointwise material test now agree with the builder?

A dense grid over several sketches, comparing `_material_at` (fed the cluster
in the order `_cluster` now returns) against whether the BUILT profile
actually contains the point. Points within TOL of any outline are skipped —
the boundary is genuinely ambiguous for both.
"""
import numpy as np
import sketch as sk
import sketch_trim as tr

def circ(x, y, r, mode="add"):
    return {"kind": "circle", "x": x, "y": y, "r": r, "mode": mode}
def rect(x, y, w, h, mode="add"):
    return {"kind": "rectangle", "x": x, "y": y, "w": w, "h": h, "mode": mode}

BOSS, BAR, POCKET = circ(0, 0, 5), rect(0, 0, 80, 6, "subtract"), rect(0, 0, 40, 20, "subtract")
FAR = circ(200, 0, 5)

CASES = {
 "boss/bar/pocket":        [BOSS, BAR, POCKET],
 "pocket first":           [POCKET, BAR, BOSS],
 "far add in front":       [FAR, BOSS, BAR, POCKET],
 "three bars in a pocket": [rect(0,0,40,20,"subtract"), rect(-12,0,6,12), rect(0,0,6,12), rect(12,0,6,12)],
 "washer + island":        [circ(0,0,30), circ(0,0,20,"subtract"), circ(0,0,10)],
 "rect bitten by circle":  [rect(0,0,40,20), circ(20,0,8,"subtract")],
 "two overlapping adds":   [circ(0,0,10), circ(12,0,10)],
 "island in a cut":        [circ(0,0,20,"subtract"), circ(0,0,10)],
}

def near_any_outline(outlines, x, y, tol=0.35):
    for o in outlines:
        d = np.hypot(o["pts"][:,0]-x, o["pts"][:,1]-y).min()
        if d < tol: return True
    return False

total_bad = 0
for name, ents in CASES.items():
    outlines = [tr._outline(e, i) for i, e in enumerate(ents)]
    _, _, crossing = tr._pieces_raw(ents)
    built = sk.make_sketch("XY", 0.0, ents)
    # sample every face of the BUILT profile ONCE (outer wire + its holes) so
    # the oracle is plain point-in-polygon, not a wire walk per grid point
    oracle = []
    for f in built.faces():
        ow = f.outer_wire()
        def samp(w):
            n = int(min(max(w.length / 0.4, 128), 768))
            return np.array([[(w.position_at(i / n)).X, (w.position_at(i / n)).Y]
                             for i in range(n)])
        oracle.append((samp(ow), [samp(w) for w in f.wires() if not w.is_same(ow)]))
    def in_built(x, y):
        for outer, holes in oracle:
            if tr._inside({"pts": outer}, x, y) and                not any(tr._inside({"pts": h}, x, y) for h in holes):
                return True
        return False
    # grid over the union bbox of the cluster containing entity 0
    clusters = {tuple(tr._cluster(ents, outlines, crossing, s0))
                for s0 in range(len(ents))}
    pts = np.vstack([o["pts"] for o in outlines])
    x0, y0 = pts.min(0) - 2; x1, y1 = pts.max(0) + 2
    bad = tested = 0
    for x in np.linspace(x0, x1, 61):
        for y in np.linspace(y0, y1, 41):
            if near_any_outline(outlines, x, y): continue
            tested += 1
            real = in_built(float(x), float(y))
            for cl in clusters:
                got = tr._material_at(ents, outlines, list(cl), float(x), float(y))
                if got != real and any(tr._inside(outlines[i], float(x), float(y))
                                       for i in cl):
                    bad += 1
                    if bad <= 3: print(f"    MISMATCH {cl} ({x:7.3f},{y:7.3f}) trim={got} builder={real}")
    total_bad += bad
    print(f"  {name:24s} clusters {sorted(clusters)}  tested {tested:5d}  mismatches {bad}")
print()
print("TOTAL MISMATCHES:", total_bad)
