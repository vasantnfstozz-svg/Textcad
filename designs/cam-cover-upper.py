"""cam-cover-upper v2 — the finned billet cover, SCALED TO THE BOX and built
UP instead of hogged out. Three changes from v1 (df159cb), all asked for:

  1. FILLS THE STOCK. 210 x 110 out of the 220 x 120 blank, 5mm parting
     trench all round, no offcut. This is a deliberate NON-UNIFORM scale:
     the real cover is 3.17:1 and the box is 1.91:1, so the part comes out
     stubbier than the engine part. Length 1:2.19 as in v1, width 1:1.32.
     Flagged once; the user asked for the box twice.
  2. NO ROUNDED LOBES, SQUARE-ISH CORNERS. v1's R11.5 ends and its 14
     bulging bolt-boss lobes are gone. The outline is a near-rectangular
     plate, CORNER_R 5 on a 110-wide part, and the bolts are plain holes in
     a flat 13mm perimeter band - which is what the reference photo shows.
  3. THE FINS ARE EXTRUSIONS, NOT CUTS. The part is now additive: base
     plate -> raised deck platform -> 19 raised fin ribs -> 3 raised cam
     bosses, ONE fuse, and the only cuts left are holes. Every raised
     element sinks EMBED into its parent first (coplanar faces are the
     classic fuse trap in this codebase).

  Same finished solid either way - a milled fin IS the material left
  between two passes - so the CAM does not change: skim the top to 11.4,
  mill the deck to 9.0 leaving the ribs, drop the flange band to 7.0.

Z STACK
  11.4  fin tops + cam boss tops   (0.6 under the raw stock = the skim)
   9.0  deck floor between the fins (fins stand 2.4 proud)
   7.0  perimeter flange band -> the deck platform stands 2.0 above it
   6.0  cam boss counterbores (D14)
   3.5  cam boss bores (D7)
   3.0  bolt hole floors (D5, blind - 3mm of steel left)
   1.5  outline trench floor (NOT modelled - machining note)

VACUUM  every cut is a blind pocket. The outline is the one through feature
        and it is a ~6mm contour trench to z1.5 with a 1.5mm skin.

TOOLING D6 to hog the deck and the flange band, D3 to finish (all inner
        corners >= R4), D2 for the 2.4mm gaps between fins - two passes at
        +-0.2, 2.4 deep, so 4 step-downs in steel.

Run:  python designs/cam-cover-upper.py           -> preview + checks
      python designs/cam-cover-upper.py --build   -> STEP + tcad.json
"""
import io
import json
import math
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = r"c:\Users\VasanSeenivasan\Desktop\textcad"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ------------------------------------------------------------------- stock
STOCK_L, STOCK_W, STOCK_T = 220.0, 120.0, 12.0
PART_GAP = 5.0                    # parting trench, all four sides

# --------------------------------------------------------------- z levels
Z_TOP = 12.0
Z_FIN = 11.4                      # fin + boss tops; 0.6 skim off the stock
Z_DECK = 9.0                      # deck floor between fins
Z_FLANGE = 7.0                    # perimeter flange band
Z_BOSS_CB = 6.0
Z_BOSS_BORE = 3.5
Z_BOLT = 3.0
Z_TRENCH = 1.5
EMBED = 0.2                       # raised features sink this into the parent

# --------------------------------------------------- outline: FILL THE BOX
REAL_L, REAL_W, REAL_H = 460.0, 145.0, 55.0
COVER_L = STOCK_L - 2 * PART_GAP            # 210.0
COVER_W = STOCK_W - 2 * PART_GAP            # 110.0
CORNER_R = 5.0                              # was 11.5 + lobes; user said no
SCALE_L = COVER_L / REAL_L                  # 0.4565
SCALE_W = COVER_W / REAL_W                  # 0.7586  <- the deliberate stretch

# ----------------------------------------------------- flange + bolt holes
FB = 13.0                                   # flat perimeter band width
BOLT_R = 2.5                                # D5 blind
N_BOLT_SIDE, N_BOLT_END = 9, 3
BOLT_SIDE_X0 = 95.0
BOLT_END_Y = (0.0, 26.0, -26.0)

