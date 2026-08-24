"""autonomiq-sat-panel v2 — the wordmark-plaque layout the user picked,
rebuilt with the OFFICIAL lockup and the requested fixes.

User feedback on v1 (2026-08-24):
  - lettering structure wrong  -> use the real SVG lockup (big word + iQ
    mark only, NO small "autonomous manufacturing" tagline paths)
  - triangles too small        -> side 14mm (was 10.1), same interlocked
    A/V row pattern, fewer of them
  - stripes/outline detailing  -> rim pinstripe groove following the whole
    silhouette + striped plaque frame (moat / raised ledge / moat)
  - long sides have the scallop "pyramid cut" edge, short sides don't
    -> twin r15 scallops per short side with a centre cusp, mirroring the
    long-side twin r40 scallops
Plate: 208 x 108 x 10 stealth octagon, 6 mounting holes, 2-fold symmetric.

z-stack (mm): tri floor 3.5 | plaque floor 8.4 | grooves 9.2 | ledge 9.4 |
              face + lockup 10.0

Run:  python designs/autonomiq-sat-panel.py           -> preview + checks
      python designs/autonomiq-sat-panel.py --build   -> STEP + tcad.json
"""
import json
import math
import re
import sys

from PIL import Image, ImageDraw

ROOT = r"c:\Users\VasanSeenivasan\Desktop\textcad"
SVG_FILE = ROOT + r"\designs\autonomIQ-Logo_cmyk.svg"
KEEP = set(range(0, 6)) | {29, 30, 31, 32, 33}   # big word + Q + i, NO tagline

# ------------------------------------------------------------------ layout
Z_TRI, Z_PLAQ, Z_GROOVE, Z_LEDGE, Z_TOP = 3.5, 8.4, 9.2, 9.4, 10.0
HALF_W, HALF_H = 104.0, 54.0
CR_CX, CR_CY, CR_R = 90.0, 40.0, 14.0            # corner-round arc
SCALLOPS = ([(sx * 52.0, sy * 86.0, 40.0) for sx in (1, -1) for sy in (1, -1)]
            + [(sx * 113.0, sy * 22.0, 15.0) for sx in (1, -1) for sy in (1, -1)])
RIM_D1, RIM_D2 = 3.0, 4.2                        # rim pinstripe offsets
HOLES = [(94, 44), (-94, 44), (-94, -44), (94, -44), (0, 46), (0, -46)]
HOLE_R = 2.25
DIMPLE = (84.0, 40.0)                            # + 2-fold pattern, r1.25

# plaque: pocket > moat > raised ledge stripe > moat > lockup (flush at 10)
POCKET_W, POCKET_H, POCKET_R = 148.0, 35.0, 5.5
LEDGE_OW, LEDGE_OH, LEDGE_OR = 132.6, 31.8, 4.3
LEDGE_IW, LEDGE_IH, LEDGE_IR = 129.2, 28.4, 2.6
LOCKUP_W = 126.0

# triangles: interlocked A/V rows, exact scale-up (x1.385) of the v1 rhythm
TRI_A, TRI_RR = 14.0, 1.1
P = 11.08                    # horizontal pitch inside a cluster
YA, YV = 32.0, 27.0          # top band: apex-up row high, apex-down row low


def tri(cx, cy, ang):
    """(cx, cy, apex-direction deg): 90=up 270=down 0=right 180=left."""
    return (cx, cy, ang)


TOP_BAND = ([tri(0, YV, 270), tri(P, YA, 90), tri(-P, YA, 90),
             tri(2 * P, YV, 270), tri(-2 * P, YV, 270)]
            + [t for bx in (61.0, -61.0)
               for t in (tri(bx - P, YA, 90), tri(bx, YV, 270),
                         tri(bx + P, YA, 90))])
SIDE_R = [tri(84, -P, 180), tri(89, 0, 0), tri(84, P, 180)]
SIDE_L = [(-x, y, (180 - a) % 360) for x, y, a in SIDE_R]
TRIS = (TOP_BAND + [(-x, -y, (a + 180) % 360) for x, y, a in TOP_BAND]
        + SIDE_R + SIDE_L)


# --------------------------------------------------- SVG helpers (v5 copy)
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


def _decimate(pts, min_d=0.12):
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


def rrect(w, h, r):
    return rounded_path_e([(w / 2, -h / 2), (w / 2, h / 2),
                           (-w / 2, h / 2), (-w / 2, -h / 2)], r)


def tri_path(cx, cy, ang):
    rc = TRI_A / math.sqrt(3)
    verts = [(cx + rc * math.cos(math.radians(ang + k * 120)),
              cy + rc * math.sin(math.radians(ang + k * 120)))
             for k in range(3)]
    return rounded_path_e(verts, TRI_RR)


