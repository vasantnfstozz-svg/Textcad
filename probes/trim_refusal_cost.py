r"""What the multi-face/holed refusal of f628ceb COST a user.

Round two of the Trim review (2026-09-18). Round one traded a wrong answer
for a refusal, which is the right direction. This measures the price, and
then the same questions against the shipped module:

  1. which characters a user can type into a Text entity the refusal caught
     (any glyph with a counter: O A B D P Q R a b d e g o p q 0 4 6 8 9 ...),
     and how many of the 90 printable ASCII characters — plus the fact that
     TWO glyph pieces is already "more than one face", so every word of two
     or more letters was refused whether it had a counter or not;
  2. whether ONE such entity anywhere in a sketch stopped Trim for the WHOLE
     sketch, including entities 200 mm away that never touched it;
  3. whether the loops the refusal threw away were available all along —
     `sketch.entity_outlines` already returns every face's outer wire AND its
     holes, and the sketcher canvas draws them.

The refusal is reproduced by its own RULE (`faces() > 1 or any hole`) rather
than by calling the deleted `_entity_face`, so the probe still runs.

    C:\Python314\python.exe probes/trim_refusal_cost.py

Read only. No design files are touched.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sketch as sk                                           # noqa: E402
import sketch_trim as tr                                      # noqa: E402

ASCII = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
         "abcdefghijklmnopqrstuvwxyz"
         "0123456789"
         "!#$%&()*+,-./:;<=>?@[]^_{|}~")


def shape_of(ch, size=10.0):
    return sk._entity({"kind": "text", "text": ch, "size": size,
                       "x": 0, "y": 0})


def was_refused(shape):
    """f628ceb's rule, verbatim: more than one face, or any hole."""
    faces = shape.faces()
    holes = sum(len(f.wires()) - 1 for f in faces)
    return len(faces) > 1 or bool(holes), len(faces), holes


def main():
    print("=" * 72)
    print("1. SINGLE CHARACTERS a user can type — refused by f628ceb or not")
    print("=" * 72)
    refused, ok, unbuildable = [], [], []
    for ch in ASCII:
        try:
            s = shape_of(ch)
        except Exception as ex:                               # noqa: BLE001
            unbuildable.append((ch, str(ex)[:40]))
            continue
        no, nf, nh = was_refused(s)
        (refused if no else ok).append((ch, nf, nh))
    print(f"   printable characters tried : {len(ASCII)}")
    print(f"   REFUSED                    : {len(refused)}")
    print(f"   still trimmed              : {len(ok)}")
    print(f"   does not build at all      : {len(unbuildable)}")
    print("   refused  :", "".join(c for c, _, _ in refused))
    print("   accepted :", "".join(c for c, _, _ in ok))

    print()
    print("=" * 72)
    print("2. WORDS — what a real Text entity looks like")
    print("=" * 72)
    for word in ["AB", "AUTONOMIQ", "TextCAD", "LX", "v1", "12", "17"]:
        e = {"kind": "text", "text": word, "size": 10.0, "x": 0, "y": 0}
        no, nf, nh = was_refused(shape_of(word))
        loops = len(sk.entity_outlines(e))
        now = len(tr._entity_loops(e, 0))
        print(f"   {word:<12} faces={nf:<3} holes={nh:<3} canvas loops="
              f"{loops:<3} -> f628ceb: {'REFUSED' if no else 'trims':<8}"
              f" shipped: reads {now} loops")

    print()
    print("=" * 72)
    print("3. HOW WIDE was it? one text entity + shapes far away")
    print("=" * 72)
    plain = [
        {"kind": "rectangle", "w": 40, "h": 20, "x": 0, "y": 0, "mode": "add"},
        {"kind": "circle", "r": 8, "x": 20, "y": 0, "mode": "add"},
    ]
    far = {"kind": "text", "text": "O", "size": 10.0,
           "x": 200, "y": 200, "mode": "add"}
    base = tr.trim_pieces(plain)
    print(f"   two overlapping shapes alone        : {len(base)} pieces")
    # f628ceb raised out of `_outline`, which runs for EVERY entity, so the
    # whole sketch went with it — hover and click alike.
    no, nf, nh = was_refused(shape_of("O"))
    print(f"   the 'O' 200 mm away                 : {nf} face(s), {nh} "
          f"hole(s) -> f628ceb refused the WHOLE sketch")
    with_word = tr.trim_pieces(plain + [far])
    keep = [(p["id"], p["ent"], p["whole"], p["pts"])
            for p in with_word if p["ent"] in (0, 1)]
    same = [(p["id"], p["ent"], p["whole"], p["pts"]) for p in base]
    print(f"   shipped, same sketch + the word     : {len(with_word)} pieces; "
          f"the other two entities are {'IDENTICAL' if keep == same else 'DIFFERENT'}")
    pid = next(p["id"] for p in base if not p["whole"])
    a = tr.trim_apply(plain, pid)["message"]
    b = tr.trim_apply(plain + [far], pid)["message"]
    print(f"   clicking {pid} without the word      : {a}")
    print(f"   clicking {pid} with the word         : {b}")

    print()
    print("=" * 72)
    print("4. Was the information the refusal threw away actually there?")
    print("=" * 72)
    e = {"kind": "text", "text": "AB", "size": 10.0, "x": 0, "y": 0}
    loops = sk.entity_outlines(e)
    print(f"   sketch.entity_outlines('AB') -> {len(loops)} loops "
          f"(sizes {[len(x) for x in loops]})")
    s = shape_of("AB")
    print(f"   faces {len(s.faces())}, total wires "
          f"{sum(len(f.wires()) for f in s.faces())}, area {s.area:.4f}")
    print(f"   sketch_trim._entity_loops -> {len(tr._entity_loops(e, 0))} loops")


if __name__ == "__main__":
    main()
