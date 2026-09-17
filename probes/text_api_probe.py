"""Text entity probe 1: build123d Text on this Windows box — fonts, holes in
letters (O, B), spaces, digits, an empty string, tiny sizes, alignment,
composition with a rectangle (engraving), validity and areas."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d  # noqa: E402
from build123d import Align, BuildSketch, Rectangle, Text  # noqa: E402
from OCP.BRepCheck import BRepCheck_Analyzer  # noqa: E402

import inspector  # noqa: E402


def make(txt, size, **kw):
    with BuildSketch() as s:
        Text(txt, size, align=(Align.CENTER, Align.CENTER), **kw)
    return s.sketch


def report(label, txt, size, **kw):
    try:
        sk = make(txt, size, **kw)
        faces = sk.faces()
        holes = sum(len(f.inner_wires()) for f in faces)
        bb = sk.bounding_box()
        valid = all(BRepCheck_Analyzer(f.wrapped).IsValid() for f in faces)
        print(f"{label:34s} faces {len(faces):2d} holes {holes:2d} area {sk.area:9.3f} "
              f"bbox {bb.size.X:.2f}x{bb.size.Y:.2f} centre ({bb.center().X:.2f},{bb.center().Y:.2f}) valid {valid}")
        return sk
    except Exception as e:
        print(f"{label:34s} EXC {type(e).__name__}: {str(e)[:80]}")


report("default font 'Hi' 10", "Hi", 10)
report("'OBA' 10 (holes)", "OBA", 10)
report("'TEXTCAD 2026' 8", "TEXTCAD 2026", 8)
report("two words 'a b' 10", "a b", 10)
report("empty string", "", 10)
report("spaces only", "   ", 10)
report("size 0.5 'Hi'", "Hi", 0.5)
report("size 0.1 'Hi'", "Hi", 0.1)
report("size 100 'M'", "M", 100)
for font in ("Arial", "Times New Roman", "Courier New", "Consolas", "NoSuchFont123"):
    report(f"font {font} 'Hi' 10", "Hi", 10, font=font)
report("bold 'Hi'", "Hi", 10, font_style=b3d.FontStyle.BOLD)
report("italic 'Hi'", "Hi", 10, font_style=b3d.FontStyle.ITALIC)
# is Text a Sketch of finished faces (holes already cut)? composing with + / -
o = make("O", 10)
print("O: faces", len(o.faces()), "inner wires", [len(f.inner_wires()) for f in o.faces()],
      "area", round(o.area, 3))
plate = Rectangle(40, 20)
engraved = plate - make("AB", 10)
print("plate - 'AB': area", round(engraved.area, 3), "= plate", round(plate.area, 3), "- text",
      round(make("AB", 10).area, 3), "faces", len(engraved.faces()), "health of extrude",
      inspector.health(b3d.extrude(engraved, amount=2)))
raised = plate + make("AB", 10)
print("plate + 'AB': area", round(raised.area, 3), "faces", len(raised.faces()))
# alignment: where does the text sit relative to (0, 0)?
for al in ((Align.MIN, Align.MIN), (Align.CENTER, Align.CENTER), (Align.MIN, Align.CENTER)):
    with BuildSketch() as s:
        Text("Hi", 10, align=al)
    bb = s.sketch.bounding_box()
    print("align", al, "bbox", (round(bb.min.X, 2), round(bb.min.Y, 2)), (round(bb.max.X, 2), round(bb.max.Y, 2)))
# rotation + placement through the same route _entity uses
t = make("Hi", 10).rotate(b3d.Axis.Z, 30)
t = b3d.Pos(20, 5) * t
print("rotated 30 + moved (20,5): centre", t.bounding_box().center(), "area", round(t.area, 3))
# extrude text: one body per piece?
p = b3d.extrude(make("TEXTCAD", 10), amount=3)
print("extrude 'TEXTCAD' 3mm: solids", len(p.solids()), "vol", round(p.volume, 3), "health", inspector.health(p))
# outline points the sketcher could draw: each face's outer + inner wires sampled
n_pts = sum(len(w.edges()) for f in make("TEXTCAD 2026", 8).faces() for w in f.wires())
print("edges in 'TEXTCAD 2026':", n_pts)
