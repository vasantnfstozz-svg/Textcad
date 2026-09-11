"""Round two of the 3b230b7 review: the fix removed the builder check from the
REBUILD branch, on the argument that the cluster has already composed and
nothing outside a cluster touches anything inside it. That argument is only
worth what the measurement behind it is worth.

Every REBUILD trim of every sketch in the library up to MAXN entities, as many
pieces as PIECES allows, each result handed straight to the builder. Any
result the builder refuses is a hole in the argument.
"""
import json, glob, os
import sketch as S
import sketch_trim as T

MAXN, PIECES = 20, 40
ran = refused = 0
for path in sorted(glob.glob("designs/*.tcad.json")):
    name = os.path.basename(path)[:-len(".tcad.json")]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for f in data.get("features", []):
        ents = (f.get("params") or {}).get("entities")
        if not ents or len(ents) > MAXN:
            continue
        try:
            pieces = [p for p in T.trim_pieces(ents) if not p["whole"]]
        except Exception:
            continue
        step = max(1, len(pieces) // PIECES)
        for p in pieces[::step][:PIECES]:
            try:
                out = T.trim_apply(ents, p["id"])
            except ValueError:
                continue                       # a refusal is not a rebuild
            ran += 1
            try:
                S.compose(out["entities"], note=False)
            except Exception as ex:
                refused += 1
                print(f"   HOLE: {name}/{f.get('id')} piece {p['id']} -> "
                      f"{str(ex)[:80]}")
    print(f"  ...{name}: running total {ran} rebuilds, {refused} refused",
          flush=True)
print()
print(f"  REBUILD trims run: {ran}   results the builder refuses: {refused}")
