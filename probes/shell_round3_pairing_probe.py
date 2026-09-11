"""ROUND THREE: attack assert_every_lump_hollowed's own pairing.

It pairs each RESULT lump to the input lump with the nearest bounding-box
CENTRE, on the stated assumption that "separate lumps stand apart by far more
than one wall, so it never ties". Two lumps that are CONCENTRIC -- a ring
around a post, a lid over a base -- break that assumption outright: their
bounding-box centres are the SAME point.

Two ways that can go wrong:
  false REFUSAL  -- both result lumps land on seat 0, seat 1 gets 0 and reads
                    as "vanished", and a legitimate shell is blocked
                    (section 5's rejected-fix shape)
  false ACCEPT   -- a block's volume is added to the seat of a lump that DID
                    hollow, the sum still drops, and the P0 walks straight
                    through the guard built to stop it
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
import sketch, inspector

def flat_tops(part):
    out = []
    for l in part.solids():
        f = max((f for f in l.faces() if sketch.face_plane(f) is not None),
                key=lambda f: (round(f.center().Z, 6), f.area))
        c = f.center()
        out.append({"center": [c.X, c.Y, c.Z], "normal": list(f.normal_at(c))})
    return out

def seats(part):
    return [tuple(round(v, 4) for v in (s.bounding_box().center().X,
                                        s.bounding_box().center().Y,
                                        s.bounding_box().center().Z))
            for s in part.solids()]

def run(name, part, t, d="inside"):
    ins = [round(s.volume, 1) for s in part.solids()]
    print(f"\n--- {name}  t={t} {d}")
    print(f"    in : {len(ins)} lumps {ins}   bbox centres {seats(part)}")
    t0 = time.perf_counter()
    try:
        out = sketch.shell(part, t, flat_tops(part), d)
    except ValueError as e:
        print(f"    REFUSED ({time.perf_counter()-t0:.2f}s): {str(e)[:90]}")
        return None
    outs = [round(s.volume, 1) for s in out.solids()]
    block = [v for v in outs if any(abs(v - iv) < 1e-6 for iv in ins)]
    print(f"    out: {len(outs)} lumps {outs}  ({time.perf_counter()-t0:.2f}s) "
          f"closed={inspector.closed_shell(out)}"
          f"{'   *** A LUMP CAME BACK UNCHANGED: ' + str(block) + ' ***' if block else ''}")
    return out

print("=== A. CONCENTRIC lumps: a ring around a post (identical bbox centres) ===")
ring = b3d.Cylinder(20, 10) - b3d.Cylinder(15, 10)
post = b3d.Cylinder(5, 10)
tube_post = b3d.Part() + ring + post
print(f"  the two seats are {seats(tube_post)} -> a TIE" )
run("ring(20/15) + post(r5), both fit", tube_post, 1.5)
run("ring(20/15) + post(r5), both fit", tube_post, 1.5, "outside")

print("\n=== B. concentric where the POST cannot take the wall (2t >= its width) ===")
thin_post = b3d.Part() + ring + b3d.Cylinder(2, 10)      # r2 post, t=2 -> 2t=4 = its width
run("ring + THIN post r2", b3d.Part() + ring + b3d.Cylinder(2, 10), 2)

print("\n=== C. a LID over a BASE: same x,y centre, different z ===")
base = b3d.Pos(0, 0, 0) * b3d.Box(40, 40, 10)
lid = b3d.Pos(0, 0, 20) * b3d.Box(40, 40, 3)             # 3 mm lid, t=2 -> too flat
run("base 10mm + lid 3mm stacked", b3d.Part() + base + lid, 2)

print("\n=== D. OUTSIDE thick enough to MERGE two lumps into one ===")
for gap, t in ((5, 4), (4, 4), (3, 4), (2, 6)):
    two = b3d.Part() + b3d.Box(20,20,10) + b3d.Pos(20+gap, 0, 0) * b3d.Box(20,20,10)
    run(f"two boxes {gap}mm apart", two, t, "outside")
