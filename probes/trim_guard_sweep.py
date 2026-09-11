"""Does the guard ever fire on the REBUILD branch, or on deleting a CUT?

Runs every trim piece of every sketch in the user's library (capped per
sketch), records which branch it took and whether the builder would refuse
the result. If the rebuild branch never produces an unbuildable list, the
guard there is 28 seconds of nothing.
"""
import json, glob, os, time
import sketch as S
import sketch_trim as T

CAP = 8                        # pieces per sketch
MAXN = 16                      # entities: above this a click costs minutes
stats = {"whole_add": [0, 0], "whole_cut": [0, 0], "rebuild": [0, 0]}
slow = []

for path in sorted(glob.glob("designs/*.tcad.json")):
    name = os.path.basename(path)[:-len(".tcad.json")]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for f in data.get("features", []):
        ents = (f.get("params") or {}).get("entities")
        if not ents or len(ents) > MAXN:
            continue
        try:
            pieces = T.trim_pieces(ents)
        except Exception:
            continue
        step = max(1, len(pieces) // CAP)
        for p in pieces[::step][:CAP]:
            i = p["ent"]
            try:
                t0 = time.perf_counter()
                out = T.trim_apply(ents, p["id"])
                dt = time.perf_counter() - t0
            except Exception:
                continue
            if p["whole"]:
                key = ("whole_cut" if ents[i].get("mode") == "subtract"
                       else "whole_add")
            else:
                key = "rebuild"
            stats[key][0] += 1
            try:
                S.compose(out["entities"], note=False)
            except Exception as ex:
                stats[key][1] += 1
                print(f"   REFUSED-WORTHY {key} {name}/{f.get('id')} "
                      f"{p['id']}: {str(ex)[:70]}")
            if dt > 3:
                slow.append((round(dt, 1), name, f.get("id"), key))

print()
print(f"  (sketches of at most {MAXN} entities, {CAP} pieces each)")
for k, (n, bad) in stats.items():
    print(f"  {k:11s} trims run {n:4d}   result the builder refuses: {bad}")
print()
print("  slowest clicks (s, design, feature, branch):")
for row in sorted(slow, reverse=True)[:8]:
    print("   ", row)
