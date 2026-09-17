"""probes/s10_r3_raise_marker.py — can we tell OUR OWN refusal from Python's
own ValueError, without reading the text?

`blocks.plain_cause` passes every `ValueError` through verbatim, on the
assumption that a ValueError came from our code and is therefore already a
sentence. It is not: `float("")`, `int("x")` and unpacking all raise ValueError
from inside the lines we wrote, and the row then reads `could not convert
string to float: ''` (measured 2026-09-17, probes/s10_r3_entity_value_door.py —
14 such rows from sketch entity coordinates alone, all in sketch.py).

Guessing from the WORDING is how the old assumption went wrong, so this probe
measures a STRUCTURAL test instead: the innermost frame's FILE plus the
BYTECODE at that frame's last instruction. A `raise` statement we wrote is
`RAISE_VARARGS` / `RERAISE`; Python raising on its own account inside one of
our lines is a `CALL`, an `UNPACK_SEQUENCE`, a `BINARY_OP`, …

The test must be SAFE in one direction above all: never call one of our own
sentences "not a sentence". So it answers "Python raised it" only for a frame
in our own directory whose instruction is unmistakably not a raise, and
anything it cannot read counts as ours.

Run:  C:\\Python314\\python.exe probes\\s10_r3_raise_marker.py
"""
import sys

sys.path.insert(0, ".")

import blocks                                        # noqa: E402
import document                                      # noqa: E402
import paramexpr                                     # noqa: E402
import sketch as sk                                  # noqa: E402


def caught(fn):
    try:
        fn()
    except Exception as e:
        return e
    return None


# --- OUR OWN refusals: every one must read as a sentence ---------------------
OURS = [
    ("blocks._positive", lambda: blocks.plate(None, 20, 5)),
    ("blocks._positive neg", lambda: blocks.plate(-2, 20, 5)),
    ("blocks.cone", lambda: blocks.cone(5, 5, 10)),
    ("blocks.tube", lambda: blocks.tube(5, 10, 10)),
    ("blocks.polygon_plate", lambda: blocks.polygon_plate(2, 10, 5)),
    ("blocks.revolve_profile", lambda: blocks.revolve_profile([(0, 0), (1, 0)])),
    ("blocks.curved_blade", lambda: blocks.curved_blade(12, 5, 20, 40, 6, 1)),
    ("blocks.rotate axis", lambda: blocks.rotate(blocks.plate(10, 10, 2), [1])),
    ("blocks.rotate angle", lambda: blocks.rotate(blocks.plate(10, 10, 2), "Z", "x")),
    ("blocks.scale_uniform", lambda: blocks.scale_uniform(blocks.plate(10, 10, 2), 0)),
    ("blocks.edges_for", lambda: blocks.edges_for(blocks.plate(10, 10, 2), [])),
    ("blocks.edges_for bad", lambda: blocks.edges_for(blocks.plate(10, 10, 2), [1])),
    ("blocks.resolve_face", lambda: blocks.resolve_face(blocks.plate(10, 10, 2), "abc")),
    ("blocks._pick_point", lambda: blocks._pick_point([1, 2], "face_center")),
    ("document._move_offsets", lambda: document._move_offsets({"x": [1]})),
    ("document._check_numeric", lambda: document._check_numeric_params(
        "extrude", {"amount": None}, "p1")),
    ("document._params_dict", lambda: document._params_dict("plate", [1], "p1")),
    ("document.add unknown op", lambda: document.Document(name="x").add("a", "nope")),
    ("paramexpr.parse", lambda: paramexpr.parse("8mm")),
    ("paramexpr.evaluate /0", lambda: paramexpr.evaluate("1/0", {})),
    ("paramexpr.evaluate name", lambda: paramexpr.evaluate("wall*2", {})),
    ("paramexpr.name_problem", lambda: document.Document(name="x").set_parameter("1a", "3")),
    ("sketch.make_sketch plane", lambda: sk.make_sketch("QQ", 0, None)),
    ("sketch entity radius", lambda: sk.make_sketch(
        "XY", 0, [{"kind": "circle", "x": 0, "y": 0, "r": None, "mode": "add"}])),
]

# --- PYTHON's own, raised from inside our files -------------------------------
PYTHONS = [
    ("float('') in sketch.py", lambda: sk.make_sketch(
        "XY", 0, [{"kind": "rectangle", "x": "", "y": 0, "w": 5, "h": 5,
                   "mode": "add"}])),
    ("float('abc') in sketch.py", lambda: sk.make_sketch(
        "XY", 0, [{"kind": "rectangle", "x": "abc", "y": 0, "w": 5, "h": 5,
                   "mode": "add"}])),
    ("polygon points 'abc'", lambda: sk.make_sketch(
        "XY", 0, [{"kind": "polygon", "points": "abc", "mode": "add"}])),
    ("float('') bare", lambda: float("")),
    ("int('x') bare", lambda: int("x")),
    ("unpack bare", lambda: (lambda: (_ for _ in ()).throw(ValueError))),
]


def frame_of(e):
    tb = e.__traceback__
    while tb and tb.tb_next is not None:
        tb = tb.tb_next
    return tb


if __name__ == "__main__":
    import dis
    import os
    ourdir = os.path.dirname(os.path.abspath(blocks.__file__))

    def describe(e):
        tb = frame_of(e)
        if tb is None:
            return ("(no traceback)", "-")
        code = tb.tb_frame.f_code
        where = os.path.dirname(os.path.abspath(code.co_filename))
        op = "?"
        for ins in dis.get_instructions(code):
            if ins.offset == tb.tb_lasti:
                op = ins.opname
                break
        return (os.path.basename(code.co_filename)
                + ("" if where == ourdir else "  [OUTSIDE]"), op)

    print("=== OUR OWN raises (must all be a RAISE opcode in our dir) ===")
    bad = 0
    for label, fn in OURS:
        e = caught(fn)
        if e is None:
            print(f"  !! {label}: did not raise")
            continue
        f, op = describe(e)
        flag = "" if (op.startswith("RAISE") or op == "RERAISE") and "[OUTSIDE]" not in f else "  <-- !!"
        if flag:
            bad += 1
        print(f"  {type(e).__name__:14s} {op:18s} {f:28s} {label}{flag}")

    print("\n=== PYTHON's own, inside our files (must NOT be a RAISE opcode) ===")
    for label, fn in PYTHONS:
        e = caught(fn)
        if e is None:
            print(f"  !! {label}: did not raise")
            continue
        f, op = describe(e)
        flag = "  <-- !!" if op.startswith("RAISE") or op == "RERAISE" else ""
        print(f"  {type(e).__name__:14s} {op:18s} {f:28s} {label}{flag}")

    print(f"\nour own refusals misread as Python: {bad}")
