"""Read-only scan: how many SAVED designs hold a pattern the new kind gate
would newly refuse — one whose input is a sketch, or whose count is 1 (the
pass-through the ops answer with the input itself).

Nothing is written; the files are only parsed.

Run:  C:\\Python314\\python.exe probes/s10_pattern_gate_library_scan.py
"""
import json
import pathlib

PAT = {"linear_pattern", "polar_pattern"}
ROOTS = (pathlib.Path("designs"), pathlib.Path("tests/fixtures"))

files = hits = 0
for root in ROOTS:
    if not root.exists():
        continue
    for p in sorted(root.glob("*.tcad.json")):
        files += 1
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:                       # pragma: no cover
            print("skip", p.name, e)
            continue
        feats = d.get("features", [])
        kind = {f.get("id"): f.get("op") for f in feats}
        for f in feats:
            if f.get("op") not in PAT:
                continue
            c = (f.get("params") or {}).get("count")
            ins = [kind.get(i) for i in (f.get("inputs") or [])]
            sketchy = any(k in ("sketch", "sketch_on_face") for k in ins)
            if sketchy or c in (1, 1.0, None):
                hits += 1
                print(f"{p.name}: {f.get('id')} {f.get('op')} count={c!r} "
                      f"inputs={f.get('inputs')} -> {ins}")
print(f"\nscanned {files} design files; newly-refused pattern features: {hits}")
