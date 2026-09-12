"""Section 8 probe A: parse_binary_stl welding + winding blindness."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, numpy as np, meshrepair as M

def soup_to_stl(tris):
    out = io.BytesIO(); out.write(b"\0"*80); out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()

def box(ox=0.0,oy=0.0,oz=0.0,s=5.0):
    P=[(ox,oy,oz),(ox+s,oy,oz),(ox+s,oy+s,oz),(ox,oy+s,oz),
       (ox,oy,oz+s),(ox+s,oy,oz+s),(ox+s,oy+s,oz+s),(ox,oy+s,oz+s)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
       (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return [(P[a],P[b],P[c]) for a,b,c in F]

# 1. does np.unique(axis=0) weld -0.0 with 0.0?
a = np.array([[0.0,1.0,2.0],[-0.0,1.0,2.0]])
u,_ = np.unique(a, axis=0, return_inverse=True)
print("A1 np.unique welds -0.0 with 0.0:", len(u)==1, "-> rows:", len(u))

# 2. a cube where ONE triangle uses -0.0 for x instead of 0.0
tris = box()
def neg(v): return tuple((-0.0 if c==0.0 else c) for c in v)
tris2 = list(tris)
tris2[0] = tuple(neg(v) for v in tris2[0])
v,f = M.parse_binary_stl(soup_to_stl(tris2))
print("A2 -0.0 cube: verts", len(v), "edge_counts", M.edge_counts(f),
      "clean", M.is_clean(f))

# 3. a cube with ONE triangle's winding flipped (mixed normals)
tris3 = list(tris); a_,b_,c_ = tris3[0]; tris3[0] = (a_,c_,b_)
v3,f3 = M.parse_binary_stl(soup_to_stl(tris3))
print("A3 flipped-one-tri cube: edge_counts", M.edge_counts(f3),
      "clean", M.is_clean(f3), "signed_volume", M.signed_volume(v3,f3),
      "(true volume 125)")

# 4. a fully inverted cube
tris4 = [(a_,c_,b_) for a_,b_,c_ in tris]
v4,f4 = M.parse_binary_stl(soup_to_stl(tris4))
print("A4 fully inverted cube: clean", M.is_clean(f4),
      "signed_volume", M.signed_volume(v4,f4))
