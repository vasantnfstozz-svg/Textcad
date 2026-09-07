"""probes/multibody_step_probe.py — can ONE STEP file carry EVERY body of a
multi-body design, exactly, and can we prove it after writing?

Why this probe exists (2026-09-07, user bug report): "exporting step file of a
design, and putting into another software, i can see only half part of design
and rest of them are missing". Measured cause: Document.to_step() exports
Document.result(), which is ONE body — the last built leaf — while
leaf_solid_ids() (and the viewport) carry ALL of them. designs/my-part-6 has
four leaves totalling 424161.3 mm3; the STEP measured n_solids=1, volume 585.6.

So the fix must write several solids into one STEP. Never from memory:
build123d 0.11.1 has NO Compound.make_compound (probed), the constructor takes
an Iterable[Shape]. What this probe must prove, section by section:

  1  Compound(list_of_solids) is built, and reports every solid.
  2  export_step of that Compound writes a file a reader sees as N solids
     whose total volume is the sum — measured with inspector, not assumed.
  3  A ONE-body design wrapped the same way still reads as exactly 1 solid
     (no regression for the normal case, no stray assembly wrapper).
  4  The bodies stay EXACT BREP, not tessellated — a STEP round-trip through
     blocks.import_step returns planar faces and the same volume.
  5  Disjoint bodies stay disjoint (the export must not fuse them) and
     TOUCHING bodies also survive as separate solids.
  6  The real failing design (designs/my-part-6) exports whole.
  7  inspector.measure on the written file is a usable PROOF for the API
     response: n_solids and volume of the WHOLE design.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d

import blocks
import inspector

OUT = os.environ.get("PROBE_OUT", os.path.dirname(os.path.abspath(__file__)))


def p(section, **facts):
    print(f"--- {section}")
    for k, v in facts.items():
        print(f"    {k} = {v}")


# 1 -- does the constructor take a plain list, and keep every solid? ----------
a = b3d.Box(20, 10, 5)                       # vol 1000
b = b3d.Pos(100, 0, 0) * b3d.Box(4, 4, 4)    # vol 64, far away
comp = b3d.Compound([a, b])
p("1 Compound(list)",
  type=type(comp).__name__,
  n_solids=len(comp.solids()),
  volume=round(comp.volume, 3),
  expected_volume=1000 + 64,
  bbox=tuple(round(v, 2) for v in comp.bounding_box().size))

# 2 -- write it and MEASURE the file (never trust the writer) -----------------
two = os.path.join(OUT, "_probe_two_bodies.step")
ok = b3d.export_step(comp, two)
m = inspector.measure(two)
p("2 export_step(Compound) then measure the FILE",
  returned=ok,
  exists=os.path.exists(two),
  n_solids=m.get("n_solids"),
  volume=m.get("volume"),
  size=m.get("size"),
  expected="n_solids 2, volume 1064.0")

# 3 -- the single-body case must not regress ---------------------------------
one = os.path.join(OUT, "_probe_one_body.step")
b3d.export_step(b3d.Compound([a]), one)
m1 = inspector.measure(one)
bare = os.path.join(OUT, "_probe_bare_body.step")
b3d.export_step(a, bare)
mb = inspector.measure(bare)
p("3 one body, wrapped vs bare",
  wrapped_n_solids=m1.get("n_solids"), wrapped_volume=m1.get("volume"),
  bare_n_solids=mb.get("n_solids"), bare_volume=mb.get("volume"),
  same=(m1.get("n_solids") == mb.get("n_solids")
        and abs(m1.get("volume") - mb.get("volume")) < 1e-6))

# 4 -- still EXACT BREP after a round trip, not a mesh -----------------------
back = blocks.import_step(two, 1.0)
kinds = sorted({f.geom_type.name for f in back.faces()})
p("4 round trip through import_step",
  n_solids=len(back.solids()),
  volume=round(back.volume, 3),
  n_faces=len(back.faces()),
  face_kinds=kinds,
  exact=("PLANE" in kinds and "BSPLINE" not in kinds))

# 5 -- disjoint stays disjoint; touching bodies stay separate ----------------
touch = b3d.Compound([a, b3d.Pos(12, 0, 0) * b3d.Box(4, 10, 5)])  # shares a face
tf = os.path.join(OUT, "_probe_touching.step")
b3d.export_step(touch, tf)
mt = inspector.measure(tf)
p("5 touching bodies are not fused by the writer",
  in_memory_solids=len(touch.solids()),
  file_n_solids=mt.get("n_solids"),
  file_volume=mt.get("volume"),
  expected="2 solids, volume 1200.0 (1000 + 200)")

# 6 -- the design that actually failed ---------------------------------------
import document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
design = os.path.join(ROOT, "designs", "my-part-6.tcad.json")
if os.path.exists(design):
    d = document.Document.load(design)
    d.rebuild()
    leaves = d.leaf_solid_ids()
    total = sum(d._parts[f].volume for f in leaves)
    whole = b3d.Compound([d._parts[f] for f in leaves])
    wf = os.path.join(OUT, "_probe_my_part_6.step")
    b3d.export_step(whole, wf)
    mw = inspector.measure(wf)
    p("6 designs/my-part-6 exported WHOLE",
      leaves=leaves,
      design_total_volume=round(total, 1),
      file_n_solids=mw.get("n_solids"),
      file_volume=mw.get("volume"),
      file_size=mw.get("size"),
      volume_matches=abs(mw.get("volume") - total) < 1.0)
else:
    p("6 designs/my-part-6", skipped="design file not present")

# 7 -- is measure() of the file a good enough PROOF for the API response? ----
p("7 measure(file) keys usable as export proof",
  keys=sorted(m.keys()))
