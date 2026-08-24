"""Sat side panel v3 — the v1 layout the user liked, refreshed:
rounded pocket corners (r1.6), rounded outer corners (r14), capsule X-slots
instead of arm dimples, 6 hexagon accents in the gaps. Vacuum-safe.
"""
import json
import math

S = 46.0 / 96.0
NORM = math.sqrt(1 + S * S)
XM = 6.8
RC = 1.6
PITCH, RIB = 16.0, 1.8
H = PITCH * math.sqrt(3) / 2
R_TRI = PITCH / math.sqrt(3) - RIB
R_HEX = 13.0 / math.sqrt(3)
SCALLOPS = [(52, 86, 40), (-52, 86, 40), (52, -86, 40), (-52, -86, 40),
            (127, 0, 30), (-127, 0, 30)]
CORNERS = [(104, 54), (-104, 54), (104, -54), (-104, -54)]
BOSS_CLEAR = 18.8
HEXES = []   # v5: user wants the original full-triangle structure, no hexagons


def ok_vertex(x, y):
    if abs(x) > 95 or abs(y) > 44.5:
        return False
    d1 = abs(y - S * x) / NORM
    d2 = abs(y + S * x) / NORM
    if d1 < XM or d2 < XM:
        return False
    if math.hypot(x, y) < BOSS_CLEAR:
        return False
    for cx, cy, r in SCALLOPS:
        if math.hypot(x - cx, y - cy) < r + RIB:
            return False
    for cx, cy in CORNERS:
        if math.hypot(x - cx, y - cy) < 26:
            return False
    for hx, hy in HEXES:
        if math.hypot(x - hx, y - hy) < R_HEX + RIB:
            return False
    return True


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


tris = []
for j in range(-8, 8):
    y_up = j * H + H / 3
    for i in range(-14, 14):
        x_up = i * PITCH + (j % 2) * PITCH / 2
        for cx, cy, up in ((x_up, y_up, True), (x_up + PITCH / 2, y_up + H / 3, False)):
            angles = (90, 210, 330) if up else (270, 30, 150)
            vs = [(cx + R_TRI * math.cos(math.radians(a)),
                   cy + R_TRI * math.sin(math.radians(a))) for a in angles]
            if all(ok_vertex(x, y) for x, y in vs):
                tris.append(rounded_path(vs))

hex_paths = []
for hx, hy in HEXES:
    vs = [(hx + R_HEX * math.cos(math.radians(a)),
           hy + R_HEX * math.sin(math.radians(a)))
          for a in (90, 150, 210, 270, 330, 30)]
    hex_paths.append(rounded_path(vs))

# ONE long capsule slot per half-arm (user-sketched style): spans s 22..80
ang = math.degrees(math.atan(S))
ca, sa = math.cos(math.atan(S)), math.sin(math.atan(S))
slots = []
S_MID = 51.0
for dx, dy, rot in ((ca, sa, ang), (-ca, sa, -ang)):
    for sgn in (1, -1):
        slots.append({"kind": "slot", "length": 58, "height": 7,
                      "x": round(sgn * S_MID * dx, 3), "y": round(sgn * S_MID * dy, 3),
                      "rotation": round(rot, 2), "mode": "add"})

print(f"# {len(tris)} tris, {len(hex_paths)} hexes, {len(slots)} slots")
for k in range(0, len(tris), 10):
    print(f"TRI_{k // 10}:", json.dumps(tris[k:k + 10]))
print("HEXES:", json.dumps(hex_paths))
print("SLOTS:", json.dumps(slots))
