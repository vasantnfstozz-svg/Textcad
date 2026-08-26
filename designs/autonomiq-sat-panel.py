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
HOLES = []                                       # all mount holes dropped:
HOLE_R = 2.25                                    # the border is a gear now

# continuous gear teeth around the whole wall: full-depth notches cut into
# the silhouette at even arc-length pitch — straight walls become racks,
# the scallop curves become internal-gear segments, corners stay toothed.
TOOTH_PITCH = 6.6
TOOTH_ROOT_W, TOOTH_TIP_W = 3.2, 1.9             # notch width at wall / tip
TOOTH_DEPTH, TOOTH_OVER = 2.0, 0.8               # into plate / past the wall

# corner blades: a round arena pocket inside each pinstripe corner arc,
# with a small tapered NACA-style airfoil blade standing in it (lofted,
# so the blade walls are true sloped surfaces, not just vertical extrude)
AERO_C = (90.0, 40.0)                            # corner cell centre (Q1)
ARENA_R, ARENA_FLOOR = 7.8, 6.5
FOIL_CHORD, FOIL_T, FOIL_M, FOIL_P = 11.0, 0.24, 0.04, 0.4
FOIL_TOP_SCALE, FOIL_ZTOP = 0.6, 9.8

# vent grilles: louver slots filling the empty end bands of the plaque
# pocket (between the ledge frame ends and the pocket wall), 1.4 deep
VENT_L, VENT_W, VENT_PITCH, VENT_N = 4.9, 1.5, 3.5, 7
VENT_FLOOR = 7.0                                 # moat floor is 8.4

# amphitheater terraces: the strips between plaque and triangle rows become
# two wide steps descending toward the wordmark; the plaque floor (8.4)
# stands 1.0 above the lower trench, so the lockup sits on a podium. The
# V-triangle tips punch through the steps (their pockets are deeper).
# Big flat pockets — a 6mm end mill clears them, no fine tooling.
TERR_X = 68.0                    # half-length; pocket straight edge is 68.5
TERR_A_Y, TERR_A_Z = (22.2, 26.8), 8.8           # upper step, 1.2 deep
TERR_B_Y, TERR_B_Z = (17.2, 22.2), 7.4           # lower trench, 2.6 deep
TERR_R = 1.5                                     # corner radius (bit-friendly)

# bounded hatch panels: where the plaque-flanking triangle clusters were,
# a framed field per side — boundary groove (trace spec, z9.2) with crossed
# 45-deg stripes inside (2mm wide, 0.5 deep at z9.5) that run INTO the
# frame, like section-hatching on a technical drawing. No loose hatch
# anywhere else — the face near the gear wall stays clean.
PANEL_C = 86.5                                   # panel centre x (+-), y=0
PANEL_OW, PANEL_OH, PANEL_OR = 16.0, 26.0, 3.0   # frame outer rrect
PANEL_BW = 1.2                                   # frame groove width
HATCH_W, PANEL_PITCH, PANEL_HZ = 2.0, 7.0, 9.5   # stripe width/pitch/floor

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
# (the vertical 3-triangle clusters that flanked the plaque ends were
# removed on user request — hatch panels live there now)
TRIS = TOP_BAND + [(-x, -y, (a + 180) % 360) for x, y, a in TOP_BAND]

# connector traces: engraved lines (rim-pinstripe spec) tying the clusters
# into one circuit — cluster-to-cluster, cluster-to-dimple "node", and a
# stub that tees into the rim pinstripe. Defined in quadrant 1, mirrored x4.
TRACE_W = 1.4
Q1_TRACES = [((27.5, 29.5), (44.6, 29.5)),    # centre cluster -> side cluster
             ((74.8, 34.2), (80.5, 35.8)),    # side cluster -> corner pinstripe
             ((72.08, 39.0), (72.08, 47.3)),  # cluster apex -> rim pinstripe
             ((82.6, 12.4), (77.5, 28.6))]    # band -> hatch-panel border
TRACES = [((sx * a[0], sy * a[1]), (sx * b[0], sy * b[1]))
          for sx in (1, -1) for sy in (1, -1) for a, b in Q1_TRACES]


