"""Confirm the round-two P0: on a MULTI-LUMP body with an opening on every lump
(so assert_every_lump_open is satisfied), a lump the wall thickness does not fit
comes back a RAW SOLID BLOCK and every check passes green.

Also: is the SAME body as ONE lump refused?  (If yes, the whole-body volume
check is the guard that multi-lump defeats.)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
import sketch, inspector, pattern

def top_refs(part):
    out = []
    for l in part.solids():
        f = max(l.faces(), key=lambda f: (round(f.center().Z, 3), f.area))
        c = f.center()
        out.append({"center": [c.X, c.Y, c.Z], "normal": list(f.normal_at(c))})
    return out

def run(name, part, t, d="inside"):
    ins = [round(s.volume, 1) for s in part.solids()]
    try:
        out = sketch.shell(part, t, top_refs(part), d)
    except ValueError as e:
        print(f"  {name:42s} t={t} {d:7s} REFUSED: {str(e)[:70]}")
        return None
    outs = [(round(s.volume, 1), len(s.faces())) for s in out.solids()]
    block = [i for i, (v, nf) in enumerate(outs) if any(abs(v - iv) < 1e-6 for iv in ins)]
    print(f"  {name:42s} t={t} {d:7s} in {ins} -> out {outs} "
          f"closed={inspector.closed_shell(out)} health={inspector.health(out)}"
          f"{'   *** LUMP(S) ' + str(block) + ' UNCHANGED = SOLID BLOCK ***' if block else ''}")
    return out

print("=== 1. the narrow lump, alone (ONE lump) — is the op's own check enough? ===")
run("narrow 3x20x10 alone", b3d.Part() + b3d.Box(3, 20, 10), 2)
run("narrow 3x20x10 alone", b3d.Part() + b3d.Box(3, 20, 10), 2, "outside")

print("\n=== 2. the SAME narrow lump beside a big one (TWO lumps) ===")
big = b3d.Box(20, 20, 10)
run("big + narrow", b3d.Part() + big + b3d.Pos(40,0,0)*b3d.Box(3,20,10), 2)
run("big + narrow", b3d.Part() + big + b3d.Pos(40,0,0)*b3d.Box(3,20,10), 2, "outside")

print("\n=== 3. the REALISTIC shape: a linear_pattern of a narrow rib ===")
rib = b3d.Part() + b3d.Box(4, 30, 12)
ribs = pattern.linear_pattern(rib, 4, dx=15)
run("4 ribs 4x30x12", ribs, 2)
run("4 ribs 4x30x12", ribs, 1.5, )
run("4 ribs 4x30x12", ribs, 1)

print("\n=== 4. where is the edge? one big lump + a lump of width W, t=2 ===")
for w in (3.0, 3.9, 4.0, 4.1, 5.0, 6.0):
    run(f"big + {w}mm-wide lump", b3d.Part() + big + b3d.Pos(40,0,0)*b3d.Box(w,20,10), 2)

print("\n=== 5. three patterned bosses, the MIDDLE one too narrow ===")
mix = b3d.Part() + b3d.Box(20,20,10) + b3d.Pos(40,0,0)*b3d.Box(3.5,20,10) + b3d.Pos(80,0,0)*b3d.Box(20,20,10)
run("20 / 3.5 / 20", mix, 2)
