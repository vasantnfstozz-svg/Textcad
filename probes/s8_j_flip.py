"""Section 8 probe J: a DENSE mesh with some flipped normals (scanner/sculpt
output) -> signed_volume is the decimation guard's reference."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import tempfile, os, struct, io, numpy as np, blocks, meshrepair as M, inspector
from build123d import Sphere, export_stl
D=tempfile.mkdtemp(); p=os.path.join(D,"ball.stl")
export_stl(Sphere(20), p, tolerance=0.002, angular_tolerance=0.05)
v,f = M.parse_binary_stl(open(p,"rb").read())
true = abs(M.signed_volume(v,f))
rng = np.random.default_rng(7)
for pct in (0.05, 0.30):
    ff = f.copy()
    idx = rng.choice(len(ff), int(len(ff)*pct), replace=False)
    ff[idx] = ff[idx][:, ::-1]
    print(f"\n{pct:.0%} flipped: edge_counts={M.edge_counts(ff)} is_clean={M.is_clean(ff)} "
          f"signed_volume={M.signed_volume(v,ff):.1f} (true {true:.1f})")
    q = os.path.join(D, f"flip{int(pct*100)}.stl")
    open(q,"wb").write(M.to_binary_stl(v, ff))
    try:
        part = blocks.import_stl(q)
        print(f"   IMPORTED volume={part.volume:.1f} error={(part.volume-true)/true*100:+.1f}% "
              f"bodies={len(part.solids())} health={inspector.health(part, check_valid=False)}")
        print(f"   report={blocks.import_stl_report(q)}")
    except Exception as e:
        print(f"   {type(e).__name__}: {str(e)[:150]}")
