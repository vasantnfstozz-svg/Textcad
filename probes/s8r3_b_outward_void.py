"""Round three B: a hollow STL whose cavity is wound OUTWARD (MeshLab's
're-orient all faces coherently' does this per connected component). Does
lib3mf hand back a VALID solid of the wrong volume, which the as-is fast path
in _stl_bytes_to_solids would take?"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, blocks, inspector
from build123d import Mesher
def to_bin(tris):
    out = io.BytesIO(); out.write(b"\0"*80); out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()
def box(x0,y0,z0,x1,y1,z1, inward=False):
    P=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    t=[(P[a],P[b],P[c]) for a,b,c in F]
    return [(a,c,b) for a,b,c in t] if inward else t
D = tempfile.mkdtemp()
for name, tris in (("cavity-inward.stl",  box(0,0,0,10,10,10) + box(3,3,3,7,7,7, inward=True)),
                   ("cavity-OUTWARD.stl", box(0,0,0,10,10,10) + box(3,3,3,7,7,7)),
                   ("cavity-OUTWARD+other.stl", box(0,0,0,10,10,10) + box(3,3,3,7,7,7) + box(30,0,0,40,10,10))):
    p = os.path.join(D, name); open(p, "wb").write(to_bin(tris))
    shp = Mesher().read(p)[0]
    print(f"{name}: lib3mf -> {type(shp).__name__} volume={shp.volume:.1f} shells={len(shp.shells())} is_valid={shp.is_valid}")
    part = blocks.import_stl(p)
    print(f"   import_stl -> volume={part.volume:.1f} bodies={len(part.solids())} "
          f"health={inspector.health(part, check_valid=False)}   (want 936 / 1 body{' + 1000' if 'other' in name else ''})")
