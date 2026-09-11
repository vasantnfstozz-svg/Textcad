"""Round TWO, the P0 through another door: assert_every_lump_open requires an
opening on EVERY lump -- but not that every lump actually HOLLOWS.

Round one's own probe recorded: "t = half the width, a face open -> 'succeeds'
and returns the body UNCHANGED". On a ONE-lump body the op's volume check
catches that (v_out >= v_in for Inside). On a MULTI-lump body the check is over
the WHOLE body, so a big lump that hollows correctly can pay for a small lump
that came back a SOLID BLOCK -- the original P0's exact symptom, with the new
guard fully satisfied.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
import sketch, inspector

def lumps_of(part): return [round(s.volume, 1) for s in part.solids()]

def top_refs(part):
    out = []
    for l in part.solids():
        f = max(l.faces(), key=lambda f: (round(f.center().Z, 3), f.area))
        c = f.center()
        out.append({"center": [c.X, c.Y, c.Z], "normal": list(f.normal_at(c))})
    return out

def trial(name, part, t, direction="inside"):
    refs = top_refs(part)
    print(f"\n--- {name}  t={t}  {direction}")
    print(f"    in : lumps {lumps_of(part)}  total {part.volume:.1f}")
    try:
        out = sketch.shell(part, t, refs, direction)
    except ValueError as e:
        print(f"    REFUSED: {e}")
        return
    print(f"    out: lumps {lumps_of(out)}  total {out.volume:.1f}  "
          f"closed={inspector.closed_shell(out)}  health={inspector.health(out) if hasattr(inspector,'health') else '?'}")
    # per-lump oracle: a correctly shelled 20x20xH box, top open, walls t
    for i, s in enumerate(out.solids()):
        bb = s.bounding_box()
        print(f"      lump {i}: vol {s.volume:9.1f}  bbox "
              f"{bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f}  "
              f"solids-in-lump {len(s.solids())}  faces {len(s.faces())}")

def shelled_box_volume(w, d, h, t):
    """top open, walls inside: outer minus the cavity (w-2t)(d-2t)(h-t)"""
    return w*d*h - (w-2*t)*(d-2*t)*(h-t)

print("=== A. two lumps, ONE TOO THIN for the wall (t >= half its height) ===")
big  = b3d.Pos(0, 0, 0)  * b3d.Box(20, 20, 10)
thin = b3d.Pos(40, 0, 0) * b3d.Box(20, 20, 3)      # 3 mm tall, t = 2
two = b3d.Part() + big + thin
print(f"  oracle if BOTH shelled at t=2: big {shelled_box_volume(20,20,10,2):.1f}  "
      f"thin {shelled_box_volume(20,20,3,2):.1f}")
trial("big 10mm + thin 3mm", two, 2)

print("\n=== B. same, but the thin lump is too NARROW (t >= half its width) ===")
narrow = b3d.Pos(40, 0, 0) * b3d.Box(3, 20, 10)
twoB = b3d.Part() + big + narrow
trial("big 20mm wide + narrow 3mm wide", twoB, 2)

print("\n=== C. OUTSIDE direction, same mixed pair ===")
trial("big + thin, outside", b3d.Part() + big + thin, 2, "outside")

print("\n=== D. control: two IDENTICAL lumps (round one's measured-good case) ===")
same = b3d.Part() + big + b3d.Pos(40, 0, 0) * b3d.Box(20, 20, 10)
trial("two identical 20x20x10", same, 2)
