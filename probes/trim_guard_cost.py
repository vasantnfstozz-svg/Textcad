"""Where do the guard's 28 seconds go on rocky-balboa/field_sketch?"""
import json, time
import sketch as S
import sketch_trim as T

with open("designs/rocky-balboa.tcad.json", encoding="utf-8") as fh:
    data = json.load(fh)
ents = next(f["params"]["entities"] for f in data["features"]
            if f.get("id") == "field_sketch")
print(f"{len(ents)} entities, "
      f"{sum(1 for e in ents if e.get('mode') == 'subtract')} cuts")

t0 = time.perf_counter()
try:
    a = float(S.compose(ents, note=False).area)
    print(f"compose(before): {time.perf_counter() - t0:.2f}s  area {a:.4f}")
except Exception as ex:
    print(f"compose(before): {time.perf_counter() - t0:.2f}s  RAISED {ex}")

t0 = time.perf_counter()
shapes = [S._entity(e) for e in ents]
print(f"  _entity x{len(ents)}: {time.perf_counter() - t0:.2f}s")
t0 = time.perf_counter()
S._containment(shapes)
print(f"  _containment:      {time.perf_counter() - t0:.2f}s")
modes = [e.get("mode", "add") for e in ents]
t0 = time.perf_counter()
S._compose_order(shapes, modes)
print(f"  _compose_order:    {time.perf_counter() - t0:.2f}s")

# count how many times the guard composes, and whether `after` builds
calls = []
real = S.compose
S.compose = lambda es, note=True: (calls.append(len(es)), real(es, note=note))[1]
try:
    pieces = T.trim_pieces(ents)
    pid = next(p for p in pieces if not p["whole"])["id"]
    calls.clear()
    t0 = time.perf_counter()
    out = T.trim_apply(ents, pid)
    print(f"trim_apply: {time.perf_counter() - t0:.2f}s, "
          f"{len(calls)} compose calls on lists of {calls}")
    print("  ->", out["message"])
finally:
    S.compose = real
