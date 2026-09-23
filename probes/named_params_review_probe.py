"""PROBE - review of the Named parameters tool (127f350 + 4343f30), 2026-09-23.

Each section measures one suspected defect found by reading the code:

  1. `floor(1e400)` - `math.floor(inf)` raises OverflowError, which the
     evaluator's call guard does not catch. Where does it go?
  2. `round(x, 2)` - the evaluator hands every argument over as a FLOAT, and
     `round(3.14159, 2.0)` is a TypeError in Python.
  3. A `move` driven by a parameter: changing the parameter moves the body,
     but the face picks downstream are carried only by `edit_many`.
  4. The edit panels: `edit_many` with the formula's own current value
     replaces the formula by a number.
  5. Measure's sketch plane and hole driver read `float(params[...])`.
  6. A file whose feature id equals a parameter name.
  7. An `int` parameter fed a formula (always a float).

Run: python probes/memcap.py --gb 4 --timeout 600 -- python probes/named_params_review_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paramexpr                     # noqa: E402
from document import Document        # noqa: E402


def vol(doc):
    doc.rebuild()
    bad = [(f.id, f.status, f.problems[:1]) for f in doc.features if f.status != "ok"]
    body = doc.result()
    return (round(body.volume, 2) if body is not None else None), bad


print("== 1. floor(1e400)")
for expr in ("floor(1e400)", "ceil(1e308*10)", "round(1e400)"):
    try:
        print("  ", expr, "->", paramexpr.evaluate(expr, {}))
    except ValueError as e:
        print("  ", expr, "-> sentence:", e)
    except Exception as e:              # noqa: BLE001 - that is the question
        print("  ", expr, "-> RAW", type(e).__name__, e)
doc = Document(name="p")
try:
    doc.set_parameter("a", "floor(1e400)")
    print("   set_parameter accepted it")
except ValueError as e:
    print("   set_parameter sentence:", e)
except Exception as e:                  # noqa: BLE001
    print("   set_parameter RAW", type(e).__name__, "; parameters now:", doc.parameters)
try:
    Document.from_data(doc.to_data())
    print("   the saved file reopens")
except Exception as e:                  # noqa: BLE001
    print("   the saved file does NOT reopen:", type(e).__name__, e)

print("== 2. round(x, 2)")
for expr in ("round(3.14159, 2)", "round(3.6)"):
    try:
        print("  ", expr, "->", paramexpr.evaluate(expr, {}))
    except ValueError as e:
        print("  ", expr, "-> sentence:", e)

print("== 3. a move driven by a parameter carries the face picks?")
BOSS_TOP, UP = [0.0, 0.0, 15.0], [0.0, 0.0, 1.0]


def stepped(z):
    d = Document(name="p-frame")
    d.set_parameter("lift", "0")
    d.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    d.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    d.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8, "x": 0, "y": 0}]})
    d.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    d.add("part", "fuse", {}, inputs=["base", "boss"])
    d.add("placed", "move", {"x": 0, "y": 0, "z": z}, inputs=["part"])
    d.add("riser", "extrude_face", {"face_center": list(BOSS_TOP),
                                    "face_normal": list(UP), "amount": 5},
          inputs=["placed"])
    d.add("final", "fuse", {}, inputs=["placed", "riser"])
    return d


d = stepped(0)
print("   at 0            :", vol(d))
d.edit_many("placed", {"z": 3})
print("   Move tool z=3   :", vol(d), d.get("riser").params["face_center"])
d = stepped("lift")
print("   z='lift', lift=0:", vol(d))
d.set_parameter("lift", "3")
print("   panel lift=3    :", vol(d), d.get("riser").params["face_center"])
d = stepped(0)
vol(d)
d.edit_many("placed", {"z": "lift+3"})
print("   tree z='lift+3' :", vol(d), d.get("riser").params["face_center"])

print("== 4. an edit panel writes the formula's own value back")
d = Document(name="p4")
d.set_parameter("t", "3")
d.add("sk", "sketch", {"plane": "XY", "entities": [{"kind": "rectangle", "w": 40, "h": 30}]})
d.add("e", "extrude", {"amount": 10, "taper": "t"}, inputs=["sk"])
print("   before:", vol(d), d.get("e").params)
d.edit_many("e", {"amount": 12, "taper": 3.0})      # what OK would push, box showing 3
print("   after :", vol(d), d.get("e").params)
d.set_parameter("t", "6")
print("   t=6   :", vol(d), d.get("e").params, "(the taper no longer follows t)")

print("== 5. measure reads float(params)")
import measure                       # noqa: E402
d = Document(name="p5")
d.set_parameter("h", "10")
d.add("sk", "sketch", {"plane": "XY", "offset": "h", "entities": [
    {"kind": "circle", "r": 5, "x": 0, "y": 0}]})
d.add("e", "extrude", {"amount": 5}, inputs=["sk"])
d.rebuild()
print("   sketch plane with offset='h':", measure._sketch_plane(d, d.get("sk")))
d.edit_many("sk", {"offset": 10})
print("   sketch plane with offset=10 :", measure._sketch_plane(d, d.get("sk")))

print("== 6. a file whose feature id is a parameter's name")
data = {"name": "p6", "parameters": {"e": {"expr": "3"}}, "features": [
    {"id": "sk", "op": "sketch", "params": {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 10, "h": 10}]}, "inputs": []},
    {"id": "e", "op": "extrude", "params": {"amount": 5}, "inputs": ["sk"]}]}
try:
    Document.from_data(data)
    print("   opens")
except Exception as e:                  # noqa: BLE001
    print("   does NOT open:", type(e).__name__, e)

print("== 7. int parameters fed a formula")
for op in ("polygon_plate", "hex_plate", "polar_pattern", "pattern", "with_bolt_circle"):
    try:
        print("  ", op, sorted(Document.numeric_params(op)))
    except Exception as e:              # noqa: BLE001
        print("  ", op, type(e).__name__, e)
