"""probes/s10_r3_entity_value_door.py — the OTHER big foreign-file surface: the
numbers inside a sketch ENTITY.

The op-parameter census (s10_r3_valueerror_census.py) walks `params`. A sketch
carries a LIST OF DICTS under `entities`, and every one of those dicts holds
numbers the kernel eventually sees. `sketch.py` reads them with `float()`, and
`float()` raises `ValueError` — the exact exception `blocks.plain_cause` passes
through verbatim on the assumption that a ValueError is one of our sentences.

This probe measures how far that reaches, and whether any bare PYTHON
ValueError still lands in a feature row after round three's source guards.

Run:  C:\\Python314\\python.exe probes\\s10_r3_entity_value_door.py
"""
import sys

sys.path.insert(0, ".")

from document import Document          # noqa: E402

ENTS = {
    "circle": {"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"},
    "rectangle": {"kind": "rectangle", "x": 0, "y": 0, "w": 10, "h": 8,
                  "mode": "add"},
    "polygon": {"kind": "polygon", "points": [[0, 0], [10, 0], [10, 10]],
                "mode": "add"},
    "slot": {"kind": "slot", "x": 0, "y": 0, "w": 12, "h": 4, "mode": "add"},
}

BADS = [None, "", "abc", True, [1, 2], {"a": 1}]

PY_WORDS = ("TypeError", "AttributeError", "ZeroDivisionError", "IndexError",
            "could not convert", "unsupported operand", "is not iterable",
            "unhashable", "object has no attribute", "not enough values",
            "too many values", "has no len()", "not supported between",
            "dictionary update sequence", "string indices")


def row(ent):
    d = Document(name="e")
    d.add("s1", "sketch", {"entities": [ent], "plane": "XY", "offset": 0.0}, [])
    d.add("p1", "extrude", {"amount": 3}, ["s1"])
    try:
        d.rebuild()
    except Exception as e:
        return f"RAISED {type(e).__name__}: {e}"
    out = []
    for f in d.features:
        out.append(f"{f.id}={f.status}:" + "|".join(f.problems or []))
    return "  ".join(out)


if __name__ == "__main__":
    py = 0
    for name, ent in ENTS.items():
        print(f"\n{name} BASELINE -> {row(ent)[:120]}")
        for k in ent:
            if k in ("kind", "mode"):
                continue
            for bad in BADS:
                out = row({**ent, k: bad})
                tag = "   "
                if any(w in out for w in PY_WORDS):
                    tag = "PY "
                    py += 1
                print(f"  {tag} {k}={bad!r:10s} -> {out[:130]}")
    print(f"\nPYTHON in a row: {py}")
