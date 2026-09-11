"""Round TWO of the Shell review (667ccc0). The brief's risks 1 and 2:

1. assert_every_lump_open keys the openings against the INPUT BODY's faces and
   asks whether each LUMP's own .faces() contains one. Probed on linear_pattern
   in round one. Does the key still match through a POLAR pattern, a MIRROR, a
   CUT that severed a plate, and an IMPORTED STEP? A miss = a FALSE REFUSAL of
   a legitimate shell (section 5's rejected-fix shape).
2. solid.solids() is called OUTSIDE the op's try. What does it answer for a
   plain Solid, a Compound, a Part -- and can it RAISE (section 4's lesson)?
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
import blocks, sketch, pattern
from blocks import _shape_key

def hdr(s): print(f"\n=== {s} " + "=" * (60 - len(s)))

def lump_report(name, body):
    """For each lump, can EVERY one of its faces be found by key in the whole
    body's faces()?  And can each lump's top face be resolved from the body?"""
    try:
        lumps = body.solids()
    except Exception as e:
        print(f"  {name}: .solids() RAISED {type(e).__name__}: {e}")
        return
    whole = {_shape_key(f) for f in body.faces()}
    n_faces = sum(len(l.faces()) for l in lumps)
    missed = sum(1 for l in lumps for f in l.faces() if _shape_key(f) not in whole)
    # key collision across lumps?
    per = [{_shape_key(f) for f in l.faces()} for l in lumps]
    shared = 0
    for i in range(len(per)):
        for j in range(i + 1, len(per)):
            shared += len(per[i] & per[j])
    print(f"  {name}: type={type(body).__name__} lumps={len(lumps)} faces={n_faces} "
          f"lump-face keys missing from body.faces(): {missed}  cross-lump shared keys: {shared}")
    return lumps

def open_top_of_each(body):
    """Resolve the top face of every lump THROUGH THE BODY (what the op does:
    resolve_face on the whole part) and check assert_every_lump_open accepts."""
    lumps = body.solids()
    refs = []
    for l in lumps:
        top = max(l.faces(), key=lambda f: (round(f.center().Z, 3), f.area))
        c = top.center()
        refs.append({"center": [c.X, c.Y, c.Z], "normal": list(top.normal_at(c))})
    try:
        openings = sketch.shell_openings(body, refs)
    except Exception as e:
        print(f"    resolve of {len(refs)} tops FAILED: {type(e).__name__}: {e}")
        return
    print(f"    resolved {len(openings)} openings for {len(lumps)} lumps")
    try:
        sketch.assert_every_lump_open(body, openings)
        print("    assert_every_lump_open: ACCEPTED (correct — every lump open)")
    except ValueError as e:
        print(f"    assert_every_lump_open: *** FALSE REFUSAL *** {e}")

hdr("1. bodies in several lumps, four ways")
box = b3d.Box(20, 20, 10)

lin = pattern.linear_pattern(b3d.Part() + box, 3, dx=40)
lump_report("linear_pattern x3", lin); open_top_of_each(lin)

pol = pattern.polar_pattern(b3d.Part() + b3d.Pos(40, 0, 0) * b3d.Box(20, 20, 10), 3)
lump_report("polar_pattern x3", pol); open_top_of_each(pol)

mir = pattern.mirror(b3d.Part() + b3d.Pos(30, 0, 0) * b3d.Box(20, 20, 10), "YZ", join=True)
lump_report("mirror join=True", mir); open_top_of_each(mir)

plate = b3d.Part() + b3d.Box(80, 20, 10)
sev = plate - b3d.Box(6, 40, 40)          # a cut that SEVERS the plate in two
lump_report("severed plate", sev); open_top_of_each(sev)

hdr("2. an IMPORTED STEP of a multi-lump body")
import tempfile
p = os.path.join(tempfile.gettempdir(), "shell_r2_lumps.step")
b3d.export_step(lin, p)
imp = blocks.import_step(p)
lump_report("import_step of the pattern", imp); open_top_of_each(imp)

hdr("3. solids() on every input kind")
for name, obj in [("Solid", b3d.Solid.make_box(10, 10, 10)),
                  ("Part (1 solid)", b3d.Part() + box),
                  ("Compound of 3", lin),
                  ("Compound EMPTY", b3d.Compound(children=[])),
                  ("a 2D sketch face", b3d.Rectangle(10, 10).face())]:
    try:
        s = obj.solids()
        print(f"  {name:18s} -> {len(s)} solids   (type {type(obj).__name__})")
    except Exception as e:
        print(f"  {name:18s} -> RAISED {type(e).__name__}: {e}")

hdr("4. does the guard fire on the ONE case it is for?")
one_ref = [{"center": [0, 0, 5], "normal": [0, 0, 1]}]
op = sketch.shell_openings(lin, one_ref)
try:
    sketch.assert_every_lump_open(lin, op)
    print("  *** NOT REFUSED *** (the P0 is back)")
except ValueError as e:
    print(f"  refused, correctly: {e}")
