"""Round four F: attribute the 0.013% volume gap on a 32k-face faceted sphere.
Housing ALONE = a valid lib3mf Solid = the as-is fast path, no regroup at all."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import os, tempfile, meshrepair as M, blocks
from build123d import Sphere, Location, export_stl
D = tempfile.mkdtemp(); p = os.path.join(D, "h.stl")
export_stl(Sphere(30).moved(Location((30, 30, 30))), p, tolerance=0.003, angular_tolerance=0.05)
v, f = M.parse_binary_stl(open(p, "rb").read())
part = blocks.import_stl(p)
print(f"housing alone: STL signed volume {M.signed_volume(v, f):.1f}; imported {part.volume:.1f}; "
      f"gap {(part.volume / M.signed_volume(v, f) - 1) * 100:+.4f}%  faces {len(part.faces())} of {len(f)} triangles")