def oct_path(d):
    """The plate outline (rect + r14 corner rounds) offset d inward."""
    x, y, r = HALF_W - d, HALF_H - d, CR_R - d
    c = r * math.sqrt(0.5)
    # walk CW from top-left; corner arcs stay tangent to both edges at any d
    return {"kind": "path", "mode": "add", "start": [-CR_CX, y], "segments": [
        {"type": "line", "to": [CR_CX, y]},
        {"type": "arc", "via": [CR_CX + c, CR_CY + c], "to": [x, CR_CY]},
        {"type": "line", "to": [x, -CR_CY]},
        {"type": "arc", "via": [CR_CX + c, -CR_CY - c], "to": [CR_CX, -y]},
        {"type": "line", "to": [-CR_CX, -y]},
        {"type": "arc", "via": [-CR_CX - c, -CR_CY - c], "to": [-x, -CR_CY]},
        {"type": "line", "to": [-x, CR_CY]},
        {"type": "arc", "via": [-CR_CX - c, CR_CY + c], "to": [-CR_CX, y]},
    ]}


def scallop_circles(d):
    return [{"kind": "circle", "r": r + d, "x": cx, "y": cy, "mode": "add"}
            for cx, cy, r in SCALLOPS]


# ------------------------------------------------------------- sanity gates
def inside(x, y, d=0.0):
    """Point at least d inside the plate silhouette."""
    if abs(x) > HALF_W - d or abs(y) > HALF_H - d:
        return False
    if abs(x) > CR_CX and abs(y) > CR_CY and \
            math.hypot(abs(x) - CR_CX, abs(y) - CR_CY) > CR_R - d:
        return False
    return all(math.hypot(x - cx, y - cy) >= r + d for cx, cy, r in SCALLOPS)


tri_paths = [tri_path(*t) for t in TRIS]
tri_pts = [(p[0], p[1]) for tp in tri_paths
           for p in [tp["start"]] + [s["to"] for s in tp["segments"]]]
for x, y in tri_pts:
    assert inside(x, y, 1.4), f"triangle point ({x:.1f},{y:.1f}) too near edge"
    # forbidden zone = rim groove ring widened 1.2 each way
    assert not (inside(x, y, RIM_D1 - 1.2) and not inside(x, y, RIM_D2 + 1.2)), \
        f"triangle point ({x:.1f},{y:.1f}) hits the rim groove"
    assert abs(x) > POCKET_W / 2 + 1.2 or abs(y) > POCKET_H / 2 + 1.2, \
        f"triangle point ({x:.1f},{y:.1f}) hits the plaque pocket"
for hx, hy in HOLES:
    assert inside(hx, hy, HOLE_R + 1.5), f"hole ({hx},{hy}) too near edge"
    for a in range(12):
        ex = hx + HOLE_R * math.cos(a * 30 * math.pi / 180)
        ey = hy + HOLE_R * math.sin(a * 30 * math.pi / 180)
        assert not (inside(ex, ey, RIM_D1 - 1.0)
                    and not inside(ex, ey, RIM_D2 + 1.0)), \
            f"hole ({hx},{hy}) crosses the rim groove"

lockup_groups, LH = load_lockup_grouped(LOCKUP_W)
assert LOCKUP_W / 2 <= LEDGE_IW / 2 - 1.4 and LH / 2 <= LEDGE_IH / 2 - 1.4, \
    f"lockup {LOCKUP_W:.0f}x{LH:.1f} does not fit ledge {LEDGE_IW}x{LEDGE_IH}"

# ------------------------------------------------------------- feature tree
F = []


def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


f("blank", "plate", {"width": 208, "depth": 108, "thickness": 10})
f("blank_seat", "move", {"z": 5}, ["blank"])
f("scallop_sketch", "sketch", {"plane": "XY", "offset": -1,
                               "entities": scallop_circles(0)})
f("scallop_tool", "extrude", {"amount": 12}, ["scallop_sketch"])
f("scallop_cut", "cut", {}, ["blank_seat", "scallop_tool"])

CORNER = []
for sx in (1, -1):
    for sy in (1, -1):
        c = CR_R * math.sqrt(0.5)
        CORNER.append({"kind": "path", "mode": "add",
                       "start": [sx * CR_CX, sy * HALF_H],
                       "segments": [
                           {"type": "arc",
                            "via": [sx * (CR_CX + c), sy * (CR_CY + c)],
                            "to": [sx * HALF_W, sy * CR_CY]},
                           {"type": "line", "to": [sx * (HALF_W + 4), sy * CR_CY]},
                           {"type": "line",
                            "to": [sx * (HALF_W + 4), sy * (HALF_H + 4)]},
                           {"type": "line",
                            "to": [sx * CR_CX, sy * (HALF_H + 4)]}]})
