"""probes/face_of_revolve_probe.py — toolplan._face_of's bbox guard on a BODY
OF REVOLUTION (review finding B, P1, 2026-09-08).

THE ASK. The shipped guard in _face_of refuses a click on a face only the
PREVIEW body has by testing that the clicked centre lies inside the RESOLVED
face's bounding box. On a box that works (a fillet band's centre is 1.46 mm
off the nearest wall, probes/feature_edges_probe.py section 3). On a DISC the
wall's bbox is the whole cube around the cylinder, so a torus band's centre is
inside it — the click is accepted and the plan silently takes the wall's TWO
circles, adding the rim at the far end of the body. Is that real, what is
Face.center() really, and which guard refuses every preview-only face while
accepting every real one?

SS1 the finding end to end: disc r=10 t=20, fillet r=3 on the top rim; the
    torus band's centre through toolplan.plan(face_toggle=...) on the DISC.
SS2 what Face.center() IS: planar faces vs curved ones, on a box top, an
    off-centre-pocket top, an ANNULUS, an L-shaped face, a cylinder wall, a
    torus band — the point, is it inside the trimming wires (provenance.OnFace),
    how far is it from the underlying surface (ShapeAnalysis_Surface.Gap).
SS3 the guard matrix: (a) on-surface, (b) on-face, (c) centre-match, (d) the
    shipped bbox, over the must-accept and must-refuse clicks.
SS4 where the clicked centre comes from (studio.py face rows, R1).
SS5 the recommended guard called exactly the way _face_of would call it.

Run: PYTHONIOENCODING=utf-8 C:/Python314/python.exe probes/face_of_revolve_probe.py
"""
import math
import sys
import time

sys.path.insert(0, ".")
from build123d import CenterOf                                    # noqa: E402
from OCP.BRep import BRep_Tool                                     # noqa: E402
from OCP.gp import gp_Pnt                                          # noqa: E402
from OCP.ShapeAnalysis import ShapeAnalysis_Surface                # noqa: E402

import blocks                                                      # noqa: E402
import provenance                                                  # noqa: E402
import toolplan                                                    # noqa: E402
from document import Document                                      # noqa: E402


def r2(v):
    """the payload's rounding: studio.py writes a face centre to 2 decimals"""
    return [round(float(x), 2) for x in v]


def r3(v):
    return [round(float(x), 3) for x in v]


def pt(v):
    return "({0:8.3f},{1:8.3f},{2:8.3f})".format(*[float(x) for x in v])


def gap_to_surface(face, c, tol=0.02):
    """distance from the point to the face's UNDERLYING (untrimmed) surface —
    the same measurement provenance.OnFace's first stage makes"""
    try:
        sas = ShapeAnalysis_Surface(BRep_Tool.Surface_s(face.wrapped))
        sas.ValueOfUV(gp_Pnt(float(c[0]), float(c[1]), float(c[2])), tol)
        return float(sas.Gap())
    except Exception:                            # noqa: BLE001
        return float("nan")


def centre_of(face):
    try:
        c = face.center()
        return [float(c.X), float(c.Y), float(c.Z)]
    except Exception:                            # noqa: BLE001
        return None


def norm_of(face):
    try:
        c = face.center()
        n = face.normal_at(c)
        return [float(n.X), float(n.Y), float(n.Z)]
    except Exception:                            # noqa: BLE001
        return None


def dist(a, b):
    return math.dist([float(x) for x in a], [float(x) for x in b])


# ---------------------------------------------------------------- bodies ----

def doc_disc(kind=None, value=3.0):
    """disc r=10 t=20; optionally a fillet / chamfer on its TOP rim"""
    d = Document(name="disc")
    d.add("d", "disc", {"radius": 10, "thickness": 20}, [])
    if kind == "fillet":
        d.add("f1", "fillet", {"radius": value, "edges": "top"}, ["d"])
    elif kind == "chamfer":
        d.add("f1", "chamfer", {"length": value, "edges": "top"}, ["d"])
    d.rebuild()
    return d


def doc_box(kind=None, value=5.0, one_edge=False):
    """plate 40x30x20; optionally a fillet / chamfer on the vertical corners"""
    d = Document(name="box")
    d.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    d.rebuild()
    if kind:
        edges = "vertical"
        if one_edge:
            part = d._parts["b"]
            e = list(blocks.edges_for(part, "vertical"))[0]
            edges = [blocks.edge_ref(part, e)]
        key = "radius" if kind == "fillet" else "length"
        d.add("g1", kind, {key: value, "edges": edges}, ["b"])
        d.rebuild()
    return d


def doc_pocket(ox=8.0, oy=5.0):
    """plate 40x30x20 with a 20x12x10 pocket whose centre is (ox, oy)"""
    d = Document(name="pk")
    d.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    d.add("t", "plate", {"width": 20, "depth": 12, "thickness": 10}, [])
    d.add("tm", "move", {"x": ox, "y": oy, "z": 10}, ["t"])
    d.add("c", "cut", {}, ["b", "tm"])
    d.rebuild()
    return d