def slot_e(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    return {"kind": "slot", "length": round(math.hypot(dx, dy) + TRACE_W, 3),
            "height": TRACE_W,
            "x": round((a[0] + b[0]) / 2, 3), "y": round((a[1] + b[1]) / 2, 3),
            "rotation": round(math.degrees(math.atan2(dy, dx)), 3)}


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


def tri_verts(cx, cy, ang, side):
    rc = side / math.sqrt(3)
    return [(cx + rc * math.cos(math.radians(ang + k * 120)),
             cy + rc * math.sin(math.radians(ang + k * 120)))
            for k in range(3)]


def tri_path(cx, cy, ang, side=TRI_A):
    return rounded_path_e(tri_verts(cx, cy, ang, side), TRI_RR)


def wall_teeth():
    """Notch polygons at even arc-length pitch along the whole wall.
    The Q1 boundary (0,54)->(104,0) is walked piecewise, then mirrored x4."""
    a_l0 = math.atan2(54 - 86, 28 - 52)
    a_l1 = math.atan2(54 - 86, 76 - 52)
    a_s0 = math.atan2(34 - 22, 104 - 113)
    a_s1 = 2 * math.pi - a_s0
    SEG = [("l", (0, 54), (28, 54), (0, -1)),
           ("a", (52, 86), 40, a_l0, a_l1, 1),      # long scallop (concave)
           ("l", (76, 54), (90, 54), (0, -1)),
           ("a", (90, 40), 14, math.pi / 2, 0, -1),  # corner round (convex)
           ("l", (104, 40), (104, 34), (-1, 0)),
           ("a", (113, 22), 15, a_s0, a_s1, 1),      # short scallop (concave)
           ("l", (104, 10), (104, 0), (-1, 0))]

    def seg_len(sg):
        if sg[0] == "l":
            return math.hypot(sg[2][0] - sg[1][0], sg[2][1] - sg[1][1])
        return abs(sg[4] - sg[3]) * sg[2]

    def seg_eval(sg, s):
        if sg[0] == "l":
            _, (x0, y0), (x1, y1), n = sg
            ll = math.hypot(x1 - x0, y1 - y0)
            return (x0 + (x1 - x0) * s / ll, y0 + (y1 - y0) * s / ll), n
        _, c, r, t0, t1, cv = sg
        th = t0 + (t1 - t0) * s / (abs(t1 - t0) * r)
        return ((c[0] + r * math.cos(th), c[1] + r * math.sin(th)),
                (cv * math.cos(th), cv * math.sin(th)))

    total = sum(seg_len(sg) for sg in SEG)
    n_teeth = round(total / TOOTH_PITCH)
    q1 = []
    for k in range(n_teeth):
        s = (k + 0.5) * total / n_teeth
        for sg in SEG:
            if s <= seg_len(sg):
                break
            s -= seg_len(sg)
        (x, y), (nx, ny) = seg_eval(sg, s)
        tx, ty = -ny, nx
        pts = [(x - tx * TOOTH_ROOT_W / 2 - nx * TOOTH_OVER,
                y - ty * TOOTH_ROOT_W / 2 - ny * TOOTH_OVER),
               (x + tx * TOOTH_ROOT_W / 2 - nx * TOOTH_OVER,
                y + ty * TOOTH_ROOT_W / 2 - ny * TOOTH_OVER),
               (x + tx * TOOTH_TIP_W / 2 + nx * TOOTH_DEPTH,
                y + ty * TOOTH_TIP_W / 2 + ny * TOOTH_DEPTH),
               (x - tx * TOOTH_TIP_W / 2 + nx * TOOTH_DEPTH,
                y - ty * TOOTH_TIP_W / 2 + ny * TOOTH_DEPTH)]
        # a tooth straddling a wall junction can't get full bite — skip it,
        # so each wall piece reads as its own crisp gear segment
        if all(inside(px_, py_, 1.2) for px_, py_ in pts[2:]):
            q1.append(pts)
    out = []
    for sx in (1, -1):
        for sy in (1, -1):
            for pts in q1:
                m = [(round(sx * px_, 3), round(sy * py_, 3))
                     for px_, py_ in pts]
                # MUST be CCW: extrude follows the face normal, and a CW
                # polygon faces -Z — the tool then extrudes AWAY from the
                # plate and the cut silently removes nothing
                out.append([[p[0], p[1]] for p in _ccw(m)])
    return out


def corner_blades():
    """(base_poly, top_poly) per corner: a cambered NACA-style foil with
    chord along the corner diagonal, tapered toward the top for the loft."""
    n = 24
    up, lo = [], []
    for i in range(n + 1):
        xc = (1 - math.cos(math.pi * i / n)) / 2
        yt = 5 * FOIL_T * (0.2969 * math.sqrt(xc) - 0.126 * xc
                           - 0.3516 * xc ** 2 + 0.2843 * xc ** 3
                           - 0.1036 * xc ** 4)
        if xc < FOIL_P:
            yc = FOIL_M / FOIL_P ** 2 * (2 * FOIL_P * xc - xc ** 2)
            dyc = 2 * FOIL_M / FOIL_P ** 2 * (FOIL_P - xc)
        else:
            yc = FOIL_M / (1 - FOIL_P) ** 2 * ((1 - 2 * FOIL_P)
                                               + 2 * FOIL_P * xc - xc ** 2)
            dyc = 2 * FOIL_M / (1 - FOIL_P) ** 2 * (FOIL_P - xc)
        th = math.atan(dyc)
        up.append((xc - yt * math.sin(th), yc + yt * math.cos(th)))
        lo.append((xc + yt * math.sin(th), yc - yt * math.cos(th)))
    prof = up[::-1] + lo[1:-1]        # TE -> upper -> LE -> lower, no dups
    ca, sa = math.cos(math.pi / 4), math.sin(math.pi / 4)
    base, top = [], []
    for scale, dest in ((1.0, base), (FOIL_TOP_SCALE, top)):
        for x, y in prof:
            fx = (x - 0.5) * FOIL_CHORD * scale
            fy = (y - 0.02) * FOIL_CHORD * scale
            dest.append((AERO_C[0] + fx * ca - fy * sa,
                         AERO_C[1] + fx * sa + fy * ca))
    out = []
    for sx in (1, -1):
        for sy in (1, -1):
            b = _ccw([(round(sx * x, 3), round(sy * y, 3)) for x, y in base])
            t_ = _ccw([(round(sx * x, 3), round(sy * y, 3)) for x, y in top])
            out.append(([[p[0], p[1]] for p in b], [[p[0], p[1]] for p in t_]))
    return out


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

TEETH = wall_teeth()
for pts in TEETH:
    for x, y in pts:
        # every corner is either a root (outside the wall) or a full-depth
        # tip — and nothing reaches the rim pinstripe (offset >= 3.0)
        assert (not inside(x, y)) or inside(x, y, 0.9), \
            f"tooth point ({x:.1f},{y:.1f}) neither root nor full tip"
        assert not inside(x, y, RIM_D1 - 0.3), \
            f"tooth point ({x:.1f},{y:.1f}) reaches the rim pinstripe"

BLADES = corner_blades()
assert ARENA_R + 2.0 <= CR_R - RIM_D2 + 0.001, \
    "arena wall too close to the pinstripe corner arc"

def pocket_clear(x, y):
    """Distance from (x, y) to the plaque pocket boundary (outside > 0)."""
    dx = abs(x) - (POCKET_W / 2 - POCKET_R)
    dy = abs(y) - (POCKET_H / 2 - POCKET_R)
    return math.hypot(max(dx, 0), max(dy, 0)) - POCKET_R


def panel_inner_clear(x, y, cx):
    """SDF vs the panel frame's INNER rounded rect (negative = inside)."""
    iw, ih = PANEL_OW - 2 * PANEL_BW, PANEL_OH - 2 * PANEL_BW
    ir = max(PANEL_OR - PANEL_BW, 0.8)
    dx = abs(x - cx) - (iw / 2 - ir)
    dy = abs(y) - (ih / 2 - ir)
    return math.hypot(max(dx, 0), max(dy, 0)) - ir


def panel_hatch(cx):
    """Crossed 45-deg stripe slots clipped to the panel interior, extended
    0.3 into the frame groove so every stripe connects to the boundary."""
    slots = []
    for ang in (45, -45):
        ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        n = int(30 // PANEL_PITCH) + 1
        for k in range(-n, n + 1):
            ox, oy = cx - uy * k * PANEL_PITCH, ux * k * PANEL_PITCH
            ts = [t * 0.1 for t in range(-200, 201)
                  if panel_inner_clear(ox + ux * t * 0.1,
                                       oy + uy * t * 0.1, cx) <= 0.3]
            if not ts or ts[-1] - ts[0] < 2.6:
                continue
            t0, t1 = ts[0], ts[-1]
            slots.append({"kind": "slot", "length": round(t1 - t0, 3),
                          "height": HATCH_W,
                          "x": round(ox + ux * (t0 + t1) / 2, 3),
                          "y": round(oy + uy * (t0 + t1) / 2, 3),
                          "rotation": ang})
    return slots


PANEL_SLOTS = panel_hatch(PANEL_C) + panel_hatch(-PANEL_C)
# frame clearances: plaque wall, cusp rim band, side-scallop rim arcs
assert PANEL_C - PANEL_OW / 2 >= POCKET_W / 2 + 3.0, "panel hits plaque"
assert PANEL_C + PANEL_OW / 2 <= HALF_W - RIM_D2 - 1.2, "panel hits rim band"
for sc_x, sc_y, sc_r in ((113, 22, 15), (113, -22, 15)):
    corner = math.hypot(PANEL_C + PANEL_OW / 2 - sc_x, PANEL_OH / 2 - abs(sc_y))
    assert corner >= sc_r + RIM_D2 + 1.2, "panel corner hits scallop rim arc"
assert Z_LEDGE < PANEL_HZ < Z_TOP


# terrace sanity: end inside the pocket's straight edge (no face slivers
# against the corner arcs), clear of the gap-link traces and the A-triangle
# bases above, and the trench must stay below the plaque floor
assert TERR_X <= POCKET_W / 2 - POCKET_R, "terrace end past pocket corner arc"
assert TERR_A_Y[1] <= 29.5 - 0.7 - 1.2, "upper step reaches the gap traces"
assert TERR_A_Y[1] <= YA - 4.04 - 1.0, "upper step reaches the A-triangle row"
assert TERR_B_Z < Z_PLAQ - 0.9, "trench must undercut the plaque podium"


VENT_X = (LEDGE_OW / 2 + POCKET_W / 2) / 2       # centred in the end band
VENTS = [(sx * VENT_X, (k - (VENT_N - 1) / 2) * VENT_PITCH)
         for sx in (1, -1) for k in range(VENT_N)]


def ledge_clear(x, y):
    """Distance outside the ledge frame's outer boundary (positive = clear)."""
    dx = abs(x) - (LEDGE_OW / 2 - LEDGE_OR)
    dy = abs(y) - (LEDGE_OH / 2 - LEDGE_OR)
    return math.hypot(max(dx, 0), max(dy, 0)) - LEDGE_OR


for vx, vy in VENTS:
    for ex, ey in [(vx - VENT_L / 2, vy - VENT_W / 2),
                   (vx - VENT_L / 2, vy + VENT_W / 2),
                   (vx + VENT_L / 2, vy - VENT_W / 2),
                   (vx + VENT_L / 2, vy + VENT_W / 2)]:
        assert pocket_clear(ex, ey) <= -1.3, \
            f"vent corner ({ex:.1f},{ey:.1f}) too close to the pocket wall"
        assert ledge_clear(ex, ey) >= 1.3, \
            f"vent corner ({ex:.1f},{ey:.1f}) too close to the ledge frame"
for b, t_ in BLADES:
    for x, y in b:
        cx = math.copysign(AERO_C[0], x)
        cy = math.copysign(AERO_C[1], y)
        assert math.hypot(x - cx, y - cy) <= ARENA_R - 1.4, \
            f"blade point ({x:.1f},{y:.1f}) leaves no cutter moat"
for x, y in tri_pts:
    assert inside(x, y, 1.4), f"triangle point ({x:.1f},{y:.1f}) too near edge"
    # forbidden zone = rim groove ring widened 1.2 each way
    assert not (inside(x, y, RIM_D1 - 1.2) and not inside(x, y, RIM_D2 + 1.2)), \
        f"triangle point ({x:.1f},{y:.1f}) hits the rim groove"
    assert abs(x) > POCKET_W / 2 + 1.2 or abs(y) > POCKET_H / 2 + 1.2, \
        f"triangle point ({x:.1f},{y:.1f}) hits the plaque pocket"
for a, b in TRACES:
    for t in (i / 10 for i in range(11)):
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        assert inside(x, y, TRACE_W / 2 + 1.2), \
            f"trace point ({x:.1f},{y:.1f}) too near edge"
        assert pocket_clear(x, y) > TRACE_W / 2 + 1.2, \
            f"trace point ({x:.1f},{y:.1f}) hits the plaque pocket"
        for hx, hy in HOLES:
            assert math.hypot(x - hx, y - hy) > HOLE_R + TRACE_W / 2 + 1.0, \
                f"trace point ({x:.1f},{y:.1f}) hits hole ({hx},{hy})"

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

# gear teeth: full-depth notches around the whole wall, batched <= 10
tooth_ids = []
for n in range(0, len(TEETH), 10):
    f(f"gear_sketch_{n // 10}", "sketch", {"plane": "XY", "offset": -1,
      "entities": [{"kind": "polygon", "mode": "add", "points": p}
                   for p in TEETH[n:n + 10]]})
    f(f"gear_tool_{n // 10}", "extrude", {"amount": 12},
      [f"gear_sketch_{n // 10}"])
    tooth_ids.append(f"gear_tool_{n // 10}")
f("gear_cut", "cut", {}, ["corner_round_cut"] + tooth_ids)

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
f("rim_groove_cut", "cut", {}, ["gear_cut", "rim_ring"])

# triangle pockets, batched <= 10 entities per sketch
tri_ids = []
for n in range(0, len(tri_paths), 10):
    f(f"tri_sketch_{n // 10}", "sketch",
      {"plane": "XY", "offset": Z_TRI, "entities": tri_paths[n:n + 10]})
    f(f"tri_tool_{n // 10}", "extrude", {"amount": 7}, [f"tri_sketch_{n // 10}"])
    tri_ids.append(f"tri_tool_{n // 10}")
f("tri_cut", "cut", {}, ["rim_groove_cut"] + tri_ids)

# connector traces, batched <= 10 entities per sketch
trace_ents = [slot_e(a, b) for a, b in TRACES]
trace_ids = []
for n in range(0, len(trace_ents), 10):
    f(f"trace_sketch_{n // 10}", "sketch",
      {"plane": "XY", "offset": Z_GROOVE, "entities": trace_ents[n:n + 10]})
    f(f"trace_tool_{n // 10}", "extrude", {"amount": 1.6},
      [f"trace_sketch_{n // 10}"])
    trace_ids.append(f"trace_tool_{n // 10}")
f("trace_cut", "cut", {}, ["tri_cut"] + trace_ids)

# plaque pocket + raised ledge stripe + flush lockup
f("plaque_sketch", "sketch", {"plane": "XY", "offset": Z_PLAQ,
                              "entities": [rrect(POCKET_W, POCKET_H, POCKET_R)]})
f("plaque_tool", "extrude", {"amount": Z_TOP - Z_PLAQ + 1}, ["plaque_sketch"])
f("plaque_cut", "cut", {}, ["trace_cut", "plaque_tool"])

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

# corner blade arenas + lofted airfoil blades
f("aero_arena_sketch", "sketch", {"plane": "XY", "offset": ARENA_FLOOR,
  "entities": [{"kind": "circle", "r": ARENA_R, "x": sx * AERO_C[0],
                "y": sy * AERO_C[1], "mode": "add"}
               for sx in (1, -1) for sy in (1, -1)]})
f("aero_arena_tool", "extrude", {"amount": Z_TOP - ARENA_FLOOR + 1},
  ["aero_arena_sketch"])
f("aero_arena_cut", "cut", {}, ["plaque_cut", "aero_arena_tool"])

# vent grilles in the plaque end bands (one sketch per end, 7 slots each)
vent_ids = []
for n, sx in enumerate((1, -1)):
    f(f"vent_sketch_{n}", "sketch", {"plane": "XY", "offset": VENT_FLOOR,
      "entities": [{"kind": "slot", "length": VENT_L, "height": VENT_W,
                    "x": vx, "y": vy, "rotation": 0}
                   for vx, vy in VENTS if vx * sx > 0]})
    f(f"vent_tool_{n}", "extrude", {"amount": Z_TOP - VENT_FLOOR + 1},
      [f"vent_sketch_{n}"])
    vent_ids.append(f"vent_tool_{n}")
f("vent_cut", "cut", {}, ["aero_arena_cut"] + vent_ids)

# amphitheater terraces: one sketch per step level (two strips each)
def terr_rect(y0, y1):
    return [rounded_path_e([(TERR_X, y0), (TERR_X, y1),
                            (-TERR_X, y1), (-TERR_X, y0)], TERR_R),
            rounded_path_e([(TERR_X, -y1), (TERR_X, -y0),
                            (-TERR_X, -y0), (-TERR_X, -y1)], TERR_R)]


f("terr_a_sketch", "sketch", {"plane": "XY", "offset": TERR_A_Z,
                              "entities": terr_rect(*TERR_A_Y)})
f("terr_a_tool", "extrude", {"amount": Z_TOP - TERR_A_Z + 1}, ["terr_a_sketch"])
f("terr_a_cut", "cut", {}, ["vent_cut", "terr_a_tool"])
f("terr_b_sketch", "sketch", {"plane": "XY", "offset": TERR_B_Z,
                              "entities": terr_rect(*TERR_B_Y)})
f("terr_b_tool", "extrude", {"amount": Z_TOP - TERR_B_Z + 1}, ["terr_b_sketch"])
f("terr_b_cut", "cut", {}, ["terr_a_cut", "terr_b_tool"])

# hatch panels: frame ring grooves, then the clipped stripes inside
frame_ents = []
for cx in (PANEL_C, -PANEL_C):
    outer = rounded_path_e([(cx + PANEL_OW / 2, -PANEL_OH / 2),
                            (cx + PANEL_OW / 2, PANEL_OH / 2),
                            (cx - PANEL_OW / 2, PANEL_OH / 2),
                            (cx - PANEL_OW / 2, -PANEL_OH / 2)], PANEL_OR)
    iw, ih = PANEL_OW - 2 * PANEL_BW, PANEL_OH - 2 * PANEL_BW
    inner = rounded_path_e([(cx + iw / 2, -ih / 2), (cx + iw / 2, ih / 2),
                            (cx - iw / 2, ih / 2), (cx - iw / 2, -ih / 2)],
                           max(PANEL_OR - PANEL_BW, 0.8))
    inner["mode"] = "subtract"
    frame_ents += [outer, inner]
f("panel_frame_sketch", "sketch", {"plane": "XY", "offset": Z_GROOVE,
                                   "entities": frame_ents})
f("panel_frame_tool", "extrude", {"amount": 1.6}, ["panel_frame_sketch"])
f("panel_frame_cut", "cut", {}, ["terr_b_cut", "panel_frame_tool"])

panel_ids = []
for n in range(0, len(PANEL_SLOTS), 10):
    i = n // 10
    f(f"panel_hatch_sketch_{i}", "sketch", {"plane": "XY", "offset": PANEL_HZ,
      "entities": PANEL_SLOTS[n:n + 10]})
    f(f"panel_hatch_tool_{i}", "extrude", {"amount": 1.5},
      [f"panel_hatch_sketch_{i}"])
    panel_ids.append(f"panel_hatch_tool_{i}")
f("panel_hatch_cut", "cut", {}, ["panel_frame_cut"] + panel_ids)

blade_ids = []
for i, (b, t_) in enumerate(BLADES, start=1):
    f(f"blade{i}_base", "sketch", {"plane": "XY", "offset": ARENA_FLOOR,
      "entities": [{"kind": "polygon", "mode": "add", "points": b}]})
    f(f"blade{i}_top", "sketch", {"plane": "XY", "offset": FOIL_ZTOP,
      "entities": [{"kind": "polygon", "mode": "add", "points": t_}]})
    f(f"blade{i}", "loft", {}, [f"blade{i}_base", f"blade{i}_top"])
    blade_ids.append(f"blade{i}")

f("autonomiq_sat_panel", "fuse", {},
  ["panel_hatch_cut", "ledge_tool"] + mark_ids + blade_ids)

# no symmetry claim: the 126mm wordmark is intentionally not 180-deg symmetric
tree = {"name": "autonomiq-sat-panel", "features": F,
        "spec": {"n_solids": 1, "size": [208, 108, 10], "tol": 0.3}}
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


for pts in TEETH:
    d.polygon([px(tuple(p)) for p in pts], fill=BG)
for e in frame_ents:
    pts = [tuple(e["start"])]
    for s in e["segments"]:
        if "via" in s:
            pts.append(tuple(s["via"]))
        pts.append(tuple(s["to"]))
    d.polygon([px(p) for p in pts],
              fill=C_GROOVE if e["mode"] == "add" else C_FACE)
for e in PANEL_SLOTS:
    a = math.radians(e["rotation"])
    hx, hy = math.cos(a) * e["length"] / 2, math.sin(a) * e["length"] / 2
    d.line([px((e["x"] - hx, e["y"] - hy)), px((e["x"] + hx, e["y"] + hy))],
           fill=(150, 155, 162), width=max(1, int(HATCH_W * S)))


def rr_box(w, h):
    return [px((-w / 2, h / 2)), px((w / 2, -h / 2))]


for y0, y1, col in ((TERR_A_Y[0], TERR_A_Y[1], (150, 155, 162)),
                    (TERR_B_Y[0], TERR_B_Y[1], (126, 132, 140))):
    for sgn in (1, -1):
        d.rounded_rectangle([px((-TERR_X, sgn * y1 if sgn > 0 else -y0)),
                             px((TERR_X, sgn * y0 if sgn > 0 else -y1))],
                            radius=TERR_R * S, fill=col)
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
for vx, vy in VENTS:
    d.rounded_rectangle([px((vx - VENT_L / 2, vy + VENT_W / 2)),
                         px((vx + VENT_L / 2, vy - VENT_W / 2))],
                        radius=VENT_W / 2 * S, fill=C_TRI)
for a, b in TRACES:
    d.line([px(a), px(b)], fill=C_GROOVE, width=max(1, int(TRACE_W * S)))
    for e in (a, b):
        d.ellipse([px((e[0] - TRACE_W / 2, e[1] + TRACE_W / 2)),
                   px((e[0] + TRACE_W / 2, e[1] - TRACE_W / 2))],
                  fill=C_GROOVE)
for tp in tri_paths:
    pts = [tuple(tp["start"])]
    for s in tp["segments"]:
        if "via" in s:
            pts.append(tuple(s["via"]))
        pts.append(tuple(s["to"]))
    d.polygon([px(p) for p in pts], fill=C_TRI)
for sx in (1, -1):
    for sy in (1, -1):
        acx, acy = sx * AERO_C[0], sy * AERO_C[1]
        d.ellipse([px((acx - ARENA_R, acy + ARENA_R)),
                   px((acx + ARENA_R, acy - ARENA_R))], fill=C_TRI)
for b, t_ in BLADES:
    d.polygon([px(tuple(p)) for p in b], fill=C_LEDGE)
    d.polygon([px(tuple(p)) for p in t_], fill=(228, 231, 236))

out = ROOT + r"\designs\autonomiq-sat-panel-preview.png"
img.save(out)
print(f"preview: {out}")
print(f"tree: {len(F)} features | lockup {LOCKUP_W:.0f} x {LH:.1f} mm, "
      f"{len(lockup_groups)} glyph groups in {len(batches)} sketches | "
      f"{len(TRIS)} triangles side {TRI_A} | {len(TRACES)} connector traces | "
      f"{len(TEETH)} gear teeth pitch {TOOTH_PITCH} depth {TOOTH_DEPTH} | "
      f"4 corner blades chord {FOIL_CHORD} z{ARENA_FLOOR}->{FOIL_ZTOP} "
      f"in arena r{ARENA_R} | {len(VENTS)} vent slots at x +-{VENT_X:.1f} | "
      f"terraces z{TERR_A_Z}/{TERR_B_Z} y {TERR_B_Y[0]}..{TERR_A_Y[1]} "
      f"x +-{TERR_X} | "
      f"2 hatch panels {PANEL_OW}x{PANEL_OH} at x +-{PANEL_C}, "
      f"{len(PANEL_SLOTS)} stripes w{HATCH_W} pitch {PANEL_PITCH} | "
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
