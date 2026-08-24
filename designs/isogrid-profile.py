"""Isogrid aerospace panel — pocket layout generator (vacuum-table safe).

210x110x10 panel, all BLIND pockets (floor 3.5mm):
- triangular isogrid field (pitch 24, rib 1.8) left of a solid spine,
  interrupted by a circular access-port boss at (-45, 0)
- orthogrid (square waffle) zone right of the spine
- port: O40 inner pocket, solid ring, 8 fastener dimples on PCD 48
Prints batched sketch-entity JSON (<=10 entities per sketch) for build_design.
"""
import json
import math

PANEL_W, PANEL_H = 210.0, 110.0
PITCH, RIB = 16.0, 1.8
H = PITCH * math.sqrt(3) / 2                 # row height 13.86
R_CELL = PITCH / math.sqrt(3) - RIB          # triangle circumradius after rib inset
PORT = (-45.0, 0.0)
PORT_CLEAR = 21.8                            # ring OD radius 20 + one rib
FIELD_X = (-96.5, 15.0)                      # triangle vertices allowed range
FIELD_Y = 46.5


def dist_to_tri(px, py, pts):
    """Distance from point to a triangle (its boundary; 0 if inside)."""
    best = float("inf")
    inside = True
    for i in range(3):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % 3]
        ex, ey = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * ex + (py - ay) * ey) / (ex * ex + ey * ey)))
        best = min(best, math.hypot(px - (ax + t * ex), py - (ay + t * ey)))
        if (ex * (py - ay) - ey * (px - ax)) < 0:
            inside = False
    return 0.0 if inside else best
SPINE_X = (17.0, 31.0)                       # solid band (slots milled shallow)
ORTHO_X = (31.0, 97.0)
SQ_PITCH, SQ = 16.5, 14.7


def tri(cx, cy, up):
    angles = (90, 210, 330) if up else (270, 30, 150)
    pts = [[round(cx + R_CELL * math.cos(math.radians(a)), 3),
            round(cy + R_CELL * math.sin(math.radians(a)), 3)] for a in angles]
    return {"kind": "polygon", "points": pts, "mode": "add"}


def fits(cx, cy, up):
    angles = (90, 210, 330) if up else (270, 30, 150)
    pts = []
    for a in angles:
        x = cx + R_CELL * math.cos(math.radians(a))
        y = cy + R_CELL * math.sin(math.radians(a))
        if not (FIELD_X[0] <= x <= FIELD_X[1] and -FIELD_Y <= y <= FIELD_Y):
            return False
        pts.append((x, y))
    return dist_to_tri(PORT[0], PORT[1], pts) >= PORT_CLEAR


tris = []
n_row = int(PANEL_H / H) + 2
n_col = int(PANEL_W / PITCH) + 2
for j in range(-n_row, n_row):
    y_up = j * H + H / 3
    for i in range(-n_col, n_col):
        x_up = i * PITCH + (j % 2) * PITCH / 2
        if fits(x_up, y_up, True):
            tris.append(tri(x_up, y_up, True))
        x_dn, y_dn = x_up + PITCH / 2, y_up + H / 3
        if fits(x_dn, y_dn, False):
            tris.append(tri(x_dn, y_dn, False))

squares = []
cols = int((ORTHO_X[1] - ORTHO_X[0]) // SQ_PITCH)
x0 = (ORTHO_X[0] + ORTHO_X[1]) / 2 - (cols - 1) * SQ_PITCH / 2
rows = int(2 * FIELD_Y // SQ_PITCH)
y0 = -(rows - 1) * SQ_PITCH / 2
for c in range(cols):
    for r in range(rows):
        squares.append({"kind": "rectangle", "w": SQ, "h": SQ,
                        "x": round(x0 + c * SQ_PITCH, 3),
                        "y": round(y0 + r * SQ_PITCH, 3), "mode": "add"})

print(f"# {len(tris)} triangles, {len(squares)} squares")
for k in range(0, len(tris), 10):
    print(f"TRI_{k // 10}:", json.dumps(tris[k:k + 10]))
for k in range(0, len(squares), 10):
    print(f"SQ_{k // 10}:", json.dumps(squares[k:k + 10]))