def doc_annulus():
    """disc r=10 t=5 with a concentric r=4 through hole: a washer"""
    d = Document(name="an")
    d.add("a", "disc", {"radius": 10, "thickness": 5}, [])
    d.add("h", "disc", {"radius": 4, "thickness": 20}, [])
    d.add("c", "cut", {}, ["a", "h"])
    d.rebuild()
    return d


def doc_L():
    """plate 40x30x20 with a corner quarter removed: an L-shaped top face"""
    d = Document(name="ell")
    d.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    d.add("t", "plate", {"width": 20, "depth": 15, "thickness": 40}, [])
    d.add("tm", "move", {"x": 10, "y": 7.5, "z": 0}, ["t"])
    d.add("c", "cut", {}, ["b", "tm"])
    d.rebuild()
    return d


def face_by(part, gtype=None, want=None, pick=0):
    """the faces of a part by geometry type / a predicate, biggest area first"""
    fs = [f for f in part.faces() if gtype is None or blocks._gtype(f) == gtype]
    if want is not None:
        fs = [f for f in fs if want(f)]
    fs.sort(key=lambda f: (round(-f.area, 4), r2(centre_of(f) or [0, 0, 0])))
    return fs[pick]


def top_face(part):
    def up(f):
        n = norm_of(f)
        return n is not None and abs(n[2] - 1) < 1e-6
    return face_by(part, "PLANE", up)


def in_bbox(face, c, tol=0.05):
    """the SHIPPED guard (toolplan._face_of)"""
    bb = face.bounding_box()
    span = ((bb.min.X, bb.max.X), (bb.min.Y, bb.max.Y), (bb.min.Z, bb.max.Z))
    return not any(float(v) < lo - tol or float(v) > hi + tol
                   for v, (lo, hi) in zip(c, span))


# =========================================================== SS1 ============
print("== SS1 the finding end to end (disc r=10 t=20, fillet r=3 on the top rim)")
d = doc_disc("fillet", 3.0)
disc, prev = d._parts["d"], d._parts["f1"]
dbb = disc.bounding_box()
print(f"  disc: {len(disc.faces())} faces {sorted({blocks._gtype(f) for f in disc.faces()})}"
      f"  z range [{dbb.min.Z:.2f},{dbb.max.Z:.2f}]")
print(f"  preview f1: {len(prev.faces())} faces "
      f"{sorted({blocks._gtype(f) for f in prev.faces()})}")
band = face_by(prev, "TORUS")
bc, bn = centre_of(band), norm_of(band)
bb = band.bounding_box()
print(f"  TORUS band: center() {pt(bc)}  normal {r3(bn)}")
print(f"              bbox x[{bb.min.X:.2f},{bb.max.X:.2f}] y[{bb.min.Y:.2f},{bb.max.Y:.2f}]"
      f" z[{bb.min.Z:.2f},{bb.max.Z:.2f}]  area {band.area:.3f}")
click = {"center": r2(bc), "normal": r3(bn)}
print(f"  the browser's payload for that click: {click}")
named = blocks.resolve_face(disc, click["center"], click["normal"])
nb = named.bounding_box()
print(f"  resolve_face(disc, ...) names: {blocks._gtype(named)} area {named.area:.2f} "
      f"center() {pt(centre_of(named))}")
print(f"              its bbox x[{nb.min.X:.2f},{nb.max.X:.2f}] y[{nb.min.Y:.2f},{nb.max.Y:.2f}]"
      f" z[{nb.min.Z:.2f},{nb.max.Z:.2f}]")
print(f"              clicked centre inside that bbox (+-0.05): "
      f"{in_bbox(named, click['center'])}  <- the shipped guard's verdict")
p = toolplan.plan(d, {"tool": "fillet", "body_id": "d", "edges": [], "face_toggle": click})
if not p["ok"]:
    print(f"  toolplan.plan -> ok=False error={p.get('error')}")
else:
    print(f"  toolplan.plan -> ok=True click={p.get('click')} n={p.get('click_n')} "
          f"edges={len(p.get('edges', []))}")
    zs = []
    for e in p.get("edges", []):
        m = (e.get("ref") or {}).get("mid") or e.get("mid")
        zs.append(round(float(m[2]), 3))
        print(f"    edge type={e.get('type')} mid={m}")
    print(f"  edge midpoint z levels: {sorted(set(zs))}   "
          f"bottom rim (z=-10) present: {-10.0 in zs}")
    print(f"  edges_param stored on the feature: {p.get('edges_param')}")
print("  the same click on a BOX for comparison (feature_edges_probe section 3):")
db = doc_box("fillet", 5.0)
qband = face_by(db._parts["g1"], "CYLINDER")
qc, qn = centre_of(qband), norm_of(qband)
pb = toolplan.plan(db, {"tool": "fillet", "body_id": "b", "edges": [],
                        "face_toggle": {"center": r2(qc), "normal": r3(qn)}})
