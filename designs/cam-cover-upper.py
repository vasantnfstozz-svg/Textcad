"""cam-cover-upper v1 — the FINNED BILLET UPPER COVER on its own, blown up
to fill the 220 x 120 x 12 steel stock. The workpiece outline IS the cover
silhouette (lobed bolt flange), not a rectangle: this is the part, not a
relief of it.

WHY IT GETS TWICE AS FAITHFUL AS THE PLAQUE
  Dropping the second cover frees the whole plate for one part, so plan scale
  jumps 0.32 -> 0.4565 (1:2.19) and the Z budget goes from 4.0mm of relief to
  the full 11.4mm of stock. Squash factor vs true scale: 2.2x flat, where the
  pair plaque was 4.4x. Two consequences worth having:
    * the fin pitch lands on 4.2mm = TRUE SCALE for a ~9mm cast fin, cut with
      the user's D2 (2.4 slot / 1.8 rib), no stylising
    * the bolt flange can be a real 5.5mm-thick LIP (true scale of a 12mm
      flange) with the finned body standing 6.4mm above it — the actual
      section of a cam cover, not a plateau on a plate

  Length is the binding constraint: 210 long keeps a 5mm parting gap in X.
  Width follows at 66.2 (true proportion, never stretched to fill the box).
  The part is pushed to the -Y edge so the leftover is ONE usable
  210 x 48.8 offcut instead of two useless 27mm strips.

  Real dims approximate (~460 x 145 x 55 from the reference photos). Only
  SCALE / REAL_* change if a measured drawing turns up.

Z STACK  (face skimmed 0.6 off the raw stock)
  11.4  body top = fin deck + cam boss tops           (highest)
   8.6  fin valleys (fins 2.8 deep = true scale of a 6mm fin)
   6.0  cam boss counterbores (D16)
   5.0  bolt flange lip top -> body stands 6.4 proud
   3.0  cam boss bores (D8)
   2.0  bolt hole floors (D4.6, blind - 2mm of steel left)
   1.5  outline trench floor (NOT modelled - machining note)

VACUUM  every cut is a blind pocket. The outline is the one through feature
        and it is machined as a trench to z1.5 leaving a ~1.5mm skin, so the
        part and the waste frame stay one piece until the bench.

TOOLING D6 to hog the flange ring where it is wide (the lobes), D5 or D4 in
        the 5.5mm-wide straight stretches, D3 to finish corners (r>=1.5),
        D2 for the fin slots. Boss bores are 8.4 deep - peck them.

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
PART_GAP = 5.0                    # parting trench width at the tight end

# --------------------------------------------------------------- z levels
Z_TOP = 12.0
Z_FACE = 11.4                     # 0.6 cleanup skim (warped stock)
Z_FIN = 8.6                       # fin valleys, 2.8 deep
Z_BOSS_CB = 6.0
Z_FLANGE = 5.0                    # bolt flange lip
Z_BOSS_BORE = 3.0
Z_BOLT = 2.0
Z_TRENCH = 1.5                    # documented, not modelled

# ---------------------------------------------------- cover, real -> stock
REAL_L, REAL_W, REAL_H = 460.0, 145.0, 55.0
COVER_L = STOCK_L - 2 * PART_GAP            # 210.0
SCALE = COVER_L / REAL_L                    # 0.4565
COVER_W = round(REAL_W * SCALE, 1)          # 66.2

LOBE_R = round(16.25 * SCALE, 2)            # real D32.5 bolt boss -> 7.42
LOBE_OUT = round(3.15 * SCALE, 2)           # boss centre outboard of the wall
WAIST = round(COVER_W - 2 * (LOBE_R + LOBE_OUT), 2)     # 48.5
END_R = 11.5
N_BOLT = 7                                  # per side, 14 total
BOLT_X0 = 84.0
BOLT_R = 2.3                                # D4.6 blind bolt hole

FW = round(12.0 * SCALE, 1)                 # flange lip width, true 12mm
BODY_L = round(COVER_L - 2 * FW, 1)         # 199.0
BODY_W = round(WAIST - 2 * FW, 1)           # 37.5
BODY_R = END_R - FW

FIN_N, FIN_W, FIN_PITCH, FIN_R = 8, 2.4, 4.2, 1.0       # 4.2 = true pitch
FIN_X = BODY_L / 2 - 3.5
FIN_MIN_SEG = 13.0
BOSS_X = (-60.0, 0.0, 60.0)
BOSS_R, BOSS_CB_R, BOSS_BORE_R = 12.5, 8.0, 4.0
BOSS_CLR = 1.8                              # fin -> boss wall

# part pushed to the -Y edge so the offcut is one usable strip
PART_Y = round(-STOCK_W / 2 + PART_GAP + COVER_W / 2, 2)
OFFCUT_W = round(STOCK_W / 2 - (PART_Y + COVER_W / 2) - PART_GAP, 1)

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


# --------------------------------------------------------- cover geometry
BOLT_X = [round(-BOLT_X0 + 2 * BOLT_X0 * i / (N_BOLT - 1), 3)
          for i in range(N_BOLT)]
BOLT_Y = round(WAIST / 2 + LOBE_OUT, 3)


def fin_segments():
    """Lengthwise fin slots, broken around the three cam bosses."""
    segs = []
    half = FIN_W / 2
    for i in range(FIN_N):
        y = (i - (FIN_N - 1) / 2) * FIN_PITCH
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
                segs.append((x, b0, y))
            x = max(x, b1)
        if FIN_X - x >= FIN_MIN_SEG:
            segs.append((x, FIN_X, y))
    return [(round(a, 3), round(b, 3), round(y, 3), half) for a, b, y in segs]


FINS = fin_segments()


# ---------------------------------------------------------- height field
def _sdf_rr(x, y, cx, cy, w, h, r):
    qx = abs(x - cx) - (w / 2 - r)
    qy = abs(y - cy) - (h / 2 - r)
    return (math.hypot(max(qx, 0.0), max(qy, 0.0))
            + min(max(qx, qy), 0.0) - r)


def in_cover(x, y):
    if _sdf_rr(x, y, 0, PART_Y, COVER_L, WAIST, END_R) <= 0:
        return True
    for bx in BOLT_X:
        for s in (1, -1):
            if math.hypot(x - bx, y - (PART_Y + s * BOLT_Y)) <= LOBE_R:
                return True
    return False


def top_z(x, y):
    """Finished height at (x, y) — 0 = air. Drives the section view AND
    double-checks the cut order the tree builds."""
    if not in_cover(x, y):
        return 0.0
    for bx in BOLT_X:                                   # blind bolt holes
        for s in (1, -1):
            if math.hypot(x - bx, y - (PART_Y + s * BOLT_Y)) <= BOLT_R:
                return Z_BOLT
    if _sdf_rr(x, y, 0, PART_Y, BODY_L, BODY_W, BODY_R) > 0:
        return Z_FLANGE                                 # flange lip
    for bx in BOSS_X:                                   # cam bosses
        d = math.hypot(x - bx, y - PART_Y)
        if d <= BOSS_BORE_R:
            return Z_BOSS_BORE
        if d <= BOSS_CB_R:
            return Z_BOSS_CB
        if d <= BOSS_R:
            return Z_FACE
    for a, b, fy, h in FINS:                            # fin valleys
        if a <= x <= b and abs(y - (PART_Y + fy)) <= h:
            return Z_FIN
    return Z_FACE


# ------------------------------------------------------------ sanity gates
assert COVER_L + 2 * PART_GAP <= STOCK_L, "no parting gap in X"
assert PART_Y - COVER_W / 2 >= -STOCK_W / 2 + PART_GAP - 0.01, "off the stock"
assert PART_Y + COVER_W / 2 + PART_GAP <= STOCK_W / 2, "offcut math"
assert OFFCUT_W >= 40.0, f"offcut {OFFCUT_W} not worth keeping"
assert abs(WAIST + 2 * (LOBE_R + LOBE_OUT) - COVER_W) < 0.02, "lobe math"
assert abs(COVER_W / REAL_W - SCALE) < 0.002, "width is not true proportion"

# flange lobes sit on the straight flange, clear of the end radii, and each
# keeps real wall around its bolt hole
assert BOLT_X0 + LOBE_R <= COVER_L / 2 - END_R, "outer lobe hits the end arc"
assert LOBE_R - BOLT_R >= 4.0, "bolt hole wall too thin"
assert min(BOLT_X[i + 1] - BOLT_X[i] for i in range(N_BOLT - 1)) \
    >= 2 * LOBE_R + 3.0, "lobes merge into a scalloped strip"
assert BOLT_R * 2 >= 4.0, "bolt hole smaller than a sane drill"

# body / fins / bosses
assert FW >= 4.0, "flange lip too narrow to machine beside"
assert (BODY_W - ((FIN_N - 1) * FIN_PITCH + FIN_W)) / 2 >= 2.5, \
    "fin field leaves no rail on the body top"
assert FIN_PITCH - FIN_W >= 1.5, "fin ribs thinner than 1.5mm"
assert FIN_W >= TOOL_MIN + 0.4, "fin slot narrower than tool + 2 passes"
assert FIN_X + 3.0 <= BODY_L / 2 + 0.01, "fins run off the body"
assert len(FINS) == FIN_N * (len(BOSS_X) + 1), \
    f"{len(FINS)} fin segments, want {FIN_N * (len(BOSS_X) + 1)}"
for bx in BOSS_X:
    assert abs(bx) + BOSS_R + 3.0 <= BODY_L / 2, f"boss {bx} off the body"
assert BOSS_R + 2.5 <= BODY_W / 2 + BOSS_R, "boss check"
assert (BODY_W / 2 - BOSS_R) >= 4.0, "boss leaves no rail on the body"
assert BOSS_R - BOSS_CB_R >= 3.5 and BOSS_CB_R - BOSS_BORE_R >= 3.0, \
    "boss steps too small to read"
assert min(BOSS_X[i + 1] - BOSS_X[i] for i in range(len(BOSS_X) - 1)) \
    >= 2 * BOSS_R + 8.0, "bosses too close"

# z stack: monotone, and nothing leaves less than 1.5mm of steel
assert Z_FACE > Z_FIN > Z_BOSS_CB > Z_FLANGE > Z_BOSS_BORE > Z_BOLT > Z_TRENCH
assert Z_TOP - Z_FACE >= 0.5, "face skim below the stock cleanup allowance"
assert Z_BOLT >= 1.5 and Z_BOSS_BORE >= 1.5, "blind floor too thin"
assert abs((Z_FACE - Z_FIN) - round(6.0 * SCALE, 1)) <= 0.3, \
    "fin depth drifted off true scale"
assert abs(Z_FLANGE - round(11.0 * SCALE, 1)) <= 0.5, \
    "flange lip drifted off true scale"
assert Z_FACE - Z_FLANGE >= 5.0, "body does not stand proud enough to read"

# the height field must agree with the design at a few known probes
assert top_z(0, PART_Y) == Z_BOSS_BORE, "centre boss bore"
assert top_z(30, PART_Y) in (Z_FACE, Z_FIN), "mid-body"
assert top_z(0, PART_Y + COVER_W / 2 - 1.0) == Z_FLANGE, "flange lip"
assert top_z(0, PART_Y + COVER_W / 2 + 3.0) == 0.0, "outside the outline"
assert top_z(BOLT_X[0], PART_Y + BOLT_Y) == Z_BOLT, "bolt hole"


# ------------------------------------------------------------ feature tree
F = []


def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


def tool(name, z, ents, over=1.0):
    f(f"{name}_sk", "sketch", {"plane": "XY", "offset": z, "entities": ents})
    f(f"{name}_tl", "extrude", {"amount": round(Z_TOP - z + over, 3)},
      [f"{name}_sk"])
    return f"{name}_tl"


PREV = None


def cut(name, z, ents, over=1.0):
    global PREV
    t = tool(name + "_c", z, ents, over)
    f(name, "cut", {}, [PREV, t])
    PREV = name


# 1. the blank IS the cover footprint: waist + a lobe row per side, fused
f("waist_sk", "sketch", {"plane": "XY", "offset": 0, "entities":
  [rbox(0, PART_Y, COVER_L, WAIST, END_R)]})
f("waist", "extrude", {"amount": Z_TOP}, ["waist_sk"])
blank_ids = ["waist"]
for s, side in ((1, "top"), (-1, "bot")):
    f(f"lobes_{side}_sk", "sketch", {"plane": "XY", "offset": 0, "entities":
      [circ(bx, PART_Y + s * BOLT_Y, LOBE_R) for bx in BOLT_X]})
    f(f"lobes_{side}", "extrude", {"amount": Z_TOP}, [f"lobes_{side}_sk"])
    blank_ids.append(f"lobes_{side}")
f("blank", "fuse", {}, blank_ids)
PREV = "blank"

# 2. face skim — a plain stock-sized rectangle takes 0.6 off everything
STOCK_RECT = rbox(0, 0, STOCK_L + 10, STOCK_W + 10, 0.001)
cut("face_skim", Z_FACE, [STOCK_RECT])

# 3. bolt flange: drop everything OUTSIDE the body down to the lip. The tool
#    is (stock slab minus body) — outside the cover outline there is already
#    no material, so this cuts exactly the flange ring and nothing else.
f("flange_slab_sk", "sketch", {"plane": "XY", "offset": Z_FLANGE,
                               "entities": [STOCK_RECT]})
f("flange_slab", "extrude", {"amount": round(Z_TOP - Z_FLANGE + 1, 3)},
  ["flange_slab_sk"])
f("body_blank_sk", "sketch", {"plane": "XY", "offset": Z_FLANGE, "entities":
  [rbox(0, PART_Y, BODY_L, BODY_W, BODY_R)]})
f("body_blank", "extrude", {"amount": round(Z_TOP - Z_FLANGE + 1, 3)},
  ["body_blank_sk"])
f("flange_ring", "cut", {}, ["flange_slab", "body_blank"])
f("bolt_flange", "cut", {}, [PREV, "flange_ring"])
PREV = "bolt_flange"

# 4. fin slots (8 per sketch)
fin_ents = [rrect(a, b, PART_Y + y - h, PART_Y + y + h, FIN_R)
            for a, b, y, h in FINS]
fin_tools = [tool(f"fins_{i // 8}", Z_FIN, fin_ents[i:i + 8])
             for i in range(0, len(fin_ents), 8)]
f("fins", "cut", {}, [PREV] + fin_tools)
PREV = "fins"

# 5. cam bosses: D16 counterbore then D8 bore
cut("boss_counterbores", Z_BOSS_CB,
    [circ(bx, PART_Y, BOSS_CB_R) for bx in BOSS_X])
cut("boss_bores", Z_BOSS_BORE,
    [circ(bx, PART_Y, BOSS_BORE_R) for bx in BOSS_X])

# 6. blind bolt holes, one sketch per flange side (7 each)
bolt_ids = []
for s, side in ((1, "top"), (-1, "bot")):
    bolt_ids.append(tool(f"bolt_holes_{side}", Z_BOLT,
                         [circ(bx, PART_Y + s * BOLT_Y, BOLT_R)
                          for bx in BOLT_X]))
f("cam_cover_upper", "cut", {}, [PREV] + bolt_ids)

for _feat in F:
    if _feat["op"] == "sketch":
        _n = len(_feat["params"]["entities"])
        assert _n <= 10, f"sketch {_feat['id']} has {_n} entities (max 10)"

tree = {"name": "cam-cover-upper", "features": F,
        "spec": {"n_solids": 1, "size": [COVER_L, COVER_W, Z_FACE],
                 "tol": 0.3}}
open(ROOT + r"\designs\cam-cover-upper-tree.json", "w").write(json.dumps(tree))


# ----------------------------------------------------------------- preview
S = 5.0
SEC_H, SEC_Y, SEC_Z = 54.0, 2.4, 4.0   # section band: height, x and z blowup
W = int(STOCK_L * S)
HT = int((STOCK_W + SEC_H) * S)
img = Image.new("RGB", (W, HT), (12, 15, 20))
dr = ImageDraw.Draw(img)
Y0 = STOCK_W * S                  # top of the section band, in px


def px(p):
    return (W / 2 + p[0] * S, STOCK_W * S / 2 - p[1] * S)


def col(z):
    t = max(0.0, min(1.0, (z - 1.0) / (Z_FACE - 1.0)))
    lo_, hi_ = (36, 40, 48), (200, 204, 210)
    return tuple(int(lo_[i] + (hi_[i] - lo_[i]) * (t ** 0.8)) for i in range(3))


def sample_rr(cx, cy, w, h, r, n=10):
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


# stock, then the part top-down
dr.rectangle([px((-STOCK_L / 2, STOCK_W / 2)),
              px((STOCK_L / 2, -STOCK_W / 2))], fill=(26, 30, 36))
box(0, PART_Y, COVER_L, WAIST, END_R, Z_FLANGE)
for bx in BOLT_X:
    for s in (1, -1):
        disc(bx, PART_Y + s * BOLT_Y, LOBE_R, Z_FLANGE)
box(0, PART_Y, BODY_L, BODY_W, BODY_R, Z_FACE)
for a, b, y, h in FINS:
    box((a + b) / 2, PART_Y + y, b - a, 2 * h, FIN_R, Z_FIN)
for bx in BOSS_X:
    disc(bx, PART_Y, BOSS_R, Z_FACE)
    disc(bx, PART_Y, BOSS_CB_R, Z_BOSS_CB)
    disc(bx, PART_Y, BOSS_BORE_R, Z_BOSS_BORE)
for bx in BOLT_X:
    for s in (1, -1):
        disc(bx, PART_Y + s * BOLT_Y, BOLT_R, Z_BOLT)

# section line + the offcut strip
SEC_X = -30.0
dr.line([px((SEC_X, PART_Y - COVER_W / 2 - 6)),
         px((SEC_X, PART_Y + COVER_W / 2 + 6))], fill=(226, 96, 72), width=2)
oy = PART_Y + COVER_W / 2 + PART_GAP
dr.rectangle([px((-COVER_L / 2, oy + OFFCUT_W)), px((COVER_L / 2, oy))],
             outline=(96, 104, 116), width=2)

# --- section A-A: sample the height field across the width at SEC_X
dr.rectangle([(0, Y0), (W, HT)], fill=(18, 22, 28))
base = HT - 16
prof = []
n = 900
for i in range(n + 1):
    y = PART_Y - COVER_W / 2 - 4 + (COVER_W + 8) * i / n
    prof.append((y, top_z(SEC_X, y)))


def spx(y, z):
    return (W / 2 + (y - PART_Y) * S * SEC_Y, base - z * S * SEC_Z)


pts = [spx(prof[0][0], 0)]
for y, z in prof:
    pts.append(spx(y, z))
pts.append(spx(prof[-1][0], 0))
dr.polygon(pts, fill=(150, 156, 166))
dr.line([spx(prof[0][0], 0), spx(prof[-1][0], 0)], fill=(96, 104, 116),
        width=2)

try:
    FN = ImageFont.truetype("arial.ttf", 14)
    FS = ImageFont.truetype("arial.ttf", 12)
except OSError:
    FN = FS = ImageFont.load_default()
dr.text((14, Y0 + 12), f"SECTION A-A   across the width at x={SEC_X:.0f}"
        f"   (width x{SEC_Y:.1f}, height x{SEC_Z:.1f})", font=FN,
        fill=(226, 96, 72))
dr.text(px((SEC_X, PART_Y + COVER_W / 2 + 9)), "A", font=FN,
        fill=(226, 96, 72), anchor="mm")
dr.text(px((SEC_X, PART_Y - COVER_W / 2 - 9)), "A", font=FN,
        fill=(226, 96, 72), anchor="mm")
dr.text(px((0, oy + OFFCUT_W - 8)),
        f"OFFCUT  {COVER_L:.0f} x {OFFCUT_W:.0f} - keep for the lower cover",
        font=FS, fill=(150, 158, 170), anchor="mm")
for bx, lab in ((BOSS_X[0], "CAM BOSS"), (BOSS_X[2], "CAM BOSS")):
    dr.text(px((bx, PART_Y - BOSS_R - 5.5)), lab, font=FS,
            fill=(236, 239, 243), anchor="mm")
dr.text(px((0, oy + 7)),
        f"BOLT FLANGE LIP {FW} WIDE, TOP z{Z_FLANGE}  -  {2*N_BOLT} BLIND"
        f" D{2*BOLT_R} HOLES", font=FS, fill=(198, 204, 214), anchor="mm")

out = ROOT + r"\designs\cam-cover-upper-preview.png"
img.save(out)

# ------------------------------------------------------------------- report
print(f"preview: {out}")
print(f"part {COVER_L} x {COVER_W} x {Z_FACE} from {STOCK_L}x{STOCK_W}x"
      f"{STOCK_T}; parting trench {PART_GAP} wide to z{Z_TRENCH}")
print(f"scale {SCALE:.4f} = 1:{1/SCALE:.2f} in plan | Z 1:"
      f"{REAL_H/Z_FACE:.2f} -> {(REAL_H/Z_FACE)*SCALE:.2f}x flatter than"
      f" true (the pair plaque was 4.4x)")
print(f"offcut left: {COVER_L:.0f} x {OFFCUT_W} at +Y")
print(f"flange lip {FW} wide, top z{Z_FLANGE}; body {BODY_L} x {BODY_W}"
      f" standing {Z_FACE - Z_FLANGE:.1f} proud")
print(f"fins: {FIN_N} slots {FIN_W} wide / rib {FIN_PITCH-FIN_W:.1f} /"
      f" pitch {FIN_PITCH} (true scale {6.0*SCALE:.1f} deep ->"
      f" {Z_FACE-Z_FIN}) -> {len(FINS)} segments")
print(f"bosses: {len(BOSS_X)} x D{2*BOSS_R} at x={BOSS_X},"
      f" cb D{2*BOSS_CB_R} z{Z_BOSS_CB}, bore D{2*BOSS_BORE_R} z{Z_BOSS_BORE}")
print(f"bolts: {2*N_BOLT} blind D{2*BOLT_R} to z{Z_BOLT}")
print(f"features: {len(F)} | through features: 0 (outline is a trench)")


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
