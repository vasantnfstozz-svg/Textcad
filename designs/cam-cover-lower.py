"""cam-cover-lower v1 — the CAST RIBBED LOWER COVER as its own part, the
matching half of designs/cam-cover-upper.py (df159cb). Same stock, same
1:2.19 plan scale, same lobed silhouette and same 5.5-wide flange lip, so
the two parts sit side by side as a true pair of banks.

  It needs its OWN blank: at this scale the cover is 66.2 wide and the
  upper cover's leftover strip is only 43.8. Shrinking it to fit that strip
  would have made a mismatched set, which is the one thing a pair must not
  be.

WHAT MAKES IT THE LOWER COVER, not a re-skin of the upper
  The upper is billet: a fin field milled into a solid deck. This one is a
  casting: a waffle of RIB CROWNS at the top face with 14 bays sunk between
  them, and the three deep cam-lobe clearance scallops that break the rib
  pattern where the cam journals run. Ribs 2.5 wide (true scale of a ~5.5mm
  cast rib) standing 5.4 tall.

  Scallops sit at x = 0, +-60 — the SAME x as the upper cover's three cam
  bosses, because on the engine those are the same three journals.

Z STACK  (face skimmed 0.6 off the raw stock)
  11.4  rib crowns = the top face of the casting        (highest)
   6.0  bay floors (5.4 deep)
   5.0  bolt flange lip top -> crowns stand 6.4 proud
   4.0  cam-lobe scallop floors (7.4 deep, 4mm of steel left)
   2.0  bolt hole floors (D4.6 blind)
   1.5  outline trench floor (NOT modelled - machining note)

VACUUM  every cut is a blind pocket; the outline is a ~6mm CONTOUR TRENCH to
        z1.5 with a 1.5mm skin - a trench, not a clear-out, so the leftover
        strip survives as stock.

TOOLING D6 for the bays (25.4 x 14.5, r3 corners) and the wide flange
        stretches, D4 in the 5.5mm flange straights, D3 to finish, D2 only
        if you want to sharpen the rib roots. Scallops are 7.4 deep - ramp
        in, do not plunge.

Run:  python designs/cam-cover-lower.py           -> preview + checks
      python designs/cam-cover-lower.py --build   -> STEP + tcad.json
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
PART_GAP = 5.0

# --------------------------------------------------------------- z levels
Z_TOP = 12.0
Z_FACE = 11.4
Z_BAY = 6.0
Z_FLANGE = 5.0
Z_SCAL = 4.0
Z_BOLT = 2.0
Z_TRENCH = 1.5

# ------------------------------- outline: IDENTICAL to cam-cover-upper.py
REAL_L, REAL_W, REAL_H = 460.0, 145.0, 55.0
COVER_L = STOCK_L - 2 * PART_GAP            # 210.0
SCALE = COVER_L / REAL_L                    # 0.4565
COVER_W = round(REAL_W * SCALE, 1)          # 66.2
LOBE_R = round(16.25 * SCALE, 2)            # 7.42
LOBE_OUT = round(3.15 * SCALE, 2)           # 1.44
WAIST = round(COVER_W - 2 * (LOBE_R + LOBE_OUT), 2)
END_R = 11.5
N_BOLT = 7
BOLT_X0 = 84.0
BOLT_R = 2.3
FW = round(12.0 * SCALE, 1)                 # 5.5
BODY_L = round(COVER_L - 2 * FW, 1)         # 199.0
BODY_W = round(WAIST - 2 * FW, 1)           # 37.5
BODY_R = END_R - FW

# ------------------------------------------------- cast interior (the waffle)
RAIL = 3.0                                  # solid rail inside the body edge
RIB = 2.5                                   # true scale of a ~5.5mm cast rib
BAY_COLS, BAY_ROWS, BAY_R = 7, 2, 3.0
INT_L = round(BODY_L - 2 * RAIL, 1)         # 193.0
INT_W = round(BODY_W - 2 * RAIL, 1)         # 31.5
BAY_W = round((INT_L - (BAY_COLS - 1) * RIB) / BAY_COLS, 2)
BAY_H = round((INT_W - (BAY_ROWS - 1) * RIB) / BAY_ROWS, 2)
SCAL_X = (-60.0, 0.0, 60.0)                 # same journals as the upper cover
SCAL_R, SCAL_DX = 9.0, 4.5                  # two-circle kidney, 27 x 18

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


def circ(cx, cy, r, mode="add"):
    return {"kind": "circle", "r": round(r, 3), "x": round(cx, 3),
            "y": round(cy, 3), "mode": mode}


# --------------------------------------------------------------- geometry
BOLT_X = [round(-BOLT_X0 + 2 * BOLT_X0 * i / (N_BOLT - 1), 3)
          for i in range(N_BOLT)]
BOLT_Y = round(WAIST / 2 + LOBE_OUT, 3)
BAY_XS = [round(-INT_L / 2 + BAY_W / 2 + k * (BAY_W + RIB), 3)
          for k in range(BAY_COLS)]
BAY_YS = [round((r - (BAY_ROWS - 1) / 2) * (BAY_H + RIB), 3)
          for r in range(BAY_ROWS)]


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
    """Finished height at (x, y); 0 = air. Drives both section views and is
    probed by the gates, so the drawing and the cut order cannot disagree."""
    if not in_cover(x, y):
        return 0.0
    for bx in BOLT_X:
        for s in (1, -1):
            if math.hypot(x - bx, y - (PART_Y + s * BOLT_Y)) <= BOLT_R:
                return Z_BOLT
    if _sdf_rr(x, y, 0, PART_Y, BODY_L, BODY_W, BODY_R) > 0:
        return Z_FLANGE
    for sx in SCAL_X:                                   # deepest first
        for d_ in (-SCAL_DX, SCAL_DX):
            if math.hypot(x - (sx + d_), y - PART_Y) <= SCAL_R:
                return Z_SCAL
    for bx in BAY_XS:
        for by in BAY_YS:
            if _sdf_rr(x, y, bx, PART_Y + by, BAY_W, BAY_H, BAY_R) <= 0:
                return Z_BAY
    return Z_FACE


# ------------------------------------------------------------ sanity gates
# the pair contract: identical outline and flange to cam-cover-upper.py
assert COVER_L == 210.0 and COVER_W == 66.2, "outline drifted off the pair"
assert FW == 5.5 and Z_FLANGE == 5.0, "flange drifted off the pair"
assert SCAL_X == (-60.0, 0.0, 60.0), "scallops must share the upper's journals"

assert COVER_L + 2 * PART_GAP <= STOCK_L, "no parting gap in X"
assert PART_Y + COVER_W / 2 + PART_GAP <= STOCK_W / 2, "off the stock"
assert abs(COVER_W / REAL_W - SCALE) < 0.002, "width is not true proportion"
assert BOLT_X0 + LOBE_R <= COVER_L / 2 - END_R, "outer lobe hits the end arc"
assert LOBE_R - BOLT_R >= 4.0, "bolt hole wall too thin"

# the waffle: real bays, real ribs, everything inside the body rail
assert BAY_W >= 10.0 and BAY_H >= 10.0, f"bays {BAY_W}x{BAY_H} too small"
assert RIB >= TOOL_MIN, "ribs thinner than the smallest cutter"
assert BAY_R * 2 <= min(BAY_W, BAY_H), "bay corner radius too big"
assert RAIL >= 2.5, "no rail left between the bays and the body wall"
assert abs(BAY_COLS * BAY_W + (BAY_COLS - 1) * RIB - INT_L) < 0.05, "col math"
assert abs(BAY_ROWS * BAY_H + (BAY_ROWS - 1) * RIB - INT_W) < 0.05, "row math"
for bx in BAY_XS:
    assert abs(bx) + BAY_W / 2 <= INT_L / 2 + 0.01, f"bay {bx} off the interior"

# scallops: inside the interior, and they are meant to BREAK the rib grid
for sx in SCAL_X:
    assert abs(sx) + SCAL_DX + SCAL_R <= INT_L / 2 - 2.0, "scallop off the end"
assert 2 * SCAL_R <= INT_W - 4.0, "scallop wider than the interior"
assert min(SCAL_X[i + 1] - SCAL_X[i] for i in range(len(SCAL_X) - 1)) \
    >= 2 * (SCAL_R + SCAL_DX) + 6.0, "scallops merge into a trough"

# z stack: monotone, nothing leaves less than 1.5mm, ribs stand proud
assert Z_FACE > Z_BAY > Z_FLANGE > Z_SCAL > Z_BOLT > Z_TRENCH
assert Z_TOP - Z_FACE >= 0.5, "face skim below the stock cleanup allowance"
assert Z_SCAL >= 1.5 and Z_BOLT >= 1.5, "blind floor too thin"
assert Z_FACE - Z_BAY >= 4.0, "bays too shallow to read as a casting"
assert Z_FACE - Z_FLANGE >= 5.0, "crowns do not stand proud enough"
assert (Z_FACE - Z_BAY) / RIB <= 3.0, "rib too slender for its height"

# probes: the height field must agree with the intent
assert top_z(0, PART_Y) == Z_SCAL, "centre scallop"
assert top_z(BAY_XS[2], PART_Y + BAY_YS[0]) == Z_BAY, "a bay floor"
assert top_z(BAY_XS[2], PART_Y) == Z_FACE, "middle rib crown"
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


# 1. blank = the cover footprint: waist + a lobe row per side, fused
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

STOCK_RECT = rbox(0, 0, STOCK_L + 10, STOCK_W + 10, 0.001)

# 2. face skim
cut("face_skim", Z_FACE, [STOCK_RECT])

# 3. bolt flange lip: drop everything outside the body to z5.0
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

# 4. the waffle: 14 bays sunk between the rib crowns (7 per sketch)
bays = [rbox(bx, PART_Y + by, BAY_W, BAY_H, BAY_R)
        for by in BAY_YS for bx in BAY_XS]
bay_tools = [tool(f"cast_bays_{i // 7}", Z_BAY, bays[i:i + 7])
             for i in range(0, len(bays), 7)]
f("cast_bays", "cut", {}, [PREV] + bay_tools)
PREV = "cast_bays"

# 5. cam-lobe clearance scallops, deeper than the bays
cut("cam_scallops", Z_SCAL,
    [circ(sx + d_, PART_Y, SCAL_R) for sx in SCAL_X
     for d_ in (-SCAL_DX, SCAL_DX)])

# 6. blind bolt holes, one sketch per flange side
bolt_ids = [tool(f"bolt_holes_{side}", Z_BOLT,
                 [circ(bx, PART_Y + s * BOLT_Y, BOLT_R) for bx in BOLT_X])
            for s, side in ((1, "top"), (-1, "bot"))]
f("cam_cover_lower", "cut", {}, [PREV] + bolt_ids)

for _feat in F:
    if _feat["op"] == "sketch":
        _n = len(_feat["params"]["entities"])
        assert _n <= 10, f"sketch {_feat['id']} has {_n} entities (max 10)"

tree = {"name": "cam-cover-lower", "features": F,
        "spec": {"n_solids": 1, "size": [COVER_L, COVER_W, Z_FACE],
                 "tol": 0.3}}
open(ROOT + r"\designs\cam-cover-lower-tree.json", "w").write(json.dumps(tree))


# ----------------------------------------------------------------- preview
S = 5.0
SEC_H, SEC_Y, SEC_Z = 54.0, 2.4, 4.0        # transverse band
LON_H, LON_Z = 42.0, 2.6                    # longitudinal band
W = int(STOCK_L * S)
HT = int((STOCK_W + SEC_H + LON_H) * S)
img = Image.new("RGB", (W, HT), (12, 15, 20))
dr = ImageDraw.Draw(img)
Y0 = STOCK_W * S
Y1 = (STOCK_W + SEC_H) * S


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


dr.rectangle([px((-STOCK_L / 2, STOCK_W / 2)),
              px((STOCK_L / 2, -STOCK_W / 2))], fill=(26, 30, 36))
box(0, PART_Y, COVER_L, WAIST, END_R, Z_FLANGE)
for bx in BOLT_X:
    for s in (1, -1):
        disc(bx, PART_Y + s * BOLT_Y, LOBE_R, Z_FLANGE)
box(0, PART_Y, BODY_L, BODY_W, BODY_R, Z_FACE)
for by in BAY_YS:
    for bx in BAY_XS:
        box(bx, PART_Y + by, BAY_W, BAY_H, BAY_R, Z_BAY)
for sx in SCAL_X:
    for d_ in (-SCAL_DX, SCAL_DX):
        disc(sx + d_, PART_Y, SCAL_R, Z_SCAL)
for bx in BOLT_X:
    for s in (1, -1):
        disc(bx, PART_Y + s * BOLT_Y, BOLT_R, Z_BOLT)

SEC_X = BAY_XS[2]   # a bay column the scallops do not reach
RED = (226, 96, 72)
dr.line([px((SEC_X, PART_Y - COVER_W / 2 - 7)),
         px((SEC_X, PART_Y + COVER_W / 2 + 7))], fill=RED, width=2)
dr.line([px((-COVER_L / 2 - 6, PART_Y)), px((COVER_L / 2 + 6, PART_Y))],
        fill=(120, 170, 226), width=2)
oy = PART_Y + COVER_W / 2 + PART_GAP
dr.rectangle([px((-COVER_L / 2, oy + OFFCUT_W)), px((COVER_L / 2, oy))],
             outline=(96, 104, 116), width=2)


def section(band_top, band_h, samples, xscale, zscale, fill):
    base = band_top + band_h - 14
    dr.rectangle([(0, band_top), (W, band_top + band_h)], fill=(18, 22, 28))

    def spx(u, z):
        return (W / 2 + u * S * xscale, base - z * S * zscale)
    pts = [spx(samples[0][0], 0)]
    pts += [spx(u, z) for u, z in samples]
    pts.append(spx(samples[-1][0], 0))
    dr.polygon(pts, fill=fill)
    dr.line([spx(samples[0][0], 0), spx(samples[-1][0], 0)],
            fill=(96, 104, 116), width=2)


n = 900
trans = [(PART_Y - COVER_W / 2 - 4 + (COVER_W + 8) * i / n, 0) for i in
         range(n + 1)]
trans = [(u - PART_Y, top_z(SEC_X, u)) for u, _ in trans]
section(Y0, SEC_H * S, trans, SEC_Y, SEC_Z, (150, 156, 166))

lon = [(-COVER_L / 2 - 4 + (COVER_L + 8) * i / n) for i in range(n + 1)]
lon = [(u, top_z(u, PART_Y)) for u in lon]
section(Y1, LON_H * S, lon, 1.0, LON_Z, (136, 158, 186))

try:
    FN = ImageFont.truetype("arial.ttf", 14)
    FS = ImageFont.truetype("arial.ttf", 12)
except OSError:
    FN = FS = ImageFont.load_default()
dr.text((14, Y0 + 12), f"SECTION A-A   across the width at x={SEC_X:.1f}"
        f"   (width x{SEC_Y:.1f}, height x{SEC_Z:.1f})", font=FN, fill=RED)
dr.text((14, Y1 + 12), "SECTION B-B   along the centreline   (length x1.0,"
        f" height x{LON_Z:.1f})   the three cam-lobe scallops",
        font=FN, fill=(120, 170, 226))
for s in (1, -1):
    dr.text(px((SEC_X, PART_Y + s * (COVER_W / 2 + 10))), "A", font=FN,
            fill=RED, anchor="mm")
dr.text(px((-COVER_L / 2 - 12, PART_Y)), "B", font=FN,
        fill=(120, 170, 226), anchor="mm")
dr.text(px((COVER_L / 2 + 12, PART_Y)), "B", font=FN,
        fill=(120, 170, 226), anchor="mm")
dr.text(px((0, oy + OFFCUT_W - 8)),
        f"OFFCUT  {COVER_L:.0f} x {OFFCUT_W:.0f}", font=FS,
        fill=(150, 158, 170), anchor="mm")
dr.text(px((0, oy + 7)), f"{BAY_ROWS}x{BAY_COLS} CAST BAYS"
        f" {BAY_W:.1f} x {BAY_H:.1f}, RIBS {RIB} WIDE x"
        f" {Z_FACE - Z_BAY:.1f} TALL   -   3 CAM-LOBE SCALLOPS"
        f" {Z_FACE - Z_SCAL:.1f} DEEP", font=FS, fill=(198, 204, 214),
        anchor="mm")

out = ROOT + r"\designs\cam-cover-lower-preview.png"
img.save(out)

# ------------------------------------------------------------------- report
print(f"preview: {out}")
print(f"part {COVER_L} x {COVER_W} x {Z_FACE} from {STOCK_L}x{STOCK_W}x"
      f"{STOCK_T}; own blank (the upper's {OFFCUT_W} strip is too narrow)")
print(f"scale {SCALE:.4f} = 1:{1/SCALE:.2f} in plan - SAME as cam-cover-upper")
print(f"flange lip {FW} wide, top z{Z_FLANGE}; rib crowns z{Z_FACE} standing"
      f" {Z_FACE - Z_FLANGE:.1f} proud")
print(f"waffle: {BAY_ROWS}x{BAY_COLS} = {BAY_ROWS*BAY_COLS} bays"
      f" {BAY_W} x {BAY_H} r{BAY_R}, floor z{Z_BAY} ({Z_FACE-Z_BAY:.1f} deep);"
      f" ribs {RIB} wide x {Z_FACE-Z_BAY:.1f} tall")
print(f"scallops: {len(SCAL_X)} kidneys {2*(SCAL_R+SCAL_DX)} x {2*SCAL_R} at"
      f" x={SCAL_X}, floor z{Z_SCAL} ({Z_FACE-Z_SCAL:.1f} deep)")
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
        doc.to_step(ROOT + r"\designs\cam-cover-lower.step")
        doc.save(ROOT + r"\designs\cam-cover-lower.tcad.json")
        print("measured:", json.dumps(rep.get("measured", {}))[:420])
        print("wrote cam-cover-lower.step + .tcad.json")
