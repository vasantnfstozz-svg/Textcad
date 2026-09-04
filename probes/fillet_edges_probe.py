"""Probe for the Fillet / Chamfer tool (LAUNCH-PLAN.md P4, textcad-dev rule 1):
what the kernel does with the things the tool will lean on, BEFORE code assumes it.

    1. fillet ONE top edge of a 40x30x20 box at growing radii: which radius
       fails, with which exception (class, MRO, message), and whether any
       "success" is an invalid solid (the second banned failure)
    2. the same for all four top edges, and for chamfer
    3. TANGENT CHAIN: on a box whose vertical edges are rounded, the top rim
       is 8 edges -- can tangent_at() at shared vertices find the chain?
    4. EDGE IDENTITY across an upstream change: box 20 -> 30 tall; does the
       nearest midpoint (+ direction) find the same edge, and how close is the
       runner-up (the ambiguity margin)?
    5. the FACE-PAIR alternative: an edge as "the edge shared by these two
       faces (centre + normal)"; does it detect an edge that is GONE?
    6. the bisector direction for the ball handle: the two adjacent faces'
       normals at the edge midpoint, summed and negated (into the material)
    7. how long one fillet costs on a box (the settle budget)
    8. build123d's Part.max_fillet(edges): value and cost -- the plan's
       limits.max_radius straight from the kernel instead of a guess

Run: PYTHONIOENCODING=utf-8 C:\\Python314\\python.exe probes\\fillet_edges_probe.py
"""
import time
from build123d import Axis, Vector, fillet, chamfer

import blocks
import inspector


def show(label, fn):
    try:
        r = fn()
        print(f"{label}: {r}")
        return r
    except Exception as e:
        mro = " > ".join(c.__name__ for c in type(e).__mro__[:4])
        print(f"{label}: RAISED {mro}: {str(e)[:140]!r}")
        return None


def top_edges(p):
    return p.edges().group_by(Axis.Z)[-1]


def key(shape):
    return hash(shape.wrapped)


def gtype(e):
    return str(e.geom_type).split(".")[-1]


box = blocks.plate(40, 30, 20)
one = top_edges(box).sort_by(Axis.Y)[0]          # the top edge along X at y=-15
print(f"box: {len(box.edges())} edges, one top edge len={one.length} mid={one @ 0.5}")

print("\n--- 1. one top edge, growing radius (adjacent faces: top 30 deep, side 20 tall)")
for r in (1, 5, 10, 15, 19, 19.9, 20, 25, 50):
    def f(r=r):
        t = time.perf_counter()
        out = fillet(one, radius=r)
        dt = time.perf_counter() - t
        h = inspector.health(out)
        return f"vol={out.volume:.1f} ok={not h} faces={len(out.faces())} {dt*1000:.0f}ms"
    show(f"  fillet r={r}", f)

print("\n--- 2. all four top edges / chamfer one edge")
for r in (5, 14.9, 15, 20):
    show(f"  fillet 4 top r={r}", lambda r=r: f"vol={fillet(top_edges(box), radius=r).volume:.1f} "
         f"ok={(not inspector.health(fillet(top_edges(box), radius=r)))}")
for L in (5, 19.9, 20, 30):
    show(f"  chamfer one L={L}", lambda L=L: f"vol={chamfer(one, length=L).volume:.1f} "
         f"ok={(not inspector.health(chamfer(one, length=L)))}")
show("  chamfer two lengths", lambda: f"vol={chamfer(one, length=5, length2=10).volume:.1f}")

print("\n--- 3. tangent chain on a rounded-corner box top rim")
rc = fillet(box.edges().filter_by(Axis.Z), radius=5)
rim = top_edges(rc)
print(f"  rim edges: {len(rim)} types={[gtype(e) for e in rim]}")


def vkey(v):
    return (round(v.X, 4), round(v.Y, 4), round(v.Z, 4))


def chain_from(edges, start):
    """edges tangent-continuous with `start`, walked through shared vertices"""
    ends = {}
    for e in edges:
        for t, v in ((0.0, e @ 0), (1.0, e @ 1)):
            ends.setdefault(vkey(v), []).append((e, t))
    seen = {key(start)}
    todo = [start]
    while todo:
        e = todo.pop()
        for t in (0.0, 1.0):
            tan = e % t
            for other, ot in ends.get(vkey(e @ t), []):
                if key(other) in seen:
                    continue
                otan = other % ot
                if abs(tan.dot(otan)) > 0.99:       # same line through the vertex
                    seen.add(key(other)); todo.append(other)
    return seen


show("  chain size from one rim line", lambda: len(chain_from(rim, rim[0])))
show("  chain size from a box top edge (sharp corners)", lambda: len(chain_from(top_edges(box), one)))
show("  fillet the whole chain r=3", lambda: f"vol={fillet(rim, radius=3).volume:.1f} "
     f"ok={(not inspector.health(fillet(rim, radius=3)))}")

print("\n--- 4. edge identity by midpoint (+direction) after 20 -> 30 tall")
tall = blocks.plate(40, 30, 30)


