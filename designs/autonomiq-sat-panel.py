"""autonomiq-sat-panel — the sat-side-panel structure the user loves,
with a company-logo pyramid at its heart.

Base: designs/sat-side-panel.tcad.json feature tree, UNCHANGED except the
center medallion (boss pocket + bolt ring) and the X-slots are removed to
clear the stage. In their place:
  - circular arena pocket (floor z=5.5) carved into the 10mm face
  - a TRUE 4-facet diamond pyramid (loft) rising from the arena floor
    back up to a flat cap at z=9.3
  - the compact iQ brand mark (segmented i + magnifier Q from the
    official SVG) raised 0.7 on the cap, apex flush with the face at 10.0
Small, centered, symmetric — the plate stays the hero.

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
KEEP = set(range(0, 6)) | {29, 30, 31, 32, 33}

Z_FLOOR, Z_CAP, Z_TOP = 5.5, 9.3, 10.0
ARENA_R, HD_BASE, HD_CAP = 21.0, 18.0, 11.0


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


def load_iq_mark(max_width, max_reach):
    """The compact iQ mark: the RIGHT cluster of the lockup (segmented i +
    magnifier Q), scaled so the mark's corners stay on the pyramid cap:
    |x|+|y| <= max_reach for every point (diamond cap), width <= max_width."""
    ds = re.findall(r'[\s"]d="([^"]+)"', open(SVG_FILE, encoding="utf-8").read())
    groups = [parse_d(d) for idx, d in enumerate(ds) if idx in KEEP]
    allx = [p[0] for g in groups for s in g for p in s]
    x0, x1 = min(allx), max(allx)
    cut = x0 + 0.78 * (x1 - x0)   # word ends at 0.772; i at 0.79, Q at 0.836
    iq = [g for g in groups
          if min(p[0] for s in g for p in s) > cut]
    pts = [p for g in iq for s in g for p in s]
    mx0, mx1 = min(p[0] for p in pts), max(p[0] for p in pts)
    my0, my1 = min(p[1] for p in pts), max(p[1] for p in pts)
    w, h = mx1 - mx0, my1 - my0
    cx, cy = (mx0 + mx1) / 2, (my0 + my1) / 2
    # diamond-cap constraint: (w/2 + h/2) * s <= max_reach
    s = min(max_width / w, 2 * max_reach / (w + h))
    grouped = []
    for g in iq:
        subs = [[((p[0] - cx) * s, (p[1] - cy) * s) for p in sub] for sub in g]
        flags = [any(j != i and point_in_poly(sub[0], subs[j])
                     for j in range(len(subs)))
                 for i, sub in enumerate(subs)]
        ordered = ([(sub, False) for sub, hh in zip(subs, flags) if not hh]
                   + [(sub, True) for sub, hh in zip(subs, flags) if hh])
        ents = []
        for sub, hole in ordered:
            pp = _decimate(_ccw(sub))
            ents.append({"kind": "polygon",
                         "points": [[round(p[0], 3), round(p[1], 3)] for p in pp],
                         "mode": "subtract" if hole else "add"})
        grouped.append(ents)
    return grouped, w * s, h * s, len(iq)


# --------------------------------------------- base tree: sat-side-panel
base = json.load(open(ROOT + r"\designs\sat-side-panel.tcad.json"))
DROP_TOOLS = {"xslot_sketch", "xslot_tool", "boss_pocket_sketch",
              "boss_pocket_tool", "boss_bolt_sketch", "boss_bolt_tool"}
DROP_CUTS = {"xslot_cut", "boss_cut", "boss_bolt_cut"}


def resolve(fid, remap):
    while fid in remap:
        fid = remap[fid]
    return fid


remap = {}
by_id = {ft["id"]: ft for ft in base["features"]}
for fid in DROP_CUTS:
    remap[fid] = by_id[fid]["inputs"][0]

F = []
for ft in base["features"]:
    if ft["id"] in DROP_TOOLS or ft["id"] in DROP_CUTS:
        continue
    nf = {"id": ft["id"], "op": ft["op"], "params": dict(ft["params"]),
          "inputs": [resolve(i, remap) for i in ft.get("inputs", [])]}
    F.append(nf)

# clearance check: nearest triangle-pocket point vs the arena radius
tri_pts = []
for ft in F:
    if ft["id"].startswith("tri_sketch"):
        for e in ft["params"]["entities"]:
            tri_pts.append(tuple(e["start"]))
            tri_pts += [tuple(s["to"]) for s in e["segments"]]
min_tri = min(math.hypot(x, y) for x, y in tri_pts)
assert min_tri > ARENA_R + 1.5, f"arena {ARENA_R} too big: tri at {min_tri:.1f}"


def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


def diamond(hd):
    return [[hd, 0], [0, hd], [-hd, 0], [0, -hd]]


last = F[-1]["id"]          # sat_panel (mount holes already cut)
f("arena_sketch", "sketch", {"plane": "XY", "offset": Z_FLOOR, "entities": [
    {"kind": "circle", "r": ARENA_R, "x": 0, "y": 0, "mode": "add"}]})
f("arena_tool", "extrude", {"amount": Z_TOP - Z_FLOOR + 1}, ["arena_sketch"])
f("arena_cut", "cut", {}, [last, "arena_tool"])

f("pyr_base_sketch", "sketch", {"plane": "XY", "offset": Z_FLOOR,
    "entities": [{"kind": "polygon", "mode": "add", "points": diamond(HD_BASE)}]})
f("pyr_cap_sketch", "sketch", {"plane": "XY", "offset": Z_CAP,
    "entities": [{"kind": "polygon", "mode": "add", "points": diamond(HD_CAP)}]})
f("logo_pyramid", "loft", {}, ["pyr_base_sketch", "pyr_cap_sketch"])

mark_groups, MW, MH, n_iq = load_iq_mark(11.0, HD_CAP - 1.5)
batches, batch = [], []
for g in mark_groups:
    if len(batch) + len(g) > 10:
        batches.append(batch)
        batch = []
    batch += g
batches.append(batch)
mark_ids = []
for n, b in enumerate(batches):
    f(f"iq_mark_sketch_{n}", "sketch", {"plane": "XY", "offset": Z_CAP,
                                        "entities": b})
    f(f"iq_mark_tool_{n}", "extrude", {"amount": Z_TOP - Z_CAP},
      [f"iq_mark_sketch_{n}"])
    mark_ids.append(f"iq_mark_tool_{n}")

f("autonomiq_sat_panel", "fuse", {},
  ["arena_cut", "logo_pyramid"] + mark_ids)

tree = {"name": "autonomiq-sat-panel", "features": F,
        "spec": {"n_solids": 1, "size": [208, 108, 10], "symmetry": 2,
                 "holes": {"2.25": 6}, "tol": 0.3}}
open(ROOT + r"\designs\autonomiq-sat-panel-tree.json", "w").write(json.dumps(tree))

# ------------------------------------------------------------- preview
S = 6.0
W, HT = int(224 * S), int(120 * S)
EH = 240
img = Image.new("RGB", (W, HT + EH), (18, 24, 32))
d = ImageDraw.Draw(img)


def px(p):
    return (W / 2 + p[0] * S, HT / 2 - p[1] * S)


C_FACE = (176, 180, 186)
C_POCKET = (86, 92, 100)
C_FLOOR = (70, 76, 84)
C_CAP = (205, 209, 215)
C_MARK = (240, 242, 245)
C_HOLE = (40, 44, 50)
BG = (18, 24, 32)

# plate silhouette: rect minus scallops (from the base tree's own entities)
d.rectangle([px((-104, 54)), px((104, -54))], fill=C_FACE)
for ft in base["features"]:
    if ft["id"] == "scallop_sketch":
        for e in ft["params"]["entities"]:
            d.ellipse([px((e["x"] - e["r"], e["y"] + e["r"])),
                       px((e["x"] + e["r"], e["y"] - e["r"]))], fill=BG)
for ft in F:
    if ft["id"].startswith("tri_sketch"):
        for e in ft["params"]["entities"]:
            pts = [tuple(e["start"])] + [tuple(s["to"]) for s in e["segments"]]
            d.polygon([px(p) for p in pts], fill=C_POCKET)
for ft in base["features"]:
    if ft["id"] == "mount_hole_sketch":
        for e in ft["params"]["entities"]:
            d.ellipse([px((e["x"] - e["r"], e["y"] + e["r"])),
                       px((e["x"] + e["r"], e["y"] - e["r"]))], fill=C_HOLE)

# center: arena, pyramid facets, cap, mark
d.ellipse([px((-ARENA_R, ARENA_R)), px((ARENA_R, -ARENA_R))], fill=C_FLOOR)
E, N, Wd, Sd = (HD_BASE, 0), (0, HD_BASE), (-HD_BASE, 0), (0, -HD_BASE)
d.polygon([px(E), px(N), px((0, HD_CAP)), px((HD_CAP, 0))], fill=(205, 209, 215))
d.polygon([px(N), px(Wd), px((-HD_CAP, 0)), px((0, HD_CAP))], fill=(180, 184, 190))
d.polygon([px(Wd), px(Sd), px((0, -HD_CAP)), px((-HD_CAP, 0))], fill=(120, 126, 134))
d.polygon([px(Sd), px(E), px((HD_CAP, 0)), px((0, -HD_CAP))], fill=(150, 156, 163))
d.polygon([px((HD_CAP, 0)), px((0, HD_CAP)), px((-HD_CAP, 0)), px((0, -HD_CAP))],
          fill=C_CAP)
for grp in mark_groups:
    for e in grp:
        d.polygon([px(tuple(p)) for p in e["points"]],
                  fill=C_MARK if e["mode"] == "add" else C_CAP)

# section through y=0
ZS, Y0 = 18.0, HT + EH - 30


def pxe(x, z):
    return (W / 2 + x * S * 1.6, Y0 - z * ZS)


def sec_z(x):
    ax = abs(x)
    if ax > 104:
        return 0
    if ax > ARENA_R:
        return Z_TOP
    if ax > HD_BASE:
        return Z_FLOOR
    if ax <= MW / 2:
        top = Z_TOP           # mark region (schematic)
    else:
        top = Z_CAP
    if ax <= HD_CAP:
        return top
    return Z_FLOOR + (Z_CAP - Z_FLOOR) * (HD_BASE - ax) / (HD_BASE - HD_CAP)


sil = [pxe(-104, 0)]
xx = -104.0
while xx <= 104.0:
    sil.append(pxe(xx, sec_z(xx)))
    xx += 0.2
sil.append(pxe(104, 0))
d.polygon(sil, fill=(150, 155, 162))
for z, lab in ((Z_FLOOR, "5.5"), (Z_CAP, "9.3"), (Z_TOP, "10.0")):
    d.line([pxe(-110, z), pxe(110, z)], fill=(70, 78, 90), width=1)
    d.text((pxe(-118, z)[0], pxe(-118, z)[1] - 5), lab, fill=(200, 205, 212))
d.text((W / 2 - 200, HT + 8),
       "SECTION AT Y=0 - logo pyramid rising from the arena, z in mm",
       fill=(255, 120, 80))

out = ROOT + r"\designs\autonomiq-sat-panel-preview.png"
img.save(out)
print(f"preview: {out}")
print(f"tree: {len(F)} features | iQ mark: {n_iq} groups, "
      f"{MW:.1f} x {MH:.1f} mm | arena r{ARENA_R} (nearest tri {min_tri:.1f}) "
      f"| pyramid hd {HD_BASE}->{HD_CAP}, z {Z_FLOOR}->{Z_CAP}, mark to {Z_TOP}")

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
