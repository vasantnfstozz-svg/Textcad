"""X-braced satellite panel v2 — shaped outline, four pocket textures,
machinable corner radii (vacuum-safe: all pockets blind).

Outline: 208x108 base, semicircular lug end (right, r54 about (50,0)),
tapered tongue end (left, 45deg from (-70,+-54) to (-104,+-20)), 4 edge
scallops. Zones by X-brace quadrant: isogrid (top/bottom), hex honeycomb
(left), round pockets + small boss (right). ALL polygon pockets emitted as
paths with 1.6mm corner radii (O3 finish cutter).
"""
import json
import math

S = 46.0 / 96.0                     # X-brace slope
NORM = math.sqrt(1 + S * S)
XM = 6.0                            # perpendicular keep-out from X centerlines
RC = 1.6                            # pocket corner radius
PITCH, RIB = 16.0, 1.8
H = PITCH * math.sqrt(3) / 2
R_TRI = PITCH / math.sqrt(3) - RIB
SCALLOPS = [(52, 86, 40), (-52, 86, 40), (52, -86, 40), (-52, -86, 40)]
LUG_C, LUG_R = (50.0, 0.0), 54.0
LUG_HOLE = (94.0, 0.0)
BOSS1_CLEAR = 18.8


def d_lines(x, y):
    return (y - S * x) / NORM, (y + S * x) / NORM


def ok_common(x, y):
    if abs(y) > 44.5 or x > 96 or x < -100:
        return False
    for cx, cy, r in SCALLOPS:
        if math.hypot(x - cx, y - cy) < r + RIB:
            return False
    if math.hypot(x - LUG_C[0], y - LUG_C[1]) > LUG_R - 8 and x > 50:
        return False
    if x < -70 and abs(y) > (x + 124) - 7:   # tongue tapers (45deg lines)
        return False
    if math.hypot(x, y) < BOSS1_CLEAR:
        return False
    if math.hypot(x - LUG_HOLE[0], y - LUG_HOLE[1]) < 5.8:
        return False
    return True


def zone_of(x, y):
    d1, d2 = d_lines(x, y)
    if d1 >= XM and d2 >= XM:
        return "top"
    if d1 <= -XM and d2 <= -XM:
        return "bot"
    if d1 >= XM and d2 <= -XM:
        return "left"
    if d1 <= -XM and d2 >= XM:
        return "right"
    return None


def ok_vertex(x, y, zone):
    if not ok_common(x, y):
        return False
    return zone_of(x, y) == zone


def rp(v):
    return [round(v[0], 3), round(v[1], 3)]


def rounded_path(verts, r=RC):
    """Closed path from CCW polygon vertices with tangent corner arcs."""
    n = len(verts)
    segs, start = [], None
    for i in range(n):
        v = verts[i]
        p = verts[i - 1]
        q = verts[(i + 1) % n]
        e_in = (v[0] - p[0], v[1] - p[1])
        e_out = (q[0] - v[0], q[1] - v[1])
        li, lo = math.hypot(*e_in), math.hypot(*e_out)
        ui, uo = (e_in[0] / li, e_in[1] / li), (e_out[0] / lo, e_out[1] / lo)
        cosang = -(ui[0] * uo[0] + ui[1] * uo[1])
        ang = math.acos(max(-1, min(1, cosang)))
        t = r / math.tan(ang / 2)
        b = (uo[0] - ui[0], uo[1] - ui[1])
        lb = math.hypot(*b)
        b = (b[0] / lb, b[1] / lb)
        d = r / math.sin(ang / 2)
        a_in = (v[0] - ui[0] * t, v[1] - ui[1] * t)
        a_out = (v[0] + uo[0] * t, v[1] + uo[1] * t)
        via = (v[0] + b[0] * (d - r), v[1] + b[1] * (d - r))
        if start is None:
            start = a_out
            first = a_out
        else:
            segs.append({"type": "line", "to": rp(a_in)})
            segs.append({"type": "arc", "via": rp(via), "to": rp(a_out)})
        if i == n - 1:
            pass
    # close: line back along last edge then final corner arc of vertex 0
    v, p, q = verts[0], verts[-1], verts[1]
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
    a_in = (v[0] - ui[0] * t, v[1] - ui[1] * t)
    via = (v[0] + b[0] * (d - r), v[1] + b[1] * (d - r))
    segs.append({"type": "line", "to": rp(a_in)})
    segs.append({"type": "arc", "via": rp(via), "to": rp(first)})
    return {"kind": "path", "mode": "add", "start": rp(first), "segments": segs}


def tri_verts(cx, cy, up):
    angles = (90, 210, 330) if up else (270, 30, 150)
    return [(cx + R_TRI * math.cos(math.radians(a)),
             cy + R_TRI * math.sin(math.radians(a))) for a in angles]


# ---- isogrid triangles, top & bottom zones
tris = []
for j in range(-8, 8):
    y_up = j * H + H / 3
    for i in range(-14, 14):
        x_up = i * PITCH + (j % 2) * PITCH / 2
        for cx, cy, up in ((x_up, y_up, True), (x_up + PITCH / 2, y_up + H / 3, False)):
            vs = tri_verts(cx, cy, up)
            for zone in ("top", "bot"):
                if all(ok_vertex(x, y, zone) for x, y in vs):
                    tris.append(rounded_path(vs))
                    break

# ---- hexagons, left zone (pointy-top, AF 13, wall 1.8)
R_HEX = 13.0 / math.sqrt(3)
hexes = []
for j in range(-4, 5):
    for i in range(-8, 1):
        cx = i * 14.8 + (j % 2) * 7.4
        cy = j * 12.817
        vs = [(cx + R_HEX * math.cos(math.radians(a)),
               cy + R_HEX * math.sin(math.radians(a)))
              for a in (90, 150, 210, 270, 330, 30)]
        if all(ok_vertex(x, y, "left") for x, y in vs):
            hexes.append(rounded_path(vs))

# ---- round pockets, right zone (r6, pitch 13.8)
circles = []
for j in range(-4, 5):
    for i in range(0, 8):
        cx = 34 + i * 13.8 + (j % 2) * 6.9
        cy = j * 11.95
        pts = [(cx + 6 * math.cos(math.radians(a)), cy + 6 * math.sin(math.radians(a)))
               for a in range(0, 360, 30)]
        if all(ok_vertex(x, y, "right") for x, y in pts):
            circles.append({"kind": "circle", "r": 6, "x": round(cx, 3),
                            "y": round(cy, 3), "mode": "add"})

print(f"# {len(tris)} tris, {len(hexes)} hexes, {len(circles)} circles")
for name, items in (("TRI", tris), ("HEX", hexes), ("CIRC", circles)):
    for k in range(0, len(items), 10):
        print(f"{name}_{k // 10}:", json.dumps(items[k:k + 10]))
