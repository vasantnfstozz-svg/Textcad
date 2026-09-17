"""probes/s10_r3_library_scan.py — READ-ONLY: what the user's saved designs
actually hold in a numeric parameter, and whether a wider rebuild-time door
would refuse any of it.

A gate must never refuse correct work. Before the numeric door is extended to
the CREATORS, every `.tcad.json` in `designs/` AND every saved version under
`designs/*.history/` is read and each numeric parameter classified:

  number      an int or a float — passes today and after
  formula     a string paramexpr can parse — passes today and after
  OTHER       anything else — the only class the change can newly refuse

Nothing is written and no design is rebuilt.

Run:  C:\\Python314\\python.exe probes\\s10_r3_library_scan.py
"""
import gzip
import json
import pathlib
import sys

sys.path.insert(0, ".")

import paramexpr                                   # noqa: E402
from document import Document                      # noqa: E402

ROOT = pathlib.Path("designs")


def classify(v):
    if isinstance(v, bool):
        return "OTHER(bool)"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "formula" if paramexpr.is_expression(v) else "OTHER(text)"
    if v is None:
        return "OTHER(null)"
    return f"OTHER({type(v).__name__})"


def scan(path):
    try:
        if path.suffix == ".gz":
            data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "doc" in data and "features" not in data:
            data = data["doc"]                      # a saved VERSION wraps the doc
    except Exception as e:
        return [("UNREADABLE", str(e), "", "")]
    out = []
    for f in data.get("features", []):
        op = f.get("op", "")
        numeric = Document.numeric_params(op)
        for k, v in (f.get("params") or {}).items():
            if k in numeric:
                out.append((classify(v), op, k, repr(v)[:60]))
    return out


if __name__ == "__main__":
    files = (sorted(ROOT.glob("*.tcad.json")) + sorted(ROOT.glob("*.json"))
             + sorted(ROOT.glob("*.history/*.json"))
             + sorted(ROOT.glob("*.history/*.json.gz")))
    tally, others, n = {}, [], 0
    for p in files:
        n += 1
        for cls, op, k, v in scan(p):
            tally[cls] = tally.get(cls, 0) + 1
            if cls.startswith("OTHER") or cls == "UNREADABLE":
                others.append((p.name, cls, op, k, v))
    print(f"files read: {n}")
    for cls, c in sorted(tally.items()):
        print(f"  {cls:15s} {c}")
    print(f"\nvalues a wider numeric door could newly refuse: {len(others)}")
    for row in others[:60]:
        print("   ", row)
