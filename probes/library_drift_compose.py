"""Probe: does the fifth-review composition-order change move ANY of the
user's 50 live designs?

Run with `old` to restore the pre-fix `_compose_order` (the overlap pass gated
on a LEADING cut) in-process, or `new` for HEAD. Prints one line per design:
name, feature count, and the volume of every leaf body, 4 decimals.
Nothing is written; every design is read with Document.from_data.
"""
import sys, json, glob, os, time
import sketch as S

MODE = sys.argv[1] if len(sys.argv) > 1 else "new"

if MODE == "old":                       # the code as it stood before the fix
    def _old_compose_order(shapes, modes=None):
        n = len(shapes)
        inside = S._containment(shapes)
        needs = [row[:] for row in inside]
        order = S._order_from(needs)
        if modes is None:
            return order
        for _ in range(n):
            lead = []
            for i in order:
                if modes[i] != "subtract":
                    break
                lead.append(i)
            if not lead:
                break
            grew = False
            for i in lead:
                for j in range(n):
                    if (i == j or modes[j] == "subtract"
                            or needs[i][j] or needs[j][i]
                            or inside[i][j] or inside[j][i]):
                        continue
                    if S._overlaps(shapes[j], shapes[i]):
                        needs[i][j] = True
                        grew = True
            if not grew:
                break
            order = S._order_from(needs)
        return order
    S._compose_order = _old_compose_order

from document import Document           # noqa: E402  (after the patch)

out = {}
for path in sorted(glob.glob("designs/*.tcad.json")):
    name = os.path.basename(path)[:-len(".tcad.json")]
    try:
        with open(path, encoding="utf-8") as fh:
            doc = Document.from_data(json.load(fh))
        t0 = time.perf_counter()
        doc.rebuild()
        secs = round(time.perf_counter() - t0, 3)
        vols = []
        for fid in doc.leaf_solid_ids():
            p = doc._parts.get(fid)
            try:
                vols.append([fid, round(float(p.volume), 4)])
            except Exception:
                vols.append([fid, None])
        out[name] = {"n": len(doc.features), "vols": vols,
                     "secs": secs, "warn": sorted(doc.warnings)}
    except Exception as ex:
        out[name] = {"error": f"{type(ex).__name__}: {ex}"}
    print(f"  {name:30s} {out[name].get('error') or out[name]['vols']}"[:150],
          flush=True)

with open(f"probes/_library_{MODE}.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, sort_keys=True)
print("wrote", f"probes/_library_{MODE}.json")