print(f"    box band centre {pt(qc)} -> ok={pb['ok']} {str(pb.get('error', ''))[:70]}")

# =========================================================== SS2 ============
print("\n== SS2 what IS build123d Face.center()?")
print("  source build123d/topology/two_d.py:1961: def center(self, center_of="
      "CenterOf.GEOMETRY)")
print("    GEOMETRY + is_planar -> BRepGProp.SurfaceProperties_s -> CentreOfMass"
      "  (AREA CENTROID)")
print("    GEOMETRY + curved    -> uv midpoint 0.5*(u0+u1), 0.5*(v0+v1) of "
      "_uv_bounds (a point ON the surface)")
dp, da, dl = doc_pocket(), doc_annulus(), doc_L()
rows = [
    ("box top (plane)", top_face(doc_box()._parts["b"])),
    ("pocket top, pocket at (8,5)", top_face(dp._parts["c"])),
    ("pocket top, pocket at (-8,-5)", top_face(doc_pocket(-8, -5)._parts["c"])),
    ("annulus washer top (r4 hole)", top_face(da._parts["c"])),
    ("L-shaped top (corner cut)", top_face(dl._parts["c"])),
    ("cylinder wall (disc r10)", face_by(disc, "CYLINDER")),
    ("torus band (fillet r3)", band),
]
print(f"  {'face':30s} {'center()':>28s} {'gtype':>9s} {'OnFace':>7s} "
      f"{'gap(mm)':>9s} {'|c-MASS|':>9s} {'|c-BBOX|':>9s}")
for name, f in rows:
    c = centre_of(f)
    on = provenance.OnFace(f.wrapped)(*c)
    g = gap_to_surface(f, c)
    planar = blocks._gtype(f)
    mass = f.center(CenterOf.MASS)
    bbc = f.bounding_box().center()
    print(f"  {name:30s} {pt(c):>28s} {planar:>9s} {str(on):>7s} {g:9.5f} "
          f"{dist(c, [mass.X, mass.Y, mass.Z]):9.4f} "
          f"{dist(c, [bbc.X, bbc.Y, bbc.Z]):9.4f}")
print("  (OnFace = provenance.OnFace(face)(centre): surface gap <= 1e-4 AND FClass2d")
print("   IN/ON — i.e. the centre lies ON THE MATERIAL of its own face.")
print("   gap = distance to the untrimmed surface.)")

# =========================================================== SS3 ============
print("\n== SS3 the guard matrix")
TOL = 0.02        # mm: covers the payload's 2-decimal rounding (sqrt(3)*0.005)


def guards(part, c, n, tol=TOL):
    """(a) on-surface  (b) on-face  (c) centre-match  (d) the shipped bbox"""
    f = blocks.resolve_face(part, c, n)
    g = gap_to_surface(f, c, tol)
    fc = centre_of(f)
    cd = dist(fc, c) if fc else float("inf")
    return (f, g, cd,
            g <= tol,
            provenance.OnFace(f.wrapped)(float(c[0]), float(c[1]), float(c[2]), tol=tol),
            cd <= tol,
            in_bbox(f, c))


cases = []          # (must_accept, label, the INPUT part, the CLICKED face)
# --- MUST ACCEPT: a face the body really has, clicked on that body
cases.append((True, "box top", doc_box()._parts["b"], top_face(doc_box()._parts["b"])))
cases.append((True, "pocket top (off-centre)", dp._parts["c"], top_face(dp._parts["c"])))
cases.append((True, "ANNULUS washer top", da._parts["c"], top_face(da._parts["c"])))
cases.append((True, "L-shaped top", dl._parts["c"], top_face(dl._parts["c"])))
cases.append((True, "cylinder wall (disc)", disc, face_by(disc, "CYLINDER")))
dfb = doc_box("fillet", 5.0)
cases.append((True, "filleted box own top", dfb._parts["g1"], top_face(dfb._parts["g1"])))
cases.append((True, "filleted box own band", dfb._parts["g1"],
              face_by(dfb._parts["g1"], "CYLINDER")))
# --- MUST ACCEPT: the PREVIEW body's unchanged / trimmed faces (tool.js allows them)
cases.append((True, "PREVIEW top (sym. fillet)", dfb._parts["b"], top_face(dfb._parts["g1"])))
d1e = doc_box("fillet", 5.0, one_edge=True)
cases.append((True, "PREVIEW top (1 edge only)", d1e._parts["b"], top_face(d1e._parts["g1"])))
cases.append((True, "PREVIEW wall (1 edge only)", d1e._parts["b"],
              face_by(d1e._parts["g1"], "PLANE",
                      lambda f: abs((norm_of(f) or [0, 0, 1])[0] - 1) < 1e-6)))
