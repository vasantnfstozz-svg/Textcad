"""Planetary gearset tooth-space cutters (involute, arc-fitted).

Module 2.8, 20 deg pressure angle, sun z9 / planets z9 / ring z27 internal,
stub teeth (addendum 0.7m) so the ring root space stays >= 2.5mm wide
(machinable with a O2.5 end mill), 0.3mm backlash for free running.
Gears are built subtractively: blank disc minus polar-patterned tooth-space
cutters (same trick as the fan disk). Prints the two cutter paths + all key
dimensions for build_design.
"""
import json
import math

M = 2.8                 # module
ALPHA = math.radians(20)
Z_SUN = Z_PLANET = 9
Z_RING = 27
ADD, DED = 0.7, 1.25    # addendum / dedendum factors (stub teeth)
BACKLASH = 0.3          # extra space width at pitch
INV_A = math.tan(ALPHA) - ALPHA

assert (Z_SUN + Z_RING) % 3 == 0, "planets cannot be equally spaced"
A_CENTER = M * (Z_SUN + Z_PLANET) / 2          # carrier pin radius = 25.2


def inv(pressure):
    return math.tan(pressure) - pressure


def rp(p):
    return [round(p[0], 3), round(p[1], 3)]


def pol(r, a):
    return (r * math.cos(a), r * math.sin(a))


def flank_angle(r, rb, theta_pitch, r_pitch, sign):
    """Angular position of the space flank at radius r. sign=+1 external
    (space widens outward), -1 internal ring (space narrows outward)."""
    if r < rb:
        r = rb
    pressure = math.acos(rb / r)
    return theta_pitch + sign * (inv(pressure) - INV_A)


def space_path(z, r_pitch, r_tip, r_root, external, r_ext):
    """Closed cutter path for ONE tooth space, centered on angle 0."""
    rb = r_pitch * math.cos(ALPHA)
    theta_p = (math.pi * M / 2 + BACKLASH) / 2 / r_pitch
    sign = +1 if external else -1
    lo, hi = (max(rb, r_root), r_tip) if external else (r_tip, r_root)
    # right flank sampled at 3 radii -> one 3-point arc
    rr = [lo, (lo + hi) / 2, hi]
    right = [pol(r, +flank_angle(r, rb, theta_p, r_pitch, sign)) for r in rr]
    left = [(p[0], -p[1]) for p in right]
    if external:
        tipR, baseR, rootR = right[2], right[0], pol(r_root, +flank_angle(lo, rb, theta_p, r_pitch, sign))
        tipL, baseL, rootL = left[2], left[0], (rootR[0], -rootR[1])
        A, B = pol(r_ext, math.atan2(tipR[1], tipR[0])), None
        B = (A[0], -A[1])
        segs = [
            {"type": "line", "to": rp(tipR)},
            {"type": "arc", "via": rp(right[1]), "to": rp(baseR)},
            {"type": "line", "to": rp(rootR)},
            {"type": "arc", "via": rp((r_root, 0)), "to": rp(rootL)},
            {"type": "line", "to": rp(baseL)},
            {"type": "arc", "via": rp(left[1]), "to": rp(tipL)},
            {"type": "line", "to": rp(B)},
            {"type": "arc", "via": rp((r_ext, 0)), "to": rp(A)},
        ]
        return {"kind": "path", "mode": "add", "start": rp(A), "segments": segs}
    else:
        tipR, rootR = right[0], right[2]
        tipL, rootL = left[0], left[2]
        A = pol(r_ext, math.atan2(tipR[1], tipR[0]))
        B = (A[0], -A[1])
        segs = [
            {"type": "line", "to": rp(tipR)},
            {"type": "arc", "via": rp(right[1]), "to": rp(rootR)},
            {"type": "arc", "via": rp((r_root, 0)), "to": rp(rootL)},
            {"type": "arc", "via": rp(left[1]), "to": rp(tipL)},
            {"type": "line", "to": rp(B)},
            {"type": "arc", "via": rp((r_ext, 0)), "to": rp(A)},
        ]
        return {"kind": "path", "mode": "add", "start": rp(A), "segments": segs}


# ---- external gear (sun & planets), z9
rp_e = M * Z_SUN / 2                      # 12.6
rt_e = rp_e + ADD * M                     # 14.56 tip
rr_e = rp_e - DED * M                     # 9.1 root
ext = space_path(Z_SUN, rp_e, rt_e, rr_e, True, rt_e + 2.0)

# ---- internal ring, z27
rp_i = M * Z_RING / 2                     # 37.8
rt_i = rp_i - ADD * M                     # 35.84 tip (= ring bore)
rr_i = rp_i + DED * M                     # 41.3? -> clamp to planet orbit + clearance
rr_i = A_CENTER + rt_e + 0.35             # 40.11 root (planet tip orbit + clearance)
ring = space_path(Z_RING, rp_i, rt_i, rr_i, False, rt_i - 1.5)

# machinability: min space widths
rb_e = rp_e * math.cos(ALPHA)
w_root_ext = 2 * rr_e * flank_angle(max(rb_e, rr_e), rb_e,
                                    (math.pi * M / 2 + BACKLASH) / 2 / rp_e, rp_e, +1)
rb_i = rp_i * math.cos(ALPHA)
w_root_ring = 2 * rr_i * flank_angle(rr_i, rb_i,
                                     (math.pi * M / 2 + BACKLASH) / 2 / rp_i, rp_i, -1)
assert w_root_ext >= 2.5 and w_root_ring >= 2.5, (w_root_ext, w_root_ring)

print("EXT_SPACE:", json.dumps(ext))
print("RING_SPACE:", json.dumps(ring))
print("gear blank r:", rt_e, "| root r:", rr_e, "| ring bore r:", rt_i,
      "| ring root r:", round(rr_i, 3), "| carrier pins at r:", A_CENTER)
print("min space widths  ext:", round(w_root_ext, 2), " ring:", round(w_root_ring, 2))
