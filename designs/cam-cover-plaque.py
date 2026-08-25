"""cam-cover-plaque v1 — a matched PAIR of flat-six camshaft covers rendered
as machined relief on one 220 x 120 x 12 steel plate (the Porsche-style
billet upper + cast lower from the user's reference photos).

WHY A RELIEF AND NOT TWO LOOSE COVERS
  A real cover is ~460 x 145 x 55 and HOLLOW. Plan view scales to the stock
  fine (0.32 => 147 x 46 each, two of them staggered fill the plate), but
  55mm of height will never fit 12mm of stock and the hollow underside would
  need a second setup that cannot vacuum-seal against the finned face. So:
  plan view at true 1:3.1, height squashed ~1:14, solid back, one top
  setup, every cut a blind pocket. Nothing is ever cut through -> the vacuum
  never sees a leak path.

  Real dims are approximate (from photos of billet flat-six covers, ~460 x
  145 x 55). Say the word and I will re-derive the layout from a measured
  drawing; only SCALE and COVER_L/W change.

LAYOUT   two covers staggered +-24mm along X, mirrored about the plate axis,
         exactly how the pair sits on the two banks. The stagger leaves two
         ~48 x 46 field patches for the raised captions.

Z STACK (face is skimmed 0.6 off the raw stock, everything hangs off that)
  11.4  skimmed face = border rim, fin deck tops, boss tops   (highest)
  10.8  cover gasket flange, cast ribs, rim pinstripe groove floor
   9.8  bolt-boss counterbore floors (D6)
   9.4  fin valley floors (fins 2.0 deep)
   9.2  raised caption tops (fused, 1.8 proud of the field)
   7.4  plate field  -> covers stand 4.0 proud
   6.8  cast bays, bolt pips (D3.2), boss counterbores (D11)
   5.6  cam-lobe scallops, boss through-look bores (D5.5)
  1.5   outline trench floor (NOT modelled - see machining note)

TOOLING   D6 rougher for the field/bays, D3 for pockets and corners (r>=1.6
          where it matters), D2 for the fin slots (2.4 wide => two passes at
          +-0.2, 4 step-downs of 0.5 in steel). The field is the long pole:
          ~9000mm2 x 4.0 deep of steel to hog.

MACHINING the model IS the finished plaque (214 x 114 x 11.4). Machine the
          outline as a trench to z1.5 leaving a ~1.5mm skin, part it off at
          the bench, deburr, oil (it rusts).

Run:  python designs/cam-cover-plaque.py           -> preview + checks
      python designs/cam-cover-plaque.py --build   -> STEP + tcad.json
"""
import io
import json
import math
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = r"c:\Users\VasanSeenivasan\Desktop\textcad"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ------------------------------------------------------------------- stock
STOCK_L, STOCK_W, STOCK_T = 220.0, 120.0, 12.0
PLATE_L, PLATE_W, PLATE_R = 214.0, 114.0, 10.0
BORDER = 6.0                      # rim width kept at the skimmed face
STRIPE_A, STRIPE_B = 2.0, 3.2     # rim pinstripe band offsets

# --------------------------------------------------------------- z levels
Z_TOP = 12.0
Z_FACE = 11.4                     # face skim (0.6 cleanup, per stock note)
Z_FLANGE = 10.8
Z_CAP = 9.2                       # raised caption tops
Z_BOLT_CB = 9.8
Z_FIN = 9.4
Z_FIELD = 7.4
Z_BAY = 6.8
Z_DEEP = 5.6
Z_TRENCH = 1.5                    # documented, not modelled

# ------------------------------------------------------- cover, real -> mm
REAL_L, REAL_W, REAL_H = 460.0, 145.0, 55.0
SCALE = 0.32
COVER_L = round(REAL_L * SCALE, 1)          # 147.2
COVER_W = round(REAL_W * SCALE, 1)          # 46.4
LOBE_R, LOBE_OUT = 5.2, 1.0                 # bolt-boss lobes on the flange
WAIST = round(COVER_W - 2 * (LOBE_R + LOBE_OUT), 1)     # 34.0
END_R = 8.0                                 # cover end corner radius
N_BOLT = 7                                  # per side (14 per cover)
BOLT_X0 = 62.0
BOLT_CB_R, BOLT_PIP_R = 3.0, 1.6