cases.append((True, "PREVIEW disc top (fillet r3)", disc, top_face(prev)))
cases.append((True, "PREVIEW disc wall (fillet r3)", disc, face_by(prev, "CYLINDER")))
# --- MUST REFUSE: a face only the preview has
cases.append((False, "box fillet band r5", dfb._parts["b"],
              face_by(dfb._parts["g1"], "CYLINDER")))
dcb = doc_box("chamfer", 3.0)
cases.append((False, "box chamfer band 3", dcb._parts["b"],
              face_by(dcb._parts["g1"], "PLANE",
                      lambda f: abs((norm_of(f) or [0, 0, 1])[2]) < 1e-6
                      and abs(abs((norm_of(f) or [1, 0, 0])[0]) - 1) > 1e-6
                      and abs(abs((norm_of(f) or [0, 1, 0])[1]) - 1) > 1e-6)))
for rad in (3.0, 0.5, 0.1):
    dd_ = doc_disc("fillet", rad)
    cases.append((False, f"disc torus band r{rad}", dd_._parts["d"],
                  face_by(dd_._parts["f1"], "TORUS")))
dch = doc_disc("chamfer", 3.0)
cases.append((False, "disc chamfer band 3 (CONE)", dch._parts["d"],
              face_by(dch._parts["f1"], "CONE")))

n_ref = sum(1 for c0 in cases if not c0[0])
n_acc = len(cases) - n_ref
print(f"  {'case':30s} {'want':>6s} {'clicked centre':>26s} {'resolved':>9s} "
      f"{'gap':>7s} {'|dc|':>8s}  a b c d")
score = {k: [0, 0] for k in "abcd"}             # [wrong accepts, wrong refuses]
rec = []
for must, label, part, f in cases:
    c, n = r2(centre_of(f)), r3(norm_of(f) or [0, 0, 0])
    rf, g, cd, a, b, cc, dd = guards(part, c, n)
    v = {"a": a, "b": b, "c": cc, "d": dd}
    for k, val in v.items():
        if val and not must:
            score[k][0] += 1
        if not val and must:
            score[k][1] += 1
    rec.append((must, label, g, cd, b, cc))
    print(f"  {label:30s} {'ACC' if must else 'REF':>6s} {pt(c):>26s} "
          f"{blocks._gtype(rf):>9s} {g:7.4f} {cd:8.3f}  "
          + " ".join("Y" if v[k] else "n" for k in "abcd"))
print(f"\n  score over {n_acc} MUST-ACCEPT and {n_ref} MUST-REFUSE cases:")
for k, nm in (("a", "on-surface gap<=0.02"), ("b", "on-face OnFace(tol=0.02)"),
              ("c", "centre-match<=0.02"), ("d", "bbox +-0.05  (SHIPPED)")):
    print(f"    ({k}) {nm:26s} wrong-accept {score[k][0]}  wrong-refuse {score[k][1]}")

print("\n  the combination (b) OR (c) — on the face's material, or IS that face's row:")
wa = wr = 0
for must, label, g, cd, b, cc in rec:
    ok = b or cc
    if ok and not must:
        wa += 1
    if not ok and must:
        wr += 1
    print(f"    {label:30s} want {'ACCEPT' if must else 'REFUSE':6s} -> "
          f"{'ACCEPT' if ok else 'REFUSE':6s} {'OK' if ok == must else '**WRONG**'}"
          f"   (on-face {str(b):5s} centre dist {cd:.3f})")
print(f"    wrong-accept {wa}  wrong-refuse {wr}")
acc_g = [(l, g) for m, l, g, _cd, _b, _c in rec if m]
ref_g = [(l, g) for m, l, g, _cd, _b, _c in rec if not m]
ref_dc = [(l, cd) for m, l, _g, cd, _b, _c in rec if not m]
print("  margins:")
print(f"    worst MUST-ACCEPT surface gap : {max(acc_g, key=lambda t: t[1])[1]:.4f} mm "
      f"({max(acc_g, key=lambda t: t[1])[0]})")
print(f"    best  MUST-REFUSE surface gap : {min(ref_g, key=lambda t: t[1])[1]:.4f} mm "
      f"({min(ref_g, key=lambda t: t[1])[0]})  vs the 0.02 mm threshold")
print(f"    closest MUST-REFUSE centre    : {min(ref_dc, key=lambda t: t[1])[1]:.3f} mm "
      f"({min(ref_dc, key=lambda t: t[1])[0]})")


# =========================================================== SS3b ===========
print("\n== SS3b two more candidates: (e) NORMAL AGREEMENT, and the case that")
print("   breaks (b) OR (c) — a preview survivor whose CENTROID is off its own material")


