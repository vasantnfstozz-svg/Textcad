"""Round FOUR, two loose ends the shape census left pointing at a line:

  * `_fail_key` (round three's own fix) joins `f.inputs` with a comma. It runs
    in `rebuild`'s pre-`try` region, so a non-string input id there takes the
    WHOLE rebuild down — the very class round three closed for `params`.
  * `spec` that is not a dict: which call on /api/doc raises?

Run: C:\\Python314\\python.exe probes/s10_r4_fail_key_and_spec.py
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document import Document                                      # noqa: E402

PLATE = {"width": 20, "depth": 20, "thickness": 5}

print("=" * 72)
print("1. a FAILING feature whose input id is not a string")
print("=" * 72)
d = Document.from_data({"name": "n", "features": [
    {"id": 5, "op": "plate", "params": PLATE, "inputs": []},
    {"id": "b", "op": "fillet", "params": {"radius": None}, "inputs": [5]},
]})
try:
    d.rebuild()
    print("rebuild returned;", [(f.id, f.status, f.problems) for f in d.features])
except Exception:                                                  # noqa: BLE001
    print("rebuild RAISED:")
    traceback.print_exc(limit=4)

print()
print("=" * 72)
print("2. `spec` that is not a dict — which call raises?")
print("=" * 72)
d = Document.from_data({"name": "n", "spec": [1, 2], "features": [
    {"id": "a", "op": "plate", "params": PLATE, "inputs": []}]})
for name, call in (("rebuild", d.rebuild), ("parameters_json", d.parameters_json),
                   ("tree", d.tree), ("to_data", d.to_data),
                   ("leaf_solid_ids", d.leaf_solid_ids),
                   ("consumed_ids", d.consumed_ids),
                   ("result_bodies", d.result_bodies),
                   ("_spec_obj", d._spec_obj)):
    try:
        call()
        print(f"  {name:<18} ok")
    except Exception as e:                                         # noqa: BLE001
        print(f"  {name:<18} {type(e).__name__}: {e}")

print()
print("=" * 72)
print("3. `parameters` that is not a dict — the file's own promise")
print("=" * 72)
for bad in ([1, 2], "wall", 5):
    try:
        Document.from_data({"name": "n", "parameters": bad, "features": [
            {"id": "a", "op": "plate", "params": PLATE, "inputs": []}]})
        print(f"  parameters={bad!r:<10} opened")
    except Exception as e:                                         # noqa: BLE001
        print(f"  parameters={bad!r:<10} {type(e).__name__}: {e}")
