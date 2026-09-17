r"""The three questions round two's close-out asks of the odd-even loop rule.

`_in_entity` says a point is inside an entity when it is inside an ODD number
of that entity's closed loops. That is plainly right for a glyph with one
counter. This measures the two shapes the 324-sketch corpus cannot produce,
against the kernel rather than against a reading, plus the one behaviour the
removed refusal existed to protect:

  A. NESTED THREE DEEP - a disc inside the hole of a ring. Parity must call
     the disc material and the gap around it empty.
  B. TWO LOOPS THAT TOUCH at a point rather than crossing - tangent circles,
     and the glyphs whose counters come closest ('8', '%', 'B').
  C. A MULTI-LETTER ENGRAVING THROUGH A REAL CLICK - the old code's sin was
     reading a word as its FIRST letter, so a real `trim_apply` on a cluster
     holding 'AB' must give back a sketch that still has BOTH letters.
  D. A bounded SWEEP of a cutter across a word, every piece clicked.

Oracle throughout: the face `sketch.py`/OpenCASCADE actually builds, sampled
independently of the code under test.

    C:\Python314\python.exe -u probes/trim_loops_edge_cases.py

Read only.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build123d as b3d                                       # noqa: E402
import sketch as sk                                           # noqa: E402
import sketch_trim as tr                                      # noqa: E402


def loops_of(shape):
    """Every wire of every face, sampled the way `_entity_loops` samples."""
    return [tr._loop(w) for f in shape.faces() for w in f.wires()]


def truly_inside(shape, x, y):
    """The kernel's own answer: is the point on any face of the shape?"""
    return any(tr._face_contains(f, x, y) for f in shape.faces())


def scan(shape, pts, label):
    loops = loops_of(shape)
    wrong = [(x, y) for x, y in pts
             if tr._in_entity(loops, x, y) != truly_inside(shape, x, y)]
    print(f"  {label:<46} loops={len(loops):<3} faces={len(shape.faces()):<3} "
          f"points={len(pts):<5} disagreements={len(wrong)}"
          f"{'' if not wrong else '   <<<< ' + str(wrong[:4])}")
    return len(wrong)


def section_a():
    print("=" * 96)
    print("A. NESTED THREE DEEP - outer / hole / island")
    print("=" * 96)
    bad = 0
    ring_and_disc = (b3d.Circle(20) - b3d.Circle(14)) + b3d.Circle(6)
    pts = [(r, 0.0) for r in
           [0.0, 2.0, 5.9, 6.1, 9.0, 13.9, 14.1, 17.0, 19.9, 20.1, 25.0]]
    pts += [(r * 0.7071, r * 0.7071) for r in
            [1.0, 5.5, 7.0, 12.0, 15.0, 19.0, 22.0]]
    bad += scan(ring_and_disc, pts, "ring 14-20 with a disc r6 in its hole")
    # four deep: ring, disc, and a hole in the disc
    deeper = (b3d.Circle(20) - b3d.Circle(14)) + \
        (b3d.Circle(6) - b3d.Circle(2))
    pts4 = [(r, 0.0) for r in
            [0.0, 1.9, 2.1, 4.0, 5.9, 6.1, 10.0, 13.9, 14.1, 17.0, 21.0]]
    bad += scan(deeper, pts4, "the same, with a r2 hole in the disc (4 deep)")
    # can any SHIPPED entity kind build three-deep loops on its own?
    chars = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
             "0123456789!#$%&()*+,-./:;<=>?@[]^_{|}~")
    deep = []
    for ch in chars:
        s = sk._entity({"kind": "text", "text": ch, "size": 14,
                        "x": 0, "y": 0})
        faces = s.faces()
        for f in faces:                       # an island inside another's hole
            c = f.center()
            for g in faces:
                if g.is_same(f):
                    continue
                ow = g.outer_wire()
                holes = [w for w in g.wires() if not w.is_same(ow)]
                if holes and tr._face_contains(g, c.X, c.Y) is False and \
                        tr._inside(tr._loop(ow), c.X, c.Y):
                    deep.append(ch)
    print(f"  glyphs in Arial whose loops nest three deep on their own: "
          f"{sorted(set(deep)) or 'NONE of ' + str(len(chars))}")
    print("  (`polygon`, `path`, `rectangle`, `circle`, `ellipse`, `slot`,")
    print("   `regular_polygon` are one loop each, so no SHIPPED entity kind")
    print("   reaches three deep today - the rule is proven above anyway.)")
    return bad