f("corner_round_sketch", "sketch", {"plane": "XY", "offset": -1,
                                    "entities": CORNER})
f("corner_round_tool", "extrude", {"amount": 12}, ["corner_round_sketch"])
f("corner_round_cut", "cut", {}, ["scallop_cut", "corner_round_tool"])

# rim pinstripe: (silhouette-3.0 minus silhouette-4.2) ring, 0.8 deep
f("rimA_sketch", "sketch", {"plane": "XY", "offset": Z_GROOVE,
                            "entities": [oct_path(RIM_D1)]})
f("rimA_tool", "extrude", {"amount": 1.6}, ["rimA_sketch"])
f("rimA_circ_sketch", "sketch", {"plane": "XY", "offset": Z_GROOVE - 0.2,
                                 "entities": scallop_circles(RIM_D1)})
f("rimA_circ_tool", "extrude", {"amount": 2.0}, ["rimA_circ_sketch"])
f("rimA_slab", "cut", {}, ["rimA_tool", "rimA_circ_tool"])
f("rimB_sketch", "sketch", {"plane": "XY", "offset": Z_GROOVE - 0.1,
                            "entities": [oct_path(RIM_D2)]})
f("rimB_tool", "extrude", {"amount": 1.8}, ["rimB_sketch"])
f("rimB_circ_sketch", "sketch", {"plane": "XY", "offset": Z_GROOVE - 0.3,
                                 "entities": scallop_circles(RIM_D2)})
f("rimB_circ_tool", "extrude", {"amount": 2.2}, ["rimB_circ_sketch"])
f("rimB_slab", "cut", {}, ["rimB_tool", "rimB_circ_tool"])
f("rim_ring", "cut", {}, ["rimA_slab", "rimB_slab"])
f("rim_groove_cut", "cut", {}, ["corner_round_cut", "rim_ring"])

# triangle pockets, batched <= 10 entities per sketch
tri_ids = []
for n in range(0, len(tri_paths), 10):
    f(f"tri_sketch_{n // 10}", "sketch",
      {"plane": "XY", "offset": Z_TRI, "entities": tri_paths[n:n + 10]})
    f(f"tri_tool_{n // 10}", "extrude", {"amount": 7}, [f"tri_sketch_{n // 10}"])
    tri_ids.append(f"tri_tool_{n // 10}")
f("tri_cut", "cut", {}, ["rim_groove_cut"] + tri_ids)

# plaque pocket + raised ledge stripe + flush lockup
f("plaque_sketch", "sketch", {"plane": "XY", "offset": Z_PLAQ,
                              "entities": [rrect(POCKET_W, POCKET_H, POCKET_R)]})
f("plaque_tool", "extrude", {"amount": Z_TOP - Z_PLAQ + 1}, ["plaque_sketch"])
f("plaque_cut", "cut", {}, ["tri_cut", "plaque_tool"])

ledge_inner = rrect(LEDGE_IW, LEDGE_IH, LEDGE_IR)
ledge_inner["mode"] = "subtract"
f("ledge_sketch", "sketch", {"plane": "XY", "offset": Z_PLAQ,
                             "entities": [rrect(LEDGE_OW, LEDGE_OH, LEDGE_OR),
                                          ledge_inner]})
f("ledge_tool", "extrude", {"amount": Z_LEDGE - Z_PLAQ}, ["ledge_sketch"])

batches, batch = [], []
for g in lockup_groups:
    if len(batch) + len(g) > 10:
        batches.append(batch)
        batch = []
    batch += g
batches.append(batch)
mark_ids = []
for n, b in enumerate(batches):
    f(f"lockup_sketch_{n}", "sketch", {"plane": "XY", "offset": Z_PLAQ,
                                       "entities": b})
    f(f"lockup_tool_{n}", "extrude", {"amount": Z_TOP - Z_PLAQ},
      [f"lockup_sketch_{n}"])
    mark_ids.append(f"lockup_tool_{n}")

# corner dimples (polar + ONE mirror + fuse: never mirror a mirror)
f("corner_dimple", "disc", {"radius": 1.25, "thickness": 2.5})
f("corner_dimple_seat", "move", {"x": DIMPLE[0], "y": DIMPLE[1], "z": 10},
  ["corner_dimple"])
f("corner_dimples_diag1", "polar_pattern", {"count": 2}, ["corner_dimple_seat"])
f("corner_dimples_diag2", "mirror", {"plane": "YZ"}, ["corner_dimples_diag1"])
f("corner_dimples_all", "fuse", {}, ["corner_dimples_diag1",
                                     "corner_dimples_diag2"])
