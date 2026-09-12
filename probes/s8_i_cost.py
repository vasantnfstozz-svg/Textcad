"""Section 8 probe I: voxel_remesh cost on a realistic mesh."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import time, tempfile, os, numpy as np, meshrepair as M
from build123d import Sphere, export_stl
D = tempfile.mkdtemp(); p = os.path.join(D,"ball.stl")
export_stl(Sphere(20), p, tolerance=0.002, angular_tolerance=0.05)
v,f = M.parse_binary_stl(open(p,"rb").read())
print("sphere:", len(f), "triangles")
for res in (100, 200):
    t=time.time(); mv,mf,lost = M.voxel_remesh(v,f,res=res); dt=time.time()-t
    print(f"  voxel_remesh res={res}: {dt:.1f}s -> {len(mf):,} triangles, "
          f"volume {abs(M.signed_volume(mv,mf)):.1f} vs {abs(M.signed_volume(v,f)):.1f} "
          f"({(abs(M.signed_volume(mv,mf))/abs(M.signed_volume(v,f))-1)*100:+.2f}%)")