STAGGER = 24.0
ROW_GAP = 5.0
ROW_Y = round((COVER_W + ROW_GAP) / 2, 2)   # 25.7

# upper (billet, finned) --------------------------------------------------
DECK_L, DECK_W, DECK_R = COVER_L - 26.0, WAIST - 8.0, 6.0     # 121.2 x 26
FIN_N, FIN_W, FIN_PITCH, FIN_R = 6, 2.4, 3.6, 1.0
FIN_X = DECK_L / 2 - 2.5                    # 58.1
FIN_MIN_SEG = 9.0
BOSS_X = (-38.0, 0.0, 38.0)
BOSS_R, BOSS_CB_R, BOSS_BORE_R = 9.0, 5.5, 2.75
BOSS_CLR = 1.2                              # fin -> boss wall

# lower (cast, ribbed) ---------------------------------------------------
INT_L, INT_W = COVER_L - 24.0, WAIST - 7.0  # 123.2 x 27
RIB = 3.0
BAY_COLS, BAY_ROWS, BAY_R = 5, 2, 2.5
BAY_W = (INT_L - (BAY_COLS - 1) * RIB) / BAY_COLS       # 22.24
BAY_H = (INT_W - RIB) / BAY_ROWS                        # 12.0
SCAL_COLS = (0, 2, 4)                       # bay columns carrying a scallop
SCAL_R, SCAL_DX = 5.5, 3.5                  # two-circle kidney pocket

TOOL_MIN = 2.0                              # smallest end mill on hand


# ------------------------------------------------------- rounded-path core
def _corner_geo(verts, radii):
    """Per corner: tangent-in, arc-via, tangent-out, center, r (CCW convex)."""
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


def rrect(x0, x1, y0, y1, r, mode="add"):
    return outline_path([(x1, y0), (x1, y1), (x0, y1), (x0, y0)],
                        [r] * 4, mode)


def rbox(cx, cy, w, h, r, mode="add"):
    return rrect(cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2, r, mode)


def circ(cx, cy, r, mode="add"):
    return {"kind": "circle", "r": round(r, 3), "x": round(cx, 3),
            "y": round(cy, 3), "mode": mode}


def sample_rr(cx, cy, w, h, r, n=8):
    """Polyline of a rounded rect, for the preview."""
    pts = []
    for sx, sy, a0 in ((1, 1, 0.0), (-1, 1, math.pi / 2),
                       (-1, -1, math.pi), (1, -1, 3 * math.pi / 2)):
        ax, ay = sx * (w / 2 - r) + cx, sy * (h / 2 - r) + cy
        for k in range(n + 1):
            a = a0 + math.pi / 2 * k / n
            pts.append((ax + r * math.cos(a), ay + r * math.sin(a)))
    return pts


# --------------------------------------------------------- cover geometry
BOLT_X = [round(-BOLT_X0 + 2 * BOLT_X0 * i / (N_BOLT - 1), 3)
          for i in range(N_BOLT)]
BOLT_Y = WAIST / 2 + LOBE_OUT


def cover_profile():
    """Waist rect UNION 14 flange lobes — all `add`, they fuse into one face."""
    ents = [rbox(0, 0, COVER_L, WAIST, END_R)]
    for bx in BOLT_X:
        for s in (1, -1):
            ents.append(circ(bx, s * BOLT_Y, LOBE_R))
    return ents


def fin_segments():
    """Lengthwise fin slots, broken around the three deck bosses."""
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


def bay_centers():
    xs = [-INT_L / 2 + BAY_W / 2 + k * (BAY_W + RIB) for k in range(BAY_COLS)]
    ys = [(-1) ** r * (RIB / 2 + BAY_H / 2) for r in range(BAY_ROWS)]
    return xs, ys


FINS = fin_segments()
BAY_XS, BAY_YS = bay_centers()
SCAL_X = [BAY_XS[k] for k in SCAL_COLS]

UP = (STAGGER, ROW_Y)              # upper cover centre
LO = (-STAGGER, -ROW_Y)            # lower cover centre


