"""What is the CHEAPEST, most exact signal that the kernel handed a lump back
UNTOUCHED?  (Deciding the fix: a false refusal is section 5's rejected-fix
shape, so the test must be one a correctly-shelled lump can never trip.)

  a) _shape_key identity — did offset() pass the lump through by reference?
  b) bounding box + volume
  c) volume alone, per lump paired by bbox
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
import sketch, blocks
from blocks import _shape_key

def tops(part):
    out = []
    for l in part.solids():
        f = max(l.faces(), key=lambda f: (round(f.center().Z, 3), f.area))
        c = f.center()
        out.append({"center": [c.X, c.Y, c.Z], "normal": list(f.normal_at(c))})
    return out

def bb(s):
    b = s.bounding_box()
    return tuple(round(x, 6) for x in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z))

for label, part, t in [
    ("big + narrow (lump 1 untouched)", b3d.Part() + b3d.Box(20,20,10) + b3d.Pos(40,0,0)*b3d.Box(3,20,10), 2),
    ("two identical (both shelled)",    b3d.Part() + b3d.Box(20,20,10) + b3d.Pos(40,0,0)*b3d.Box(20,20,10), 2),
]:
    print(f"\n=== {label} ===")
    ins = part.solids()
    out = sketch.shell(part, t, tops(part), "inside")
    outs = out.solids()
    in_keys = {_shape_key(s): i for i, s in enumerate(ins)}
    in_bb   = {bb(s): i for i, s in enumerate(ins)}
    for j, s in enumerate(outs):
        k, b = _shape_key(s), bb(s)
        print(f"  out lump {j}: vol {s.volume:9.1f}  "
              f"shape_key match -> {in_keys.get(k, '-')}   bbox match -> {in_bb.get(b, '-')}  "
              f"(in vol there: {ins[in_bb[b]].volume:.1f})" if b in in_bb else
              f"  out lump {j}: vol {s.volume:9.1f}  shape_key match -> {in_keys.get(k,'-')}  bbox match -> NONE")

print("\n=== can an INSIDE shell leave a lump's bounding box, or split a lump? ===")
# an L-shaped lump and a lump with a thin neck, shelled inside
L = (b3d.Part() + b3d.Box(40,10,10) + b3d.Pos(15,15,0)*b3d.Box(10,40,10))
two = b3d.Part() + L + b3d.Pos(80,0,0)*b3d.Box(20,20,10)
ins = two.solids()
print(f"  in : {len(ins)} lumps {[round(s.volume,1) for s in ins]}  bboxes {[bb(s) for s in ins]}")
o = sketch.shell(two, 1.5, tops(two), "inside")
print(f"  out: {len(o.solids())} lumps {[round(s.volume,1) for s in o.solids()]}")
for j, s in enumerate(o.solids()):
    inside_of = [i for i, p in enumerate(ins)
                 if bb(p)[0]-1e-6 <= bb(s)[0] and bb(p)[3]+1e-6 >= bb(s)[3]
                 and bb(p)[1]-1e-6 <= bb(s)[1] and bb(p)[4]+1e-6 >= bb(s)[4]]
    print(f"    out lump {j} vol {s.volume:9.1f} sits inside input lump(s) {inside_of}")
