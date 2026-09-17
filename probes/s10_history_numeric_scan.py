"""Read-only scan of every SAVED VERSION of every design (designs/*.history/)
for a numeric parameter that is not a number.

The library scan covers the designs as they stand; this one covers what a
RESTORE would rebuild. A version that stopped rebuilding would be data loss by
another name, so the rebuild-time numeric check may only ship if this is zero.

No kernel, no imports from the product: the numeric parameter names are the
ones `Document.numeric_params` printed on 2026-09-17, pasted in, so this can
run beside anything.

Run:  C:\\Python314\\python.exe probes/s10_history_numeric_scan.py
"""
import gzip
import json
import pathlib

# MODIFIERS only — the rebuild-time check runs in the modifier branch of _eval
NUMERIC = {
    "chamfer": {"length"},
    "extrude": {"amount", "amount2", "taper"},
    "extrude_face": {"amount", "taper"},
    "fillet": {"radius"},
    "hole": {"cbore_depth", "cbore_diameter", "csink_angle", "csink_diameter",
             "depth", "diameter"},
    "linear_pattern": {"count2", "distance", "distance2", "dx", "dy", "dz"},
    "polar_pattern": {"angle"},
    "revolve": {"angle", "angle2"},
    "revolve_face": {"angle", "angle2"},
    "rotate": {"angle_deg"},
    "scale": {"factor"},
    "shell": {"thickness"},
    "sketch_on_face": {"offset"},
    "with_bolt_circle": {"bolt_radius", "count", "pitch_circle_dia"},
    "with_center_hole": {"radius"},
}

SOLID_ONLY = {"fillet", "chamfer", "shell", "hole", "with_center_hole",
              "with_bolt_circle"}

files = hits = kind_hits = 0
paths =(sorted(pathlib.Path("designs").glob("*.history/**/*.json"))
         + sorted(pathlib.Path("designs").glob("*.history/**/*.json.gz")))
for p in paths:
    files += 1
    try:
        if p.suffix == ".gz":                    # a saved version is gzipped
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                d = json.load(fh)
        else:
            d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print("skip", p, e)
        continue
    if not isinstance(d, dict):
        continue
    feats = d.get("features", []) or []
    kind = {f.get("id"): f.get("op") for f in feats}
    for f in feats:
        if f.get("op") in SOLID_ONLY:
            ins = [kind.get(i) for i in (f.get("inputs") or [])]
            if any(k in ("sketch", "sketch_on_face") for k in ins):
                kind_hits += 1
                print(f"KIND {p}: {f.get('id')} {f.get('op')} -> {ins}")
        num = NUMERIC.get(f.get("op"))
        if not num:
            continue
        for k, v in (f.get("params") or {}).items():
            if k in num and (isinstance(v, bool)
                             or not isinstance(v, (int, float))):
                hits += 1
                print(f"NUM  {p}: {f.get('id')} {f.get('op')} {k}={v!r}")

print(f"\nscanned {files} saved version files")
print(f"  not-a-number numeric params : {hits}")
print(f"  solid-only op fed a sketch  : {kind_hits}")