def at(c, p):
    return (c[0] + p[0], c[1] + p[1])


# ------------------------------------------------------------ raised text
def text_block(lines, cx, cy, max_w, max_h, gap=0.30):
    """PIL -> imgtrace -> polygon entities, scaled to fit and centred."""
    import imgtrace
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\bahnschrift.ttf", 200)
    except OSError:
        font = ImageFont.truetype("arial.ttf", 200)
    pad, lead = 40, int(200 * (1 + gap))
    img = Image.new("L", (4200, lead * len(lines) + 2 * pad), 255)
    d = ImageDraw.Draw(img)
    widths = [d.textlength(s, font=font) for s in lines]
    x0 = pad
    for i, s in enumerate(lines):
        d.text((x0 + (max(widths) - widths[i]) / 2, pad + i * lead), s,
               font=font, fill=0)
    img = img.crop(ImageOps.invert(img).getbbox())
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    ents, info = imgtrace.image_to_entities(buf.getvalue(), height_mm=max_h,
                                            tol_mm=0.10)
    k = min(1.0, max_w / info["width_mm"])
    for e in ents:
        e["points"] = [[round(ex * k, 3), round(ey * k, 3)]
                       for ex, ey in e["points"]]
        e["x"] = round(e["x"] * k + cx, 3)
        e["y"] = round(e["y"] * k + cy, 3)
    return ents, (round(info["width_mm"] * k, 1),
                  round(info["height_mm"] * k, 1))


PATCH_A = (-(PLATE_L / 2 - BORDER) + 26.5, ROW_Y)     # left of upper cover
PATCH_B = ((PLATE_L / 2 - BORDER) - 26.5, -ROW_Y)     # right of lower cover
CAP_A = ["FLAT-SIX", "CAM COVER", "PAIR"]
CAP_B = ["RELIEF", "1:3.1", "STEEL"]

try:
    CAP_A_ENTS, CAP_A_WH = text_block(CAP_A, *PATCH_A, 40.0, 26.0)
    CAP_B_ENTS, CAP_B_WH = text_block(CAP_B, *PATCH_B, 40.0, 26.0)
    HAVE_TEXT = True
except Exception as exc:                       # pragma: no cover
    print("!! caption tracing unavailable:", exc)
    CAP_A_ENTS = CAP_B_ENTS = []
    CAP_A_WH = CAP_B_WH = (0, 0)
    HAVE_TEXT = False


# ------------------------------------------------------------ sanity gates
assert PLATE_L + 4 <= STOCK_L and PLATE_W + 4 <= STOCK_W, "outline needs a trench"
FX, FY = PLATE_L / 2 - BORDER, PLATE_W / 2 - BORDER     # field half-extents

# covers fit the field with >=2mm of field all round, and do not touch
for c in (UP, LO):
    assert abs(c[0]) + COVER_L / 2 <= FX - 2.0, f"cover overruns X at {c}"
    assert abs(c[1]) + COVER_W / 2 <= FY - 2.0, f"cover overruns Y at {c}"
assert 2 * ROW_Y - COVER_W >= 4.0, "rows too close"
assert WAIST + 2 * (LOBE_R + LOBE_OUT) == COVER_W, "lobe math"

# lobes stay on the straight part of the flange (they are half-bosses, not
# corner blobs) and their counterbores keep a wall to the lobe edge
assert BOLT_X0 <= COVER_L / 2 - END_R, "outer bolt lobe hits the end radius"
assert LOBE_R + LOBE_OUT - BOLT_CB_R >= 2.0, "bolt counterbore wall too thin"
assert BOLT_CB_R > BOLT_PIP_R + 1.0, "counterbore/pip not distinguishable"
assert min(BOLT_X[i + 1] - BOLT_X[i] for i in range(N_BOLT - 1)) \
    >= 2 * LOBE_R + 3.0, "lobes merge into a scallop strip"

