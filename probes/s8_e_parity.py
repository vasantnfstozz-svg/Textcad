"""Section 8 probe E: the parity voxel fill XORs overlapping material, and
MIN_COMPONENT_BUDGET blows the triangle budget on a many-body assembly."""
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

def run(name, tris, true_vol):
    data = soup_to_stl(tris)
    v,f = M.parse_binary_stl(data)
    b,o = M.edge_counts(f)
    print(f"\n== {name}: boundary={b} overshared={o} tris={len(f)}")
    d = tempfile.mkdtemp(); p = os.path.join(d,"x.stl"); open(p,"wb").write(data)
    try:
        part = blocks.import_stl(p); rep = blocks.import_stl_report(p)
        print(f"   IMPORTED volume={part.volume:.1f} (true {true_vol}) "
              f"error={(part.volume-true_vol)/true_vol*100:+.1f}%  "
              f"bodies={len(part.solids())} health={inspector.health(part, check_valid=False)}")
        print(f"   bbox={part.bounding_box().size}  report={rep}")
    except Exception as e:
        print(f"   REFUSED -> {e}")

# E1: two INTERPENETRATING bodies welded along a shared edge (assembly export).
#     A = 20x20x20 at origin, B = 10x20x40 at origin -> they share the bottom
#     edge (0,0,0)-(0,20,0) (overshared -> remesh) and overlap in 10x20x20.
run("two interpenetrating bodies sharing an edge",
    box(0,0,0,20,20,20) + box(0,0,0,10,20,40), 12000.0)

# E2: many small bodies -> MIN_COMPONENT_BUDGET x N blows DEFAULT_BUDGET
import meshrepair
print("\n== budget: DEFAULT_BUDGET =", meshrepair.DEFAULT_BUDGET,
      " MIN_COMPONENT_BUDGET =", meshrepair.MIN_COMPONENT_BUDGET)
def sphere_ish(cx, n=40):
    """a blob of n*2 triangles: a subdivided tetra-ish fan, closed."""
    import math
    pts = [(cx + math.cos(i*2*math.pi/n)*3, math.sin(i*2*math.pi/n)*3, 0.0)
           for i in range(n)]
    top, bot = (cx, 0.0, 4.0), (cx, 0.0, -4.0)
    t = []
    for i in range(n):
        a, b = pts[i], pts[(i+1) % n]
        t.append((a, b, top)); t.append((b, a, bot))
    return t
many = []
for k in range(40):
    many += sphere_ish(k*20)
data = soup_to_stl(many)
v,f = M.parse_binary_stl(data)
print("   40-body mesh:", len(f), "triangles, edge_counts", M.edge_counts(f),
      "clean", M.is_clean(f))
d = tempfile.mkdtemp(); p = os.path.join(d,"many.stl"); open(p,"wb").write(data)
# force the repair path by exceeding MAX_STL_TRIANGLES? it is only 3200 tris,
# so instead call the pipeline directly with a small budget to show the maths
pieces, rep = M.repair_stl_mesh(data, budget=meshrepair.DEFAULT_BUDGET)
print("   repair_stl_mesh report:", rep)