def doc_U():
    """plate 40x30x20 with a deep notch: the top face's area centroid falls
    INSIDE the notch, i.e. off the material (the annulus case, non-symmetric)"""
    d = Document(name="yu")
    d.add("b", "plate", {"width": 40, "depth": 30, "thickness": 20}, [])
    d.add("t", "plate", {"width": 10, "depth": 25, "thickness": 40}, [])
    d.add("tm", "move", {"x": 0, "y": 2.5, "z": 0}, ["t"])
    d.add("c", "cut", {}, ["b", "tm"])
    d.rebuild()
    return d


def doc_U_filleted(rad=2.0):
    d = doc_U()
    d.add("g1", "fillet", {"radius": rad, "edges": "vertical"}, ["c"])
    d.rebuild()
    return d


du = doc_U()
duf = doc_U_filleted(2.0)
utop, uftop = top_face(du._parts["c"]), top_face(duf._parts["g1"])
uc, ufc = centre_of(utop), centre_of(uftop)
print(f"  U top face      center() {pt(uc)}  on its own material: "
      f"{provenance.OnFace(utop.wrapped)(*uc)}")
print(f"  U+fillet r2 top center() {pt(ufc)}  centroid moved "
      f"{dist(uc, ufc):.4f} mm; on the INPUT face: "
      f"{provenance.OnFace(utop.wrapped)(*r2(ufc), tol=0.02)}; "
      f"centre-match: {dist(r2(ufc), uc) <= 0.02}")
print("  => a click on the PREVIEW body's U top would be WRONGLY REFUSED by (b) OR (c);")
print("     its surface gap is "
      f"{gap_to_surface(blocks.resolve_face(du._parts['c'], r2(ufc), r3(norm_of(uftop))), r2(ufc)):.5f} mm, so (a) accepts it.")


def normal_at(face, c):
    """the resolved face's normal AT THE CLICKED POINT (not at its own centre)"""
    from build123d import Vector
    for arg in (Vector(float(c[0]), float(c[1]), float(c[2])),
                (float(c[0]), float(c[1]), float(c[2]))):
        try:
            n = face.normal_at(arg)
            return [float(n.X), float(n.Y), float(n.Z)]
        except Exception:                        # noqa: BLE001
            continue
    return None


def align(face, c, n):
    m = normal_at(face, c)
    if m is None or n is None:
        return None
    return sum(a * b for a, b in zip(m, [float(v) for v in n]))


print("\n  (e) align = dot(clicked normal, resolved face normal AT the clicked point):")
ALIGN = 0.99      # cos 8.1 deg (the payload rounds the normal to 3 decimals)
print(f"  (e) threshold: align >= {ALIGN}")
allcases = cases + [(True, "PREVIEW U top (fillet r2)", du._parts["c"], uftop),
                    (True, "U top on its own body", du._parts["c"], utop)]
print(f"  {'case':30s} {'want':>6s} {'gap':>7s} {'align':>7s}   a  e  a+e")
wa = wr = 0
worst_acc_align, best_ref_align = 1.0, -1.0
for must, label, part, f in allcases:
    c, n = r2(centre_of(f)), r3(norm_of(f) or [0, 0, 0])
    rf = blocks.resolve_face(part, c, n)
    g = gap_to_surface(rf, c, 0.02)
    al = align(rf, c, n)
    a = g <= 0.02
    e = al is not None and al >= ALIGN
    ok = a and e
    if ok and not must:
        wa += 1
    if not ok and must:
        wr += 1
    if must:
        worst_acc_align = min(worst_acc_align, -1.0 if al is None else al)
    else:
        best_ref_align = max(best_ref_align, -1.0 if al is None else al)
    print(f"  {label:30s} {'ACC' if must else 'REF':>6s} {g:7.4f} "
          f"{(float('nan') if al is None else al):7.3f}   "
          f"{'Y' if a else 'n'}  {'Y' if e else 'n'}  {'Y' if ok else 'n'}"
          f"{'' if ok == must else '   **WRONG**'}")
print(f"  (a)+(e): wrong-accept {wa}  wrong-refuse {wr}")
print(f"  worst MUST-ACCEPT align {worst_acc_align:.4f} (threshold {ALIGN})   "
      f"best MUST-REFUSE align {best_ref_align:.4f}")

print("\n  the SMALL-RADIUS floor: how far off the wall is the band's centre, and")
print("  what does each guard say, as the radius shrinks (disc r=10 t=20)?")
print(f"  {'feature':22s} {'clicked centre':>26s} {'resolved':>9s} {'gap':>7s} "
      f"{'align':>7s}  a  e  d")