def sig(e):
    m = e @ 0.5
    d = e % 0.5
    return (m.X, m.Y, m.Z), (d.X, d.Y, d.Z), gtype(e), e.length


def score(sig_a, e):
    (mx, my, mz), (dx, dy, dz), gt, _ = sig_a
    m = e @ 0.5; d = e % 0.5
    dist2 = (m.X - mx) ** 2 + (m.Y - my) ** 2 + (m.Z - mz) ** 2
    align = abs(d.X * dx + d.Y * dy + d.Z * dz)
    return dist2 + (1 - align) * 25.0 + (0 if gtype(e) == gt else 100.0)


worst_margin = 1e9
for e in box.edges():
    s = sig(e)
    ranked = sorted(tall.edges(), key=lambda x: score(s, x))
    margin = score(s, ranked[1]) - score(s, ranked[0])
    worst_margin = min(worst_margin, margin)
print(f"  every edge re-found; worst runner-up margin (score units) = {worst_margin:.1f}")
moved = []
for s in [sig(e) for e in top_edges(box)]:
    best = sorted(tall.edges(), key=lambda x: score(s, x))[0]
    moved.append(round(((best @ 0.5) - Vector(*s[0])).length, 1))
print(f"  top edges moved by {moved} mm (expected 10)")

print("\n--- 5. face pair: the edge shared by two faces (centre + normal)")


def faces_of(part, edge):
    k = key(edge)
    return [f for f in part.faces() if any(key(x) == k for x in f.edges())]


def face_sig(f):
    c = f.center(); n = f.normal_at(c)
    return (c.X, c.Y, c.Z), (n.X, n.Y, n.Z)


def resolve_face(part, fs):
    (cx, cy, cz), (nx, ny, nz) = fs
    def sc(f):
        c = f.center(); n = f.normal_at(c)
        return (c.X-cx)**2 + (c.Y-cy)**2 + (c.Z-cz)**2 + (1 - (n.X*nx+n.Y*ny+n.Z*nz)) * 25
    return min(part.faces(), key=sc)


def shared_edges(fa, fb):
    kb = {key(e) for e in fb.edges()}
    return [e for e in fa.edges() if key(e) in kb]


pair = faces_of(box, one)
print(f"  faces at the probe edge: {len(pair)} normals={[tuple(round(v,2) for v in face_sig(f)[1]) for f in pair]}")
fsigs = [face_sig(f) for f in pair]
show("  re-found on the tall box (midpoint z)", lambda: [round((se @ 0.5).Z, 2) for se in shared_edges(*[resolve_face(tall, s) for s in fsigs])])
gone = chamfer(one, length=4)          # the edge is replaced by a bevel face
show("  after a chamfer ATE the edge: shared edges of the resolved pair",
     lambda: len(shared_edges(*[resolve_face(gone, s) for s in fsigs])))
show("  ...and what nearest-midpoint would pick instead",
     lambda: sig(min(gone.edges(), key=lambda x: score(sig(one), x)))[:3])

print("\n--- 6. bisector for the ball: -(n1 + n2) at the edge midpoint")
m = one @ 0.5
ns = [f.normal_at(m) for f in pair]
bis = -(ns[0] + ns[1]).normalized()
print(f"  normals={[tuple(round(v,2) for v in (n.X,n.Y,n.Z)) for n in ns]} bisector={tuple(round(v,3) for v in (bis.X,bis.Y,bis.Z))}")

print("\n--- 7. fillet on a tube rim, and a fillet next to a fillet")
tube = blocks.tube(15, 10, 20)
show("  tube outer top rim r=2", lambda: f"ok={(not inspector.health(fillet(top_edges(tube).sort_by(lambda e: e.length)[-1], radius=2)))}")
show("  tube both top rims r=2.4 (wall 5)", lambda: f"ok={(not inspector.health(fillet(top_edges(tube), radius=2.4)))}")
show("  tube both top rims r=2.6 (wall 5)", lambda: f"ok={(not inspector.health(fillet(top_edges(tube), radius=2.6)))}")
show("  rounded box: fillet top rim r=6 (corner r=5)", lambda: f"ok={(not inspector.health(fillet(rim, radius=6)))} vol={fillet(rim, radius=6).volume:.0f}")

print("\n--- 8. max_fillet from the kernel: value and cost")
for label, part, edges in (("box one top edge (expect <20)", box, [one]),
                           ("box 4 top edges (expect <15)", box, list(top_edges(box))),
                           ("tube both rims (wall 5, expect <2.5)", tube, list(top_edges(tube))),
                           ("rounded-box rim chain", rc, list(rim))):
    def f(part=part, edges=edges):
        t = time.perf_counter()
        r = part.max_fillet(edges, tolerance=0.05, max_iterations=12)
        return f"{r:.3f} in {(time.perf_counter()-t)*1000:.0f}ms"
    show(f"  {label}", f)
show("  max_fillet on a 50mm ask? (does it need a starting radius)", lambda: box.max_fillet([one], tolerance=0.01, max_iterations=14))