def section_b():
    print()
    print("=" * 96)
    print("B. TWO LOOPS THAT TOUCH AT A POINT")
    print("=" * 96)
    bad = 0
    # internally tangent: a disc sitting against the inside of a ring's hole
    tangent_in = (b3d.Circle(20) - b3d.Circle(14)) + \
        b3d.Pos(7.0, 0) * b3d.Circle(7.0)
    pts = [(x, 0.0) for x in
           [-19, -16, -14.5, -13.9, -7, 0.1, 7, 13.9, 14.1, 17, 21]]
    pts += [(0.0, y) for y in [-19, -15, -10, -1, 1, 10, 15, 19]]
    bad += scan(tangent_in, pts, "disc tangent to the inside of a ring hole")
    # externally tangent: two discs meeting at one point
    tangent_out = b3d.Pos(-9, 0) * b3d.Circle(9) + \
        b3d.Pos(9, 0) * b3d.Circle(9)
    pts2 = [(x, 0.0) for x in [-18.5, -12, -5, -0.2, 0.2, 5, 12, 18.5, 19.5]]
    pts2 += [(x, 4.0) for x in [-12, -2, 0, 2, 12]]
    bad += scan(tangent_out, pts2, "two discs meeting at exactly one point")
    # the glyphs whose loops come closest
    for ch in ("8", "%", "B", "g", "Q"):
        s = sk._entity({"kind": "text", "text": ch, "size": 24,
                        "x": 0, "y": 0})
        bb = s.bounding_box()
        pts3 = []
        for i in range(17):
            for j in range(17):
                pts3.append((bb.min.X + (bb.max.X - bb.min.X) * i / 16,
                             bb.min.Y + (bb.max.Y - bb.min.Y) * j / 16))
        bad += scan(s, pts3, f"glyph {ch!r} at 24 mm, 289-point grid")
    # and what a tangency does to the PIECES (crossing detection)
    ents = [{"kind": "circle", "mode": "add", "x": -9, "y": 0, "r": 9},
            {"kind": "circle", "mode": "add", "x": 9, "y": 0, "r": 9}]
    pieces = tr.trim_pieces(ents)
    kinds = {p["id"]: p["whole"] for p in pieces}
    print(f"  two tangent circles as TWO entities -> {len(pieces)} pieces, "
          f"whole={list(kinds.values())}")
    for pid in list(kinds):
        try:
            out = tr.trim_apply([dict(e) for e in ents], pid)
            print(f"    click {pid}: {out['message']}")
        except ValueError as ex:
            print(f"    click {pid}: refused - {str(ex)[:72]}")
    return bad


def section_c():
    print()
    print("=" * 96)
    print("C. A MULTI-LETTER ENGRAVING THROUGH A REAL trim_apply CLICK")
    print("=" * 96)
    plate = {"kind": "rectangle", "mode": "add", "x": 0, "y": 0,
             "w": 60, "h": 30}
    word = {"kind": "text", "mode": "subtract", "x": 0, "y": 0,
            "text": "AB", "size": 14}
    bar = {"kind": "rectangle", "mode": "add", "x": 0, "y": 13.2,
           "w": 70, "h": 3}
    ents = [plate, word, bar]
    before = sk.compose([dict(e) for e in ents], note=False)
    print(f"  before: {before.area:.4f} mm2, {len(before.faces())} faces, "
          f"{sum(len(f.wires()) for f in before.faces())} wires")
    # Points genuinely INSIDE each letter's stroke, found with the kernel -
    # a glyph's centroid is not on the glyph (an 'A' centroid near the
    # baseline sits in the gap between its legs). The builder leaves NO
    # material inside a stroke of an engraved word, and a word read as its
    # FIRST letter loses the B.
    glyph = sk._entity({"kind": "text", "mode": "add", "x": 0, "y": 0,
                        "text": "AB", "size": 14})
    strokes = []
    for f in sorted(glyph.faces(), key=lambda g: g.center().X):
        bb = f.bounding_box()
        found = None
        for i in range(1, 40):
            for j in range(1, 40):
                x = bb.min.X + (bb.max.X - bb.min.X) * i / 40
                y = bb.min.Y + (bb.max.Y - bb.min.Y) * j / 40
                if tr._face_contains(f, x, y):
                    found = (x, y)
                    break
            if found:
                break
        strokes.append(found)
    a_stroke, b_stroke = strokes[0], strokes[1]
    print(f"  a point in the A's stroke {a_stroke}, in the B's {b_stroke}")
    print(f"  before the click: material at A = "
          f"{truly_inside(before, *a_stroke)}, at B = "
          f"{truly_inside(before, *b_stroke)}  (both must be False - engraved)")
    bad = 0
    done = deletes = 0
    for p in tr.trim_pieces(ents):
        try:
            out = tr.trim_apply([dict(e) for e in ents], p["id"])
        except ValueError:
            continue
        after = sk.compose(out["entities"], note=False)
        in_a = truly_inside(after, *a_stroke)
        in_b = truly_inside(after, *b_stroke)
        if p["whole"] and p["ent"] == 1:
            # the promised gesture: a crossing-free entity is DELETED by a
            # click, so the whole engraving goes - both letters together,
            # which is the point. Anything else would be half a word.
            deletes += 1
            if not (in_a and in_b) or len(out["entities"]) != 2:
                bad += 1
                print(f"    {p['id']}: deleting the word left A={not in_a} "
                      f"B={not in_b} engraved and {len(out['entities'])} "
                      f"entities  <<<< HALF A WORD")
            continue
        done += 1
        if in_a or in_b:
            bad += 1
            print(f"    {p['id']}: material back in the A = {in_a}, in the "
                  f"B = {in_b}  <<<< A LETTER WAS FILLED IN "
                  f"({out['message']})")
    print(f"  {deletes} clicks deleted the whole word (both letters back, "
          f"2 entities left); {done} other clicks applied and both letters "
          f"stayed engraved through every one ({bad} failures)")

    # and the same with the bar driven THROUGH the word, so the word's own
    # loops are cut into real pieces and the boolean path runs on them
    ents2 = [plate, word, dict(bar, y=0.0)]
    before2 = sk.compose([dict(e) for e in ents2], note=False)
    pieces2 = tr.trim_pieces(ents2)
    word_pieces = [p for p in pieces2 if p["ent"] == 1]
    print(f"  bar driven through the word: {len(pieces2)} pieces, "
          f"{len(word_pieces)} of them the word's, "
          f"{sum(1 for p in word_pieces if p['whole'])} whole")
    lost = applied = 0
    for p in word_pieces:
        try:
            out = tr.trim_apply([dict(e) for e in ents2], p["id"])
        except ValueError:
            continue
        applied += 1
        after = sk.compose(out["entities"], note=False)
        # every click here is local: it may fill ONE cell, never a whole
        # letter, so the area must stay within one bar-width of where it was
        if after.area < before2.area - 1e-6:
            lost += 1
            print(f"    {p['id']}: LOST material {before2.area:.4f} -> "
                  f"{after.area:.4f} ({out['message']})")
    print(f"  {applied} clicks on the word's own pieces, {lost} lost "
          f"material; area before {before2.area:.4f}")

    # and the dissolve's own number, against the kernel
    for p in tr.trim_pieces(ents):
        if p["whole"]:
            continue
        try:
            out = tr.trim_apply([dict(e) for e in ents], p["id"])
        except ValueError:
            continue
        if "dissolved" in out["message"]:
            got = sk.compose(out["entities"], note=False)
            print(f"  dissolve {p['id']}: {before.area:.4f} -> "
                  f"{got.area:.4f} mm2, {len(got.faces())} faces, "
                  f"{sum(len(f.wires()) for f in got.faces())} wires "
                  f"(both letters are still holes in it)")
            break
    return bad + lost