for kind, vals in (("fillet", (3.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02)),
                   ("chamfer", (3.0, 0.5, 0.1))):
    for v in vals:
        dd_ = doc_disc(kind, v)
        gt = "TORUS" if kind == "fillet" else "CONE"
        try:
            fb = face_by(dd_._parts["f1"], gt)
        except Exception:                        # noqa: BLE001
            print(f"  {kind} {v}: no {gt} face built")
            continue
        c, n = r2(centre_of(fb)), r3(norm_of(fb))
        rf = blocks.resolve_face(dd_._parts["d"], c, n)
        g = gap_to_surface(rf, c, 0.02)
        al = align(rf, c, n)
        print(f"  {kind + ' ' + str(v):22s} {pt(c):>26s} {blocks._gtype(rf):>9s} "
              f"{g:7.4f} {(float('nan') if al is None else al):7.3f}  "
              f"{'Y' if g <= 0.02 else 'n'}  "
              f"{'Y' if (al is not None and al >= ALIGN) else 'n'}  "
              f"{'Y' if in_bbox(rf, c) else 'n'}   "
              f"{'<- (a) alone ACCEPTS a preview-only face' if g <= 0.02 else ''}")


# =========================================================== SS3c ===========
print("")
print("== SS3c the blind spot both distance and normal share: a round on a")
print("   NEARLY TANGENT (shallow-dihedral) edge — disc r10 h10 + a 168.7 deg taper")


def doc_shallow(rad=1.0):
    d = Document(name="sh")
    d.add("c1", "disc", {"radius": 10, "thickness": 10}, [])
    d.add("k", "cone", {"bottom_radius": 10, "top_radius": 8, "height": 2}, [])
    d.add("km", "move", {"x": 0, "y": 0, "z": 6}, ["k"])
    d.add("body", "fuse", {}, ["c1", "km"], )
    d.rebuild()
    part = d._parts["body"]
    rim = [e for e in part.edges()
           if blocks._gtype(e) == "CIRCLE" and abs(float((e @ 0.5).Z) - 5.0) < 1e-6]
    if not rim:
        return d, None
    d.add("g1", "fillet", {"radius": rad, "edges": [blocks.edge_ref(part, rim[0])]}, ["body"])
    d.rebuild()
    return d, "g1"


for rad in (1.0, 0.3, 0.1, 0.05):
    ds, fid = doc_shallow(rad)
    if fid is None:
        print("   (no rim at z=5 — geometry not as expected)")
        break
    inp = ds._parts["body"]
    newf = [f for f in ds._parts[fid].faces()
            if blocks._gtype(f) in ("TORUS", "BSPLINE", "BEZIER")]
    if not newf:
        print(f"   fillet r{rad}: no band face ({sorted({blocks._gtype(f) for f in ds._parts[fid].faces()})})")
        continue
    fb = newf[0]
    c, n = r2(centre_of(fb)), r3(norm_of(fb))
    rf = blocks.resolve_face(inp, c, n)
    g = gap_to_surface(rf, c, 0.02)
    al = align(rf, c, n)
    print(f"   shallow band r{rad}: centre {pt(c)} -> resolved {blocks._gtype(rf)}  "
          f"gap {g:.4f}  align {al:.4f}  -> (a) {'ACCEPT' if g <= 0.02 else 'REFUSE'}  "
          f"(e) {'ACCEPT' if al >= ALIGN else 'REFUSE'}  "
          f"(a)+(e) {'ACCEPT (blind spot)' if (g <= 0.02 and al >= ALIGN) else 'REFUSE'}")
    p2 = toolplan.plan(ds, {"tool": "fillet", "body_id": "body", "edges": [],
                            "face_toggle": {"center": c, "normal": n}})
    print(f"     shipped plan today: ok={p2['ok']} "
          + (f"edges={len(p2.get('edges', []))} z levels="
             f"{sorted({round(float(((e.get('ref') or {}).get('mid') or e.get('mid'))[2]), 2) for e in p2.get('edges', [])})}"
             if p2["ok"] else str(p2.get('error'))[:60]))

# =========================================================== SS4 ============
print("\n== SS4 where does the clicked centre come from?")
print("  studio.py:1369-1373   c = face.center(); info['center'] = [round(c.X, 2), ...]")
print("                        n = face.normal_at(c); info['normal'] = [round(n.X, 3), ...]")
print("  viewport.js:916       faceInfoAt(hit) -> entry.data.faces.find(f => f.id === faceId)")
print("  tool.js:472           replan({face_toggle: {center: info.center, normal: info.normal}})")
print("  => the centre IS the server's own Face.center(), rounded to 2 decimals (R1 kept);")
print("     the browser computes nothing, it only echoes the face row back.")
print(f"     worst-case rounding shift sqrt(3)*0.005 = {math.sqrt(3) * 0.005:.5f} mm")
worst = max(dist(centre_of(f), r2(centre_of(f))) for _m, _l, _p, f in cases)
print(f"     measured worst shift over the {len(cases)} probe cases: {worst:.5f} mm")

# =========================================================== SS5 ============
print("\n== SS5 the recommended guard as _face_of would call it")
print(f"  toolplan already imports provenance: {'provenance' in dir(toolplan)}  "
      f"(no new OCP import needed; OnFace lives in provenance.py:242)")


