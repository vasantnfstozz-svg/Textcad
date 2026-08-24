"""Tapered impeller blade outline for the pump impeller (v8).

Same camber law as blocks.py curved_blade (beta linear from inlet to exit,
measured from radial), but with a thickness profile: narrow rounded nose,
full thickness mid-blade, thin trailing edge. Emits the closed sketch-path
JSON (arcs + exit line) for build_design.
"""
import json
import math

R_IN, R_OUT = 6.0, 24.4
BETA_IN, BETA_OUT = 30.0, 50.0        # deg from radial
T_NOSE, T_MID, T_EXIT = 1.2, 2.5, 1.0
TAPER_IN_END, TAPER_OUT_START = 10.0, 18.0   # r where inlet taper ends / exit taper starts

def thickness(r):
    if r <= TAPER_IN_END:
        u = (r - R_IN) / (TAPER_IN_END - R_IN)
        return T_NOSE + (T_MID - T_NOSE) * u
    if r >= TAPER_OUT_START:
        u = (r - TAPER_OUT_START) / (R_OUT - TAPER_OUT_START)
        return T_MID + (T_EXIT - T_MID) * u
    return T_MID

# camber line: integrate d(theta) = tan(beta)/r dr  (fine grid)
N = 400
rs, thetas = [R_IN], [0.0]
for i in range(N):
    r0 = R_IN + (R_OUT - R_IN) * i / N
    r1 = R_IN + (R_OUT - R_IN) * (i + 1) / N
    beta = math.radians(BETA_IN + (BETA_OUT - BETA_IN) * (i + 0.5) / N)
    thetas.append(thetas[-1] + math.tan(beta) / (0.5 * (r0 + r1)) * (r1 - r0))
    rs.append(r1)

def camber(r):
    # interpolate theta at r
    u = (r - R_IN) / (R_OUT - R_IN) * N
    i = min(int(u), N - 1)
    th = thetas[i] + (thetas[i + 1] - thetas[i]) * (u - i)
    return th

def point_and_normal(r):
    th = camber(r)
    p = (r * math.cos(th), r * math.sin(th))
    # tangent via finite difference along r
    dr = 0.01
    r0, r1 = max(R_IN, r - dr), min(R_OUT, r + dr)
    a0, a1 = camber(r0), camber(r1)
    t = (r1 * math.cos(a1) - r0 * math.cos(a0), r1 * math.sin(a1) - r0 * math.sin(a0))
    L = math.hypot(*t)
    t = (t[0] / L, t[1] / L)
    n = (-t[1], t[0])
    return p, t, n

# 7 sample stations for 3 arcs per side
SAMPLES = [R_IN + (R_OUT - R_IN) * k / 6 for k in range(7)]
A, B = [], []
for r in SAMPLES:
    p, t, n = point_and_normal(r)
    h = thickness(r) / 2
    A.append((p[0] + n[0] * h, p[1] + n[1] * h))
    B.append((p[0] - n[0] * h, p[1] - n[1] * h))

# rounded nose: arc from B[0] via nose tip to A[0]
p0, t0, _ = point_and_normal(R_IN)
nose = (p0[0] - t0[0] * T_NOSE / 2, p0[1] - t0[1] * T_NOSE / 2)

def rp(pt):
    return [round(pt[0], 3), round(pt[1], 3)]

segments = [{"type": "arc", "via": rp(nose), "to": rp(A[0])}]
for i in (0, 2, 4):
    segments.append({"type": "arc", "via": rp(A[i + 1]), "to": rp(A[i + 2])})
segments.append({"type": "line", "to": rp(B[6])})
for i in (6, 4, 2):
    segments.append({"type": "arc", "via": rp(B[i - 1]), "to": rp(B[i - 2])})

path = {"kind": "path", "mode": "add", "start": rp(B[0]), "segments": segments}
print(json.dumps(path))
print("wrap deg:", round(math.degrees(thetas[-1]), 1),
      "| t at samples:", [round(thickness(r), 2) for r in SAMPLES])
