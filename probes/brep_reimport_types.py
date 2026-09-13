"""What does `import_brep` actually hand back, and what does wrapping it cost?

The kernel worker writes a body to .brep and reads it on the other side. The
fast tier caught it reading 24000 mm3 as 0: `tests/test_health_degenerate_edges.py`
fillets a BARE `Solid.make_box(40, 30, 20)`, not a `Part`, and `Part(shape.wrapped)`
on a bare Solid is the known volume-0 trap (the STL import hit it too). Measure
the three shapes the product actually passes to fillet / chamfer / shell.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build123d as b3d                                       # noqa: E402
from build123d import Compound, Part, export_brep, import_brep  # noqa: E402

OUT = ROOT / "probes" / "_sidecar_tmp"
OUT.mkdir(exist_ok=True)


def show(label, shape):
    p = OUT / "types.brep"
    export_brep(shape, str(p))
    back = import_brep(str(p))
    wrapped = Part(back.wrapped)
    print(f"\n{label}")
    print(f"  sent      {type(shape).__name__:10s} volume {shape.volume:12.4f}")
    print(f"  import_brep -> {type(back).__name__:10s} volume {back.volume:12.4f}"
          f"   solids {len(back.solids())}")
    print(f"  Part(.wrapped) {type(wrapped).__name__:10s} volume {wrapped.volume:12.4f}"
          f"   solids {len(wrapped.solids())}")
    print(f"  is Compound? {isinstance(back, Compound)}   is Part? {isinstance(back, Part)}"
          f"   is Solid? {isinstance(back, b3d.Solid)}")


show("a build123d Box (a Part)", Part(b3d.Box(20, 10, 5).wrapped))
show("a bare Solid.make_box (what test_health_degenerate_edges passes)",
     b3d.Solid.make_box(40, 30, 20))
show("two lumps in one Part",
     Part((b3d.Box(10, 10, 10) + b3d.Pos(30, 0, 0) * b3d.Box(6, 6, 6)).wrapped))
