"""autonomiQ panel v2 — stealth-octagon showcase plate.

v2 changes (user feedback + their iQ logo SVG):
- brand: "autonom" in the fixed stroke font + the REAL iQ mark converted
  from the company SVG (cubic Beziers -> arc-fitted sketch paths)
- font fixes: 'a' = small bowl + distinct full-height stem; 't' = crossbar
  at the x-line with a short ascender; tighter 't' advance
- staircase: scoop edges get 3 depth steps (10 -> 9.8 -> 9.6 -> void);
  the whole text band is recessed 0.4 as its own plateau (floor 9.0)
Depth stack: rim 10 / steps 9.8, 9.6 / face 9.4 / band 9.0 / dimples 8.6 /
frame 8.4 / triangles 7.9 / lettering 7.8.  All engraving blind.
"""
import json
import math
import re

RC = 1.6
PITCH, RIB = 12.0, 1.8
H = PITCH * math.sqrt(3) / 2
R_TRI = PITCH / math.sqrt(3) - RIB
BAND = 17.5
SCALLOPS = [(0, 108, 60), (0, -108, 60)]


def rp(v):
    return [round(v[0], 3), round(v[1], 3)]


def rounded_path(verts, r=RC):
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
        d = r / math.sin(ang / 2)
        corners.append(((v[0] - ui[0] * t, v[1] - ui[1] * t),
                        (v[0] + b[0] * (d - r), v[1] + b[1] * (d - r)),
                        (v[0] + uo[0] * t, v[1] + uo[1] * t)))
    first = corners[0][2]
    segs = []
    for i in list(range(1, n)) + [0]:
        a_in, via, a_out = corners[i]
        segs.append({"type": "line", "to": rp(a_in)})
        segs.append({"type": "arc", "via": rp(via),
                     "to": rp(first if i == 0 else a_out)})
    return {"kind": "path", "mode": "add", "start": rp(first), "segments": segs}


OCT = [(-104, 28), (-104, -28), (-78, -54), (78, -54),
       (104, -28), (104, 28), (78, 54), (-78, 54)]
INSET = [(-96, 24.686), (-96, -24.686), (-74.686, -46), (74.686, -46),
         (96, -24.686), (96, 24.686), (74.686, 46), (-74.686, 46)]


def in_field(x, y, m):
    if abs(x) > 96 - m or abs(y) > 46 - m:
        return False
    if abs(x) + abs(y) > 120.686 - m * math.sqrt(2):
        return False
    for cx, cy, r in SCALLOPS:
        if math.hypot(x - cx, y - cy) < r + 8 + m:
            return False
    return True


tris = []
for j in range(-8, 8):
    y_up = j * H + H / 3
    for i in range(-14, 14):
        x_up = i * PITCH + (j % 2) * PITCH / 2
        for cx, cy, up in ((x_up, y_up, True), (x_up + PITCH / 2, y_up + H / 3, False)):
            angles = (90, 210, 330) if up else (270, 30, 150)
            vs = [(cx + R_TRI * math.cos(math.radians(a)),
                   cy + R_TRI * math.sin(math.radians(a))) for a in angles]
            if all(in_field(x, y, 2.5) for x, y in vs):
                ys = [y for _, y in vs]
                if all(y >= BAND for y in ys) or all(y <= -BAND for y in ys):
                    tris.append(rounded_path(vs))

dimples = []
for j in range(-6, 7):
    for i in range(-13, 14):
        x = i * PITCH + (j % 2) * PITCH / 2 - PITCH / 2
        y = j * H
        if in_field(x, y, 4.0) and abs(y) >= BAND + 1.5:
            dimples.append({"kind": "circle", "r": 1.25,
                            "x": round(x, 3), "y": round(y, 3), "mode": "add"})

# ------------------------------------------------------------------ font
W = 3.5
DY = -2.6


def slot(cx, cy, length, rot):
    return {"kind": "slot", "length": round(length, 3), "height": W,
            "x": round(cx, 3), "y": round(cy + DY, 3),
            "rotation": rot, "mode": "add"}


def circ(cx, cy, r, mode="add"):
    return {"kind": "circle", "r": round(r, 3), "x": round(cx, 3),
            "y": round(cy + DY, 3), "mode": mode}


def rect(cx, cy, w, h, mode):
    return {"kind": "rectangle", "w": round(w, 3), "h": round(h, 3),
            "x": round(cx, 3), "y": round(cy + DY, 3), "mode": mode}


