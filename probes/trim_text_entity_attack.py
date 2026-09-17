"""What the author's 324-sketch identity corpus does not contain: a TEXT entity.

The Text sketch entity landed in d3c8c85, AFTER the 40 designs the identity
probe swept, and it is the first entity kind whose `sk._entity()` returns MORE
THAN ONE FACE (one per glyph piece).  `sketch_trim._entity_face` takes
`.faces()[0]`, so every part of Trim that works from an entity's outline sees
only the FIRST glyph.

Run:  C:\\Python314\\python.exe probes/trim_text_entity_attack.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sketch as sk          # noqa: E402
import sketch_trim as tr     # noqa: E402

TEXT = {"kind": "text", "mode": "add", "x": 0, "y": 0, "text": "AB", "size": 14}
PLATE = {"kind": "rectangle", "mode": "add", "x": 0, "y": 0, "w": 60, "h": 30}


def area(shape):
    return sum(f.area for f in shape.faces()) if shape is not None else 0.0


def main():
    faces = sk._entity(TEXT).faces()
    print(f"sk._entity(text 'AB') -> {len(faces)} faces, "
          f"areas {[round(f.area, 4) for f in faces]}")
    print(f"sketch_trim._entity_face -> ONE face, area "
          f"{tr._entity_face(TEXT, 0).area:.4f}")
    print(f"sk.entity_outlines  -> {len(sk.entity_outlines(TEXT))} loops "
          f"(what the sketcher canvas draws)")

    print("\n--- 1. hover: how many pieces does Trim offer? ---")
    ents = [dict(PLATE), dict(TEXT, mode="subtract")]
    pieces = tr.trim_pieces(ents)
    for p in pieces:
        print(f"   piece {p['id']} ent={p['ent']} whole={p['whole']} "
              f"{len(p['pts'])} pts")

    print("\n--- 2. the builder's own answer for the same sketch ---")
    composed = sk.compose(ents, note=False)
    print(f"   sk.compose area = {area(composed):.4f} mm2")
    union = tr._union_faces(ents, [0, 1])
    print(f"   trim _union_faces area = {area(union):.4f} mm2   "
          f"(plate alone = {60 * 30})")

    print("\n--- 3. what a click on the text piece does ---")
    for p in pieces:
        if p["ent"] != 1:
            continue
        try:
            res = tr.trim_apply(ents, p["id"])
            after = res["entities"]
            print(f"   click {p['id']}: {res['message']}")
            print(f"      entity kinds after = "
                  f"{[e.get('kind') for e in after]}")
            try:
                a2 = area(sk.compose(after, note=False))
            except Exception as ex:                  # noqa: BLE001
                a2 = f"compose failed: {ex}"
            print(f"      area before {area(composed):.4f} -> after {a2}")
        except ValueError as ex:
            print(f"   click {p['id']}: REFUSED {ex}")

    print("\n--- 4. a text entity that CROSSES the plate edge ---")
    ents2 = [dict(PLATE), dict(TEXT, mode="add", x=28, y=0)]
    try:
        pieces2 = tr.trim_pieces(ents2)
        print(f"   {len(pieces2)} pieces: "
              f"{[(p['id'], p['whole']) for p in pieces2]}")
        composed2 = sk.compose(ents2, note=False)
        print(f"   builder area {area(composed2):.4f}")
        for p in pieces2:
            try:
                res = tr.trim_apply(ents2, p["id"])
                a2 = area(sk.compose(res['entities'], note=False))
                print(f"   click {p['id']}: {res['message']}  area -> {a2:.4f}")
            except ValueError as ex:
                print(f"   click {p['id']}: REFUSED {ex}")
    except Exception as ex:                          # noqa: BLE001
        print(f"   trim_pieces raised {type(ex).__name__}: {ex}")


if __name__ == "__main__":
    main()
