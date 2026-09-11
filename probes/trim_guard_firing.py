"""How often does the delete guard actually REFUSE, and on what?

The sweep counted "results the builder refuses" including the empty list a
last-entity delete leaves, which the guard skips. This counts the guard's own
refusals, and splits them by cause.
"""
import json, glob, os
import sketch_trim as T

MAXN, CAP = 14, 8
refused = allowed = empty = 0
causes = {}
for path in sorted(glob.glob("designs/*.tcad.json")):
    name = os.path.basename(path)[:-len(".tcad.json")]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for f in data.get("features", []):
        ents = (f.get("params") or {}).get("entities")
        if not ents or len(ents) > MAXN:
            continue
        try:
            pieces = [p for p in T.trim_pieces(ents) if p["whole"]]
        except Exception:
            continue
        for p in pieces[:CAP]:
            try:
                out = T.trim_apply(ents, p["id"])
            except ValueError as ex:
                if "builder cannot make" in str(ex):
                    refused += 1
                    tail = str(ex).split("—")[-1].strip()[:60]
                    causes[tail] = causes.get(tail, 0) + 1
                    if refused <= 6:
                        print(f"   REFUSED {name}/{f.get('id')} ent "
                              f"{p['ent']} ({ents[p['ent']].get('kind')}, "
                              f"{ents[p['ent']].get('mode','add')}): {tail}")
                continue
            allowed += 1
            if not out["entities"]:
                empty += 1
print()
print(f"  whole-entity deletes: {allowed} allowed ({empty} left an EMPTY "
      f"sketch, allowed on purpose), {refused} refused by the guard")
for k, v in sorted(causes.items(), key=lambda kv: -kv[1]):
    print(f"    {v:4d}x  {k}")
