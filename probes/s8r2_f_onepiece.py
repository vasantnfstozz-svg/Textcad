"""Round two F: if repair_stl_mesh wrote ONE STL piece (all components), does
lib3mf + the shell regrouping in blocks give the same bodies for the real
88,990-triangle assembly, and at what cost?"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import time, numpy as np, blocks, meshrepair as M, inspector
raw = open("imports/liquid-piston-2-v1.stl", "rb").read()
t = time.time(); pieces, rep = M.repair_stl_mesh(raw); t_rep = time.time() - t
print(f"repair: {t_rep:.1f}s, {len(pieces)} pieces, report {rep}")
t = time.time()
per = [blocks._stl_bytes_to_solids(p) for p in pieces]; t_per = time.time() - t
sol_per = [s for ss, _ in per for s in ss]
print(f"per-piece read: {t_per:.1f}s -> {len(sol_per)} solids, volumes "
      f"{[round(s.volume,1) for s in sol_per]}")
vs, fs, off = [], [], 0
for p in pieces:
    v, f = M.parse_binary_stl(p); vs.append(v); fs.append(f + off); off += len(v)
one = M.to_binary_stl(np.concatenate(vs), np.concatenate(fs))
t = time.time(); sol_one, opens = blocks._stl_bytes_to_solids(one); t_one = time.time() - t
print(f"ONE-piece read: {t_one:.1f}s -> {len(sol_one)} solids, open {opens}, volumes "
      f"{[round(s.volume,1) for s in sol_one]}")
for s in sol_one:
    print("   health", inspector.health(s, check_valid=False), "valid", s.is_valid)