# upper cover: deck inside the flange, fins inside the deck, bosses on deck
assert (WAIST - DECK_W) / 2 >= 3.5, "deck leaves no gasket flange"
fin_span = (FIN_N - 1) * FIN_PITCH + FIN_W
assert (DECK_W - fin_span) / 2 >= 2.0, f"fin field {fin_span} too wide for deck"
assert FIN_PITCH - FIN_W >= 1.2, "fin ribs thinner than 1.2mm"
assert FIN_W >= TOOL_MIN + 0.4, "fin slot narrower than the tool + 2 passes"
assert FIN_X + 2.0 <= DECK_L / 2 + 0.01, "fins run off the deck"
# every slot must clear each boss on BOTH sides, or the deck ends go bare
assert len(FINS) == FIN_N * (len(BOSS_X) + 1), (
    f"{len(FINS)} fin segments, want {FIN_N * (len(BOSS_X) + 1)}"
    " - bosses too far out for a full-length fin field")
for bx in BOSS_X:
    assert abs(bx) + BOSS_R + 2.0 <= DECK_L / 2, f"boss {bx} off the deck"
    assert BOSS_R + 2.0 <= DECK_W / 2 + 4.0, "boss wider than the deck"
assert BOSS_R - BOSS_CB_R >= 3.0, "boss wall too thin"
assert BOSS_CB_R - BOSS_BORE_R >= 2.5, "boss counterbore step too small"
assert min(BOSS_X[i + 1] - BOSS_X[i] for i in range(len(BOSS_X) - 1)) \
    >= 2 * BOSS_R + 6.0, "bosses too close"
assert FINS, "no fin segments survived the boss keep-outs"
assert min(b - a for a, b, _, _ in FINS) >= FIN_MIN_SEG - 1e-6

# lower cover: bays inside the flange, ribs real, scallops inside their bay
assert (WAIST - INT_W) / 2 >= 3.0, "cast interior leaves no flange"
assert BAY_W >= 8.0 and BAY_H >= 8.0, "bays too small to rough"
assert RIB >= 2.5, "cast ribs thinner than 2.5mm"
for sx in SCAL_X:
    assert 2 * SCAL_DX + 2 * SCAL_R <= BAY_W - 3.0, "scallop overruns its bay"
    assert abs(sx) + SCAL_DX + SCAL_R <= INT_L / 2 - 2.0, "scallop off the interior"
assert SCAL_R * 2 <= INT_W - 4.0, "scallop wider than the interior"

# floors: nothing thinner than 4mm of steel under any pocket
for z in (Z_FACE, Z_FLANGE, Z_BOLT_CB, Z_FIN, Z_FIELD, Z_BAY, Z_DEEP):
    assert z >= 4.0, f"floor {z} leaves <4mm of steel"
assert Z_TOP - Z_FACE >= 0.5, "face skim below the 0.5mm stock cleanup"
assert (Z_FACE > Z_FLANGE > Z_BOLT_CB > Z_FIN > Z_CAP > Z_FIELD
        > Z_BAY > Z_DEEP)
assert Z_CAP - Z_FIELD >= 1.5, "captions too shallow to read as raised"
assert Z_FACE - Z_FIELD >= 3.5, "relief too shallow to read"
assert Z_FIN + 2.0 <= Z_FACE + 0.01, "fins not 2.0 deep"

# captions stay in their field patch and clear of the covers and the rim
if HAVE_TEXT:
    for (px_, py_), (cw, ch), c in ((PATCH_A, CAP_A_WH, UP),
                                    (PATCH_B, CAP_B_WH, LO)):
        assert abs(px_) + cw / 2 <= FX - 3.0, "caption hits the rim"
        assert abs(py_) + ch / 2 <= FY - 3.0, "caption hits the rim"
        # the patch sits outboard of its cover's near end (mirrored pair,
        # so one signed expression covers both)
        gap = abs(px_) - (COVER_L / 2 - abs(c[0]))
        assert cw / 2 <= gap - 4.0, (
            f"caption {cw} wide leaves only {gap:.1f} to its cover")

# stripe band lives inside the border and is a real groove
assert STRIPE_B < BORDER and STRIPE_B - STRIPE_A >= 1.0, "pinstripe band"


# ------------------------------------------------------------ feature tree
F = []


def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


def tool(name, z, ents, over=1.0):
    """Sketch at z + extrude up past the top face = a blind-pocket cutter."""
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


