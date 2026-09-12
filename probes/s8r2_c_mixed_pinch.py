"""Round two C: the docstring still promises 'whatever the input's sins ...
inconsistent winding'. A pinched mesh with SOME flipped triangles: parity did
not care about direction; the winding fill does."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, numpy as np, blocks, inspector, meshrepair as M
def to_bin(tris):
    out = io.BytesIO(); out.write(b"\0"*80); out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()
def box(x0,y0,z0,x1,y1,z1):
    P=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return [(P[a],P[b],P[c]) for a,b,c in F]
# two 20-cubes pinched at an edge (the existing remesh test), then flip the
# TOP two triangles of cube A only (a scanner / sculpt-tool export sin)
tris = box(0,0,0,20,20,20) + box(20,20,0,40,40,20)
mixed = list(tris)
for i in (2, 3):                      # cube A's top face
    a,b,c = mixed[i]; mixed[i] = (a,c,b)
D = tempfile.mkdtemp()
for name, t in (("pinched-consistent.stl", tris), ("pinched-MIXED.stl", mixed)):
    p = os.path.join(D, name); open(p,"wb").write(to_bin(t))
    v,f = M.parse_binary_stl(to_bin(t))
    try:
        part = blocks.import_stl(p)
        print(f"{name}: edge_counts={M.edge_counts(f)} -> volume={part.volume:.1f} "
              f"(true 16000) bodies={len(part.solids())} drift={blocks.import_stl_report(p)['remesh_drift_pct']}")
    except Exception as e:
        print(f"{name}: REFUSED -> {str(e)[:150]}")
