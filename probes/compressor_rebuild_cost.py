"""probes/compressor_rebuild_cost.py -- WHERE does the compressor sample's
1-2 minute rebuild actually go?  (LAUNCH-PLAN s10: "Compressor sample rebuild
~1-2 min.")

Measure before changing anything. Times, for a COLD process:
  * meanline.design()               (pure arithmetic)
  * every feature's own _eval        (the kernel calls, one row each)
  * the health check per feature
  * the deep validity pass
  * the spec check (symmetry proof over 13 blades is the suspect)
  * the mesh the viewport needs, if asked for

Run serially. Nothing else may touch OpenCASCADE beside it.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import document  # noqa: E402
import inspector  # noqa: E402
import samples  # noqa: E402

WHICH = sys.argv[1] if len(sys.argv) > 1 else "compressor"

eval_times: list[tuple[str, str, float]] = []
health_times: list[tuple[str, float]] = []
deep_times: list[float] = []

_eval = document.Document._eval
_health = inspector.health
_deep = document._deep_valid


def timed_eval(self, f):
    t0 = time.perf_counter()
    try:
        return _eval(self, f)
    finally:
        eval_times.append((f.id, f.op, time.perf_counter() - t0))


def timed_health(part, **kw):
    t0 = time.perf_counter()
    try:
        return _health(part, **kw)
    finally:
        health_times.append((str(kw), time.perf_counter() - t0))


def timed_deep(part):
    t0 = time.perf_counter()
    try:
        return _deep(part)
    finally:
        deep_times.append(time.perf_counter() - t0)


document.Document._eval = timed_eval
inspector.health = timed_health
document._deep_valid = timed_deep

t0 = time.perf_counter()
doc = samples.SAMPLES[WHICH]()
t_make = time.perf_counter() - t0

t0 = time.perf_counter()
ok = doc.rebuild()
t_rebuild = time.perf_counter() - t0

print(f"=== {WHICH}: {doc.name} ===")
print(f"  build the tree object (incl. meanline.design): {t_make * 1000:8.1f} ms")
print(f"  doc.rebuild() total                          : {t_rebuild:8.2f} s "
      f"(ok={ok})")
print(f"\n  per-feature _eval ({len(eval_times)} features):")
for fid, op, dt in eval_times:
    print(f"    {fid:16s} {op:18s} {dt * 1000:10.1f} ms")
print(f"    {'SUM':16s} {'':18s} "
      f"{sum(d for _, _, d in eval_times) * 1000:10.1f} ms")
print(f"\n  inspector.health calls: {len(health_times)}, "
      f"{sum(d for _, d in health_times) * 1000:.1f} ms total")
for kw, dt in health_times:
    print(f"    health({kw}) {dt * 1000:8.1f} ms")
print(f"  _deep_valid calls: {len(deep_times)}, "
      f"{sum(deep_times) * 1000:.1f} ms total")
accounted = (sum(d for _, _, d in eval_times) + sum(d for _, d in health_times)
             + sum(deep_times))
print(f"\n  accounted for : {accounted:8.2f} s")
print(f"  unaccounted   : {t_rebuild - accounted:8.2f} s  "
      f"(spec check / signatures / bookkeeping)")
print(f"\n  spec: {doc.spec}")
print(f"  spec_problems: {doc.spec_problems}")

# the spec check on its own, with the parts already built
if doc.spec:
    t0 = time.perf_counter()
    doc._spec_cache = None
    doc.rebuild()
    print(f"\n  WARM rebuild (feature cache hot): "
          f"{time.perf_counter() - t0:.2f} s")

res = doc.result()
if res is not None:
    t0 = time.perf_counter()
    n = inspector.is_rotationally_symmetric(res, doc.spec.get("symmetry", 13))
    print(f"  is_rotationally_symmetric(result, "
          f"{doc.spec.get('symmetry')}) = {n} in "
          f"{time.perf_counter() - t0:.2f} s")
    t0 = time.perf_counter()
    m = inspector.measure(res)
    print(f"  inspector.measure(result) in {time.perf_counter() - t0:.2f} s: "
          f"volume={m['volume']} faces={len(res.faces())} "
          f"n_solids={m['n_solids']}")
