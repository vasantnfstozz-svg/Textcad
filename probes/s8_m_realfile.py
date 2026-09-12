"""Section 8 FIX check: the REAL Fusion assembly export the pipeline was
built against, through the fixed pipeline."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import time, blocks, inspector, meshrepair as M
p = "liquid-piston-2-v1.stl"
raw = open("imports/" + p, "rb").read()
v, f = M.parse_binary_stl(raw)
print("file:", len(f), "triangles, edge_counts", M.edge_counts(f),
      "dupes", int(M.duplicate_triangles(f).sum()),
      "signed_volume", round(M.signed_volume(v, f), 1))
t = time.time()
part = blocks.import_stl(p)
print(f"import_stl: {time.time()-t:.1f}s -> volume {part.volume:.1f} "
      f"bodies {len(part.solids())}")
print("  health:", inspector.health(part, check_valid=False))
print("  bbox:", [round(c, 2) for c in part.bounding_box().size])
print("  report:", blocks.import_stl_report(p))