def face_of_new(part, pick, body, tol=0.02):
    """the proposed _face_of body — nothing but blocks + provenance"""
    c = pick.get("center") if isinstance(pick, dict) else None
    if c is None:
        raise ValueError("that face has no centre to name it by — click one of its edges instead")
    n = pick.get("normal")
    face = blocks.resolve_face(part, c, n)
    x, y, z = (float(v) for v in c)
    on_surface = gap_to_surface(face, (x, y, z), tol) <= tol
    faces_the_same_way = True
    if n:
        m = normal_at(face, (x, y, z))
        faces_the_same_way = m is not None and sum(
            a * b for a, b in zip(m, [float(v) for v in n])) >= 0.99
    if not (on_surface and faces_the_same_way):
        raise ValueError(f"that face is not on {body} — a round or bevel this tool drew has no "
                         f"edges of its own to pick; click a face of {body}, or an edge")
    return face


bad = 0
for must, label, part, f in allcases:
    c, n = r2(centre_of(f)), r3(norm_of(f) or [0, 0, 0])
    by_edge = blocks._edge_faces(part)
    try:
        got = face_of_new(part, {"center": c, "normal": n}, "d")
        res = (f"ACCEPT {blocks._gtype(got)} "
               f"{len(toolplan._corners(got.edges(), by_edge))} edges")
        ok = must
    except ValueError as e:
        res = f"REFUSE: {str(e)[:40]}"
        ok = not must
    bad += 0 if ok else 1
    print(f"  {label:30s} want {'ACCEPT' if must else 'REFUSE':6s} -> {res:44s} "
          f"{'OK' if ok else '**WRONG**'}")
print(f"  wrong verdicts: {bad}")
# the helper the fix wants in provenance.py (same imports OnFace already uses)
def surface_gap(tface, x, y, z, tol=provenance.TOL) -> float:
    """distance from a point to a face's UNDERLYING (untrimmed) surface"""
    try:
        sas = ShapeAnalysis_Surface(BRep_Tool.Surface_s(tface))
        sas.ValueOfUV(gp_Pnt(float(x), float(y), float(z)), tol)
        return float(sas.Gap())
    except Exception:                            # noqa: BLE001
        return float("inf")


wall = face_by(disc, "CYLINDER")
print(f"  provenance-shaped helper surface_gap(wall, band centre) = "
      f"{surface_gap(wall.wrapped, *r2(bc), tol=0.02):.4f} mm  "
      f"(the same number gap_to_surface printed above)")
n_it = 200
t0 = time.perf_counter()
for _ in range(n_it):
    surface_gap(wall.wrapped, *r2(bc), tol=0.02)
    normal_at(wall, r2(bc))
rec_ms = (time.perf_counter() - t0) * 1000
t0 = time.perf_counter()
for _ in range(n_it):
    in_bbox(wall, r2(bc))
bbox_ms = (time.perf_counter() - t0) * 1000
t0 = time.perf_counter()
for _ in range(n_it):
    provenance.OnFace(wall.wrapped)(*r2(bc), tol=0.02)
onface_ms = (time.perf_counter() - t0) * 1000
print(f"  cost per call, {n_it} iterations on the disc wall:")
print(f"    recommended (surface_gap + normal_at) {rec_ms / n_it:8.3f} ms")
print(f"    provenance.OnFace (build + query)     {onface_ms / n_it:8.3f} ms")
print(f"    the SHIPPED bbox guard                {bbox_ms / n_it:8.3f} ms  "
      f"<- face.bounding_box() is the expensive one")