def section_d():
    print()
    print("=" * 96)
    print("D. SWEEP - a 3 mm bar walked across the word 'A8', every piece")
    print("=" * 96)
    clicks = refused = crashes = broke = invalid = 0
    bad = []
    t0 = time.perf_counter()
    for angle in (0, 62):
        for k in range(4):
            y = -6.0 + k * 4.0
            ents = [{"kind": "text", "mode": "add", "x": 0, "y": 0,
                     "text": "A8", "size": 20},
                    {"kind": "rectangle", "mode": "add", "x": 0, "y": y,
                     "w": 44, "h": 3, "rotation": angle}]
            try:
                pieces = tr.trim_pieces(ents)
            except ValueError:
                continue
            except Exception as ex:                           # noqa: BLE001
                crashes += 1
                bad.append(f"hover y={y} a={angle}: {type(ex).__name__}: "
                           f"{str(ex)[:60]}")
                continue
            for p in pieces:
                clicks += 1
                try:
                    out = tr.trim_apply([dict(e) for e in ents], p["id"])
                except ValueError:
                    refused += 1
                    continue
                except Exception as ex:                       # noqa: BLE001
                    crashes += 1
                    bad.append(f"y={y} a={angle} {p['id']}: "
                               f"{type(ex).__name__}: {str(ex)[:60]}")
                    continue
                if not out["entities"]:
                    continue
                try:
                    shape = sk.compose(out["entities"], note=False)
                except Exception as ex:                       # noqa: BLE001
                    broke += 1
                    bad.append(f"y={y} a={angle} {p['id']}: does NOT compose:"
                               f" {str(ex)[:60]}")
                    continue
                if not shape.is_valid:            # a PROPERTY, not a method
                    invalid += 1
                    bad.append(f"y={y} a={angle} {p['id']}: INVALID faces")
            print(f"  bar at y={y:>5.1f} angle={angle:<3} -> "
                  f"{len(pieces)} pieces, running total {clicks} clicks "
                  f"({time.perf_counter() - t0:.0f} s)")
    print(f"  {clicks} clicks, {refused} refused, {crashes} raw/kernel "
          f"exceptions, {broke} that do not build, {invalid} invalid")
    for line in bad[:20]:
        print("   ", line)
    return crashes + broke + invalid


def main():
    bad = section_a() + section_b() + section_c() + section_d()
    print()
    print(f"TOTAL disagreements / failures: {bad}")


if __name__ == "__main__":
    main()