# ------------------------------------------------------------- deck + fins
DECK_L = round(COVER_L - 2 * FB, 1)         # 184.0
DECK_W = round(COVER_W - 2 * FB, 1)         # 84.0
DECK_R = 4.0
FIN_N, FIN_RIB, FIN_PITCH, FIN_R = 19, 1.8, 4.2, 0.8
FIN_GAP = round(FIN_PITCH - FIN_RIB, 2)     # 2.4 = what the D2 cuts
FIN_X = DECK_L / 2 - 4.0                    # 88.0
FIN_MIN_SEG = 12.0
BOSS_X = (-60.0, 0.0, 60.0)                 # same journals as the lower cover
BOSS_R, BOSS_CB_R, BOSS_BORE_R = 12.0, 7.0, 3.5
BOSS_CLR = 1.8

TOOL_MIN = 2.0


# ------------------------------------------------------- rounded-path core
def _corner_geo(verts, radii):
    n = len(verts)
    out = []
    for i in range(n):
        v, p, q = verts[i], verts[i - 1], verts[(i + 1) % n]
        r = radii[i]
        e_in = (v[0] - p[0], v[1] - p[1])
        e_out = (q[0] - v[0], q[1] - v[1])
        li, lo = math.hypot(*e_in), math.hypot(*e_out)
        ui, uo = (e_in[0] / li, e_in[1] / li), (e_out[0] / lo, e_out[1] / lo)
        ang = math.acos(max(-1, min(1, -(ui[0] * uo[0] + ui[1] * uo[1]))))
        t = r / math.tan(ang / 2)
        assert t < li and t < lo, f"radius {r} too big at vertex {v}"
        b = (uo[0] - ui[0], uo[1] - ui[1])
        lb = math.hypot(*b)
        b = (b[0] / lb, b[1] / lb)
        dd = r / math.sin(ang / 2)
        out.append({"a_in": (v[0] - ui[0] * t, v[1] - ui[1] * t),
                    "via": (v[0] + b[0] * (dd - r), v[1] + b[1] * (dd - r)),
                    "a_out": (v[0] + uo[0] * t, v[1] + uo[1] * t),
                    "c": (v[0] + b[0] * dd, v[1] + b[1] * dd), "r": r})
    return out


def outline_path(verts, radii, mode="add"):
    geo = _corner_geo(verts, radii)
    first = geo[0]["a_out"]

    def q3(p):
        return [round(p[0], 3), round(p[1], 3)]
    segs = []
    for i in list(range(1, len(verts))) + [0]:
        g = geo[i]
        segs.append({"type": "line", "to": q3(g["a_in"])})
        segs.append({"type": "arc", "via": q3(g["via"]),
                     "to": q3(first if i == 0 else g["a_out"])})
    return {"kind": "path", "mode": mode, "start": q3(first),
            "segments": segs}


def rbox(cx, cy, w, h, r, mode="add"):
    return outline_path([(cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2),
                        (cx - w / 2, cy + h / 2), (cx - w / 2, cy - h / 2)],
                        [r] * 4, mode)


def rrect(x0, x1, y0, y1, r, mode="add"):
    return outline_path([(x1, y0), (x1, y1), (x0, y1), (x0, y0)],
                        [r] * 4, mode)


def circ(cx, cy, r, mode="add"):
    return {"kind": "circle", "r": round(r, 3), "x": round(cx, 3),
            "y": round(cy, 3), "mode": mode}


# ------------------------------------------------------------ bolt pattern
BOLT_Y = round(COVER_W / 2 - FB / 2, 2)      # 48.5, centre of the band
BOLT_END_X = round(COVER_L / 2 - FB / 2, 2)  # 98.5
BOLTS = []
for _i in range(N_BOLT_SIDE):
    _bx = round(-BOLT_SIDE_X0 + 2 * BOLT_SIDE_X0 * _i / (N_BOLT_SIDE - 1), 3)
    BOLTS += [(_bx, BOLT_Y), (_bx, -BOLT_Y)]
for _by in BOLT_END_Y:
    BOLTS += [(BOLT_END_X, _by), (-BOLT_END_X, _by)]