# ---------------------------------------------------------------------------
# MEASURED 2026-09-08, C:/Python314/python.exe, this machine
# ---------------------------------------------------------------------------
# SS1 CONFIRMED, and it is silent. disc r=10 t=20 (z -10..+10), fillet r=3 on
#   the top rim. The preview's TORUS band center() = (-9.121, 0, 9.121); the
#   payload rounds it to [-9.12, 0.0, 9.12] with normal [-0.707, 0, 0.707].
#   resolve_face(disc, ...) names the CYLINDER WALL (its center() is
#   (-10, 0, 0), a point ON the surface); the wall's bbox is the whole
#   x[-10,10] y[-10,10] z[-10,10] cube, so the shipped guard says "inside" ->
#   toolplan.plan returns ok=True, click=added, 2 edges: mid z = +10 AND
#   z = -10. The rim at the FAR END of the body joins the selection with no
#   warning, and it is stored that way in edges_param.
#   The same click on a box (band centre (-18.536,-13.536,0)) is refused, as
#   probes/feature_edges_probe.py section 3 measured -> the shipped test misses it.
#   A second instance: disc r10 h10 + a cone taper fused on top (dihedral
#   168.7 deg), fillet on the shared rim -> the band resolves to the CONE and
#   the plan takes the cone's z=5 and z=7 rims. Not only bodies of revolution.
#
# SS2 build123d Face.center() (topology/two_d.py:1961) defaults to
#   CenterOf.GEOMETRY, which is TWO different things:
#     planar face -> BRepGProp SurfaceProperties CentreOfMass = the AREA CENTROID
#     curved face -> the uv midpoint of _uv_bounds = a point ON the surface
#   Measured (point, on its own material?, gap to its own surface):
#     box top            ( 0.000,  0.000, 10.000)  on-face True   gap 0.00000
#     pocket top (8,5)   (-2.000, -1.250, 10.000)  on-face True   gap 0.00000
#     pocket top (-8,-5) ( 2.000,  1.250, 10.000)  -> the centroid MOVES with
#                                                    the pocket (mirror image)
#     ANNULUS r10/r4     ( 0.000,  0.000,  2.500)  on-face FALSE  gap 0.00000
#                                                    -> IN THE HOLE
#     L-shaped top       (-3.333, -2.500, 10.000)  on-face True   gap 0.00000
#     cylinder wall      (-10.000, 0.000,  0.000)  on-face True   gap 0.00000
#     torus band r3      (-9.121,  0.000,  9.121)  on-face True   gap 0.00000
#   So a face centre is ALWAYS on its own surface (gap 0 everywhere) but is not
#   always on its own material (the annulus). A U-shaped top face
#   (0, -0.658, 10) is off-material too.
#
# SS3 guard matrix, 12 must-accept / 6 must-refuse clicks, tol 0.02 mm:
#     (a) on-surface gap <= 0.02      wrong-accept 0   wrong-refuse 0
#     (b) OnFace (gap + FClass2d)     wrong-accept 0   wrong-refuse 1 (annulus)
#     (c) centre-match <= 0.02        wrong-accept 0   wrong-refuse 2
#     (d) bbox +-0.05 (SHIPPED)       wrong-accept 4   wrong-refuse 0
#   (d)'s four wrong accepts are every disc case: torus r3 / r0.5 / r0.1 and
#   the cone chamfer. (b) OR (c) scores 0/0 on this matrix but is WRONG on a
#   U-shaped top face clicked on the PREVIEW body: the centroid is off the
#   material (OnFace False) and it moved 0.0461 mm > 0.02 (centre-match False).
#
# SS3b (e) NORMAL AGREEMENT: dot(clicked normal, resolved face's normal AT the
#   clicked point) >= 0.99. Worst must-accept 0.9998; every must-refuse band
#   0.7070 (a 45 deg band on a 90 deg dihedral) — SCALE-FREE, so it holds where
#   distance dies: the small-radius floor of (a) is real (disc fillet r=0.05 and
#   r=0.02 leave the band centre only 0.0100 mm off the wall, inside any
#   tolerance the 2-decimal payload allows), and (e) still refuses them.
#   (a)+(e): wrong-accept 0, wrong-refuse 0 over all 20 cases.
#
# SS3c the only blind spot left: a round on a NEARLY TANGENT edge. Disc r10 h10
#   + a 168.7 deg taper, fillet on the shared rim:
#     r=1.0   gap 0.0778  align 0.9242  -> refused
#     r=0.3   gap 0.0212  align 0.9242  -> refused
#     r=0.1   gap 0.0071  align 0.9242  -> refused by (e), (a) alone accepts
#     r=0.05  gap 0.0000  align 0.9242  -> refused by (e), (a) alone accepts
#   (the shipped guard accepts all four). A dihedral above ~172 deg with a
#   sub-0.1 mm radius would defeat both halves; nothing local can see it.
#
# SS4 the clicked centre is the SERVER's own Face.center() rounded to 2 decimals
#   (studio.py:1369-1373 -> viewport.js:916 faceInfoAt -> tool.js:472), and the
#   normal is face.normal_at(centre) to 3 decimals. R1 is intact: the browser
#   echoes the face row, it computes nothing. Worst rounding shift possible
#   sqrt(3)*0.005 = 0.00866 mm; worst measured over the 20 cases 0.00632 mm ->
#   0.02 mm is 2.3x the worst case and 3.2x the worst measured.
#
# SS5 the recommendation needs NO new import in toolplan (it already imports
#   provenance and blocks) plus ONE new helper beside provenance.OnFace:
#   surface_gap(tface, x, y, z, tol) -> Gap(), built from the imports
#   provenance.py:47-48 already has. Verified: surface_gap(wall, band centre) =
#   0.8800 mm, the same number, and the proposed _face_of gives 0 wrong verdicts
#   over all 20 cases. Cost per face click (200 iterations, disc wall):
#     recommended (surface_gap + normal_at)  0.469 ms
#     provenance.OnFace (build + query)      0.181 ms
#     the SHIPPED bbox guard                 0.222 ms
#   i.e. +0.25 ms on ONE call per click. (face.bounding_box() is cheap on a
#   plane or a cylinder but cost 91 ms on the torus band face in an earlier run,
#   so dropping bounding_box() is not a loss anywhere.)