f("corner_dimple_cut", "cut", {}, ["plaque_cut", "corner_dimples_all"])

f("mount_hole_sketch", "sketch", {"plane": "XY", "offset": -1, "entities": [
    {"kind": "circle", "r": HOLE_R, "x": hx, "y": hy, "mode": "add"}
    for hx, hy in HOLES]})
f("mount_hole_tool", "extrude", {"amount": 12}, ["mount_hole_sketch"])
f("mount_hole_cut", "cut", {}, ["corner_dimple_cut", "mount_hole_tool"])

f("autonomiq_sat_panel", "fuse", {},
  ["mount_hole_cut", "ledge_tool"] + mark_ids)

# no symmetry claim: the 126mm wordmark is intentionally not 180-deg symmetric
tree = {"name": "autonomiq-sat-panel", "features": F,
        "spec": {"n_solids": 1, "size": [208, 108, 10],
                 "holes": {"2.25": 6}, "tol": 0.3}}
open(ROOT + r"\designs\autonomiq-sat-panel-tree.json", "w").write(json.dumps(tree))

# ------------------------------------------------------------- preview
S = 4.0
W, HT = int(216 * S), int(116 * S)
img = Image.new("RGB", (W, HT), (18, 24, 32))
d = ImageDraw.Draw(img)
BG, C_FACE, C_GROOVE = (18, 24, 32), (176, 180, 186), (110, 116, 124)
C_POCKET, C_LEDGE, C_MARK = (120, 126, 134), (198, 202, 208), (240, 242, 245)
C_TRI, C_HOLE, C_DIMP = (76, 82, 90), (35, 39, 45), (140, 146, 153)

for py in range(HT):
    my = 58.0 - (py + 0.5) / S
    for px_i in range(W):
        mx = (px_i + 0.5) / S - 108.0
        if not inside(mx, my):
            continue
        in_ring = inside(mx, my, RIM_D1) and not inside(mx, my, RIM_D2)
        img.putpixel((px_i, py), C_GROOVE if in_ring else C_FACE)


def px(p):
    return (W / 2 + p[0] * S, HT / 2 - p[1] * S)


def rr_box(w, h):
    return [px((-w / 2, h / 2)), px((w / 2, -h / 2))]


d.rounded_rectangle(rr_box(POCKET_W, POCKET_H), radius=POCKET_R * S,
                    fill=C_POCKET)
d.rounded_rectangle(rr_box(LEDGE_OW, LEDGE_OH), radius=LEDGE_OR * S,
                    fill=C_LEDGE)
d.rounded_rectangle(rr_box(LEDGE_IW, LEDGE_IH), radius=LEDGE_IR * S,
                    fill=C_POCKET)
for grp in lockup_groups:
    for e in grp:
        d.polygon([px(tuple(p)) for p in e["points"]],
                  fill=C_MARK if e["mode"] == "add" else C_POCKET)
for tp in tri_paths:
    pts = [tuple(tp["start"])]
    for s in tp["segments"]:
        if "via" in s:
            pts.append(tuple(s["via"]))
        pts.append(tuple(s["to"]))
    d.polygon([px(p) for p in pts], fill=C_TRI)
for hx, hy in HOLES:
    d.ellipse([px((hx - HOLE_R, hy + HOLE_R)), px((hx + HOLE_R, hy - HOLE_R))],
              fill=C_HOLE)
for sx in (1, -1):
    for sy in (1, -1):
        cx, cy = sx * DIMPLE[0], sy * DIMPLE[1]
        d.ellipse([px((cx - 1.25, cy + 1.25)), px((cx + 1.25, cy - 1.25))],
                  fill=C_DIMP)

out = ROOT + r"\designs\autonomiq-sat-panel-preview.png"
img.save(out)
print(f"preview: {out}")
print(f"tree: {len(F)} features | lockup {LOCKUP_W:.0f} x {LH:.1f} mm, "
      f"{len(lockup_groups)} glyph groups in {len(batches)} sketches | "
      f"{len(TRIS)} triangles side {TRI_A} | "
      f"plaque {POCKET_W}x{POCKET_H} ledge {LEDGE_OW}x{LEDGE_OH}")

# ------------------------------------------------------------- build
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
        doc.to_step(ROOT + r"\designs\autonomiq-sat-panel.step")
        doc.save(ROOT + r"\designs\autonomiq-sat-panel.tcad.json")
        print("measured:", json.dumps(rep.get("measured", {}))[:400])
        print("wrote autonomiq-sat-panel.step + autonomiq-sat-panel.tcad.json")
