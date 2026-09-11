"""Is "a lump came back UNTOUCHED" an EXACT signal, or a fuzzy one?

If the kernel sometimes hands back a lump ALMOST unchanged (0.999 of its
volume), an identity test would miss it and a per-lump volume-drop rule would
be needed after all -- with all the pairing trouble that brought. So: sweep
mixed pairs over the whole thickness ladder and, for every result lump, print
how close it is to the input lump sharing its bounding box.
Also: can a lump VANISH, and can .volume / .bounding_box() / .solids() RAISE?
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
import sketch, pattern, inspector

def tops(part):
    out = []
    for l in part.solids():
        f = max((f for f in l.faces() if sketch.face_plane(f) is not None),
                key=lambda f: (round(f.center().Z, 6), f.area))
        c = f.center()
        out.append({"center": [c.X, c.Y, c.Z], "normal": list(f.normal_at(c))})
    return out

def bx(s):
    b = s.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)

def raw(part, t, d):
    return b3d.offset(part, amount=(-t if d == "inside" else t),
                      openings=sketch.shell_openings(part, tops(part)),
                      kind=b3d.Kind.INTERSECTION)

SECONDS = {"w": (3.0, 20.0, 10.0), "f": (20.0, 20.0, 4.0), "m": (12.0, 20.0, 10.0),
           "e": (20.0, 20.0, 10.0), "t": (0.8, 20.0, 10.0)}
ratios = []
print("=== ratio of each result lump to the input lump sharing its box ===")
for key, size in SECONDS.items():
    for t in (0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8):
        for d in ("inside", "outside"):
            body = b3d.Part() + b3d.Box(20, 20, 10) + b3d.Pos(40, 0, 0) * b3d.Box(*size)
            ins = body.solids()
            try:
                o = raw(body, t, d)
            except Exception:
                continue
            if len(o.solids()) != len(ins):
                print(f"  !! {key} t={t} {d}: lump COUNT changed {len(ins)} -> {len(o.solids())}")
            for piece in o.solids():
                same_box = [l for l in ins
                            if max(abs(a - b) for a, b in zip(bx(piece), bx(l))) <= 1e-9]
                if same_box:
                    ratios.append((piece.volume / same_box[0].volume, key, t, d))
near = sorted(r for r in ratios if 0.95 <= r[0] <= 1.05)
print(f"  {len(ratios)} result lumps shared a box with an input lump")
print(f"  ratios in [0.95, 1.05]: {[(round(r[0],12), r[1], r[2], r[3]) for r in near]}")
others = sorted(r[0] for r in ratios if not (0.95 <= r[0] <= 1.05))
print(f"  every other ratio: min {min(others):.4f}  max {max(others):.4f}  (n={len(others)})")

print("\n=== can a lump VANISH? (inside, thickness past everything) ===")
for t in (5, 6, 8, 10, 12, 20):
    body = b3d.Part() + b3d.Box(60, 60, 40) + b3d.Pos(120, 0, 0) * b3d.Box(20, 20, 10)
    try:
        o = raw(body, t, "inside")
        print(f"  t={t:<4} lumps {len(body.solids())} -> {len(o.solids())}  "
              f"{[round(s.volume,1) for s in o.solids()]}")
    except Exception as e:
        print(f"  t={t:<4} kernel raised {type(e).__name__}")

print("\n=== do .solids() / .volume / .bounding_box() raise on a RESULT? cost? ===")
big = pattern.linear_pattern(b3d.Box(20, 20, 10), count=12, dx=30)
print(f"  a 12-lump body, {len(big.faces())} faces")
t0 = time.perf_counter(); o = raw(big, 2, "inside"); t1 = time.perf_counter()
print(f"  kernel offset: {t1-t0:.3f}s, result {len(o.faces())} faces")
t0 = time.perf_counter()
n = 0
for s in list(big.solids()) + list(o.solids()):
    _ = s.volume; _ = s.bounding_box(); n += 1
print(f"  {n} x (.volume + .bounding_box()) on input AND result: "
      f"{time.perf_counter()-t0:.3f}s -- no exception")
