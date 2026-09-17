"""probes/s10_round_two_attack.py — round TWO of the review of 15eff19..9de0dc2.

§A  the mirror matrix round one's fix created: seed x join x input kind.
    Does the gate agree with `pattern.mirror` in EVERY cell, and can it now
    refuse a joined mirror of a real solid?
§B  a SEEDED pattern fed a sketch — the cell where the gate ignores `seed`
    and `mirror` defers to it.
§C  a sketch with NO area (the gate's other half).
§D  revolve_face with a valid axis, on a solid and on a sketch — the census
    could not decide it with an axis missing.

Run:  C:\\Python314\\python.exe probes\\s10_round_two_attack.py
"""
import sys

sys.path.insert(0, ".")

from document import Document, n_solids            # noqa: E402
import inspector                                   # noqa: E402

ONE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]


def run(build):
    d = Document(name="a")
    build(d)
    try:
        d.rebuild()
    except Exception as e:                          # a raise out of rebuild is itself news
        return f"RAISED {type(e).__name__}: {e}"
    f = d.get("p1")
    return f"{f.status:7s} vol={f.volume} :: " + " | ".join(f.problems or [])


def sketch_src(d):
    d.add("s1", "sketch", {"entities": ONE, "plane": "XY", "offset": 0.0}, [])
    return "s1"


def solid_src(d):
    d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    return "b1"


print("=" * 78)
print("§A  mirror: seed x join x input kind")
print("=" * 78)
for kind, src in (("sketch", sketch_src), ("solid", solid_src)):
    for seed in (None, "", "b1", "s1"):
        for join in (False, True, "false", 0, 1):
            def build(d, src=src, seed=seed, join=join):
                s = src(d)
                params = {"plane": "YZ", "join": join}
                if seed is not None:
                    params["seed"] = seed
                d.add("p1", "mirror", params, [s])
            print(f"  {kind:6s} seed={seed!r:6s} join={join!r:7s} -> {run(build)}")

print()
print("=" * 78)
print("§B  a SEEDED pattern / mirror fed a SKETCH, seed = a real solid feature")
print("=" * 78)
for op, extra in (("linear_pattern", {"count": 2, "dx": 20}),
                  ("polar_pattern", {"count": 3}),
                  ("mirror", {"plane": "YZ"}),
                  ("mirror", {"plane": "YZ", "join": True})):
    def build(d, op=op, extra=extra):
        d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
        d.add("h1", "with_center_hole", {"radius": 2}, ["b1"])
        d.add("s1", "sketch", {"entities": ONE, "plane": "XY", "offset": 20.0}, [])
        d.add("p1", op, {**extra, "seed": "h1"}, ["s1"])
    print(f"  {op:16s} {str(extra)[:30]:32s} -> {run(build)}")

print()
print("=" * 78)
print("§C  an EMPTY sketch (no entities): what the gate's area half sees")
print("=" * 78)
d = Document(name="e")
d.add("s1", "sketch", {"entities": [], "plane": "XY", "offset": 0.0}, [])
d.rebuild()
part = d._parts.get("s1")
print(f"  part={type(part).__name__ if part is not None else None} "
      f"n_solids={n_solids(part)} area={inspector._try(lambda: part.area)} "
      f"status={d.get('s1').status} {d.get('s1').problems}")
for op, params in (("mirror", {"plane": "YZ", "join": True}),
                   ("linear_pattern", {"count": 3, "dx": 20}),
                   ("fillet", {"radius": 1}),
                   ("shell", {"thickness": 1})):
    def build(d2, op=op, params=params):
        d2.add("s1", "sketch", {"entities": [], "plane": "XY", "offset": 0.0}, [])
        d2.add("p1", op, params, ["s1"])
    print(f"  {op:16s} -> {run(build)}")

print()
print("=" * 78)
print("§D  revolve_face with a valid axis")
print("=" * 78)
for kind, src in (("solid", solid_src), ("sketch", sketch_src)):
    for axis in ("u", "v", [[-5, -5], [5, -5]]):
        def build(d, src=src, axis=axis):
            s = src(d)
            d.add("p1", "revolve_face",
                  {"face_center": [0, 0, 5] if src is solid_src else [0, 0, 0],
                   "face_normal": [0, 0, 1], "axis": axis, "angle": 90}, [s])
        print(f"  {kind:6s} axis={str(axis)[:22]:24s} -> {run(build)}")
