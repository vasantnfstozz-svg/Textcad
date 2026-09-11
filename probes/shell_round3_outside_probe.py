"""ROUND THREE risk 3: the identity guard is now direction-agnostic, so probe
OUTSIDE (and INSIDE) on the bodies round two did not reach -- nested lumps, a
lump that is ALREADY hollow, an imported STEP, and a pattern of a shelled boss.
A false refusal is as bad as a missed block."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
import sketch, blocks, pattern, inspector

def tops(part):
    out = []
    for l in part.solids():
        f = max((f for f in l.faces() if sketch.face_plane(f) is not None),
                key=lambda f: (round(f.center().Z, 6), f.area))
        c = f.center()
        out.append({"center": [c.X, c.Y, c.Z], "normal": list(f.normal_at(c))})
    return out

def run(name, part, t, d):
    ins = [round(s.volume, 1) for s in part.solids()]
    try:
        out = sketch.shell(part, t, tops(part), d)
    except ValueError as e:
        print(f"  {name:34s} t={t:<4} {d:7s} REFUSED: {str(e)[:58]}")
        return
    outs = [round(s.volume, 1) for s in out.solids()]
    same = [v for v in outs if any(abs(v - iv) < 1e-6 for iv in ins)]
    print(f"  {name:34s} t={t:<4} {d:7s} {ins} -> {outs} "
          f"closed={inspector.closed_shell(out)} health={inspector.health(out)}"
          f"{'  *** UNCHANGED ' + str(same) + ' ***' if same else ''}")

print("=== nested / concentric, both directions, whole ladder ===")
ring = b3d.Cylinder(20, 10) - b3d.Cylinder(15, 10)
conc = b3d.Part() + ring + b3d.Cylinder(5, 10)
for t in (0.25, 0.5, 1, 1.5, 2, 3):
    run("ring + post", conc, t, "inside")
for t in (0.25, 1, 2):
    run("ring + post", conc, t, "outside")

print("\n=== a lump that is ALREADY hollow (shell of a shelled body) ===")
once = sketch.shell(b3d.Part() + b3d.Box(30, 30, 20), 2, [{"center": [0, 0, 10], "normal": [0, 0, 1]}])
twice = b3d.Part() + once + b3d.Pos(60, 0, 0) * b3d.Box(20, 20, 10)
run("hollow box + solid boss", twice, 1, "inside")
run("hollow box + solid boss", twice, 1, "outside")

print("\n=== an IMPORTED STEP of a multi-lump body ===")
p = os.path.join(tempfile.gettempdir(), "r3.step")
b3d.export_step(b3d.Part() + b3d.Box(20,20,10) + b3d.Pos(40,0,0)*b3d.Box(3,20,10), p)
imp = blocks.import_step(p)
run("imported big + narrow", imp, 2, "inside")
run("imported big + narrow", imp, 1, "inside")
run("imported big + narrow", imp, 2, "outside")

print("\n=== a PATTERN of a shelled boss ===")
boss = sketch.shell(b3d.Part() + b3d.Box(20, 20, 10), 2, [{"center": [0,0,5], "normal": [0,0,1]}])
pat = pattern.linear_pattern(boss, count=3, dx=40)
run("3 shelled bosses", pat, 1, "inside")
run("3 shelled bosses", pat, 1, "outside")
