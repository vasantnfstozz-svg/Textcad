"""Is the concentric refusal FALSE (the kernel shelled both lumps fine), and
what is the right identity key to replace the bbox CENTRE with?

The centre ties for concentric lumps. The whole BOUNDING BOX does not: a ring
r20/r15 boxes 40x40x10 and the post r5 inside it boxes 10x10x10 -- same centre,
different box. So "is this result lump IDENTICAL to some input lump (same box,
same volume)" needs no pairing at all, and an exact match is the only thing it
can ever fire on."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
import sketch, inspector

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

def raw_shell(part, t, d="inside"):
    """what the KERNEL returns, with the round-two guard bypassed"""
    openings = sketch.shell_openings(part, tops(part))
    amount = -t if d == "inside" else t
    return b3d.offset(part, amount=amount, openings=openings, kind=b3d.Kind.INTERSECTION)

print("=== 1. the concentric case the guard refuses: what did the kernel do? ===")
ring = b3d.Cylinder(20, 10) - b3d.Cylinder(15, 10)
tube_post = b3d.Part() + ring + b3d.Cylinder(5, 10)
ins = tube_post.solids()
out = raw_shell(tube_post, 1.5)
print(f"  in  lumps: {[round(s.volume,2) for s in ins]}")
print(f"      boxes: {[tuple(round(v,2) for v in bx(s)) for s in ins]}")
print(f"  out lumps: {[round(s.volume,2) for s in out.solids()]}")
print(f"      boxes: {[tuple(round(v,2) for v in bx(s)) for s in out.solids()]}")
print(f"  watertight={inspector.closed_shell(out)} health={inspector.health(out)}")
import math
print(f"  oracle ring  shelled (annulus, top open, t=1.5): "
      f"{math.pi*(400-225)*10 - math.pi*(18.5**2-16.5**2)*8.5:.2f}")
print(f"  oracle post  shelled (r5, top open, t=1.5): "
      f"{math.pi*25*10 - math.pi*3.5**2*8.5:.2f}")
print("  -> both lumps hollowed?  the guard REFUSED this.")

print("\n=== 2. how exact is an UNTOUCHED lump's identity? (tolerance choice) ===")
for name, second, t in (("narrow 3x20x10", b3d.Box(3,20,10), 2),
                        ("flat 20x20x4",   b3d.Box(20,20,4), 5),
                        ("w=4.0 (8 faces)", b3d.Box(4,20,10), 2)):
    body = b3d.Part() + b3d.Box(20,20,10) + b3d.Pos(40,0,0)*second
    ins = body.solids(); o = raw_shell(body, t)
    for j, piece in enumerate(o.solids()):
        for i, lump in enumerate(ins):
            dv = abs(piece.volume - lump.volume)
            db = max(abs(a-b) for a, b in zip(bx(piece), bx(lump)))
            if dv < 1.0 and db < 1.0:
                print(f"  {name:16s} out[{j}] vs in[{i}]: "
                      f"d(volume)={dv:.3e}  d(box)={db:.3e}  vol={lump.volume:.1f}")

print("\n=== 3. does the (box, volume) key still tell the GOOD cases apart? ===")
for name, body, t, d in (
        ("two identical",   b3d.Part()+b3d.Box(20,20,10)+b3d.Pos(40,0,0)*b3d.Box(20,20,10), 2, "inside"),
        ("ring + post",     tube_post, 1.5, "inside"),
        ("ring + post out", tube_post, 1.5, "outside"),
        ("big + 12mm",      b3d.Part()+b3d.Box(20,20,10)+b3d.Pos(40,0,0)*b3d.Box(12,20,10), 2, "inside")):
    body_ins = body.solids(); o = raw_shell(body, t, d)
    hits = [(round(p.volume,2), round(l.volume,2)) for p in o.solids() for l in body_ins
            if abs(p.volume-l.volume) <= 1e-6 and max(abs(a-b) for a,b in zip(bx(p),bx(l))) <= 1e-6]
    print(f"  {name:16s} {d:7s} identical-lump hits: {hits or 'none -> builds'}")
