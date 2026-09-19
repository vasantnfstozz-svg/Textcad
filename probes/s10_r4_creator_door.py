"""Round FOUR, attack on round three's P0 fix: the CREATORS now go through
`_check_numeric_params`, the door written for the MODIFIERS.

Three questions the brief puts to it:

  1. did a sentence that was BETTER before get lost?
  2. was the UNIT lost where the unit mattered?
  3. is there a THIRD class of parameter where None or a negative genuinely
     IS the intended value, and is now refused?

Answered by walking the registry itself: every op, every numeric parameter,
its annotation, its DEFAULT, and — where the default is None or the parameter
is optional — by putting the real value to the kernel.

Run: C:\\Python314\\python.exe probes/s10_r4_creator_door.py
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document import COMBINERS, CREATORS, MODIFIERS, Document      # noqa: E402

print("=" * 78)
print("1. every numeric parameter of every op: annotation + DEFAULT")
print("=" * 78)
print(f"{'op':<18}{'kind':<10}{'param':<20}{'default':<14}{'in numeric_params'}")
none_defaults = []
for kind, reg in (("creator", CREATORS), ("modifier", MODIFIERS),
                  ("combiner", COMBINERS)):
    for op, fn in sorted(reg.items()):
        numeric = Document.numeric_params(op)
        for p in inspect.signature(fn).parameters.values():
            if p.name.startswith("_") or p.name not in numeric:
                continue
            dflt = "REQUIRED" if p.default is p.empty else repr(p.default)
            print(f"{op:<18}{kind:<10}{p.name:<20}{dflt:<14}{p.name in numeric}")
            if p.default is None:
                none_defaults.append((op, kind, p.name))
print()
print("numeric parameters whose DEFAULT is None (None would be a real answer):")
print("  ", none_defaults or "none")

print()
print("=" * 78)
print("2. a numeric parameter whose ANNOTATION admits None (float | None)")
print("=" * 78)
for kind, reg in (("creator", CREATORS), ("modifier", MODIFIERS),
                  ("combiner", COMBINERS)):
    for op, fn in sorted(reg.items()):
        numeric = Document.numeric_params(op)
        for p in inspect.signature(fn).parameters.values():
            if p.name.startswith("_"):
                continue
            ann = p.annotation
            txt = ann if isinstance(ann, str) else getattr(ann, "__name__", str(ann))
            if "None" in str(txt) and ("float" in str(txt) or "int" in str(txt)):
                print(f"  {op:<18}{p.name:<20}{txt!r:<28}"
                      f"in numeric_params: {p.name in numeric}")

print()
print("=" * 78)
print("3. the sentence a CREATOR gave before, and the one it gives now")
print("=" * 78)
CASES = [
    ("plate", {"width": None, "depth": 20, "thickness": 5}),
    ("disc", {"radius": None, "thickness": 5}),
    ("ball", {"radius": None}),
    ("cone", {"radius1": None, "radius2": 2, "height": 5}),
    ("tube", {"outer_radius": None, "inner_radius": 2, "height": 5}),
    ("hex_plate", {"across_flats": None, "thickness": 5}),
    ("polygon_plate", {"sides": None, "radius": 10, "thickness": 5}),
    ("curved_blade", {"inner_radius": None, "outer_radius": 20,
                      "height": 5, "thickness": 2,
                      "inlet_angle_deg": 30, "exit_angle_deg": 60}),
]
for op, params in CASES:
    fn = CREATORS[op]
    try:                            # what the BLOCK itself says, unchanged
        fn(**params)
        block = "(built)"
    except Exception as e:                                         # noqa: BLE001
        block = f"{type(e).__name__}: {e}"
    d = Document(name="c")
    d.add("c1", op, params, [])
    d.rebuild()
    print(f"\n{op}")
    print(f"   block  : {block}")
    print(f"   tree    : {' '.join(d.get('c1').problems)}")

print()
print("=" * 78)
print("4. a DEGREES / COUNT parameter: does the tree still name the unit?")
print("=" * 78)
for op, params, key in (("polygon_plate", {"sides": "x", "radius": 10,
                                           "thickness": 5}, "sides"),
                        ("curved_blade", {"inner_radius": 10, "outer_radius": 20,
                                          "height": 5, "thickness": 2,
                                          "inlet_angle_deg": None,
                                          "exit_angle_deg": 60},
                         "inlet_angle_deg")):
    d = Document(name="c")
    d.add("c1", op, params, [])
    d.rebuild()
    print(f"  {op}.{key}: {' '.join(d.get('c1').problems)}")

print()
print("=" * 78)
print("5. REQUIRED + optional numeric params: is a MISSING one still allowed?")
print("=" * 78)
for op, params in (("sketch", {"entities": [{"kind": "circle", "x": 0, "y": 0,
                                             "r": 5, "mode": "add"}],
                               "plane": "XY"}),          # no offset at all
                   ("cone", {"radius1": 10, "radius2": 0, "height": 5})):
    d = Document(name="c")
    d.add("c1", op, params, [])
    ok = d.rebuild()
    f = d.get("c1")
    print(f"  {op:<10} ok={ok} status={f.status} volume={f.volume} {f.problems}")
