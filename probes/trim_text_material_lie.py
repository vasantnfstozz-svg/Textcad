r"""Trim reports MATERIAL where the builder has a hole — on a Text entity.

`sketch_trim` models an entity as ONE face and only that face's OUTER wire.
That held for the 7 kinds the user's 40 designs contain (censused by
probes/trim_corpus_census.py: 0 multi-face entities, 0 holed faces).  The Text
entity (d3c8c85) breaks BOTH halves: a word is one face per glyph piece, and a
glyph such as O/A/B/8 has holes.  `_entity_face` keeps `faces()[0]`, `_outline`
keeps its outer wire, so every later decision is made about one solid letter.

This measures the lie the same way the module's own docstring measures its
old one: a POINT, what Trim says about it, and what the builder leaves there.

    C:\Python314\python.exe probes/trim_text_material_lie.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sketch as sk          # noqa: E402
import sketch_trim as tr     # noqa: E402

PLATE = {"kind": "rectangle", "mode": "add", "x": 0, "y": 0, "w": 60, "h": 30}
TEXT = {"kind": "text", "mode": "subtract", "x": 0, "y": 0, "text": "AB",
        "size": 14}


def builder_material(entities, x, y):
    """The BUILDER's answer at one point: is there material there?"""
    shape = sk.compose(entities, note=False)
    return any(tr._face_contains(f, x, y) for f in shape.faces())


def main():
    ents = [dict(PLATE), dict(TEXT)]
    faces = sk._entity(TEXT).faces()
    print(f"text 'AB' builds {len(faces)} faces; sketch_trim keeps faces()[0] "
          f"(area {faces[0].area:.4f}, bbox x "
          f"{faces[0].bounding_box().min.X:.2f}..{faces[0].bounding_box().max.X:.2f})")

    outlines = [tr._outline(e, i) for i, e in enumerate(ents)]
    idxs = [0, 1]

    print("\npoint                     Trim says   builder says")
    probes = []
    # a point inside the SECOND glyph ('A'), which Trim never sampled
    g1 = faces[1]
    bb = g1.bounding_box()
    for xx in [bb.min.X + 0.15 * (bb.max.X - bb.min.X) + k * 0.3
               for k in range(20)]:
        for yy in (bb.min.Y + 0.25 * (bb.max.Y - bb.min.Y),):
            if tr._face_contains(g1, xx, yy):
                probes.append(("inside glyph 2 ('A')", xx, yy))
                break
        if probes:
            break
    # a point inside the HOLE of glyph 1 ('B'), which Trim treats as solid
    f0 = faces[0]
    ow = f0.outer_wire()
    holes = [w for w in f0.wires() if not w.is_same(ow)]
    if holes:
        hb = holes[0].bounding_box()
        probes.append(("inside a hole of glyph 1",
                       (hb.min.X + hb.max.X) / 2, (hb.min.Y + hb.max.Y) / 2))

    bad = 0
    for label, x, y in probes:
        t = tr._material_at(ents, outlines, idxs, x, y)
        b = builder_material(ents, x, y)
        flag = "" if t == b else "   <-- WRONG"
        if t != b:
            bad += 1
        print(f"{label:26s} ({x:6.2f},{y:6.2f})  {str(t):5s}       "
              f"{str(b):5s}{flag}")

    print(f"\n{bad} of {len(probes)} probe points are classified wrongly by "
          f"Trim.")

    print("\nand the union Trim subtracts material from:")
    print(f"   _union_faces([plate, text])          = "
          f"{sum(f.area for f in tr._union_faces(ents, idxs).faces()):.4f} mm2")
    whole = None
    for e in ents:
        s = sk._entity(e)
        whole = s if whole is None else whole + s
    print(f"   every face of every entity            = "
          f"{sum(f.area for f in whole.faces()):.4f} mm2")

    print("\nand what the tool offers the user:")
    print(f"   sk.entity_outlines(text) draws        = "
          f"{len(sk.entity_outlines(TEXT))} loops")
    pieces = tr.trim_pieces(ents)
    for p in pieces:
        if p["ent"] == 1:
            print(f"   trim piece {p['id']} covers            = 1 loop, "
                  f"{len(p['pts'])} points")

    print("\nand a circle that visibly crosses glyph 2:")
    ents2 = [dict(TEXT, mode="add"),
             {"kind": "circle", "mode": "add", "x": -5, "y": 0, "r": 3}]
    for p in tr.trim_pieces(ents2):
        print(f"   piece {p['id']} ent={p['ent']} whole={p['whole']}")
    try:
        r = tr.trim_apply(ents2, "1:0")
        print(f"   click 1:0 -> {r['message']}")
    except ValueError as ex:
        print(f"   click 1:0 -> REFUSED {ex}")


if __name__ == "__main__":
    main()
