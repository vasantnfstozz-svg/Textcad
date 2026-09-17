"""probes/s10_r3_creator_door.py — the CREATORS' numeric door, measured.

`Document._eval` runs `_check_numeric_params` for MODIFIERS only; the comment
says "every creator already names the parameter AND its unit". That is true of
the creators whose every number must be POSITIVE (`blocks._positive` speaks for
those), and this probe asks whether it is true of the rest — `sketch.offset`
(0 and negative are real answers), `curved_blade`'s two blade ANGLES (0 is a
straight radial blade, negative is forward-swept) and the importers' `scale`.

It also measures what a value that is not refused actually BUILDS, because a
placement silently taken as 0 is worse than a refusal.

Run:  C:\\Python314\\python.exe probes\\s10_r3_creator_door.py
"""
import sys

sys.path.insert(0, ".")

from document import Document, CREATORS   # noqa: E402

ONE = [{"kind": "rectangle", "x": 0, "y": 0, "w": 10, "h": 10, "mode": "add"}]

CASES = {
    "sketch": ({"entities": ONE, "plane": "XY", "offset": 7.0}, ["offset"]),
    "curved_blade": ({"inner_radius": 5, "outer_radius": 12,
                      "inlet_angle_deg": 30, "exit_angle_deg": 50,
                      "height": 6, "thickness": 1.5},
                     ["inlet_angle_deg", "exit_angle_deg", "inner_radius",
                      "outer_radius", "height", "thickness"]),
    "import_stl": ({"file": "nope.stl", "scale": 1.0}, ["scale"]),
}

BADS = [None, "", True, False, [1, 2], {"a": 1}, "8mm"]

RAW_WORDS = ("TypeError", "could not convert", "unsupported operand",
             "is not iterable", "unhashable", "object is not",
             "argument must be", "cannot use", "invalid literal",
             "not enough values", "object has no attribute", "NoneType",
             "'str' object", "'int' object", "'bool' object", "'list' object",
             "not supported between", "ZeroDivisionError")


def build(op, params):
    d = Document(name="n")
    d.add("p1", op, params, [])
    try:
        d.rebuild()
    except Exception as e:
        return f"RAISED {type(e).__name__}: {e}", None
    f = d.get("p1")
    part = d._parts.get("p1")
    where = None
    if part is not None:
        try:
            bb = part.bounding_box()
            where = (round(bb.min.Z, 3), round(bb.max.Z, 3))
        except Exception:
            where = "?"
    return (f"{f.status:7s} vol={f.volume} :: "
            + " | ".join(f.problems or []), where)


if __name__ == "__main__":
    for op, (base, keys) in CASES.items():
        if op not in CREATORS:
            print(f"{op}: not a creator here")
            continue
        out, where = build(op, base)
        print(f"\n{op}  BASELINE -> {out}   z={where}")
        for k in keys:
            if k not in Document.numeric_params(op):
                print(f"  ({k} is not a numeric parameter)")
            for bad in BADS:
                out, where = build(op, {**base, k: bad})
                tag = "RAW" if any(w in out for w in RAW_WORDS) else (
                    "BLD" if out.startswith("ok") else "   ")
                print(f"  {tag} {k}={bad!r:8s} -> {out[:130]}   z={where}")
