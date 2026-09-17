r"""probes/wire_sample_probe.py — can a wire be sampled without re-walking it?

`sketch_trim._outline` samples an entity's outer wire with
`wire.position_at(i / n)`. The profile (probes/trim_profile.py) says that ONE
call is 99% of Trim's hover cost, because build123d's `Wire._occt_param_at`
rebuilds the whole edge table on EVERY call:

    self_edges   = self.edges()              # E python Edge objects
    edge_lengths = [e.length for e in ...]   # E BRepGProp calls
    cumulative   = running sums
    bisect -> target_edge, local_frac
    local_frac   = 1 - local_frac  if not target_edge.is_forward
    param        = target_edge.param_at(local_frac)
    return Vector(target_edge.geom_adaptor().Value(param))

On `rocky-balboa/field_sketch` the traced polygons have ~250 edges each, so
2671 sample points built 247,466 Edge objects.

Everything above the bisect is the SAME for every sample of one wire. This
probe checks the claim that makes the fix safe:

    wire.position_at(f)  ==  target_edge.position_at(local_dist / edge.length)

exactly — same float bits — because `Edge.position_at` applies the very same
`1 - x` flip and the very same `param_at` formula the wire applies by hand.

Run:  C:\Python314\python.exe probes/wire_sample_probe.py
"""
from __future__ import annotations
import json
import struct
import sys
import time
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sketch as sk                                           # noqa: E402


def bits(x: float) -> str:
    return struct.pack("<d", x).hex()


def hoisted(wire, n: int):
    """The same points, with the per-wire table built once."""
    wire_len = wire.length
    fwd = wire.is_forward
    edges = wire.edges()
    lens = [e.length for e in edges]
    cum, total = [], 0.0
    for L in lens:
        total += L
        cum.append(total)
    out = []
    for i in range(n):
        position = i / n
        if not fwd:
            position = 1.0 - position
        distance = position * wire_len
        if distance <= 0.0:
            k, local = 0, 0.0
        elif distance >= total:
            k = len(edges) - 1
            local = lens[k]
        else:
            k = bisect_right(cum, distance)
            local = distance - (cum[k - 1] if k > 0 else 0.0)
        e = edges[k]
        frac = 0.0 if lens[k] == 0 else local / lens[k]
        out.append(e.position_at(frac))
    return out


def stock(wire, n: int):
    return [wire.position_at(i / n) for i in range(n)]


def check(label, e):
    face = sk._entity(e).faces()[0]
    wire = face.outer_wire()
    n = int(min(max(wire.length / 0.8, 96), 384))
    t = time.perf_counter()
    a = stock(wire, n)
    t_stock = time.perf_counter() - t
    t = time.perf_counter()
    b = hoisted(wire, n)
    t_hoist = time.perf_counter() - t
    bad = [i for i in range(n)
           if bits(a[i].X) != bits(b[i].X) or bits(a[i].Y) != bits(b[i].Y)]
    print(f"  {label:34s} edges={len(wire.edges()):4d} n={n:3d}  "
          f"stock {t_stock * 1000:7.1f} ms  hoisted {t_hoist * 1000:6.1f} ms  "
          f"speedup {t_stock / max(t_hoist, 1e-9):6.1f}x  "
          f"{'IDENTICAL' if not bad else f'DIFFERS at {bad[:4]}'}")
    if bad:
        i = bad[0]
        print(f"      stock {a[i].X!r},{a[i].Y!r}  hoisted {b[i].X!r},{b[i].Y!r}")
    return not bad


def load(design: str, sketch_id: str) -> list:
    d = json.loads((ROOT / "designs" / f"{design}.tcad.json")
                   .read_text(encoding="utf-8"))
    f = next(f for f in d["features"] if f.get("id") == sketch_id)
    return f["params"]["entities"]


if __name__ == "__main__":
    ok = True
    print("synthetic kinds (every primitive _entity builds):")
    synth = [
        {"kind": "rectangle", "w": 40, "h": 25, "x": 2, "y": -3},
        {"kind": "circle", "r": 12},
        {"kind": "ellipse", "rx": 15, "ry": 6, "rotation": 31},
        {"kind": "slot", "length": 30, "height": 8, "rotation": 90},
        {"kind": "regular_polygon", "radius": 14, "sides": 7},
        {"kind": "polygon", "points": [[0, 0], [20, 0], [20, 10], [8, 17]]},
        {"kind": "path", "x": 0, "y": 0, "start": [0, 0], "segments": [
            {"type": "line", "to": [20, 0]},
            {"type": "arc", "via": [26, 6], "to": [20, 12]},
            {"type": "line", "to": [0, 12]},
            {"type": "arc", "via": [-5, 6], "to": [0, 0]}]},
    ]
    for e in synth:
        ok &= check(e["kind"], e)
    for design, sid in [("rocky-balboa", "field_sketch"),
                        ("esp32-remote", "sketch28")]:
        print(f"{design}/{sid}:")
        for i, e in enumerate(load(design, sid)):
            ok &= check(f"[{i}] {e.get('kind')}", e)
    print("ALL IDENTICAL" if ok else "MISMATCH — do not ship")