# ------------------------------------------------------------------- fins
def fin_ribs():
    """The RAISED ribs (not the gaps), broken around the three cam bosses."""
    out = []
    half = FIN_RIB / 2
    for i in range(FIN_N):
        y = round((i - (FIN_N - 1) / 2) * FIN_PITCH, 3)
        blocked = []
        for bx in BOSS_X:
            dy = max(0.0, abs(y) - half)
            rr_ = BOSS_R + BOSS_CLR
            if dy >= rr_:
                continue
            b = math.sqrt(rr_ * rr_ - dy * dy)
            blocked.append((bx - b, bx + b))
        blocked.sort()
        x = -FIN_X
        for b0, b1 in blocked:
            if b0 - x >= FIN_MIN_SEG:
                out.append((round(x, 3), round(b0, 3), y, half))
            x = max(x, b1)
        if FIN_X - x >= FIN_MIN_SEG:
            out.append((round(x, 3), round(FIN_X, 3), y, half))
    return out


FINS = fin_ribs()


# ------------------------------------------------------------ height field
def _sdf_rr(x, y, cx, cy, w, h, r):
    qx = abs(x - cx) - (w / 2 - r)
    qy = abs(y - cy) - (h / 2 - r)
    return (math.hypot(max(qx, 0.0), max(qy, 0.0))
            + min(max(qx, qy), 0.0) - r)


def top_z(x, y):
    """Finished height at (x, y); 0 = air. Drives the section view and is
    probed by the gates, so drawing and tree cannot silently disagree."""
    if _sdf_rr(x, y, 0, 0, COVER_L, COVER_W, CORNER_R) > 0:
        return 0.0
    for bx, by in BOLTS:
        if math.hypot(x - bx, y - by) <= BOLT_R:
            return Z_BOLT
    if _sdf_rr(x, y, 0, 0, DECK_L, DECK_W, DECK_R) > 0:
        return Z_FLANGE
    for bx in BOSS_X:
        d = math.hypot(x - bx, y)
        if d <= BOSS_BORE_R:
            return Z_BOSS_BORE
        if d <= BOSS_CB_R:
            return Z_BOSS_CB
        if d <= BOSS_R:
            return Z_FIN
    for a, b, fy, h in FINS:
        if a <= x <= b and abs(y - fy) <= h:
            return Z_FIN
    return Z_DECK


# ------------------------------------------------------------ sanity gates
assert COVER_L + 2 * PART_GAP <= STOCK_L, "no parting gap in X"
assert COVER_W + 2 * PART_GAP <= STOCK_W, "no parting gap in Y"
assert CORNER_R <= 6.0, "corners are meant to read SQUARE, not rounded"
assert CORNER_R >= 3.0, "corner tighter than a D6 rougher"
# the box fill is deliberate and non-uniform - keep the fact visible
assert SCALE_W > SCALE_L, "width should be stretched, that is the whole ask"

# the flange band carries its bolts with real wall on both sides
assert FB >= 2 * BOLT_R + 6.0, f"flange band {FB} too narrow for D{2*BOLT_R}"
for bx, by in BOLTS:
    assert -_sdf_rr(bx, by, 0, 0, COVER_L, COVER_W, CORNER_R) >= BOLT_R + 3.0, \
        f"bolt ({bx},{by}) too close to the outline"
    assert _sdf_rr(bx, by, 0, 0, DECK_L, DECK_W, DECK_R) >= BOLT_R + 2.0, \
        f"bolt ({bx},{by}) breaks into the deck"
for _j, _p in enumerate(BOLTS):
    for _q in BOLTS[_j + 1:]:
        assert math.hypot(_p[0] - _q[0], _p[1] - _q[1]) >= 2 * BOLT_R + 5.0, \
            f"bolts {_p} and {_q} too close"

