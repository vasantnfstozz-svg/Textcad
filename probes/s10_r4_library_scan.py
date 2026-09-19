"""Round FOUR: a gate must never refuse correct work.

READ-ONLY. Opens every file the library holds — the 47 designs AND every
saved version in each design's `.history/` — through the door round four
tightened (`Document.from_data` / `Document.add`), and checks that what comes
back out is byte for byte what went in.

It also counts the shapes the new door looks at, so a claim about "nothing in
the library can be newly refused" is a measurement and not an opinion:
feature ids, op names, `inputs`, `suppressed`, `parameters` and `spec`.

Run: C:\\Python314\\python.exe probes/s10_r4_library_scan.py
"""
import collections
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document import Document                                      # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent / "designs"

files = (sorted(ROOT.rglob("*.tcad.json")) + sorted(ROOT.rglob("*.history/*.json"))
         + sorted(ROOT.rglob("*.history/*.json.gz")))
print(f"{len(files)} files under {ROOT}")

shapes = collections.Counter()
refused, drifted = [], []
for p in files:
    try:
        if p.suffix == ".gz":
            import gzip
            raw = json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))
        else:
            raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:                                         # noqa: BLE001
        print(f"  (not JSON, skipped) {p.name}: {e}")
        continue
    payloads = [raw] if isinstance(raw, dict) and "features" in raw else []
    if isinstance(raw, dict) and isinstance(raw.get("versions"), list):
        payloads += [v["doc"] for v in raw["versions"]
                     if isinstance(v, dict) and isinstance(v.get("doc"), dict)]
    for data in payloads:
        shapes["documents"] += 1
        shapes["name is text"] += isinstance(data.get("name"), str)
        shapes["spec is a table"] += isinstance(data.get("spec", {}), dict)
        shapes["parameters absent or a table"] += isinstance(
            data.get("parameters") or {}, dict)
        for f in data.get("features", []):
            shapes["features"] += 1
            shapes["id is text"] += isinstance(f.get("id"), str)
            shapes["op is text"] += isinstance(f.get("op"), str)
            shapes["inputs absent or a list"] += isinstance(f.get("inputs", []), list)
            shapes["suppressed absent or a bool"] += isinstance(
                f.get("suppressed", False), bool)
            shapes["params absent or a table"] += isinstance(f.get("params") or {}, dict)
            for ch in "<,!":
                if ch in str(f.get("id", "")):
                    shapes[f"id holding {ch!r}"] += 1
        try:
            back = Document.from_data(data).to_data()
        except Exception as e:                                     # noqa: BLE001
            refused.append((p.name, data.get("name"), f"{type(e).__name__}: {e}"))
            continue
        want = {k: v for k, v in data.items() if k in back}
        if back != {**back, **want} or json.dumps(back, sort_keys=True) != \
                json.dumps({**back, **want}, sort_keys=True):
            drifted.append((p.name, data.get("name")))

print()
for k, v in shapes.items():
    print(f"  {k:<34}{v}")
print()
print(f"REFUSED: {len(refused)}")
for r in refused:
    print("   ", r)
print(f"DRIFTED (what came back is not what went in): {len(drifted)}")
for r in drifted:
    print("   ", r)
