"""probes/s10_required_params_probe.py — the three LAUNCH-PLAN section 10 rows
this pass fixes, MEASURED before anything is touched.

Run:  C:\\Python314\\python.exe probes\\s10_required_params_probe.py

  (1) P2 `op_params` cannot say REQUIRED: a parameter with no default and one
      whose default IS None come back identically, so `author._catalog_text`
      renders both bare and the model cannot tell them apart. An omitted
      required parameter then reaches the feature row as raw Python.
  (2) P2 `is_valid` — what it actually IS in the installed build123d, and
      whether the as-is Solid fast path in blocks._stl_bytes_to_solids is alive.
  (3) P3 a pattern fed a SKETCH answers with a diagnosis about a shape the
      user never asked for.
"""
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

import build123d as b3d                                   # noqa: E402

import author                                             # noqa: E402
import blocks                                             # noqa: E402
import document                                           # noqa: E402
from document import Document, op_params                  # noqa: E402

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]


def line(t):
    print("\n" + "=" * 70 + "\n" + t + "\n" + "=" * 70, flush=True)


# ---------------------------------------------------------------- (1) required
line("(1) op_params: a REQUIRED parameter vs a parameter defaulting to None")

for op in ("extrude", "hole", "sketch", "shell"):
    print(f"  {op:14s} {op_params(op)}", flush=True)

print("\n  the signatures themselves:", flush=True)
for op in ("extrude", "hole"):
    fn = document.MODIFIERS.get(op) or document.CREATORS.get(op)
    for p in list(inspect.signature(fn).parameters.values())[1:]:
        if p.name.startswith("_"):
            continue
        d_ = "<EMPTY>" if p.default is inspect._empty else repr(p.default)
        print(f"    {op}.{p.name:14s} default={d_}", flush=True)

print("\n  what the AI reads in the catalogue:", flush=True)
for ln in author._catalog_text().splitlines():
    if ln.strip().startswith(("extrude(", "hole(", "shell(")):
        print("   ", ln.strip(), flush=True)

print("\n  the row a user sees when the required parameter is omitted:", flush=True)
d = Document(name="p")
d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
d.add("e1", "extrude", {}, ["s1"])                 # no `amount`
d.rebuild()
print("    status  :", d.get("e1").status, flush=True)
print("    problems:", d.get("e1").problems, flush=True)

print("\n  and the raw exception underneath:", flush=True)
try:
    document.MODIFIERS["extrude"](d._parts["s1"])
except Exception as e:                             # noqa: BLE001
    print(f"    {type(e).__name__}: {e}", flush=True)
    print(f"    plain_cause -> {blocks.plain_cause(e)!r}", flush=True)


# ---------------------------------------------------------------- (2) is_valid
line("(2) is_valid in the installed build123d")

print("  build123d", getattr(b3d, "__version__", "?"), flush=True)
box = b3d.Box(10, 10, 10)
for klass in type(box).__mro__:
    if "is_valid" in klass.__dict__:
        print(f"  is_valid lives on {klass.__name__} as "
              f"{type(klass.__dict__['is_valid']).__name__}", flush=True)
        break
print("  isinstance(box.is_valid, bool):", isinstance(box.is_valid, bool), flush=True)
try:
    box.is_valid()
except Exception as e:                             # noqa: BLE001
    print(f"  calling it as a METHOD -> {type(e).__name__}: {e}", flush=True)

print("\n  where the project still names it (product code only):", flush=True)
for f in ("blocks.py", "document.py", "author.py", "pattern.py",
          "sketch.py", "inspector.py", "studio.py", "kernelguard.py"):
    for i, ln in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"\.is_valid\b", ln):
            call = "METHOD CALL" if re.search(r"\.is_valid\s*\(", ln) else "property"
            print(f"    {f}:{i} [{call}] {ln.strip()}", flush=True)

print("\n  the as-is Solid fast path (blocks._stl_bytes_to_solids): alive?", flush=True)
solid = b3d.Solid.make_box(10, 10, 10)
print("    isinstance(Solid)", isinstance(solid, b3d.Solid),
      " volume", solid.volume, " is_valid", bool(solid.is_valid), flush=True)


# ---------------------------------------------------------------- (3) pattern
line("(3) a pattern fed a SKETCH")

for op, params in (("linear_pattern", {"count": 3, "dx": 20}),
                   ("polar_pattern", {"count": 4, "axis": "Z"})):
    d = Document(name="pat")
    d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add("p1", op, params, ["s1"])
    d.rebuild()
    f = d.get("p1")
    print(f"  {op}: status={f.status}", flush=True)
    print(f"    problems: {f.problems}", flush=True)

print("\n  what the two EXISTING gates say, for comparison:", flush=True)
d = Document(name="c")
d.add("p1", "plate", {"width": 20, "depth": 20, "thickness": 10}, [])
d.add("s1", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
d.add("cut1", "cut", {}, ["p1", "s1"])
d.add("ex1", "extrude", {"amount": 4}, ["p1"])
d.rebuild()
print("    combiner:", d.get("cut1").problems, flush=True)
print("    modifier:", d.get("ex1").problems, flush=True)
