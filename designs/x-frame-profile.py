"""X-frame panel — the outer shape IS the X (vacuum-safe, rounded pockets).

Body = one sketch: 2 arm rectangles (w190 x h34, rot +-22.38deg) + hub circle
r28 + 4 pad circles r18 at (+-85, +-35), extruded 10. Pockets (blind, floor
3.5, corners r1.6): rounded isogrid triangles along one diagonal, rounded
hexagons along the other; central boss pocket + dimples; O8 pad holes.
"""
import json
import math

THETA = math.atan2(35.0, 85.0)          # arm angle, 22.38 deg
C, S = math.cos(THETA), math.sin(THETA)
RC = 1.6
PITCH = 16.0
R_TRI = PITCH / math.sqrt(3) - 1.8
R_HEX = 13.0 / math.sqrt(3)
T_BAND = 11.0                            # |t| limit for pocket vertices
S_MAX = 80.0
R_HUB_CLEAR = 20.0                       # boss ring r17 + rib
PAD_S, PAD_CLEAR = 91.924, 7.0           # pad centers on the arm axis


def rot(p, direction):
    c, s = (C, S) if direction > 0 else (C, -S)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def rp(v):
    return [round(v[0], 3), round(v[1], 3)]


def rounded_path(verts, r=RC):
    n = len(verts)
    segs, first = [], None
    order = list(range(n)) + [0]
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
    for i in range(1, n):
        a_in, via, a_out = corners[i]
        segs.append({"type": "line", "to": rp(a_in)})
        segs.append({"type": "arc", "via": rp(via), "to": rp(a_out)})
    a_in, via, _ = corners[0]
    segs.append({"type": "line", "to": rp(a_in)})
    segs.append({"type": "arc", "via": rp(via), "to": rp(first)})
    return {"kind": "path", "mode": "add", "start": rp(first), "segments": segs}


def ok(pts_local):
    for s, t in pts_local:
        if abs(t) > T_BAND or abs(s) > S_MAX or math.hypot(s, t) < R_HUB_CLEAR:
            return False
        if math.hypot(abs(s) - PAD_S, t) < PAD_CLEAR:
            return False
    return True


# triangles along the +theta diagonal (one row, alternating up/down)
tris = []
for k in range(-5, 6):
    # phase +4/+12 so a 180-deg rotation maps up-tris onto down-tris exactly
    for s0, up in ((k * PITCH + 4, True), (k * PITCH + 12, False)):
        ct = -1.86 if up else 1.86
        angles = (90, 210, 330) if up else (270, 30, 150)
        loc = [(s0 + R_TRI * math.cos(math.radians(a)),
                ct + R_TRI * math.sin(math.radians(a))) for a in angles]
        if ok(loc):
            tris.append(rounded_path([rot(p, +1) for p in loc]))

# hexagons along the -theta diagonal
hexes = []
for k in range(-5, 6):
    s0 = k * 14.8 + 7.4
    loc = [(s0 + R_HEX * math.cos(math.radians(a)),
            R_HEX * math.sin(math.radians(a)))
           for a in (90, 150, 210, 270, 330, 30)]
    if ok(loc):
        hexes.append(rounded_path([rot(p, -1) for p in loc]))

print(f"# {len(tris)} tris, {len(hexes)} hexes | arm angle deg:",
      round(math.degrees(THETA), 2))
for name, items in (("TRI", tris), ("HEX", hexes)):
    for k in range(0, len(items), 10):
        print(f"{name}_{k // 10}:", json.dumps(items[k:k + 10]))