def glyph(ch, x):
    if ch == "o":
        return [circ(x + 6.5, 0, 6.5), circ(x + 6.5, 0, 3, "subtract")], 13
    if ch == "a":     # small bowl + distinct full-height stem
        return [circ(x + 5.5, -1, 5.5), circ(x + 5.5, -1, 2, "subtract"),
                slot(x + 11.25, 0, 13, 90)], 13
    if ch == "u":
        return [circ(x + 6.5, 0, 6.5), circ(x + 6.5, 0, 3, "subtract"),
                rect(x + 6.5, 4, 13.2, 8, "subtract"),
                slot(x + 1.75, 1.75, 9.5, 90),
                slot(x + 11.25, 0, 13, 90)], 13
    if ch == "t":     # crossbar ON the x-line, short ascender
        return [slot(x + 1.75, 0.75, 14.5, 90),
                slot(x + 2, 6.5, 9, 0)], 6.5
    if ch == "n":
        return [circ(x + 6.5, 0, 6.5), circ(x + 6.5, 0, 3, "subtract"),
                rect(x + 6.5, -4, 13.2, 8, "subtract"),
                slot(x + 1.75, 0, 13, 90),
                slot(x + 11.25, -2.75, 7.5, 90)], 13
    if ch == "m":
        return [circ(x + 5.25, 1.25, 5.25), circ(x + 5.25, 1.25, 1.75, "subtract"),
                rect(x + 5.25, -3.75, 10.7, 10, "subtract"),
                circ(x + 15.75, 1.25, 5.25), circ(x + 15.75, 1.25, 1.75, "subtract"),
                rect(x + 15.75, -3.75, 10.7, 10, "subtract"),
                slot(x + 1.75, 0, 13, 90),
                slot(x + 10.5, -2.25, 8.5, 90),
                slot(x + 19.25, -2.25, 8.5, 90)], 21
    raise ValueError(ch)


# --------------------------------------------------------- iQ mark (SVG)
IQ_D = """M 371.00,402.00 C 306.55,427.77 225.19,419.73 174.04,369.91
121.67,318.91 111.94,229.40 146.31,166.00 158.49,143.53 174.89,125.55
196.00,111.19 222.76,92.99 253.96,84.36 286.00,82.96 286.00,82.96
297.00,82.01 297.00,82.01 297.00,82.01 307.00,82.91 307.00,82.91
307.00,82.91 326.00,84.28 326.00,84.28 359.87,88.61 391.68,103.30
417.00,126.17 478.49,181.71 485.39,292.89 432.00,356.00 438.24,359.62
447.14,367.41 453.00,372.25 461.66,379.41 466.98,380.44 467.00,392.00
467.00,392.00 467.00,444.00 467.00,444.00 467.00,444.00 418.00,404.25
418.00,404.25 418.00,404.25 339.00,339.42 339.00,339.42 339.00,339.42
311.00,316.58 311.00,316.58 303.08,310.08 299.02,309.38 299.00,299.00
299.00,299.00 299.00,248.00 299.00,248.00 305.89,250.70 320.52,263.90
327.00,269.25 327.00,269.25 386.00,317.00 386.00,317.00 386.00,317.00
394.80,298.00 394.80,298.00 400.05,284.74 403.83,268.30 404.00,254.00
404.23,234.44 401.53,216.19 393.99,198.00 386.54,180.05 372.27,161.77
356.00,151.08 320.57,127.79 266.72,128.15 233.00,154.67 183.24,193.80
176.33,275.45 214.24,325.00 230.96,346.87 257.28,362.01 285.00,363.87
292.43,364.42 301.61,364.54 309.00,363.87 312.41,363.51 320.13,361.73
323.00,362.63 326.02,363.58 335.06,371.48 338.00,373.92 345.33,380.00
366.25,395.91 371.00,402.00 Z M 32.00,83.00 C 32.00,83.00 84.00,83.00
84.00,83.00 92.64,83.02 92.98,83.36 93.00,92.00 93.00,92.00 93.00,307.00
93.00,307.00 86.94,304.27 80.25,297.78 75.00,293.41 75.00,293.41
45.00,268.25 45.00,268.25 36.59,261.24 32.02,260.32 32.00,249.00
32.00,249.00 32.00,83.00 32.00,83.00 Z M 32.00,291.00 C 38.15,293.62
44.78,300.02 50.00,304.42 50.00,304.42 80.00,329.73 80.00,329.73
88.34,336.84 92.98,337.53 93.00,349.00 93.00,349.00 93.00,380.00
93.00,380.00 86.96,376.78 80.39,370.57 75.00,366.08 75.00,366.08
46.00,341.92 46.00,341.92 37.46,334.79 32.02,333.50 32.00,322.00
32.00,322.00 32.00,291.00 32.00,291.00 Z M 32.00,364.00 C 38.05,366.06
43.10,371.51 48.00,375.59 48.00,375.59 79.00,401.59 79.00,401.59
84.03,405.77 91.86,410.25 93.00,417.00 93.00,417.00 33.00,417.00
33.00,417.00 33.00,417.00 33.00,384.00 33.00,384.00 33.00,384.00
32.00,364.00 32.00,364.00 Z"""


