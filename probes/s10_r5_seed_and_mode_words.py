r"""Round FIVE, part 6: what the full census turned up.

  1  A pattern's or a mirror's `seed` that a file holds as a LIST or a DICT.
     `_eval` hands `kw["seed"]` to `_seed_parts` raw, while the very next line
     hands `str(kw["path"])` to `_path_part` -- so the seed reaches
     `delta_features`' `by_id.get(seed)` unhashable. Round four's census never
     fed `seed`: it walks the keys its own BASE dict sets, and `seed` is not
     one of them for any op.

  2  A MODE WORD nobody recognises. `linear_steps` reads
     `distance if distance_type == "spacing" else distance / (count - 1)`, so
     every word that is not exactly "spacing" is the OTHER mode. Does a typo
     silently change the geometry, and how does the sibling gate (`shell`'s
     `direction`) answer the same shape?

  3  `sweep`'s legacy `path_points` with no `path` beside it.

READ-ONLY with respect to designs/.

Run: C:\Python314\python.exe probes/s10_r5_seed_and_mode_words.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pattern                                                      # noqa: E402
from document import Document                                       # noqa: E402

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]


def line(t):
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


line("1. a seed a file holds as a list or a dict")
for op in pattern.SEEDED_OPS:
    for bad in ([1, 2], {"a": 1}, [[1, 2]], "ghost", 5):
        d = Document(name="s")
        d._cache = {}
        d.add("body", "plate", {"width": 40, "depth": 40, "thickness": 10}, [])
        d.add("h", "with_center_hole", {"radius": 3}, ["body"])
        params = {"seed": bad}
        params.update({"linear_pattern": {"count": 3, "dx": 8},
                       "polar_pattern": {"count": 3, "axis": "+z"},
                       "mirror": {"plane": "YZ"}}[op])
        d.add("p", op, params, ["h"])
        try:
            d.rebuild()
            said = (d.get("p").problems or ["(built)"])[0]
        except Exception as e:                                      # noqa: BLE001
            said = f"RAISED {type(e).__name__}: {e}"
        print(f"  {op:16s} seed={bad!r:10s} -> {said[:95]}")

line("2. the mode word: is an unknown one named, or silently the other mode?")


def span(distance_type, count=3, distance=20.0):
    d = Document(name="m")
    d._cache = {}
    d.add("body", "plate", {"width": 8, "depth": 8, "thickness": 4}, [])
    d.add("p", "linear_pattern",
          {"count": count, "direction": [1, 0, 0], "distance": distance,
           "distance_type": distance_type}, ["body"])
    d.rebuild()
    f = d.get("p")
    if f.status != "ok":
        return f"refused: {(f.problems or [''])[0][:70]}"
    bb = d._parts["p"].bounding_box()
    return f"x {round(bb.min.X, 3)} .. {round(bb.max.X, 3)}  vol {f.volume}"


print(f"   linear_steps('spacing') = {pattern.linear_steps(3, 20.0, 'spacing')}")
print(f"   linear_steps('extent')  = {pattern.linear_steps(3, 20.0, 'extent')}")
print(f"   linear_steps('spacng')  = {pattern.linear_steps(3, 20.0, 'spacng')}"
      "   <- a TYPO of the first word")
for w in ("spacing", "extent", "total", "spacng", "SPACING", "", None, 0):
    print(f"   distance_type={w!r:10s} -> {span(w)}")

print("\n   the sibling gate, for the comparison: shell's `direction`")
for w in ("inside", "outside", "insde", "", None):
    d = Document(name="sh")
    d._cache = {}
    d.add("b", "plate", {"width": 20, "depth": 20, "thickness": 10}, [])
    d.add("s", "shell", {"thickness": 1, "direction": w}, ["b"])
    d.rebuild()
    f = d.get("s")
    print(f"   direction={w!r:10s} -> {f.status} {f.volume} "
          f"{(f.problems or [''])[0][:60]}")

line("3. sweep's legacy path_points, with no `path` beside it")
for pp in (None, "abc", [[0, 0, 0], [0, 0, 20]], [1, 2], {"a": 1}, True):
    d = Document(name="pp")
    d._cache = {}
    d.add("prof", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add("sw", "sweep", {"path_points": pp, "full": True}, ["prof"])
    try:
        d.rebuild()
        f = d.get("sw")
        said = f"{f.status} vol={f.volume} {(f.problems or [''])[0][:70]}"
    except Exception as e:                                          # noqa: BLE001
        said = f"RAISED {type(e).__name__}: {e}"
    print(f"   path_points={pp!r:22s} -> {said}")
