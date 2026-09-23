"""PROBE - review of the Text sketch entity (d3c8c85), 2026-09-23.

  A. Characters Arial has no glyph for (an emoji, CJK, a symbol): does the
     kernel give nothing (a sentence), a fallback glyph, or a BOX (the font's
     "notdef" rectangle) that would be milled as a slab and called a word?
  B. `text` given as a number (2026) - the AI writes that.
  C. A subtract word straddling the plate's edge.

Run: python probes/memcap.py --gb 4 --timeout 600 -- python probes/text_review_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sketch as sk                # noqa: E402

print("== A. glyphs Arial lacks")
for word in ("A", "AB", "été", "日本", "\U0001F600", "A\U0001F600B", "☃",
             "Ωμ", "नम"):
    try:
        s = sk._text_faces({"kind": "text", "text": word, "size": 10})
        faces = s.faces()
        boxes = sum(1 for f in faces
                    if len(f.edges()) == 4 and not f.inner_wires()
                    and all(e.geom_type.name == "LINE" for e in f.edges()))
        bb = s.bounding_box()
        print(f"   {word!r}: {len(faces)} faces, {boxes} plain rectangles, area {s.area:.2f}, "
              f"box {bb.size.X:.2f} x {bb.size.Y:.2f}")
    except ValueError as e:
        print(f"   {word!r}: sentence: {e}")

print("== B. text as a number")
for v in (2026, 3.5, True):
    try:
        s = sk._text_faces({"kind": "text", "text": v, "size": 10})
        print(f"   {v!r}: {len(s.faces())} faces")
    except ValueError as e:
        print(f"   {v!r}: sentence: {e}")

print("== C. a subtract word over the plate's edge")
ents = [{"kind": "rectangle", "w": 40, "h": 20, "mode": "add"},
        {"kind": "text", "text": "EDGE", "size": 8, "x": 20, "y": 0, "mode": "subtract"}]
s = sk.make_sketch(plane="XY", entities=ents)
print(f"   plate 800 - word over the edge: area {s.area:.2f}, faces {len(s.faces())}")
