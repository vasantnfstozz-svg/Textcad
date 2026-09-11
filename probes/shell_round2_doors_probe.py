"""How many doors lead to "one lump came back a solid block, green row"?

  door 1: openings on every lump, one lump too narrow for the wall   (measured)
  door 2: NO openings at all (the difference route) — assert_every_lump_open
          returns early there, and round one only measured IDENTICAL lumps
  door 3: one lump comes back a NON-WATERTIGHT open shell — is closed_shell
          whole-body or per-lump?
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
import sketch, inspector

def tops(part):
    out = []
    for l in part.solids():
        f = max(l.faces(), key=lambda f: (round(f.center().Z, 3), f.area))
        c = f.center()
        out.append({"center": [c.X, c.Y, c.Z], "normal": list(f.normal_at(c))})
    return out

def run(name, part, t, refs, d="inside"):
    ins = [round(s.volume, 1) for s in part.solids()]
    try:
        out = sketch.shell(part, t, refs, d)
    except ValueError as e:
        print(f"  {name:38s} t={t} {d:7s} REFUSED: {str(e)[:60]}")
        return
    outs = [(round(s.volume,1), len(s.faces())) for s in out.solids()]
    block = [i for i,(v,n) in enumerate(outs) if any(abs(v-iv) < 1e-6 for iv in ins)]
    print(f"  {name:38s} t={t} {d:7s} in {ins} -> {outs} closed={inspector.closed_shell(out)} "
          f"health={inspector.health(out)}{'  *** BLOCK at '+str(block)+' ***' if block else ''}")

big = b3d.Box(20, 20, 10)
mixed = b3d.Part() + big + b3d.Pos(40,0,0)*b3d.Box(3,20,10)

print("=== door 2: NO openings (the difference route), MIXED lumps ===")
run("big + narrow, closed hollow", mixed, 2, None)
run("big + narrow, closed hollow", mixed, 2, None, "outside")
print("  control, identical lumps (round one's measured case):")
same = b3d.Part() + big + b3d.Pos(40,0,0)*b3d.Box(20,20,10)
run("two identical, closed hollow", same, 2, None)
print("  and the narrow lump ALONE, closed hollow:")
run("narrow alone, closed hollow", b3d.Part() + b3d.Box(3,20,10), 2, None)

print("\n=== door 3: is closed_shell whole-body or per-lump? ===")
# t past the far wall on ONE lump only: round one's probe recorded that as
# "an OPEN SHELL the kernel calls a success"
tall = b3d.Part() + b3d.Box(60,60,40) + b3d.Pos(120,0,0)*b3d.Box(20,20,10)
run("big60 + small20, t=6", tall, 6, tops(tall))
run("big60 + small20, t=9", tall, 9, tops(tall))

print("\n=== how many of the 50 live designs even have a multi-lump body? ===")
