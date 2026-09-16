"""probes/imgtrace_case53_face.py - the SKETCH FACE of fuzz case 53 is already
invalid before any extrude. Which entity (or pair) does it?
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imgtrace  # noqa: E402
import sketch as sk  # noqa: E402
from imgtrace_case53_probe import case  # noqa: E402

from OCP.BRepCheck import BRepCheck_Analyzer  # noqa: E402
from OCP.TopAbs import TopAbs_ShapeEnum  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402


def ok(ents):
    try:
        f = sk.make_sketch("XY", 0, ents)
    except Exception as e:                      # noqa: BLE001
        return f"RAISED {type(e).__name__}: {str(e)[:70]}"
    return BRepCheck_Analyzer(f.wrapped).IsValid()


def bad_bits(shape):
    an = BRepCheck_Analyzer(shape)
    out = {}
    for name, k in (("FACE", TopAbs_ShapeEnum.TopAbs_FACE),
                    ("WIRE", TopAbs_ShapeEnum.TopAbs_WIRE),
                    ("EDGE", TopAbs_ShapeEnum.TopAbs_EDGE),
                    ("VERTEX", TopAbs_ShapeEnum.TopAbs_VERTEX)):
        exp = TopExp_Explorer(shape, k)
        n = 0
        while exp.More():
            if not an.IsValid(exp.Current()):
                n += 1
            exp.Next()
        if n:
            out[name] = n
    return out


def main():
    data, h = case(53)
    ents, info = imgtrace.image_to_entities(data, height_mm=h)
    print("all entities ->", ok(ents), info)
    print("  bad subshapes:", bad_bits(sk.make_sketch("XY", 0, ents).wrapped))
    print("outer alone ->", ok(ents[:1]))
    for k in range(1, len(ents)):
        r = ok([ents[0], ents[k]])
        if r is not True:
            print(f"  outer + ent{k} ({ents[k]['mode']}, "
                  f"{len(ents[k]['points'])} pts) -> {r}")
    # growing prefix: where does it first go invalid?
    for k in range(1, len(ents) + 1):
        r = ok(ents[:k])
        if r is not True:
            print(f"  first invalid prefix: ents[:{k}] -> {r} "
                  f"(added ent{k - 1}, {ents[k - 1]['mode']})")
            break


if __name__ == "__main__":
    main()
