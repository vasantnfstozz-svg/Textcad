"""X-braced satellite side panel — pocket layout generator (vacuum-safe).

208x108x10 shaped panel: chamfered corners, scalloped edges between six
mounting tabs, solid X-brace corner-to-corner with a central boss, isogrid
pockets (blind, floor 3.5) filling the quadrants. Prints batched sketch
entities for build_design.
"""
import json
import math

PANEL_HW, PANEL_HH = 104.0, 54.0
PITCH, RIB = 16.0, 1.8
H = PITCH * math.sqrt(3) / 2
R_CELL = PITCH / math.sqrt(3) - RIB
SLOPE = 46.0 / 96.0                       # X-brace direction (to corner tabs)
X_MARGIN = 6.0                            # pocket keep-out from X centerlines
BOSS_CLEAR = 18.8                         # central boss ring r17 + rib
SCALLOPS = [(52, 86, 40), (-52, 86, 40), (52, -86, 40), (-52, -86, 40),
            (127, 0, 30), (-127, 0, 30)]  # (cx, cy, r)
CORNERS = [(104, 54), (-104, 54), (104, -54), (-104, -54)]


def ok_vertex(x, y):
    if abs(x) > 95 or abs(y) > 44.5:
        return False
    d1 = abs(y - SLOPE * x) / math.sqrt(1 + SLOPE ** 2)
    d2 = abs(y + SLOPE * x) / math.sqrt(1 + SLOPE ** 2)
    if d1 < X_MARGIN or d2 < X_MARGIN:
        return False
    if math.hypot(x, y) < BOSS_CLEAR:
        return False
    for cx, cy, r in SCALLOPS:
        if math.hypot(x - cx, y - cy) < r + RIB:
            return False
    for cx, cy in CORNERS:
        if math.hypot(x - cx, y - cy) < 26:
            return False
    return True


def tri(cx, cy, up):
    angles = (90, 210, 330) if up else (270, 30, 150)
    pts = []
    for a in angles:
        x = cx + R_CELL * math.cos(math.radians(a))
        y = cy + R_CELL * math.sin(math.radians(a))
        if not ok_vertex(x, y):
            return None
        pts.append([round(x, 3), round(y, 3)])
    return {"kind": "polygon", "points": pts, "mode": "add"}


tris = []
n_row, n_col = 10, 16
for j in range(-n_row, n_row):
    y_up = j * H + H / 3
    for i in range(-n_col, n_col):
        x_up = i * PITCH + (j % 2) * PITCH / 2
        t = tri(x_up, y_up, True)
        if t:
            tris.append(t)
        t = tri(x_up + PITCH / 2, y_up + H / 3, False)
        if t:
            tris.append(t)

print(f"# {len(tris)} triangles")
for k in range(0, len(tris), 10):
    print(f"TRI_{k // 10}:", json.dumps(tris[k:k + 10]))

# X-arm rivet dimples: along +diagonal from t=24 outward, step 16
ux, uy = 1 / math.sqrt(1 + SLOPE ** 2), SLOPE / math.sqrt(1 + SLOPE ** 2)
print("dimple start:", round(24 * ux, 3), round(24 * uy, 3),
      "| step:", round(16 * ux, 3), round(16 * uy, 3))
