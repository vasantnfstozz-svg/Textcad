"""autonomiQ panel v4 — tree builder. Reuses the layout from
autonomiq-panel-v4.py (exec'd; also refreshes the preview PNG) and emits
designs/autonomiq-panel-tree.json.

Stack: rim 10 / lockup 10 (raised) / podium 9.5 / strip1 9.2 / strip2 8.9;
row A tris engraved to 8.0, row B to 7.7, dots to 8.3; brackets to 7.7;
4 through holes in the bracket elbows.
"""
import json
import math
import re

_ns = {}
exec(open(r"c:\Users\VasanSeenivasan\Desktop\textcad\designs\autonomiq-panel-v4.py",
          encoding="utf-8").read(), _ns)
field = _ns["field"]
BR_ELBOWS = _ns["BR_ELBOWS"]
OCT = _ns["OCT"]
parse_d = _ns["parse_d"]
point_in_poly = _ns["point_in_poly"]
SVG_FILE = _ns["SVG_FILE"]
KEEP = _ns["KEEP"]

INSET = [(-96, 24.686), (-96, -24.686), (-74.686, -46), (74.686, -46),
         (96, -24.686), (96, 24.686), (74.686, 46), (-74.686, 46)]


def _ccw(pts):
    a = sum((pts[i][0] - pts[i - 1][0]) * (pts[i][1] + pts[i - 1][1])
            for i in range(len(pts)))
    return pts if a < 0 else pts[::-1]


def _decimate(pts, min_d=0.25):
    out = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= min_d:
            out.append(p)
    if math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < min_d and len(out) > 3:
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
    return grouped


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


F = []
def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


f("outline_sketch", "sketch", {"plane": "XY", "offset": 0,
                               "entities": [rounded_path_e(OCT, 12)]})
f("blank", "extrude", {"amount": 10}, ["outline_sketch"])
f("scoop_sketch", "sketch", {"plane": "XY", "offset": -1, "entities": [
    {"kind": "circle", "r": 60, "x": 0, "y": 108, "mode": "add"},
    {"kind": "circle", "r": 60, "x": 0, "y": -108, "mode": "add"}]})
f("scoop_tool", "extrude", {"amount": 12}, ["scoop_sketch"])
f("scoop_cut", "cut", {}, ["blank", "scoop_tool"])

prev = "scoop_cut"
for idx, (offset, mid) in enumerate(((9.5, 0), (9.2, 20), (8.9, 33)), start=1):
    ents = [rounded_path_e(INSET, 8),
            {"kind": "circle", "r": 68, "x": 0, "y": 108, "mode": "subtract"},
            {"kind": "circle", "r": 68, "x": 0, "y": -108, "mode": "subtract"}]
    if mid:
        ents.append({"kind": "rectangle", "w": 210, "h": mid * 2,
                     "x": 0, "y": 0, "mode": "subtract"})
    f(f"skim{idx}_sketch", "sketch", {"plane": "XY", "offset": offset,
                                      "entities": ents})
    f(f"skim{idx}_tool", "extrude", {"amount": 2}, [f"skim{idx}_sketch"])
    f(f"skim{idx}_cut", "cut", {}, [prev, f"skim{idx}_tool"])
    prev = f"skim{idx}_cut"

lock_groups = load_lockup_grouped(150.0)
batches, batch = [], []
for g in lock_groups:
    if len(batch) + len(g) > 10:
        batches.append(batch)
        batch = []
    batch += g
batches.append(batch)
lock_ids = []
for n, b in enumerate(batches):
    f(f"lockup_sketch_{n}", "sketch", {"plane": "XY", "offset": 9.3,
                                       "entities": b})
    f(f"lockup_tool_{n}", "extrude", {"amount": 0.7}, [f"lockup_sketch_{n}"])
    lock_ids.append(f"lockup_tool_{n}")
f("lockup_fuse", "fuse", {}, [prev] + lock_ids)
prev = "lockup_fuse"

rowA = [g for k, g, R in field if k == "tri" and abs(g[0][1]) < 33]
rowB = [g for k, g, R in field if k == "tri" and abs(g[0][1]) >= 33]
dots = [g for k, g, R in field if k == "dot"]
for name, items, off in (("rowA", rowA, 8.0), ("rowB", rowB, 7.7)):
    ids = []
    for i in range(0, len(items), 10):
        n = i // 10
        ents = [rounded_path_e(vs, 1.6) for vs in items[i:i + 10]]
        f(f"{name}_sketch_{n}", "sketch", {"plane": "XY", "offset": off,
                                           "entities": ents})
        f(f"{name}_tool_{n}", "extrude", {"amount": 3}, [f"{name}_sketch_{n}"])
        ids.append(f"{name}_tool_{n}")
    f(f"{name}_cut", "cut", {}, [prev] + ids)
    prev = f"{name}_cut"
dot_ids = []
for i in range(0, len(dots), 10):
    n = i // 10
    ents = [{"kind": "circle", "r": 1.5, "x": round(c[0], 3),
             "y": round(c[1], 3), "mode": "add"} for c in dots[i:i + 10]]
    f(f"dots_sketch_{n}", "sketch", {"plane": "XY", "offset": 8.3,
                                     "entities": ents})
    f(f"dots_tool_{n}", "extrude", {"amount": 3}, [f"dots_sketch_{n}"])
    dot_ids.append(f"dots_tool_{n}")
f("dots_cut", "cut", {}, [prev] + dot_ids)
prev = "dots_cut"

br = []
for ex, ey in BR_ELBOWS:
    sx = 1 if ex > 0 else -1
    sy = 1 if ey > 0 else -1
    br.append({"kind": "slot", "length": 28, "height": 5.2,
               "x": round(ex - 14 * sx, 3), "y": ey, "rotation": 0, "mode": "add"})
    br.append({"kind": "slot", "length": 14, "height": 5.2,
               "x": ex, "y": round(ey - 7 * sy, 3), "rotation": 90, "mode": "add"})
f("bracket_sketch", "sketch", {"plane": "XY", "offset": 7.7, "entities": br})
f("bracket_tool", "extrude", {"amount": 3}, ["bracket_sketch"])
f("bracket_cut", "cut", {}, [prev, "bracket_tool"])
f("hole_sketch", "sketch", {"plane": "XY", "offset": -1, "entities": [
    {"kind": "circle", "r": 2.1, "x": ex, "y": ey, "mode": "add"}
    for ex, ey in BR_ELBOWS]})
f("hole_tool", "extrude", {"amount": 12}, ["hole_sketch"])
f("autonomiq_panel", "cut", {}, ["bracket_cut", "hole_tool"])

tree = {"name": "autonomiq-panel", "features": F,
        "spec": {"n_solids": 1, "size": [208, 108, 10],
                 "holes": {"2.1": 4}, "tol": 0.05}}
open(r"c:\Users\VasanSeenivasan\Desktop\textcad\designs\autonomiq-panel-tree.json",
     "w").write(json.dumps(tree))
print(f"TREE: features={len(F)} lockup_batches={len(batches)}"
      f" rowA={len(rowA)} rowB={len(rowB)} dots={len(dots)}"
      f" lockup_pts={sum(len(e['points']) for b in batches for e in b)}")
