"""Section 8 probe D: voxel_remesh has NO volume guard and the report carries
no number for how far the surface moved."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, numpy as np, blocks, inspector, meshrepair as M

def soup_to_stl(tris):
    out = io.BytesIO(); out.write(b"\0"*80); out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()

def box(x0,y0,z0,x1,y1,z1):
    P=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
       (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
       (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return [(P[a],P[b],P[c]) for a,b,c in F]

def case(name, tris, true_vol):
    data = soup_to_stl(tris)
    v,f = M.parse_binary_stl(data)
    b,o = M.edge_counts(f)
    print(f"\n== {name}: boundary={b} overshared={o} "
          f"mesh_volume={M.signed_volume(v,f):.2f} (true {true_vol})")
    d = tempfile.mkdtemp(); p = os.path.join(d, "x.stl")
    open(p,"wb").write(data)
    try:
        part = blocks.import_stl(p)
        rep = blocks.import_stl_report(p)
        err = (part.volume - true_vol) / true_vol * 100
        print(f"   IMPORTED volume={part.volume:.2f}  error={err:+.1f}%  "
              f"bodies={len(part.solids())}  health={inspector.health(part, check_valid=False)}")
        print(f"   report={rep}")
    except Exception as e:
        print(f"   REFUSED -> {e}")

# 1. two cubes sharing ONE EDGE: the classic assembly-export pinch
case("two 20mm cubes pinched at an edge",
     box(0,0,0,20,20,20) + box(20,20,0,40,40,20), 16000.0)

# 2. the same pinch on a LARGE THIN part: a 0.6 mm plate, 100 mm across
case("0.6mm plate 100x100 pinched to a 10mm tab",
     box(0,0,0,100,100,0.6) + box(100,100,0,110,110,0.6), 6060.0)