# deck, fins, bosses
assert DECK_R >= 3.0, "deck corner tighter than a D6 rougher"
FIN_SPAN = (FIN_N - 1) * FIN_PITCH + FIN_RIB
assert (DECK_W - FIN_SPAN) / 2 >= 2.5, f"fin field {FIN_SPAN} too wide"
assert FIN_RIB >= 1.5, "fin ribs thinner than 1.5mm"
assert FIN_GAP >= TOOL_MIN + 0.4, "gap between fins narrower than tool+2 passes"
assert (Z_FIN - Z_DECK) / FIN_RIB <= 2.0, "fin ribs too slender for their height"
assert FIN_X + 4.0 <= DECK_L / 2 + 0.01, "fins run off the deck"
assert len(FINS) > FIN_N, "fins are not being broken around the bosses"
assert min(b - a for a, b, _, _ in FINS) >= FIN_MIN_SEG - 1e-6
for bx in BOSS_X:
    assert abs(bx) + BOSS_R + 3.0 <= DECK_L / 2, f"boss {bx} off the deck"
assert BOSS_R + 3.0 <= DECK_W / 2, "boss leaves no deck around it"
assert BOSS_R - BOSS_CB_R >= 3.5 and BOSS_CB_R - BOSS_BORE_R >= 3.0, \
    "boss steps too small to read"
assert min(BOSS_X[i + 1] - BOSS_X[i] for i in range(len(BOSS_X) - 1)) \
    >= 2 * BOSS_R + 8.0, "bosses too close"

# z stack
assert Z_FIN > Z_DECK > Z_FLANGE > Z_BOSS_CB > Z_BOSS_BORE > Z_BOLT > Z_TRENCH
assert Z_TOP - Z_FIN >= 0.5, "no stock cleanup allowance left on top"
assert Z_BOLT >= 1.5 and Z_BOSS_BORE >= 1.5, "blind floor too thin"
assert Z_FIN - Z_DECK >= 2.0, "fins too short to read"
assert Z_DECK - Z_FLANGE >= 1.5, "deck platform does not stand proud"
assert EMBED > 0.05, "raised features must sink into their parent before fusing"

# probes against the intent
assert top_z(0, 0) == Z_BOSS_BORE, "centre boss bore"
assert top_z(30, 0) == Z_FIN, "a fin rib on the centreline"
assert top_z(30, FIN_PITCH / 2) == Z_DECK, "the gap between two fins"
assert top_z(0, COVER_W / 2 - FB - 3.0) == Z_DECK, "deck just inside the band"
assert top_z(0, COVER_W / 2 - 2.0) == Z_FLANGE, "flange band"
assert top_z(0, COVER_W / 2 + 3.0) == 0.0, "outside the outline"
assert top_z(*BOLTS[0]) == Z_BOLT, "bolt hole"


# ------------------------------------------------------------ feature tree
F = []


def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


def raise_(name, z_from, z_to, ents):
    """A RAISED element: sketch at (z_from - EMBED) and pull it up to z_to."""
    z0 = round(z_from - EMBED, 3)
    f(f"{name}_sk", "sketch", {"plane": "XY", "offset": z0, "entities": ents})
    f(name, "extrude", {"amount": round(z_to - z0, 3)}, [f"{name}_sk"])
    return name


PREV = None


def cut(name, z, ents, over=1.0):
    global PREV
    f(f"{name}_c_sk", "sketch", {"plane": "XY", "offset": z, "entities": ents})
    f(f"{name}_c_tl", "extrude", {"amount": round(Z_TOP - z + over, 3)},
      [f"{name}_c_sk"])
    f(name, "cut", {}, [PREV, f"{name}_c_tl"])
    PREV = name


# ---- additive half: base plate, raised deck, raised fins, raised bosses
f("base_sk", "sketch", {"plane": "XY", "offset": 0, "entities":
  [rbox(0, 0, COVER_L, COVER_W, CORNER_R)]})
f("base_plate", "extrude", {"amount": Z_FLANGE}, ["base_sk"])
parts = ["base_plate"]

parts.append(raise_("deck_platform", Z_FLANGE, Z_DECK,
                    [rbox(0, 0, DECK_L, DECK_W, DECK_R)]))

fin_ents = [rrect(a, b, y - h, y + h, FIN_R) for a, b, y, h in FINS]
for i in range(0, len(fin_ents), 8):
    parts.append(raise_(f"fin_ribs_{i // 8}", Z_DECK, Z_FIN,
                        fin_ents[i:i + 8]))

