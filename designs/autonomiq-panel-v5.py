"""autonomiq panel v5 — REAL ziggurat + pyramid field.

v4's "ziggurat" had 0.3mm steps on a 10mm block — invisible. v5 uses the
WHOLE box: a stepped pyramid rising from a 4mm rim ledge to the lockup at
the 10mm summit, with two rows of TRUE sloped pyramids (lofted square
frusta, near-apex) standing on the terraces.

Stack (top-of-face z, mm):
  rim ledge 4.0 | tier1 6.0 | tier2 8.0 | podium 9.3 | lockup 10.0
  row-A pyramids on tier1: 6.0 -> 8.5   (base 8mm diamond, 1.6mm apex flat)
  row-B pyramids on tier2: 8.0 -> 9.8   (base 6.4mm diamond)
Mounting: 4x r2.1 through-holes moved OUT onto the low rim ledge so bolt
heads never touch the art. Scoops + stealth octagon unchanged from v4.

Run:  python designs/autonomiq-panel-v5.py           -> preview + tree json
      python designs/autonomiq-panel-v5.py --build   -> also STEP + tcad.json
"""
import json
import math
import re
import sys

from PIL import Image, ImageDraw

ROOT = r"c:\Users\VasanSeenivasan\Desktop\textcad"
SVG_FILE = ROOT + r"\designs\autonomIQ-Logo_cmyk.svg"
KEEP = set(range(0, 6)) | {29, 30, 31, 32, 33}   # word, Q, I pieces


# ----------------------------------------------------------- SVG helpers
def parse_d(d):
    tok = re.findall(r"[MmCcLlHhVvZz]|-?\d+\.?\d*(?:e-?\d+)?", d)
    subs, cur, pos, start = [], None, (0.0, 0.0), (0.0, 0.0)
    i = 0

    def num(k):
        return float(tok[k])
    while i < len(tok):
        t = tok[i]
        if t in "Mm":
            rel = t == "m"
            x, y = num(i + 1), num(i + 2)
            pos = (pos[0] + x, pos[1] + y) if rel else (x, y)
            start = pos
            cur = [pos]
            subs.append(cur)
            i += 3
            while i + 1 < len(tok) and re.match(r"-?\d", tok[i]):
                x, y = num(i), num(i + 1)
                pos = (pos[0] + x, pos[1] + y) if rel else (x, y)
                cur.append(pos)
                i += 2
        elif t in "Cc":
            rel = t == "c"
            i += 1
            while i + 5 < len(tok) and re.match(r"-?\d", tok[i]):
                if rel:
                    c1 = (pos[0] + num(i), pos[1] + num(i + 1))
                    c2 = (pos[0] + num(i + 2), pos[1] + num(i + 3))
                    p1 = (pos[0] + num(i + 4), pos[1] + num(i + 5))
                else:
                    c1 = (num(i), num(i + 1))
                    c2 = (num(i + 2), num(i + 3))
                    p1 = (num(i + 4), num(i + 5))
                p0 = pos
                for tt in (0.2, 0.4, 0.6, 0.8, 1.0):
                    x = ((1 - tt) ** 3 * p0[0] + 3 * (1 - tt) ** 2 * tt * c1[0]
                         + 3 * (1 - tt) * tt ** 2 * c2[0] + tt ** 3 * p1[0])
                    y = ((1 - tt) ** 3 * p0[1] + 3 * (1 - tt) ** 2 * tt * c1[1]
                         + 3 * (1 - tt) * tt ** 2 * c2[1] + tt ** 3 * p1[1])
                    cur.append((x, y))
                pos = p1
                i += 6
        elif t in "Ll":
            rel = t == "l"
            i += 1
            while i + 1 < len(tok) and re.match(r"-?\d", tok[i]):
                x, y = num(i), num(i + 1)
                pos = (pos[0] + x, pos[1] + y) if rel else (x, y)
                cur.append(pos)
                i += 2
        elif t in "Hh":
            rel = t == "h"
            i += 1
            while i < len(tok) and re.match(r"-?\d", tok[i]):
                x = num(i)
                pos = (pos[0] + x if rel else x, pos[1])
                cur.append(pos)
                i += 1
        elif t in "Vv":
            rel = t == "v"
            i += 1
            while i < len(tok) and re.match(r"-?\d", tok[i]):
                y = num(i)
                pos = (pos[0], pos[1] + y if rel else y)
                cur.append(pos)
                i += 1
        else:
            pos = start
            i += 1
    return subs


