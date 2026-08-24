"""autonomiQ panel v4 — layout + PREVIEW renderer (no CAD build yet).

Concept: compact stealth-octagon plate; width-wise ziggurat terraces
(podium 9.7 / strip1 9.4 / strip2 9.1, rim 10); size-gradient triangle
field fading to dots toward the edges; 4 corner bracket channels; the
OFFICIAL autonomIQ lockup (word + segmented I + magnifier Q, tagline
dropped) raised to rim height on the podium.

Run:  python autonomiq-panel-v4.py   -> designs/autonomiq-panel-preview.png
"""
import math
import re
import sys

from PIL import Image, ImageDraw

# ----------------------------------------------------------- SVG lockup
SVG_FILE = r"c:\Users\VasanSeenivasan\Desktop\textcad\designs\autonomIQ-Logo_cmyk.svg"
KEEP = set(range(0, 6)) | {29, 30, 31, 32, 33}   # word, Q, I pieces, t


def parse_d(d):
    """Full mini-parser: M/m C/c L/l H/h V/v Z/z with repeats. Returns
    list of subpaths, each a list of (x, y) polygon points (cubics sampled)."""
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
            # implicit linetos
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
        else:  # Z/z
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


def load_lockup(target_width):
    ds = re.findall(r'[\s"]d="([^"]+)"', open(SVG_FILE, encoding="utf-8").read())
    subs = []
    for idx, d in enumerate(ds):
        if idx in KEEP:
            subs += parse_d(d)
    xs = [p[0] for s in subs for p in s]
    ys = [p[1] for s in subs for p in s]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = target_width / (x1 - x0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out = [[((p[0] - cx) * s, (p[1] - cy) * s) for p in sub] for sub in subs]
    # classify holes: first point inside another subpath -> subtract
    modes = []
    for i, sub in enumerate(out):
        hole = any(j != i and point_in_poly(sub[0], out[j]) for j in range(len(out)))
        modes.append("subtract" if hole else "add")
    return out, modes, (x1 - x0) * s, (y1 - y0) * s


# ------------------------------------------------------------ layout
OCT = [(-104, 28), (-104, -28), (-78, -54), (78, -54),
       (104, -28), (104, 28), (78, 54), (-78, 54)]
SCOOPS = [(0, 108, 60), (0, -108, 60)]
PODIUM_H = 40.0          # podium half extent: |y| < 20
STRIP1 = 33.0            # strip1: 20..33, strip2: 33..46


def in_face(x, y, m=0.0):
    if abs(x) > 96 - m or abs(y) > 46 - m:
        return False
    if abs(x) + abs(y) > 120.686 - m * 1.414:
        return False
    for cx, cy, r in SCOOPS:
        if math.hypot(x - cx, y - cy) < r + 8 + m:
            return False
    return True


ROWS = [  # (|y|, kind, size, pitch)
    (26.5, "tri", 5.6, 13.0),
    (37.5, "tri", 3.8, 10.0),
    (42.5, "dot", 1.5, 6.5),
]
BR_ELBOWS = [(84 * sx, 34 * sy) for sx in (1, -1) for sy in (1, -1)]


def near_bracket(x, y):
    for ex, ey in BR_ELBOWS:
        hx0, hx1 = min(ex, ex - 28 * (1 if ex > 0 else -1)), max(ex, ex - 28 * (1 if ex > 0 else -1))
        if hx0 - 6 <= x <= hx1 + 6 and abs(y - ey) <= 6:
            return True
        vy0, vy1 = min(ey, ey - 14 * (1 if ey > 0 else -1)), max(ey, ey - 14 * (1 if ey > 0 else -1))
        if abs(x - ex) <= 6 and vy0 - 6 <= y <= vy1 + 6:
            return True
    return False


field = []
for yy, kind, size, pitch in ROWS:
    for sy in (1, -1):
        cy = yy * sy
        n = int(200 / pitch)
        for k in range(-n, n + 1):
            cx = k * pitch
            up = (k % 2 == 0) if sy > 0 else (k % 2 == 1)
            if kind == "tri":
                angles = (90, 210, 330) if up else (270, 30, 150)
                vs = [(cx + size * math.cos(math.radians(a)),
                       cy + size * math.sin(math.radians(a))) for a in angles]
                if all(in_face(x, y, 2.5) for x, y in vs) and                    not any(near_bracket(x, y) for x, y in vs):
                    field.append(("tri", vs, size))
            else:
                if in_face(cx, cy, 2.5) and not near_bracket(cx, cy):
                    field.append(("dot", (cx, cy), size))

# corner brackets (L channels) with the mounting hole in each elbow
BRACKETS = []
for ex, ey in BR_ELBOWS:
    sx = 1 if ex > 0 else -1
    sy = 1 if ey > 0 else -1
    BRACKETS.append(("h", (ex - 28 * sx, ey), (ex, ey)))
    BRACKETS.append(("v", (ex, ey), (ex, ey - 14 * sy)))
HOLES = BR_ELBOWS

lockup, lockup_modes, LW, LH = load_lockup(150.0)

# ------------------------------------------------------------ preview
S = 6.0
W, Hpx = int(224 * S), int(120 * S)
img = Image.new("RGB", (W, Hpx), (18, 24, 32))
d = ImageDraw.Draw(img)


def px(p):
    return (W / 2 + p[0] * S, Hpx / 2 - p[1] * S)


def poly(pts, fill, outline=None):
    d.polygon([px(p) for p in pts], fill=fill, outline=outline)


# depth palette (lighter = higher)
C_RIM = (208, 210, 214)
C_PODIUM = (188, 191, 196)
C_S1 = (168, 172, 178)
C_S2 = (148, 153, 160)
C_POCKET = (86, 92, 100)
C_LOGO = (240, 242, 245)
C_HOLE = (40, 44, 50)

# body silhouette (octagon rounded approx + scoops)
oct_pts = []
for i in range(len(OCT)):
    a = OCT[i]
    b = OCT[(i + 1) % len(OCT)]
    for t in (0.08, 0.5, 0.92):
        oct_pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
poly(oct_pts, C_RIM)
for cx, cy, r in SCOOPS:
    d.ellipse([px((cx - r, cy + r)), px((cx + r, cy - r))], fill=(18, 24, 32))

# terraces (drawn inside the inset region, coarse preview clip)
def clipped_rect(y0, y1, color):
    # simple horizontal band clipped against inset octagon x-limit per y
    band = []
    for yy in (y0, y1):
        lim = min(96.0, 120.686 - abs(yy) - 8 * 1.414)
        band.append(lim)
    poly([(-band[0], y0), (band[0], y0), (band[1], y1), (-band[1], y1)], color)


for sy in (1, -1):
    clipped_rect(20 * sy, 33 * sy, C_S1)
    clipped_rect(33 * sy, 46 * sy, C_S2)
for cx, cy, r in SCOOPS:  # rim ring back on top, then the void
    d.ellipse([px((cx - r - 8, cy + r + 8)), px((cx + r + 8, cy - r - 8))],
              fill=C_RIM)
    d.ellipse([px((cx - r, cy + r)), px((cx + r, cy - r))], fill=(18, 24, 32))

# podium
poly([(-88, -20), (88, -20), (88, 20), (-88, 20)], C_PODIUM)

# field
for kind, g, R in field:
    if kind == "tri":
        col = C_POCKET
        poly(g, col)
    else:
        cx, cy = g
        d.ellipse([px((cx - R, cy + R)), px((cx + R, cy - R))], fill=C_POCKET)

# brackets
for kind, a, b in BRACKETS:
    w = 2.6
    if kind == "h":
        y = a[1]
        d.rounded_rectangle([px((min(a[0], b[0]) - w, y + w)),
                             px((max(a[0], b[0]) + w, y - w))],
                            radius=w * S, fill=C_POCKET)
    else:
        x = a[0]
        d.rounded_rectangle([px((x - w, max(a[1], b[1]) + w)),
                             px((x + w, min(a[1], b[1]) - w))],
                            radius=w * S, fill=C_POCKET)

# lockup raised on podium
for sub, mode in zip(lockup, lockup_modes):
    poly(sub, C_LOGO if mode == "add" else C_PODIUM)

# mounting holes (inside the bracket elbows)
for hx, hy in HOLES:
    d.ellipse([px((hx - 2.1, hy + 2.1)), px((hx + 2.1, hy - 2.1))], fill=C_HOLE)

out = r"c:\Users\VasanSeenivasan\Desktop\textcad\designs\autonomiq-panel-preview.png"
img.save(out)
tris = sum(1 for k, *_ in field if k == "tri")
dots = sum(1 for k, *_ in field if k == "dot")
print(f"preview saved: {out}")
print(f"lockup: {len(lockup)} regions ({lockup_modes.count('subtract')} holes),"
      f" {LW:.1f} x {LH:.1f} mm | field: {tris} tris + {dots} dots")