PLATE = [(PLATE_L / 2, -PLATE_W / 2), (PLATE_L / 2, PLATE_W / 2),
         (-PLATE_L / 2, PLATE_W / 2), (-PLATE_L / 2, -PLATE_W / 2)]


def plate_outline():
    return outline_path(PLATE, [PLATE_R] * 4)


def cover_solid(tag, c, z, over=1.0):
    """One cover footprint as its own solid: the waist, then a row of flange
    lobes per side. Three sketches, not one — the history lint caps a sketch
    at 10 entities, and waist / lobe-row ARE the design elements."""
    amt = round(Z_TOP - z + over, 3)
    f(f"{tag}_waist_sk", "sketch", {"plane": "XY", "offset": z, "entities":
      [rbox(c[0], c[1], COVER_L, WAIST, END_R)]})
    f(f"{tag}_waist", "extrude", {"amount": amt}, [f"{tag}_waist_sk"])
    ids = [f"{tag}_waist"]
    for s, side in ((1, "top"), (-1, "bot")):
        f(f"{tag}_lobes_{side}_sk", "sketch", {"plane": "XY", "offset": z,
          "entities": [circ(*at(c, (bx, s * BOLT_Y)), LOBE_R)
                       for bx in BOLT_X]})
        f(f"{tag}_lobes_{side}", "extrude", {"amount": amt},
          [f"{tag}_lobes_{side}_sk"])
        ids.append(f"{tag}_lobes_{side}")
    f(tag, "fuse", {}, ids)
    return tag


def _abs_pts(e):
    return [(e["x"] + p[0], e["y"] + p[1]) for p in e["points"]]


