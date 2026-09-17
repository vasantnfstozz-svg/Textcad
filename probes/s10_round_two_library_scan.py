"""Read-only scan of every SAVED design, for the two round-two fixes.

  A. a solid-only modifier (fillet, chamfer, shell, hole, with_center_hole,
     with_bolt_circle) whose input is a sketch — the features the new kind
     gate would newly refuse.
  B. a NUMERIC parameter (as Document.numeric_params reads the annotation)
     whose stored value is null, "" or any non-number — the features a
     rebuild-time numeric check would newly refuse.

Nothing is written; the files are only parsed.

Run:  C:\\Python314\\python.exe probes/s10_round_two_library_scan.py
"""
import json
import pathlib
import sys

sys.path.insert(0, ".")

from document import Document                       # noqa: E402

SOLID_ONLY = {"fillet", "chamfer", "shell", "hole", "with_center_hole",
              "with_bolt_circle"}
SKETCHY = {"sketch", "sketch_on_face"}
ROOTS = (pathlib.Path("designs"), pathlib.Path("tests/fixtures"))

files = kind_hits = num_hits = 0
for root in ROOTS:
    if not root.exists():
        continue
    for p in sorted(root.glob("*.tcad.json")):
        files += 1
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print("skip", p.name, e)
            continue
        feats = d.get("features", [])
        kind = {f.get("id"): f.get("op") for f in feats}
        for f in feats:
            op = f.get("op")
            params = f.get("params") or {}
            if op in SOLID_ONLY:
                ins = [kind.get(i) for i in (f.get("inputs") or [])]
                if any(k in SKETCHY for k in ins):
                    kind_hits += 1
                    print(f"KIND  {p.name}: {f.get('id')} {op} "
                          f"inputs={f.get('inputs')} -> {ins}")
            try:
                numeric = Document.numeric_params(op)
            except Exception:
                continue
            for k, v in params.items():
                if k not in numeric:
                    continue
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    num_hits += 1
                    print(f"NUM   {p.name}: {f.get('id')} {op} {k}={v!r}")

print(f"\nscanned {files} design files")
print(f"  solid-only op fed a sketch : {kind_hits}")
print(f"  numeric param not a number : {num_hits}")
