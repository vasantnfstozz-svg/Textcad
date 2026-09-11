"""Is there an OUTSIDE-direction door to the same "a lump came back untouched"?
Outside grows every lump, so there is no "the wall does not fit" failure -- but
round one's P0 WAS an outside case (blocks grown by 2 mm), so measure before
deciding the fix guards one direction or both."""
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

def run(name, part, t, d):
    ins = [round(s.volume,1) for s in part.solids()]
    try:
        out = sketch.shell(part, t, tops(part), d)
    except ValueError as e:
        print(f"  {name:34s} t={t:<5} {d:7s} REFUSED: {str(e)[:55]}"); return
    outs = [round(s.volume,1) for s in out.solids()]
    block = [v for v in outs if any(abs(v-iv) < 1e-6 for iv in ins)]
    print(f"  {name:34s} t={t:<5} {d:7s} in {ins} -> {outs} "
          f"lumps {len(ins)}->{len(outs)}{'  *** UNCHANGED ' + str(block) + ' ***' if block else ''}")

big = b3d.Box(20,20,10)
print("=== outside: hostile mixed pairs ===")
for w in (0.5, 1.0, 3.0, 4.0):
    run(f"big + {w}mm-wide lump", b3d.Part() + big + b3d.Pos(40,0,0)*b3d.Box(w,20,10), 2, "outside")
for t in (0.1, 5, 12, 30):
    run("big + narrow 3mm", b3d.Part() + big + b3d.Pos(40,0,0)*b3d.Box(3,20,10), t, "outside")

print("\n=== outside: a wall thick enough to MERGE two lumps ===")
run("two boxes 5mm apart", b3d.Part() + big + b3d.Pos(25,0,0)*b3d.Box(20,20,10), 4, "outside")

print("\n=== inside: can a lump VANISH, or SPLIT? ===")
for t in (0.5, 1, 2, 3, 4, 4.9):
    run("big + 12mm-wide lump", b3d.Part() + big + b3d.Pos(40,0,0)*b3d.Box(12,20,10), t, "inside")
print("\n=== inside: a lump whose HEIGHT is the tight one ===")
for t in (2, 3, 4, 5, 6):
    run("big10 + flat 20x20x4", b3d.Part() + big + b3d.Pos(40,0,0)*b3d.Box(20,20,4), t, "inside")