def parse_svg(d):
    tok = re.findall(r"[MCZz]|-?\d+\.?\d*", d)
    subs, cur, i = [], None, 0
    while i < len(tok):
        t = tok[i]
        if t == "M":
            cur = {"start": (float(tok[i + 1]), float(tok[i + 2])), "cubics": []}
            subs.append(cur)
            i += 3
        elif t == "C":
            i += 1
            while i + 5 < len(tok) and re.match(r"-?\d", tok[i]):
                cur["cubics"].append(tuple(float(tok[i + k]) for k in range(6)))
                i += 6
        else:
            i += 1
    return subs


def bez(p0, c, t):
    x = ((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * c[0]
         + 3 * (1 - t) * t ** 2 * c[2] + t ** 3 * c[4])
    y = ((1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * c[1]
         + 3 * (1 - t) * t ** 2 * c[3] + t ** 3 * c[5])
    return (x, y)


def iq_mark_entities(pen_x):
    """Convert the SVG (y-down, units) into engraving path entities."""
    S_ = 19.0 / (417.0 - 82.0)                   # cap height 19mm
    def tf(p):
        return (pen_x + (p[0] - 32.0) * S_, -6.5 + DY + (417.0 - p[1]) * S_)
    ents = []
    for sub in parse_svg(IQ_D):
        pts = [tf(sub["start"])]
        segs = []
        cur = sub["start"]
        for c in sub["cubics"]:
            p0 = cur
            sam = [bez(p0, c, t) for t in (0.25, 0.5, 0.75)]
            end = (c[4], c[5])
            for a, b in ((sam[0], sam[1]), (sam[2], end)):
                pa, pv, pb = tf(p0), tf(a), tf(b)
                if math.hypot(pb[0] - pa[0], pb[1] - pa[1]) < 0.08:
                    p0 = b if b == end else p0
                    continue
                cross = abs((pv[0] - pa[0]) * (pb[1] - pa[1])
                            - (pv[1] - pa[1]) * (pb[0] - pa[0]))
                if cross < 0.02:
                    segs.append({"type": "line", "to": rp(pb)})
                else:
                    segs.append({"type": "arc", "via": rp(pv), "to": rp(pb)})
                p0 = b
            cur = end
        ents.append({"kind": "path", "mode": "add",
                     "start": rp(tf(sub["start"])), "segments": segs})
    width = (467.0 - 32.0) * S_
    return ents, width


word = "autonom"
SPACING = 4.5
MARK_GAP = 5.0
adv_total = sum(glyph(ch, 0)[1] + SPACING for ch in word) - SPACING
_, mark_w = iq_mark_entities(0)
total = adv_total + MARK_GAP + mark_w
pen = -total / 2
glyph_batches, batch = [], []
for ch in word:
    ents, adv = glyph(ch, pen)
    if len(batch) + len(ents) > 10:
        glyph_batches.append(batch)
        batch = []
    batch += ents
    pen += adv + SPACING
glyph_batches.append(batch)
mark_ents, _ = iq_mark_entities(pen + MARK_GAP - SPACING)
glyph_batches.append(mark_ents)

# ------------------------------------------------------------------ tree
F = []
def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})

f("outline_sketch", "sketch", {"plane": "XY", "offset": 0,
                               "entities": [rounded_path(OCT, 12)]})
f("body", "extrude", {"amount": 10}, ["outline_sketch"])
f("scoop_sketch", "sketch", {"plane": "XY", "offset": -1, "entities": [
    {"kind": "circle", "r": 60, "x": 0, "y": 108, "mode": "add"},
    {"kind": "circle", "r": 60, "x": 0, "y": -108, "mode": "add"}]})
f("scoop_tool", "extrude", {"amount": 12}, ["scoop_sketch"])
f("scoop_cut", "cut", {}, ["body", "scoop_tool"])
# staircase steps on the scoop rims: 10 -> 9.8 -> 9.6 -> void
f("step1_sketch", "sketch", {"plane": "XY", "offset": 9.8, "entities": [
    {"kind": "circle", "r": 65.4, "x": 0, "y": 108, "mode": "add"},
    {"kind": "circle", "r": 62.7, "x": 0, "y": 108, "mode": "subtract"},
    {"kind": "circle", "r": 65.4, "x": 0, "y": -108, "mode": "add"},
    {"kind": "circle", "r": 62.7, "x": 0, "y": -108, "mode": "subtract"}]})
