"""autonomiQ panel — stealth-octagon showcase plate (DATRON-NEO-style, cooler).

208x108x10 steel, vacuum-safe (all engraving blind):
- outline: rounded stealth octagon (r12) with two shallow arc scoops (r60)
- rim: 8mm border at full height; inner face skimmed 0.6 (floor z9.4)
- field: wall-to-wall triangle lattice (pitch 17, rib 1.8, r1.6 corners),
  engraved 1.5 into the skim floor; spot dimple at every lattice node
- center band: engraved frame + "autonomiQ" in a single-stroke channel
  font (3.5 wide, 1.2 deep), capital Q taller
- 4 mounting holes on the corner-facet rim
Writes the COMPLETE build tree to autonomiq-panel-tree.json.
"""
import json
import math

RC = 1.6
PITCH, RIB = 12.0, 1.8
H = PITCH * math.sqrt(3) / 2
R_TRI = PITCH / math.sqrt(3) - RIB
BAND = 17.5                       # text band half-height (field keep-out)
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
    """Inside the skim region shrunk by margin m beyond the 8mm rim inset."""
    if abs(x) > 96 - m or abs(y) > 46 - m:
        return False
    if abs(x) + abs(y) > 120.686 - m * math.sqrt(2):
        return False
    for cx, cy, r in SCALLOPS:
        if math.hypot(x - cx, y - cy) < r + 8 + m:
            return False
    return True


# ---- triangle field (whole face except the text band)
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

# ---- node dimples at lattice vertices
dimples = []
for j in range(-6, 7):
    for i in range(-13, 14):
        x = i * PITCH + (j % 2) * PITCH / 2 - PITCH / 2
        y = j * H
        if in_field(x, y, 4.0) and abs(y) >= BAND + 1.5:
            dimples.append({"kind": "circle", "r": 1.25,
                            "x": round(x, 3), "y": round(y, 3), "mode": "add"})

# ---- stroke font: a u t o n o m i Q  (channel width 3.5, x-height 13)
W = 3.5
DY = -2.6          # vertical centering shift


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
    """Return (entities, advance) for glyph at pen position x."""
    e = []
    if ch == "o":
        e = [circ(x + 6.5, 0, 6.5), circ(x + 6.5, 0, 3, "subtract")]
        return e, 13
    if ch == "a":
        e = [circ(x + 6.5, 0, 6.5), circ(x + 6.5, 0, 3, "subtract"),
             slot(x + 11.25, 0, 13, 90)]
        return e, 13
    if ch == "u":
        e = [circ(x + 6.5, 0, 6.5), circ(x + 6.5, 0, 3, "subtract"),
             rect(x + 6.5, 4, 13.2, 8, "subtract"),      # keep lower half
             slot(x + 1.75, 1.75, 9.5, 90),               # left stem
             slot(x + 11.25, 0, 13, 90)]                  # right stem full
        return e, 13
    if ch == "t":
        e = [slot(x + 1.75, 1.25, 15.5, 90),              # stem to ascender
             slot(x + 2.5, 4.75, 9, 0)]                   # crossbar
        return e, 7
    if ch == "n":
        e = [circ(x + 6.5, 0, 6.5), circ(x + 6.5, 0, 3, "subtract"),
             rect(x + 6.5, -4, 13.2, 8, "subtract"),      # keep upper half
             slot(x + 1.75, 0, 13, 90),                   # left stem full
             slot(x + 11.25, -2.75, 7.5, 90)]             # right stem down
        return e, 13
    if ch == "m":
        e = [circ(x + 5.25, 1.25, 5.25), circ(x + 5.25, 1.25, 1.75, "subtract"),
             rect(x + 5.25, -3.75, 10.7, 10, "subtract"),
             circ(x + 15.75, 1.25, 5.25), circ(x + 15.75, 1.25, 1.75, "subtract"),
             rect(x + 15.75, -3.75, 10.7, 10, "subtract"),
             slot(x + 1.75, 0, 13, 90),
             slot(x + 10.5, -2.25, 8.5, 90),
             slot(x + 19.25, -2.25, 8.5, 90)]
        return e, 21
    if ch == "i":
        e = [slot(x + 1.75, 0, 13, 90), circ(x + 1.75, 10, 1.75)]
        return e, 3.5
    if ch == "Q":
        e = [circ(x + 8.5, 2, 8.5), circ(x + 8.5, 2, 5, "subtract"),
             slot(x + 14, -3.5, 9, -45)]
        return e, 18
    raise ValueError(ch)


word = "autonomiQ"
SPACING = 4.5
adv_total = 0
for ch in word:
    adv_total += glyph(ch, 0)[1] + SPACING
adv_total -= SPACING
pen = -adv_total / 2
glyph_batches, batch = [], []
for ch in word:
    ents, adv = glyph(ch, pen)
    if len(batch) + len(ents) > 10:
        glyph_batches.append(batch)
        batch = []
    batch += ents
    pen += adv + SPACING
glyph_batches.append(batch)

# ---- assemble tree
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
f("skim_sketch", "sketch", {"plane": "XY", "offset": 9.4, "entities": [
    rounded_path(INSET, 8),
    {"kind": "circle", "r": 68, "x": 0, "y": 108, "mode": "subtract"},
    {"kind": "circle", "r": 68, "x": 0, "y": -108, "mode": "subtract"}]})
f("skim_tool", "extrude", {"amount": 2}, ["skim_sketch"])
f("skim_cut", "cut", {}, ["scoop_cut", "skim_tool"])
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
f("frame_sketch", "sketch", {"plane": "XY", "offset": 8.6, "entities": [
    rounded_path([(-89, -16.5), (89, -16.5), (89, 16.5), (-89, 16.5)], 4),
    dict(rounded_path([(-85.5, -13), (85.5, -13), (85.5, 13), (-85.5, 13)], 2.5),
         mode="subtract")]})
f("frame_tool", "extrude", {"amount": 3}, ["frame_sketch"])
f("frame_cut", "cut", {}, ["dimple_cut", "frame_tool"])
g_ids = []
for n, b in enumerate(glyph_batches):
    f(f"glyph_sketch_{n}", "sketch", {"plane": "XY", "offset": 8.2, "entities": b})
    f(f"glyph_tool_{n}", "extrude", {"amount": 3}, [f"glyph_sketch_{n}"])
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
print(f"tris={len(tris)} dimples={len(dimples)} glyph_batches={len(glyph_batches)}"
      f" features={len(F)} word_width={adv_total:.1f}")