parts.append(raise_("cam_bosses", Z_DECK, Z_FIN,
                    [circ(bx, 0, BOSS_R) for bx in BOSS_X]))

f("cover_body", "fuse", {}, parts)
PREV = "cover_body"

# ---- subtractive half: nothing but holes
cut("boss_counterbores", Z_BOSS_CB, [circ(bx, 0, BOSS_CB_R) for bx in BOSS_X])
cut("boss_bores", Z_BOSS_BORE, [circ(bx, 0, BOSS_BORE_R) for bx in BOSS_X])
bolt_ids = []
for i in range(0, len(BOLTS), 8):
    f(f"bolt_holes_{i // 8}_sk", "sketch", {"plane": "XY", "offset": Z_BOLT,
      "entities": [circ(bx, by, BOLT_R) for bx, by in BOLTS[i:i + 8]]})
    f(f"bolt_holes_{i // 8}", "extrude",
      {"amount": round(Z_TOP - Z_BOLT + 1, 3)}, [f"bolt_holes_{i // 8}_sk"])
    bolt_ids.append(f"bolt_holes_{i // 8}")
f("cam_cover_upper", "cut", {}, [PREV] + bolt_ids)

N_ADD = len(parts)
N_CUT = sum(1 for x in F if x["op"] == "cut")
for _feat in F:
    if _feat["op"] == "sketch":
        _n = len(_feat["params"]["entities"])
        assert _n <= 10, f"sketch {_feat['id']} has {_n} entities (max 10)"

tree = {"name": "cam-cover-upper", "features": F,
        "spec": {"n_solids": 1, "size": [COVER_L, COVER_W, Z_FIN],
                 "tol": 0.3}}
open(ROOT + r"\designs\cam-cover-upper-tree.json", "w").write(json.dumps(tree))


# ----------------------------------------------------------------- preview
S = 5.0
SEC_H, SEC_Y, SEC_Z = 50.0, 1.4, 3.4
W = int(STOCK_L * S)
HT = int((STOCK_W + SEC_H) * S)
img = Image.new("RGB", (W, HT), (12, 15, 20))
dr = ImageDraw.Draw(img)
Y0 = STOCK_W * S


def px(p):
    return (W / 2 + p[0] * S, STOCK_W * S / 2 - p[1] * S)


def col(z):
    t = max(0.0, min(1.0, (z - 2.0) / (Z_FIN - 2.0)))
    lo_, hi_ = (38, 42, 50), (202, 206, 212)
    return tuple(int(lo_[i] + (hi_[i] - lo_[i]) * (t ** 0.8)) for i in range(3))


def sample_rr(cx, cy, w, h, r, n=8):
    pts = []
    for sx, sy, a0 in ((1, 1, 0.0), (-1, 1, math.pi / 2),
                       (-1, -1, math.pi), (1, -1, 3 * math.pi / 2)):
        ax, ay = sx * (w / 2 - r) + cx, sy * (h / 2 - r) + cy
        for k in range(n + 1):
            a = a0 + math.pi / 2 * k / n
            pts.append((ax + r * math.cos(a), ay + r * math.sin(a)))
    return pts


def box(cx, cy, w, h, r, z):
    dr.polygon([px(p) for p in sample_rr(cx, cy, w, h, r)], fill=col(z))


def disc(cx, cy, r, z):
    dr.ellipse([px((cx - r, cy + r)), px((cx + r, cy - r))], fill=col(z))


dr.rectangle([px((-STOCK_L / 2, STOCK_W / 2)),
              px((STOCK_L / 2, -STOCK_W / 2))], fill=(26, 30, 36))
box(0, 0, COVER_L, COVER_W, CORNER_R, Z_FLANGE)
box(0, 0, DECK_L, DECK_W, DECK_R, Z_DECK)
for a, b, y, h in FINS:
    box((a + b) / 2, y, b - a, 2 * h, FIN_R, Z_FIN)
for bx in BOSS_X:
    disc(bx, 0, BOSS_R, Z_FIN)
    disc(bx, 0, BOSS_CB_R, Z_BOSS_CB)
    disc(bx, 0, BOSS_BORE_R, Z_BOSS_BORE)
for bx, by in BOLTS:
    disc(bx, by, BOLT_R, Z_BOLT)