def _area(pts):
    n = len(pts)
    return abs(sum(pts[i][0] * pts[(i + 1) % n][1]
                   - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2


def _inside(pt, poly):
    x, y = pt
    hit, n = False, len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def glyph_groups(ents):
    """Each outer contour with ITS OWN holes. imgtrace returns every contour
    area-sorted, so batching 10-at-a-time would strand a counter in a sketch
    that does not hold its letter — and that subtract would eat the plate."""
    adds = [e for e in ents if e["mode"] == "add"]
    groups = [[a] for a in adds]
    for s in (e for e in ents if e["mode"] == "subtract"):
        c = _abs_pts(s)
        ctr = (sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c))
        best = None
        for i, a in enumerate(adds):
            ap = _abs_pts(a)
            if _inside(ctr, ap):
                ar = _area(ap)
                if best is None or ar < best[1]:
                    best = (i, ar)
        assert best is not None, "traced hole with no parent contour"
        groups[best[0]].append(s)
    return groups


def pack(groups, cap=10):
    out, cur = [], []
    for g in groups:
        if cur and len(cur) + len(g) > cap:
            out.append(cur)
            cur = []
        cur.extend(g)
    return out + ([cur] if cur else [])


f("plate_sk", "sketch", {"plane": "XY", "offset": 0,
                         "entities": [plate_outline()]})
f("body", "extrude", {"amount": Z_TOP}, ["plate_sk"])
PREV = "body"

# 1. face skim - 0.6 cleanup off the raw stock top
cut("face_skim", Z_FACE, [plate_outline()])

# 2. field: everything inside the border EXCEPT the two cover footprints
UP_PAD = cover_solid("upper_cover_pad", UP, Z_FIELD)
LO_PAD = cover_solid("lower_cover_pad", LO, Z_FIELD)
f("field_blank_sk", "sketch", {"plane": "XY", "offset": Z_FIELD, "entities":
  [rbox(0, 0, 2 * FX, 2 * FY, PLATE_R - BORDER)]})
f("field_blank", "extrude", {"amount": round(Z_TOP - Z_FIELD + 1, 3)},
  ["field_blank_sk"])
f("field_tool", "cut", {}, ["field_blank", UP_PAD, LO_PAD])
f("field", "cut", {}, [PREV, "field_tool"])
PREV = "field"

# 3. gasket flanges: drop both cover tops 0.6. The cover pads already exist
#    (from Z_FIELD up), so intersect them with a slab that starts at the
#    flange level instead of re-sketching both footprints.
f("flange_slab_sk", "sketch", {"plane": "XY", "offset": Z_FLANGE,
                               "entities": [plate_outline()]})
f("flange_slab", "extrude", {"amount": round(Z_TOP - Z_FLANGE + 1, 3)},
  ["flange_slab_sk"])
f("upper_flange_pad", "intersect", {}, [UP_PAD, "flange_slab"])
f("deck_blank_sk", "sketch", {"plane": "XY", "offset": Z_FLANGE, "entities":
  [rbox(UP[0], UP[1], DECK_L, DECK_W, DECK_R)]})
f("deck_blank", "extrude", {"amount": round(Z_TOP - Z_FLANGE + 1, 3)},
  ["deck_blank_sk"])
f("upper_flange_ring", "cut", {}, ["upper_flange_pad", "deck_blank"])
f("upper_flange", "cut", {}, [PREV, "upper_flange_ring"])
PREV = "upper_flange"
f("lower_flange_pad", "intersect", {}, [LO_PAD, "flange_slab"])
f("lower_flange", "cut", {}, [PREV, "lower_flange_pad"])
PREV = "lower_flange"

# 4. fin slots on the billet deck (batched 8 per sketch)
fin_ents = [rrect(UP[0] + a, UP[0] + b, UP[1] + y - h, UP[1] + y + h, FIN_R)
            for a, b, y, h in FINS]
fin_tools = [tool(f"fins_{i // 8}", Z_FIN, fin_ents[i:i + 8])
             for i in range(0, len(fin_ents), 8)]
f("fins", "cut", {}, [PREV] + fin_tools)
PREV = "fins"

# 5. bolt bosses: D6 counterbore then D3.2 pip, both covers
cb, pip = [], []
for c in (UP, LO):
    for bx in BOLT_X:
        for s in (1, -1):
            p = at(c, (bx, s * BOLT_Y))
            cb.append(circ(p[0], p[1], BOLT_CB_R))
            pip.append(circ(p[0], p[1], BOLT_PIP_R))
for tag, z, ents in (("bolt_counterbores", Z_BOLT_CB, cb),
                     ("bolt_pips", Z_BAY, pip)):
    ids = [tool(f"{tag}_{i // 10}", z, ents[i:i + 10])
           for i in range(0, len(ents), 10)]
    f(tag, "cut", {}, [PREV] + ids)
    PREV = tag

# 6. cam bosses on the deck: D11 counterbore + D5.5 bore
cut("boss_counterbores", Z_BAY, [circ(*at(UP, (bx, 0)), BOSS_CB_R)
                                 for bx in BOSS_X])
cut("boss_bores", Z_DEEP, [circ(*at(UP, (bx, 0)), BOSS_BORE_R)
                           for bx in BOSS_X])

# 7. cast bays and the three cam-lobe scallops
bays = [rbox(*at(LO, (bx, by)), BAY_W, BAY_H, BAY_R)
        for by in BAY_YS for bx in BAY_XS]
bay_ids = [tool(f"cast_bays_{i // 10}", Z_BAY, bays[i:i + 10])
           for i in range(0, len(bays), 10)]
f("cast_bays", "cut", {}, [PREV] + bay_ids)
PREV = "cast_bays"
scal = []
for sx in SCAL_X:
    for d_ in (-SCAL_DX, SCAL_DX):
        scal.append(circ(*at(LO, (sx + d_, 0)), SCAL_R))
cut("cam_scallops", Z_DEEP, scal)

# 8. rim pinstripe groove
f("stripeA_sk", "sketch", {"plane": "XY", "offset": Z_FLANGE, "entities":
  [rbox(0, 0, PLATE_L - 2 * STRIPE_A, PLATE_W - 2 * STRIPE_A,
        PLATE_R - STRIPE_A)]})
f("stripeA", "extrude", {"amount": round(Z_TOP - Z_FLANGE + 1, 3)},
  ["stripeA_sk"])
f("stripeB_sk", "sketch", {"plane": "XY", "offset": Z_FLANGE - 0.1, "entities":
  [rbox(0, 0, PLATE_L - 2 * STRIPE_B, PLATE_W - 2 * STRIPE_B,
        PLATE_R - STRIPE_B)]})
f("stripeB", "extrude", {"amount": round(Z_TOP - Z_FLANGE + 1.2, 3)},
  ["stripeB_sk"])
f("stripe_band", "cut", {}, ["stripeA", "stripeB"])
f("pinstripe", "cut", {}, [PREV, "stripe_band"])
PREV = "pinstripe"

# 9. raised captions (0.2 embedded into the field floor, then fused)
if HAVE_TEXT:
    cap_ids = []
    for tag, ents in (("caption_left", CAP_A_ENTS),
                      ("caption_right", CAP_B_ENTS)):
        for i, batch in enumerate(pack(glyph_groups(ents))):
            f(f"{tag}_{i}_sk", "sketch", {"plane": "XY",
              "offset": Z_FIELD - 0.2, "entities": batch})
            f(f"{tag}_{i}", "extrude",
              {"amount": round(Z_CAP - Z_FIELD + 0.2, 3)}, [f"{tag}_{i}_sk"])
            cap_ids.append(f"{tag}_{i}")
    f("cam_cover_plaque", "fuse", {}, [PREV] + cap_ids)
else:
    f("cam_cover_plaque", "cut", {}, [PREV, "stripeB"])   # no-op tail

# the history lint is a hard gate — catch a fat sketch here, not at build
for _feat in F:
    if _feat["op"] == "sketch":
        _n = len(_feat["params"]["entities"])
        assert _n <= 10, f"sketch {_feat['id']} has {_n} entities (max 10)"

tree = {"name": "cam-cover-plaque", "features": F,
        "spec": {"n_solids": 1, "size": [PLATE_L, PLATE_W, Z_FACE],
                 "tol": 0.3}}
open(ROOT + r"\designs\cam-cover-plaque-tree.json", "w").write(
    json.dumps(tree))


# ----------------------------------------------------------------- preview
S = 5.0
W, HT = int(STOCK_L * S), int(STOCK_W * S)
img = Image.new("RGB", (W, HT), (14, 18, 24))
dr = ImageDraw.Draw(img)


def px(p):
    return (W / 2 + p[0] * S, HT / 2 - p[1] * S)


def col(z):
    """Monotone steel depth ramp: z6.4 dark -> z11.4 bright."""
    t = max(0.0, min(1.0, (z - 6.0) / (Z_FACE - 6.0)))
    lo_, hi_ = (34, 38, 46), (198, 202, 208)
    return tuple(int(lo_[i] + (hi_[i] - lo_[i]) * (t ** 0.85)) for i in range(3))


def poly(pts, z):
    dr.polygon([px(p) for p in pts], fill=col(z))


def disc(cx, cy, r, z):
    dr.ellipse([px((cx - r, cy + r)), px((cx + r, cy - r))], fill=col(z))


def box(cx, cy, w, h, r, z):
    poly(sample_rr(cx, cy, w, h, r), z)


# stock edge -> plate -> pinstripe -> field
dr.rectangle([px((-STOCK_L / 2, STOCK_W / 2)),
              px((STOCK_L / 2, -STOCK_W / 2))], fill=(24, 28, 34))
box(0, 0, PLATE_L, PLATE_W, PLATE_R, Z_FACE)
box(0, 0, PLATE_L - 2 * STRIPE_A, PLATE_W - 2 * STRIPE_A,
    PLATE_R - STRIPE_A, Z_FLANGE)
box(0, 0, PLATE_L - 2 * STRIPE_B, PLATE_W - 2 * STRIPE_B,
    PLATE_R - STRIPE_B, Z_FACE)
box(0, 0, 2 * FX, 2 * FY, PLATE_R - BORDER, Z_FIELD)


def draw_cover(c, upper):
    box(c[0], c[1], COVER_L, WAIST, END_R, Z_FLANGE)
    for bx in BOLT_X:
        for s in (1, -1):
            disc(*at(c, (bx, s * BOLT_Y)), LOBE_R, Z_FLANGE)
    if upper:
        box(*at(c, (0, 0)), DECK_L, DECK_W, DECK_R, Z_FACE)
        for a, b, y, h in FINS:
            box(c[0] + (a + b) / 2, c[1] + y, b - a, 2 * h, FIN_R, Z_FIN)
        for bx in BOSS_X:
            disc(*at(c, (bx, 0)), BOSS_R, Z_FACE)
            disc(*at(c, (bx, 0)), BOSS_CB_R, Z_BAY)
            disc(*at(c, (bx, 0)), BOSS_BORE_R, Z_DEEP)
    else:
        for by in BAY_YS:
            for bx in BAY_XS:
                box(*at(c, (bx, by)), BAY_W, BAY_H, BAY_R, Z_BAY)
        for sx in SCAL_X:
            for d_ in (-SCAL_DX, SCAL_DX):
                disc(*at(c, (sx + d_, 0)), SCAL_R, Z_DEEP)
    for bx in BOLT_X:
        for s in (1, -1):
            p = at(c, (bx, s * BOLT_Y))
            disc(p[0], p[1], BOLT_CB_R, Z_BOLT_CB)
            disc(p[0], p[1], BOLT_PIP_R, Z_BAY)


draw_cover(UP, True)
draw_cover(LO, False)

for ents in (CAP_A_ENTS, CAP_B_ENTS):
    for e in ents:
        dr.polygon([px((e["x"] + p[0], e["y"] + p[1])) for p in e["points"]],
                   fill=col(Z_CAP) if e["mode"] == "add" else col(Z_FIELD))

try:
    FN = ImageFont.truetype("arial.ttf", 13)
except OSError:
    FN = ImageFont.load_default()
for (lx, ly), s in (((UP[0], UP[1] + COVER_W / 2 + 3.4),
                     "FINNED BILLET UPPER COVER"),
                    ((LO[0], LO[1] - COVER_W / 2 - 3.4),
                     "CAST RIBBED LOWER COVER")):
    dr.text(px((lx, ly)), s, font=FN, fill=(236, 239, 243), anchor="mm")

out = ROOT + r"\designs\cam-cover-plaque-preview.png"
img.save(out)

# ------------------------------------------------------------------- report
print(f"preview: {out}")
print(f"plate {PLATE_L} x {PLATE_W} x {Z_FACE} from {STOCK_L}x{STOCK_W}x"
      f"{STOCK_T} (trench to z{Z_TRENCH}, ~1.5mm skin)")
print(f"cover {COVER_L} x {COVER_W} @ scale {SCALE} (1:{1/SCALE:.2f} in plan)"
      f" | height {REAL_H} -> {Z_FACE - Z_FIELD} of relief"
      f" -> Z squashed 1:{REAL_H/(Z_FACE-Z_FIELD):.0f})")
print(f"stagger +-{STAGGER} | rows y=+-{ROW_Y} | gap {2*ROW_Y - COVER_W}")
print(f"upper: deck {DECK_L}x{DECK_W}, {len(FINS)} fin segments from {FIN_N}"
      f" slots ({FIN_W} wide, rib {FIN_PITCH-FIN_W:.1f}, {Z_FACE-Z_FIN} deep),"
      f" {len(BOSS_X)} bosses D{2*BOSS_R}")
print(f"lower: {BAY_ROWS*BAY_COLS} bays {BAY_W:.2f}x{BAY_H:.1f} (rib {RIB}),"
      f" {len(SCAL_X)} cam scallops")
print(f"bolts: {2*N_BOLT} per cover, D{2*BOLT_CB_R} cb + D{2*BOLT_PIP_R} pip")
if HAVE_TEXT:
    print(f"captions: {'/'.join(CAP_A)} {CAP_A_WH} | {'/'.join(CAP_B)}"
          f" {CAP_B_WH}")
print(f"features: {len(F)} | deepest cut z{Z_DEEP} ({Z_TOP-Z_DEEP} from raw)")


# --------------------------------------------------------------------- build
if "--build" in sys.argv:
    import contextlib
    sys.path.insert(0, ROOT)
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
        doc.to_step(ROOT + r"\designs\cam-cover-plaque.step")
        doc.save(ROOT + r"\designs\cam-cover-plaque.tcad.json")
        print("measured:", json.dumps(rep.get("measured", {}))[:400])
        print("wrote cam-cover-plaque.step + .tcad.json")
