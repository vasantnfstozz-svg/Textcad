"""Probe (2026-09-07): what the per-edge host-face lookup adds to _tagged_mesh.

The viewport payload now names, for every edge, the ids of the faces it bounds
(the picker's own-face rule for inside corners). That is one face.edges() pass
over the solid on every model load; _tagged_mesh is the function whose 8.8 s
history made every millisecond here suspect. Measured on the largest fixture.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio                                   # noqa: E402
from document import Document                   # noqa: E402

doc = Document.load(str(Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "esp32-remote.tcad.json"))
assert doc.rebuild(), doc.tree()
part = doc.result()
print("faces", len(part.faces()), "edges", len(part.edges()))

t0 = time.perf_counter()
m = studio._tagged_mesh(part, body_id="x")
t_all = time.perf_counter() - t0
print(f"_tagged_mesh: {t_all * 1e3:.0f} ms, {len(m['edges'])} edges, "
      f"{sum(1 for e in m['edges'] if len(e['faces']) == 2)} with 2 faces, "
      f"{sum(1 for e in m['edges'] if len(e['faces']) == 1)} with 1 (seams)")

# FIRST VERSION: a separate face.edges() pass — measured 367 ms, 6.6% of the
# mesh (under load). Replaced: the faces come off the ancestor map
# _edge_polylines already builds, so the cost is the map iteration below.
t0 = time.perf_counter()
hosts = {}
for fi, face in enumerate(part.faces()):
    for fe in face.edges():
        hosts.setdefault(studio._shape_key(fe), []).append(fi)
t_hosts = time.perf_counter() - t0
print(f"separate face.edges() pass (rejected): {t_hosts * 1e3:.0f} ms "
      f"({t_hosts / t_all * 100:.1f}% of the mesh)")

t0 = time.perf_counter()
polys, faces_of = studio._edge_polylines(part)
t_poly = time.perf_counter() - t0
print(f"_edge_polylines incl. the faces_of map (shipped): {t_poly * 1e3:.0f} ms, "
      f"{len(faces_of)} edges keyed, all found in the payload: "
      f"{all(len(e['faces']) == len(faces_of.get(k, [])) for e, k in zip(m['edges'], (studio._shape_key(x) for x in part.edges())))}")