def point_in_poly(p, poly):
    x, y = p
    inside = False
    for i in range(len(poly)):
        x1, y1 = poly[i - 1]
        x2, y2 = poly[i]
        if (y1 > y) != (y2 > y):
            xt = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < xt:
                inside = not inside
    return inside


def _ccw(pts):
    a = sum((pts[i][0] - pts[i - 1][0]) * (pts[i][1] + pts[i - 1][1])
            for i in range(len(pts)))
    return pts if a < 0 else pts[::-1]


def _decimate(pts, min_d=0.25):
    out = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= min_d:
            out.append(p)
    if math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < min_d \
            and len(out) > 3:
        out.pop()
    return out


def load_lockup_grouped(target_width):
    ds = re.findall(r'[\s"]d="([^"]+)"', open(SVG_FILE, encoding="utf-8").read())
    groups = [parse_d(d) for idx, d in enumerate(ds) if idx in KEEP]
    allpts = [p for g in groups for s in g for p in s]
    xs = [p[0] for p in allpts]
    ys = [p[1] for p in allpts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = target_width / (x1 - x0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    grouped = []
    for g in groups:
        subs = [[((p[0] - cx) * s, (p[1] - cy) * s) for p in sub] for sub in g]
        flags = [any(j != i and point_in_poly(sub[0], subs[j])
                     for j in range(len(subs)))
                 for i, sub in enumerate(subs)]
        ordered = ([(sub, False) for sub, h in zip(subs, flags) if not h]
                   + [(sub, True) for sub, h in zip(subs, flags) if h])
        ents = []
        for sub, hole in ordered:
            pts = _decimate(_ccw(sub))
            ents.append({"kind": "polygon",
                         "points": [[round(p[0], 3), round(p[1], 3)] for p in pts],
                         "mode": "subtract" if hole else "add"})
        grouped.append(ents)
    return grouped, (y1 - y0) * s


def rounded_path_e(verts, r):
    n = len(verts)
    corners = []
    for i in range(n):
        v, p, q = verts[i], verts[i - 1], verts[(i + 1) % n]
        e_in = (v[0] - p[0], v[1] - p[1])
        e_out = (q[0] - v[0], q[1] - v[1])
        li, lo = math.hypot(*e_in), math.hypot(*e_out)
        ui, uo = (e_in[0] / li, e_in[1] / li), (e_out[0] / lo, e_out[1] / lo)
        ang = math.acos(max(-1, min(1, -(ui[0] * uo[0] + ui[1] * uo[1]))))
        t = r / math.tan(ang / 2)
        b = (uo[0] - ui[0], uo[1] - ui[1])
        lb = math.hypot(*b)
        b = (b[0] / lb, b[1] / lb)
        dd = r / math.sin(ang / 2)
        corners.append(((v[0] - ui[0] * t, v[1] - ui[1] * t),
                        (v[0] + b[0] * (dd - r), v[1] + b[1] * (dd - r)),
                        (v[0] + uo[0] * t, v[1] + uo[1] * t)))
    first = corners[0][2]

    def q3(v):
        return [round(v[0], 3), round(v[1], 3)]
    segs = []
    for i in list(range(1, n)) + [0]:
        a_in, via, a_out = corners[i]
        segs.append({"type": "line", "to": q3(a_in)})
        segs.append({"type": "arc", "via": q3(via),
                     "to": q3(first if i == 0 else a_out)})
    return {"kind": "path", "mode": "add", "start": q3(first), "segments": segs}


# ------------------------------------------------------------ layout
OCT = [(-104, 28), (-104, -28), (-78, -54), (78, -54),
       (104, -28), (104, 28), (78, 54), (-78, 54)]
INSET = [(-96, 24.686), (-96, -24.686), (-74.686, -46), (74.686, -46),
         (96, -24.686), (96, 24.686), (74.686, 46), (-74.686, 46)]
# INSET clipped to |y| <= 33 (chamfer corners recomputed on the 45deg edges)
TIER2 = [(96, -24.686), (96, 24.686), (87.686, 33), (-87.686, 33),
         (-96, 24.686), (-96, -24.686), (-87.686, -33), (87.686, -33)]
PODIUM = [(88, -20), (88, 20), (-88, 20), (-88, -20)]
SCOOPS = [(0, 108, 60), (0, -108, 60)]

Z_RIM, Z_T1, Z_T2, Z_POD, Z_TOP = 4.0, 6.0, 8.0, 9.3, 10.0

# pyramid rows: (row y, base half-diag, apex half-diag, z base, z top)
ROW_A = dict(y=39.5, hd=4.0, hd_top=0.8, z0=Z_T1, z1=8.5)
ROW_B = dict(y=26.5, hd=3.2, hd_top=0.7, z0=Z_T2, z1=9.8)
A_X0, A_PITCH, A_N = 27.0, 12.0, 5        # per quadrant, mirrored x and y
B_X0, B_PITCH, B_N = -84.0, 10.5, 17      # full row, mirrored y only
HOLES = [(sx * 88.5, sy * 38.0) for sx in (1, -1) for sy in (1, -1)]

lockup_groups, LH = load_lockup_grouped(150.0)


def diamond(cx, cy, hd):
    return [[round(cx + hd, 3), round(cy, 3)], [round(cx, 3), round(cy + hd, 3)],
            [round(cx - hd, 3), round(cy, 3)], [round(cx, 3), round(cy - hd, 3)]]


# ------------------------------------------------------------ tree
F = []


def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


f("outline_sketch", "sketch", {"plane": "XY", "offset": 0,
                               "entities": [rounded_path_e(OCT, 12)]})
f("base_extrude", "extrude", {"amount": Z_RIM}, ["outline_sketch"])

# tier1: whole inset region, kept 8mm back from the scoops (4mm ledge stays)
f("tier1_sketch", "sketch", {"plane": "XY", "offset": Z_RIM, "entities": [
    rounded_path_e(INSET, 8),
    {"kind": "circle", "r": 68, "x": 0, "y": 108, "mode": "subtract"},
    {"kind": "circle", "r": 68, "x": 0, "y": -108, "mode": "subtract"}]})
f("tier1_extrude", "extrude", {"amount": Z_T1 - Z_RIM}, ["tier1_sketch"])
f("tier1_fuse", "fuse", {}, ["base_extrude", "tier1_extrude"])

f("tier2_sketch", "sketch", {"plane": "XY", "offset": Z_T1,
                             "entities": [rounded_path_e(TIER2, 8)]})
f("tier2_extrude", "extrude", {"amount": Z_T2 - Z_T1}, ["tier2_sketch"])
f("tier2_fuse", "fuse", {}, ["tier1_fuse", "tier2_extrude"])

f("podium_sketch", "sketch", {"plane": "XY", "offset": Z_T2,
                              "entities": [rounded_path_e(PODIUM, 8)]})
f("podium_extrude", "extrude", {"amount": Z_POD - Z_T2}, ["podium_sketch"])
f("podium_fuse", "fuse", {}, ["tier2_fuse", "podium_extrude"])

# lockup raised to the 10mm summit
batches, batch = [], []
for g in lockup_groups:
    if len(batch) + len(g) > 10:
        batches.append(batch)
        batch = []
    batch += g
batches.append(batch)
lock_ids = []
for n, b in enumerate(batches):
    f(f"lockup_sketch_{n}", "sketch", {"plane": "XY", "offset": Z_POD,
                                       "entities": b})
    f(f"lockup_tool_{n}", "extrude", {"amount": Z_TOP - Z_POD},
      [f"lockup_sketch_{n}"])
    lock_ids.append(f"lockup_tool_{n}")

# row-A pyramids: one lofted frustum, patterned, mirrored into 4 quadrants
f("pyrA_base_sketch", "sketch", {"plane": "XY", "offset": ROW_A["z0"],
    "entities": [{"kind": "polygon", "mode": "add",
                  "points": diamond(A_X0, ROW_A["y"], ROW_A["hd"])}]})
f("pyrA_top_sketch", "sketch", {"plane": "XY", "offset": ROW_A["z1"],
    "entities": [{"kind": "polygon", "mode": "add",
                  "points": diamond(A_X0, ROW_A["y"], ROW_A["hd_top"])}]})
f("pyrA_loft", "loft", {}, ["pyrA_base_sketch", "pyrA_top_sketch"])
f("pyrA_row", "linear_pattern", {"count": A_N, "dx": A_PITCH}, ["pyrA_loft"])
# mirror-of-mirror yields an empty solid, so each quadrant row is patterned
# from a first-level mirror of the single pyramid
f("pyrA_west_seed", "mirror", {"plane": "YZ"}, ["pyrA_loft"])
f("pyrA_row_west", "linear_pattern", {"count": A_N, "dx": -A_PITCH},
  ["pyrA_west_seed"])
f("pyrA_row_south", "mirror", {"plane": "XZ"}, ["pyrA_row"])
f("pyrA_row_sw", "mirror", {"plane": "XZ"}, ["pyrA_row_west"])

# row-B pyramids: full-width row on tier2, mirrored to -y
f("pyrB_base_sketch", "sketch", {"plane": "XY", "offset": ROW_B["z0"],
    "entities": [{"kind": "polygon", "mode": "add",
                  "points": diamond(B_X0, ROW_B["y"], ROW_B["hd"])}]})
f("pyrB_top_sketch", "sketch", {"plane": "XY", "offset": ROW_B["z1"],
    "entities": [{"kind": "polygon", "mode": "add",
                  "points": diamond(B_X0, ROW_B["y"], ROW_B["hd_top"])}]})
f("pyrB_loft", "loft", {}, ["pyrB_base_sketch", "pyrB_top_sketch"])
f("pyrB_row", "linear_pattern", {"count": B_N, "dx": B_PITCH}, ["pyrB_loft"])
f("pyrB_row_south", "mirror", {"plane": "XZ"}, ["pyrB_row"])

f("ziggurat_fuse", "fuse", {},
  ["podium_fuse"] + lock_ids
  + ["pyrA_row", "pyrA_row_west", "pyrA_row_south", "pyrA_row_sw",
     "pyrB_row", "pyrB_row_south"])

f("scoop_sketch", "sketch", {"plane": "XY", "offset": -1, "entities": [
    {"kind": "circle", "r": 60, "x": 0, "y": 108, "mode": "add"},
    {"kind": "circle", "r": 60, "x": 0, "y": -108, "mode": "add"}]})
f("scoop_tool", "extrude", {"amount": 12}, ["scoop_sketch"])
f("scoop_cut", "cut", {}, ["ziggurat_fuse", "scoop_tool"])

f("hole_sketch", "sketch", {"plane": "XY", "offset": -1, "entities": [
    {"kind": "circle", "r": 2.1, "x": hx, "y": hy, "mode": "add"}
    for hx, hy in HOLES]})
f("hole_tool", "extrude", {"amount": 12}, ["hole_sketch"])
f("autonomiq_panel", "cut", {}, ["scoop_cut", "hole_tool"])

tree = {"name": "autonomiq-panel", "features": F,
        "spec": {"n_solids": 1, "size": [208, 108, 10],
                 "holes": {"2.1": 4}, "tol": 0.05}}
open(ROOT + r"\designs\autonomiq-panel-tree.json", "w").write(json.dumps(tree))

# ------------------------------------------------------------ preview
S = 6.0
W, HT = int(224 * S), int(120 * S)
EH = 300                       # elevation strip height (px)
img = Image.new("RGB", (W, HT + EH), (18, 24, 32))
d = ImageDraw.Draw(img)


def px(p):
    return (W / 2 + p[0] * S, HT / 2 - p[1] * S)


def poly(pts, fill):
    d.polygon([px(p) for p in pts], fill=fill)


C = {Z_RIM: (98, 104, 112), Z_T1: (136, 141, 148), Z_T2: (168, 172, 178),
     Z_POD: (196, 199, 204), Z_TOP: (240, 242, 245)}
C_HOLE = (40, 44, 50)
BG = (18, 24, 32)

poly(OCT, C[Z_RIM])
poly(INSET, C[Z_T1])
for cx, cy, r in SCOOPS:                       # scoop clearance ledge + void
    d.ellipse([px((cx - 68, cy + 68)), px((cx + 68, cy - 68))], fill=C[Z_RIM])
    d.ellipse([px((cx - 60, cy + 60)), px((cx + 60, cy - 60))], fill=BG)
poly(TIER2, C[Z_T2])
poly(PODIUM, C[Z_POD])

for grp in lockup_groups:
    for e in grp:
        poly(e["points"], C[Z_TOP] if e["mode"] == "add" else C[Z_POD])


def draw_pyr(cx, cy, hd, hd_top):
    E, N, Wc, Sc = (cx + hd, cy), (cx, cy + hd), (cx - hd, cy), (cx, cy - hd)
    ctr = (cx, cy)
    poly([E, N, ctr], (205, 209, 215))     # NE facet, lit
    poly([N, Wc, ctr], (180, 184, 190))    # NW
    poly([Wc, Sc, ctr], (120, 126, 134))   # SW, shadow
    poly([Sc, E, ctr], (150, 156, 163))    # SE
    poly(diamond(cx, cy, hd_top), C[Z_TOP])


rowA_x = [A_X0 + k * A_PITCH for k in range(A_N)]
for sx in (1, -1):
    for sy in (1, -1):
        for x in rowA_x:
            draw_pyr(sx * x, sy * ROW_A["y"], ROW_A["hd"], ROW_A["hd_top"])
rowB_x = [B_X0 + k * B_PITCH for k in range(B_N)]
for sy in (1, -1):
    for x in rowB_x:
        draw_pyr(x, sy * ROW_B["y"], ROW_B["hd"], ROW_B["hd_top"])

for hx, hy in HOLES:
    d.ellipse([px((hx - 2.1, hy + 2.1)), px((hx + 2.1, hy - 2.1))], fill=C_HOLE)

# section marker at x = 63 (passes through a row-A and a row-B pyramid)
for yy in range(-54, 55, 4):
    d.line([px((63, yy)), px((63, yy + 2))], fill=(255, 120, 80), width=2)

# ------------------------------------------------- elevation at x = 63
LH2 = LH / 2


def elev_z(y):
    ay = abs(y)
    if ay > 54:
        return 0.0
    if ay > 46:
        return Z_RIM
    if ay > 33:
        z = Z_T1
        dd = abs(ay - ROW_A["y"])
        if dd <= ROW_A["hd_top"]:
            z = ROW_A["z1"]
        elif dd <= ROW_A["hd"]:
            z = Z_T1 + (ROW_A["z1"] - Z_T1) * (ROW_A["hd"] - dd) \
                / (ROW_A["hd"] - ROW_A["hd_top"])
        return z
    if ay > 20:
        z = Z_T2
        dd = abs(ay - ROW_B["y"])
        if dd <= ROW_B["hd_top"]:
            z = ROW_B["z1"]
        elif dd <= ROW_B["hd"]:
            z = Z_T2 + (ROW_B["z1"] - Z_T2) * (ROW_B["hd"] - dd) \
                / (ROW_B["hd"] - ROW_B["hd_top"])
        return z
    return Z_TOP if ay <= LH2 else Z_POD


ZS, Y0 = 22.0, HT + EH - 40    # px per mm; baseline y in image


def pxe(y, z):
    return (W / 2 + y * S * 1.9, Y0 - z * ZS)


sil = [pxe(-56, 0)]
yy = -56.0
while yy <= 56.0:
    sil.append(pxe(yy, elev_z(yy)))
    yy += 0.2
sil.append(pxe(56, 0))
d.polygon(sil, fill=(150, 155, 162))
for z, lab in ((Z_RIM, "4.0"), (Z_T1, "6.0"), (Z_T2, "8.0"),
               (Z_POD, "9.3"), (Z_TOP, "10.0")):
    d.line([pxe(-60, z), pxe(60, z)], fill=(70, 78, 90), width=1)
    d.text((pxe(-64, z)[0], pxe(-64, z)[1] - 5), lab, fill=(200, 205, 212))
d.text((W / 2 - 170, HT + 12),
       "SECTION AT X=63 (orange line) - full-depth ziggurat, z in mm",
       fill=(255, 120, 80))

out = ROOT + r"\designs\autonomiq-panel-preview.png"
img.save(out)
n_pyr = 4 * A_N + 2 * B_N
print(f"preview: {out}")
print(f"tree: {len(F)} features | lockup batches {len(batches)} "
      f"({sum(len(b) for b in batches)} regions) | {n_pyr} pyramids | "
      f"stack 4/6/8/9.3/10")

# ------------------------------------------------------------ build
if "--build" in sys.argv:
    import contextlib
    import io
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
        doc.to_step(ROOT + r"\designs\autonomiq-panel.step")
        doc.save(ROOT + r"\designs\autonomiq-panel.tcad.json")
        print("measured:", json.dumps(rep.get("measured", {}))[:400])
        M._notify_studio("autonomiq-panel")
        print("wrote autonomiq-panel.step + autonomiq-panel.tcad.json")
