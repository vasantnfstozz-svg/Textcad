r"""Section 5 review probe (2026-09-10): where every primitive sits, and what
a degenerate dimension says.

This is the measurement the P0 came from. `polygon_plate` and `hex_plate` span
Z 0..thickness while every primitive documented as centred spans -t/2..+t/2 —
and `author.AUTHOR_PROMPT` listed all five together as CENTERED, so every
`move` the AI computed for a hex body was half a thickness out (in
designs/planetary-assembly four bolt heads seated 1.4 mm high). The PROMPT was
corrected rather than the solid: two saved designs are built on the geometry as
it stands, and moving a shipped part to fix a sentence is the wrong trade.

The second half is the message half. Before the fix these rows read, in order:
`Standard_DomainError('')` (the same empty diagnosis for all three of a
plate's dimensions), a twelve-line pybind11 constructor dump for the string
"8mm", `StdFail_NotDone('BRep_API: command not done')`, and — worst — a
`with_center_hole` of radius 0 that handed back the UNDRILLED body with a green
row and an unchanged volume of 78539.82.

Run: C:\Python314\python.exe probes/primitives_review_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blocks                                                    # noqa: E402
import inspector                                                 # noqa: E402
from document import Document                                    # noqa: E402

T = 8.0
CASES = {
    "plate(40,30,8)": blocks.plate(40, 30, T),
    "disc(20,8)": blocks.disc(20, T),
    "ball(15)": blocks.ball(15),
    "cone(20,8,8)": blocks.cone(20, 8, T),
    "tube(20,12,8)": blocks.tube(20, 12, T),
    "polygon_plate(6,20,8)": blocks.polygon_plate(6, 20, T),
    "hex_plate(af=30,8)": blocks.hex_plate(30, T),
    "revolve_profile(0..8)": blocks.revolve_profile(
        [(0, 0), (10, 0), (10, 8), (0, 8)]),
    "curved_blade(h=8)": blocks.curved_blade(10, 40, 25, 55, T, 2.5),
}


def row(op, params, inputs=None):
    """What the feature tree would actually print for this feature."""
    doc = Document(name="probe")
    if inputs:
        doc.add("d", "disc", {"radius": 50, "thickness": 10})
    try:
        doc.add("p", op, dict(params), inputs=inputs, strict=True)
    except Exception as e:
        return f"REFUSED AT ADD: {e}"
    doc.rebuild()
    f = doc.get("p")
    return f"{f.status:7} vol={f.volume} {f.problems or ''}"


DEGENERATE = [
    ("plate", {"width": 40, "depth": 40, "thickness": 0}, None),
    ("disc", {"radius": 0, "thickness": 10}, None),
    ("polygon_plate", {"sides": 6, "circumradius": 20, "thickness": 0}, None),
    ("polygon_plate", {"sides": 2, "circumradius": 20, "thickness": 8}, None),
    ("polygon_plate", {"sides": 6.5, "circumradius": 20, "thickness": 8}, None),
    ("revolve_profile", {"points": [[-10, 0], [10, 0], [10, 5]]}, None),
    ("with_center_hole", {"radius": 0}, ["d"]),
    ("with_bolt_circle",
     {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 200}, ["d"]),
    ("with_bolt_circle",
     {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 0}, ["d"]),
]


if __name__ == "__main__":
    print(f"{'block':26} {'zmin':>9} {'zmax':>9}  centred in Z?")
    print("-" * 62)
    for name, part in CASES.items():
        bb = part.bounding_box()
        centred = abs(bb.min.Z + bb.max.Z) < 1e-9
        print(f"{name:26} {bb.min.Z:9.3f} {bb.max.Z:9.3f}  "
              f"{'YES' if centred else 'NO  <<< stands on Z=0'}")
        assert not inspector.health(part), f"{name} is not healthy"

    print()
    print("what the feature row says for a dimension that cannot work:")
    for op, params, inputs in DEGENERATE:
        print(f"  {op:18} {str(params):58} -> {row(op, params, inputs)}")

    print()
    print("a number typed with its unit, the way a CAD user types it:")
    doc = Document(name="probe")
    doc.add("p", "plate", {"width": 40, "depth": 30, "thickness": 8})
    try:
        doc.edit("p", "width", "8mm")
        print("  NOT REFUSED — this is the bug")
    except ValueError as e:
        print(f"  refused: {e}")
