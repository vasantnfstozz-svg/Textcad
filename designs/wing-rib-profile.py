"""NACA 2412 wing rib outline + web pockets for the TextCAD wing-rib design.

Machined-rib construction: airfoil plate, web pockets (3.5mm deep) leaving a
3mm flange along the skin and around the spar slots, two spar slots, round
lightening holes. Prints sketch-path JSON blocks ready for build_design.
Stock: 220x120x12 steel -> rib 200 chord x 10 thick.
"""
import json
import math

CHORD = 200.0
M, P, T = 0.02, 0.4, 0.12           # NACA 2412
FLANGE = 3.0                        # wall left between pocket and skin
SPAR_MAIN = (60.0, 8.0)             # (center x, slot width)
SPAR_REAR = (140.0, 6.0)
CAP = 3.5                           # material above/below spar slots


def camber(u):
    if u < P:
        yc = M / P**2 * (2 * P * u - u * u)
        dy = 2 * M / P**2 * (P - u)
    else:
        yc = M / (1 - P)**2 * ((1 - 2 * P) + 2 * P * u - u * u)
        dy = 2 * M / (1 - P)**2 * (P - u)
    return yc, dy


def thick(u):
    return 5 * T * (0.2969 * math.sqrt(u) - 0.1260 * u - 0.3516 * u**2
                    + 0.2843 * u**3 - 0.1015 * u**4)


def surf(u, side, inset=0.0):
    """Point on upper (+1) / lower (-1) surface, offset inward by `inset` mm
    (offset along the camber-frame normal — accurate enough at these slopes)."""
    yc, dy = camber(u)
    th = math.atan(dy)
    yt = yt_eff = thick(u) - inset / CHORD
    x = (u - side * yt_eff * math.sin(th)) * CHORD
    y = (yc + side * yt_eff * math.cos(th)) * CHORD
    return (x, y)


def rp(p):
    return [round(p[0], 3), round(p[1], 3)]


def arcs_from(pts):
    """Consecutive 3-point arcs over an odd-length point list."""
    segs = []
    for i in range(0, len(pts) - 2, 2):
        segs.append({"type": "arc", "via": rp(pts[i + 1]), "to": rp(pts[i + 2])})
    return segs


# ---- outer airfoil path: TE upper -> LE -> TE lower, auto-close blunt TE
STATIONS = [1.0, 0.95, 0.9, 0.8, 0.65, 0.5, 0.35, 0.22, 0.12, 0.06, 0.025, 0.008, 0.0]
upper = [surf(u, +1) for u in STATIONS]
lower = [surf(u, -1) for u in reversed(STATIONS)]
outline = {"kind": "path", "mode": "add", "start": rp(upper[0]),
           "segments": arcs_from(upper) + arcs_from(lower[0:])[0:]}
# join LE: upper ends at u=0 (LE), lower starts at u=0 -> same point, so chain lower arcs
outline["segments"] = arcs_from(upper) + arcs_from(lower)

# ---- web pocket bays (offset FLANGE inward, straight walls at bay ends)
def bay(xa, xb, n=5):
    us = [xa / CHORD + (xb - xa) / CHORD * k / (n - 1) for k in range(n)]
    top = [surf(u, +1, FLANGE) for u in us]
    bot = [surf(u, -1, FLANGE) for u in us]
    segs = [{"type": "line", "to": rp(top[0])}]
    segs += arcs_from(top)
    segs.append({"type": "line", "to": rp(bot[-1])})
    segs += arcs_from(list(reversed(bot)))
    return {"kind": "path", "mode": "add", "start": rp(bot[0]), "segments": segs}

bay1 = bay(14.0, SPAR_MAIN[0] - SPAR_MAIN[1] / 2 - FLANGE)          # LE bay
bay2 = bay(SPAR_MAIN[0] + SPAR_MAIN[1] / 2 + FLANGE,
           SPAR_REAR[0] - SPAR_REAR[1] / 2 - FLANGE)                 # mid bay
# TE bay: extend while inner height stays workable (>= 6mm)
xe = SPAR_REAR[0] + SPAR_REAR[1] / 2 + FLANGE
x_end = xe
while x_end < 190:
    h = (surf(x_end / CHORD, +1, FLANGE)[1] - surf(x_end / CHORD, -1, FLANGE)[1])
    if h < 6.0:
        break
    x_end += 1.0
bay3 = bay(xe, x_end - 1.0)

# ---- spar slots (rect w x h centered on camber midpoint)
def slot(cx, w):
    yu = surf(cx / CHORD, +1)[1]
    yl = surf(cx / CHORD, -1)[1]
    h = (yu - yl) - 2 * CAP
    return {"kind": "rectangle", "w": w, "h": round(h, 3),
            "x": cx, "y": round((yu + yl) / 2, 3), "mode": "add"}, h

slot_main, hm = slot(*SPAR_MAIN)
slot_rear, hr = slot(*SPAR_REAR)

# ---- lightening holes on the camber line
def hole(cx, d):
    yu = surf(cx / CHORD, +1, FLANGE)[1]
    yl = surf(cx / CHORD, -1, FLANGE)[1]
    assert d <= (yu - yl) - 4, f"hole d{d} too big at x={cx} (inner h={yu-yl:.1f})"
    return {"kind": "circle", "r": d / 2, "x": cx, "y": round((yu + yl) / 2, 3),
            "mode": "add"}

holes = [hole(35, 11), hole(90, 12), hole(115, 9)]

ys = [p[1] for p in upper + lower]
print("OUTLINE:", json.dumps(outline))
print("BAY1:", json.dumps(bay1))
print("BAY2:", json.dumps(bay2))
print("BAY3:", json.dumps(bay3), "| TE bay ends at x =", x_end - 1.0)
print("SLOTS:", json.dumps([slot_main, slot_rear]), "| slot heights:",
      round(hm, 2), round(hr, 2))
print("HOLES:", json.dumps(holes))
print("bbox y:", round(min(ys), 3), "..", round(max(ys), 3),
      "| span:", round(max(ys) - min(ys), 3))