f("step1_tool", "extrude", {"amount": 2}, ["step1_sketch"])
f("step1_cut", "cut", {}, ["scoop_cut", "step1_tool"])
f("step2_sketch", "sketch", {"plane": "XY", "offset": 9.6, "entities": [
    {"kind": "circle", "r": 62.7, "x": 0, "y": 108, "mode": "add"},
    {"kind": "circle", "r": 60, "x": 0, "y": 108, "mode": "subtract"},
    {"kind": "circle", "r": 62.7, "x": 0, "y": -108, "mode": "add"},
    {"kind": "circle", "r": 60, "x": 0, "y": -108, "mode": "subtract"}]})
f("step2_tool", "extrude", {"amount": 2}, ["step2_sketch"])
f("step2_cut", "cut", {}, ["step1_cut", "step2_tool"])
f("skim_sketch", "sketch", {"plane": "XY", "offset": 9.4, "entities": [
    rounded_path(INSET, 8),
    {"kind": "circle", "r": 68, "x": 0, "y": 108, "mode": "subtract"},
    {"kind": "circle", "r": 68, "x": 0, "y": -108, "mode": "subtract"}]})
f("skim_tool", "extrude", {"amount": 2}, ["skim_sketch"])
f("skim_cut", "cut", {}, ["step2_cut", "skim_tool"])
tri_ids = []
for i in range(0, len(tris), 10):
    n = i // 10
    f(f"tri_sketch_{n}", "sketch", {"plane": "XY", "offset": 7.9,
                                    "entities": tris[i:i + 10]})
    f(f"tri_tool_{n}", "extrude", {"amount": 4}, [f"tri_sketch_{n}"])
    tri_ids.append(f"tri_tool_{n}")
f("field_cut", "cut", {}, ["skim_cut"] + tri_ids)
dim_ids = []
for i in range(0, len(dimples), 10):
    n = i // 10
    f(f"dimple_sketch_{n}", "sketch", {"plane": "XY", "offset": 8.6,
                                       "entities": dimples[i:i + 10]})
    f(f"dimple_tool_{n}", "extrude", {"amount": 3}, [f"dimple_sketch_{n}"])
    dim_ids.append(f"dimple_tool_{n}")
f("dimple_cut", "cut", {}, ["field_cut"] + dim_ids)
# text band plateau (staircase level of its own)
f("band_sketch", "sketch", {"plane": "XY", "offset": 9.0, "entities": [
    rounded_path([(-89, -16.5), (89, -16.5), (89, 16.5), (-89, 16.5)], 4)]})
f("band_tool", "extrude", {"amount": 2}, ["band_sketch"])
f("band_cut", "cut", {}, ["dimple_cut", "band_tool"])
f("frame_sketch", "sketch", {"plane": "XY", "offset": 8.4, "entities": [
    rounded_path([(-86.5, -14.5), (86.5, -14.5), (86.5, 14.5), (-86.5, 14.5)], 3),
    dict(rounded_path([(-83, -11), (83, -11), (83, 11), (-83, 11)], 2),
         mode="subtract")]})
f("frame_tool", "extrude", {"amount": 3}, ["frame_sketch"])
f("frame_cut", "cut", {}, ["band_cut", "frame_tool"])
g_ids = []
for n, b in enumerate(glyph_batches):
    f(f"glyph_sketch_{n}", "sketch", {"plane": "XY", "offset": 7.8, "entities": b})
    f(f"glyph_tool_{n}", "extrude", {"amount": 3.4}, [f"glyph_sketch_{n}"])
    g_ids.append(f"glyph_tool_{n}")
f("text_cut", "cut", {}, ["frame_cut"] + g_ids)
f("mount_hole_sketch", "sketch", {"plane": "XY", "offset": -1, "entities": [
    {"kind": "circle", "r": 2.1, "x": 88.2, "y": 38.2, "mode": "add"},
    {"kind": "circle", "r": 2.1, "x": -88.2, "y": 38.2, "mode": "add"},
    {"kind": "circle", "r": 2.1, "x": -88.2, "y": -38.2, "mode": "add"},
    {"kind": "circle", "r": 2.1, "x": 88.2, "y": -38.2, "mode": "add"}]})
f("mount_hole_tool", "extrude", {"amount": 12}, ["mount_hole_sketch"])
f("autonomiq_panel", "cut", {}, ["text_cut", "mount_hole_tool"])

tree = {"name": "autonomiq-panel", "features": F,
        "spec": {"n_solids": 1, "size": [208, 108, 10],
                 "holes": {"2.1": 4}, "tol": 0.3}}
open(r"c:\Users\VasanSeenivasan\Desktop\textcad\designs\autonomiq-panel-tree.json",
     "w").write(json.dumps(tree))
seg_counts = [len(e["segments"]) for e in mark_ents]
print(f"tris={len(tris)} dimples={len(dimples)} glyph_batches={len(glyph_batches)}"
      f" features={len(F)} total_word_width={total:.1f} mark_segs={seg_counts}")
