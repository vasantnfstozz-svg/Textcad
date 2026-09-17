r"""Every click, on every piece, of every sketch that holds a WORD.

Round two of the Trim review. Reading an entity as all its loops lets a Text
entity into the cluster machinery for the first time: `_union_faces` unions a
multi-face Sketch, the cell refinement clips a Face by one, and
`_shape_to_entities` writes the answer back. "An operation is the feature
TIMES the geometry", so this clicks EVERY piece of every sketch below and
checks three things each time:

  * nothing but a plain ValueError reaches the caller (rule 5: no kernel
    exception, and OCP errors derive from Exception, not RuntimeError);
  * whatever comes back COMPOSES — `sketch.compose` builds it;
  * the area it composes to is the area the click promised: a dissolve keeps
    the cluster's composed area, a fill grows it, a whole-delete drops the
    entity. The oracle is the builder, never this module.

    C:\Python314\python.exe probes/trim_text_gauntlet.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sketch as sk                                           # noqa: E402
import sketch_trim as tr                                      # noqa: E402


def txt(t, x=0.0, y=0.0, size=14, mode="add", **kw):
    return dict({"kind": "text", "mode": mode, "x": x, "y": y,
                 "text": t, "size": size}, **kw)


def rect(w, h, x=0.0, y=0.0, mode="add"):
    return {"kind": "rectangle", "mode": mode, "x": x, "y": y, "w": w, "h": h}


def circ(r, x=0.0, y=0.0, mode="add"):
    return {"kind": "circle", "mode": mode, "x": x, "y": y, "r": r}


CASES = {
    "word alone": [txt("AB")],
    "word engraved in a plate": [rect(60, 30), txt("AB", mode="subtract")],
    "word raised on a plate": [rect(60, 30), txt("AB")],
    "O alone": [txt("O", size=20)],
    "O engraved": [rect(40, 30), txt("O", size=20, mode="subtract")],
    "circle across the A": [rect(60, 30), txt("AB", mode="subtract"),
                            circ(4, -7.5, 0)],
    "circle through the O ring": [txt("O", size=24), circ(5, 6, 0)],
    "circle in the O counter": [txt("O", size=24), circ(2.5, 0, 0)],
    "bar across a whole word": [txt("AB", size=18), rect(40, 2, 0, 0)],
    "bar across a word, cut": [txt("AB", size=18),
                               rect(40, 2, 0, 0, mode="subtract")],
    "plate, word, bar all tangled": [rect(60, 30), txt("AB", size=18),
                                     rect(70, 3, 0, 0)],
    "word far away from a trim": [rect(40, 20), circ(8, 20, 0),
                                  txt("O", x=200, y=200)],
    "two words": [txt("AB", x=-14, size=12), txt("OD", x=14, size=12)],
    "8 over a slot": [txt("8", size=24),
                      {"kind": "slot", "mode": "add", "x": 0, "y": 0,
                       "length": 26, "height": 4}],
    "word inside a ring": [circ(22), circ(15, mode="subtract"),
                           txt("AB", size=8)],
}


def area(ents):
    return float(sk.compose(ents, note=False).area)


def main():
    total = clicks = refusals = crashes = broke = 0
    bad = []
    for name, ents in CASES.items():
        total += 1
        try:
            pieces = tr.trim_pieces(ents)
        except ValueError as ex:
            print(f"  {name:<32} HOVER REFUSED: {str(ex)[:70]}")
            continue
        except Exception as ex:                               # noqa: BLE001
            crashes += 1
            bad.append(f"{name}: hover raised {type(ex).__name__}: {ex}")
            continue
        before = area(ents)
        n_ref = n_ok = 0
        for p in pieces:
            clicks += 1
            try:
                out = tr.trim_apply([dict(e) for e in ents], p["id"])
            except ValueError:
                n_ref += 1
                refusals += 1
                continue
            except Exception as ex:                           # noqa: BLE001
                crashes += 1
                bad.append(f"{name} {p['id']}: {type(ex).__name__}: "
                           f"{str(ex)[:80]}")
                continue
            n_ok += 1
            if not out["entities"]:
                continue                      # the last entity was deleted
            try:
                after = area(out["entities"])
            except Exception as ex:                           # noqa: BLE001
                broke += 1
                bad.append(f"{name} {p['id']}: result does NOT compose: "
                           f"{type(ex).__name__}: {str(ex)[:70]}")
                continue
            if after < before - 1e-6 and not p["whole"]:
                bad.append(f"{name} {p['id']}: trim REMOVED material "
                           f"{before:.4f} -> {after:.4f} ({out['message']})")
            shape = sk.compose(out["entities"], note=False)
            if not shape.is_valid:            # a PROPERTY, not a method
                bad.append(f"{name} {p['id']}: result is NOT a valid face set")
        print(f"  {name:<32} pieces={len(pieces):<4} applied={n_ok:<4} "
              f"refused={n_ref:<4} area before={before:.4f}")
    print()
    print(f"sketches {total}, clicks {clicks}, refused {refusals}, "
          f"kernel/raw crashes {crashes}, results that do not build {broke}")
    if bad:
        print(f"PROBLEMS ({len(bad)}):")
        for line in bad[:30]:
            print("   ", line)
    else:
        print("no problem found")


if __name__ == "__main__":
    main()
