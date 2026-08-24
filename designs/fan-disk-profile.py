"""Turbofan fan disk (display model) — window cutout geometry.

O110 x 10 through-cut plate: hub O30, ring O110/O100, 14 wide-chord swept
blades. Built subtractively: the disk minus 14 window openings, so blade
roots pick up the tool radius like real root fillets. Prints the window
path JSON for build_design (polar_pattern x14).
"""
import json
import math

R_HUB, R_RING = 15.0, 50.0          # window spans hub OD .. ring ID
N_BLADES = 14
T_ROOT, T_TIP = 3.0, 2.2            # blade thickness taper
BETA0, BETA1 = 15.0, 45.0           # blade sweep, deg from radial
PITCH = 2 * math.pi / N_BLADES

# camber theta(r) by integrating tan(beta)/r, over an extended range
r0, r1, N = 13.5, 52.0, 600
rs = [r0 + (r1 - r0) * i / N for i in range(N + 1)]
th = [0.0]
for i in range(N):
    rm = (rs[i] + rs[i + 1]) / 2
    u = min(max((rm - R_HUB) / (R_RING - R_HUB), 0), 1)
    beta = math.radians(BETA0 + (BETA1 - BETA0) * u)
    th.append(th[-1] + math.tan(beta) / rm * (rs[i + 1] - rs[i]))


def camber(r):
    u = (r - r0) / (r1 - r0) * N
    i = min(int(u), N - 1)
    return th[i] + (th[i + 1] - th[i]) * (u - i)


def pnt(r):
    a = camber(r)
    return (r * math.cos(a), r * math.sin(a))


def flank(r, side):
    p = pnt(r)
    d = 0.01
    pa, pb = pnt(max(r0, r - d)), pnt(min(r1, r + d))
    t = (pb[0] - pa[0], pb[1] - pa[1])
    L = math.hypot(*t)
    t = (t[0] / L, t[1] / L)
    n = (-t[1], t[0])
    u = min(max((r - R_HUB) / (R_RING - R_HUB), 0), 1)
    h = (T_ROOT + (T_TIP - T_ROOT) * u) / 2
    return (p[0] + side * n[0] * h, p[1] + side * n[1] * h)


def cross_radius(side, target):
    lo, hi = r0, r1
    for _ in range(60):
        mid = (lo + hi) / 2
        if math.hypot(*flank(mid, side)) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return (c * p[0] - s * p[1], s * p[0] + c * p[1])


def rp(p):
    return [round(p[0], 3), round(p[1], 3)]


# which flank faces +theta
sideP = +1 if math.atan2(*reversed(flank(30, +1))) > math.atan2(*reversed(flank(30, -1))) else -1
sideM = -sideP

# flank sample stations trimmed exactly to the hub/ring circles
def flank_pts(side, rotate=0.0):
    ra, rb = cross_radius(side, R_HUB), cross_radius(side, R_RING)
    pts = [flank(ra + (rb - ra) * k / 4, side) for k in range(5)]
    return [rot(p, rotate) for p in pts]

A = flank_pts(sideP)                 # blade 0, window-facing flank
B = flank_pts(sideM, rotate=PITCH)   # next blade, opposite flank

def arc_chain(pts):
    return [{"type": "arc", "via": rp(pts[i + 1]), "to": rp(pts[i + 2])}
            for i in range(0, len(pts) - 2, 2)]

def circle_arc(p_from, p_to, radius):
    # both window arcs span < 26 deg, so the plain angle midpoint is always
    # on the SHORT arc (forcing CCW here would route the hub arc through the blade)
    a1, a2 = math.atan2(p_from[1], p_from[0]), math.atan2(p_to[1], p_to[0])
    am = (a1 + a2) / 2
    return {"type": "arc", "via": rp((radius * math.cos(am), radius * math.sin(am))),
            "to": rp(p_to)}

segs = arc_chain(A)                                  # up blade-0 flank
segs.append(circle_arc(A[-1], B[-1], R_RING))        # along ring ID
segs += arc_chain(list(reversed(B)))                 # down next flank
segs.append(circle_arc(B[0], A[0], R_HUB))           # back along hub OD... direction!
window = {"kind": "path", "mode": "add", "start": rp(A[0]), "segments": segs}

# channel width check
gmin = min(math.hypot(rot(flank(r, sideM), PITCH)[0] - flank(r, sideP)[0],
                      rot(flank(r, sideM), PITCH)[1] - flank(r, sideP)[1])
           for r in [R_HUB + (R_RING - R_HUB) * k / 20 for k in range(21)])
assert gmin >= 3.2, f"window too narrow: {gmin:.2f}"

print("WINDOW:", json.dumps(window))
print("min channel width:", round(gmin, 2),
      "| blade wrap deg:", round(math.degrees(camber(R_RING) - camber(R_HUB)), 1))