SEC_X = -30.0
RED = (226, 96, 72)
dr.line([px((SEC_X, -COVER_W / 2 - 4)), px((SEC_X, COVER_W / 2 + 4))],
        fill=RED, width=2)

base = HT - 14
dr.rectangle([(0, Y0), (W, HT)], fill=(18, 22, 28))
n = 1600
prof = [(-COVER_W / 2 - 3 + (COVER_W + 6) * i / n) for i in range(n + 1)]
prof = [(u, top_z(SEC_X, u)) for u in prof]


def spx(u, z):
    return (W / 2 + u * S * SEC_Y, base - z * S * SEC_Z)


pts = [spx(prof[0][0], 0)] + [spx(u, z) for u, z in prof] \
    + [spx(prof[-1][0], 0)]
dr.polygon(pts, fill=(150, 156, 166))
dr.line([spx(prof[0][0], 0), spx(prof[-1][0], 0)], fill=(96, 104, 116),
        width=2)

try:
    FN = ImageFont.truetype("arial.ttf", 14)
except OSError:
    FN = ImageFont.load_default()
dr.text((14, Y0 + 12), f"SECTION A-A   across the width at x={SEC_X:.0f}"
        f"   (width x{SEC_Y:.1f}, height x{SEC_Z:.1f})   -   {FIN_N} RAISED"
        f" FIN RIBS {FIN_RIB} WIDE x {Z_FIN-Z_DECK:.1f} TALL, {FIN_GAP} GAPS",
        font=FN, fill=RED)
for s in (1, -1):
    dr.text(px((SEC_X, s * (COVER_W / 2 + 8))), "A", font=FN, fill=RED,
            anchor="mm")

out = ROOT + r"\designs\cam-cover-upper-preview.png"
img.save(out)

# ------------------------------------------------------------------- report
print(f"preview: {out}")
print(f"part {COVER_L} x {COVER_W} x {Z_FIN} FILLS the {STOCK_L}x{STOCK_W}"
      f" blank ({PART_GAP} trench all round, no offcut)")
print(f"scale: length 1:{1/SCALE_L:.2f}  width 1:{1/SCALE_W:.2f}"
      f"  -> aspect {COVER_L/COVER_W:.2f}:1 vs the real"
      f" {REAL_L/REAL_W:.2f}:1 (stretched on purpose)")
print(f"corners R{CORNER_R} (was R11.5 + 14 bulging lobes); flange band {FB}"
      f" wide at z{Z_FLANGE} with {len(BOLTS)} blind D{2*BOLT_R} holes")
print(f"deck {DECK_L} x {DECK_W} at z{Z_DECK}; {FIN_N} RAISED ribs"
      f" {FIN_RIB} wide x {Z_FIN-Z_DECK:.1f} tall, pitch {FIN_PITCH},"
      f" {FIN_GAP} gaps -> {len(FINS)} rib solids")
print(f"bosses: {len(BOSS_X)} x D{2*BOSS_R} raised, cb D{2*BOSS_CB_R}"
      f" z{Z_BOSS_CB}, bore D{2*BOSS_BORE_R} z{Z_BOSS_BORE}")
print(f"features: {len(F)} | {N_ADD} solids FUSED, only {N_CUT} cuts"
      f" (holes only) | through features: 0")


# --------------------------------------------------------------------- build
if "--build" in sys.argv:
    import contextlib
    import mcp_server as M
    with contextlib.redirect_stdout(io.StringIO()):
        doc = M.author._to_document(tree)
        ok = doc.rebuild()
        rep = M._report(doc, ok)
    print("verified:", rep["verified"])
    for feat in rep["features"]:
        if feat["status"] != "ok":
            print("  FEATURE", feat["id"], feat["status"], feat["problems"])
    if rep.get("spec_problems"):
        print("  SPEC", rep["spec_problems"])
    if ok:
        doc.to_step(ROOT + r"\designs\cam-cover-upper.step")
        doc.save(ROOT + r"\designs\cam-cover-upper.tcad.json")
        print("measured:", json.dumps(rep.get("measured", {}))[:420])
        print("wrote cam-cover-upper.step + .tcad.json")
