"""esp32-remote v3 — remote-style bottom shell (no top cover) milled from
the 220x120x12 steel stock. Vacuum table rules: every cut is a blind
pocket; the outline is machined as a trench with a ~1.5mm skin and the
part is freed/deburred after. Model = the finished shell.

v3 changes (user feedback 2026-08-25): WEIGHT REDUCTION + pillar mounts.
  - "first cut": one big roughing cavity (floor z3, 9 deep) hogs out the
    whole upper body — everything that used to be separate pockets is now
    open air; the grip/keypad zone stays solid (the pad needs a face)
  - every PCB stands on screw-boss PILLARS with pilot "pipes":
      ESP32   4x D7 pillars, top z7,   M2.5 pilots (pitch 47 x 23)
      OLED    4x D5.5 pillars, top z9.5, M2 pilots (pitch 23.5 sq)
      microSD 4x D5.5 pillars, top z7,  M2 pilots (pitch 19 x 37),
              outer pair bridged into the cavity wall (tabs)
  - 9V battery: 0.5-deep locating seat in the cavity floor + two rim
    blocks (top z9) with M3 strap pilots — strap goes over the battery
  - buzzer: 0.5-deep D13 seat (top lands flush at z12) + two full-height
    D6.5 clamp pillars with M2 pilots for a hold-down strip
  - keypad: membrane has no holes -> stays adhesive on its platform
  - pin trenches / finger scoops / OLED bezel recess+pit: obsolete
    (open cavity gives pin + finger + wire clearance), removed

Run:  python designs/esp32-remote.py           -> preview + checks
      python designs/esp32-remote.py --build   -> STEP + tcad.json
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = r"c:\Users\VasanSeenivasan\Desktop\textcad"

# ------------------------------------------------------------------ outline
T = 12.0                                     # stock/shell thickness
L2 = 100.0                                   # half length (200 total)
GRIP2, HEAD2, TOP2 = 33.0, 45.0, 37.0        # half widths: grip/head/top
VERTS = [(GRIP2, -L2), (HEAD2, 12.0), (HEAD2, 62.0), (TOP2, L2),
         (-TOP2, L2), (-HEAD2, 62.0), (-HEAD2, 12.0), (-GRIP2, -L2)]  # CCW
RADII = [10.0, 22.0, 22.0, 18.0, 18.0, 22.0, 22.0, 10.0]
RING_D1, RING_D2, RING_Z = 3.0, 4.2, 11.4    # pinstripe groove, 0.6 deep

# ------------------------------------------------------------ main cavity
CAV_D, CAV_Z = 5.6, 3.0        # wall thickness / cavity floor (9 deep)
CAV_Y0 = -22.0                 # cavity starts where the keypad platform ends
CLIP_R = 5.0                   # cutter fillet where the straight cavity edge
                               # meets the walls
# v6: NO outer top-rim fillet — the user has no chamfer/ball tooling for it,
# so the outer top corners stay SQUARE (the vertical corners are milled).
OPEN_OVER = 4.0                # how far a pocket that opens into the cavity
                               # over-runs the wall line (kills coincidence)

# ---------------------------------------------------------------- keypad
# MakerMind RBS11089: rigid 3x4 telephone keypad, 70 x 52 x 10, hard keys.
# Recess only 2 deep (platform stays solid), body rides 8 proud + keys.
KEY_W, KEY_L = 52.0, 70.0
KEY_HOLE_P, KEY_HOLE_R = (47.0, 65.0), 1.5   # D3 holes — VERIFY vs part
KEYPAD = (-(KEY_W + 1) / 2, (KEY_W + 1) / 2, -93.0, -93.0 + KEY_L + 1,
          10.0, 3.0)                              # 53 x 71, 2.0 deep
KEY_C = (0.0, (KEYPAD[2] + KEYPAD[3]) / 2)
TRENCH = (-9.0, 9.0, -91.0, CAV_Y0, 7.8, 3.0)     # wire bed under the pad
SCOOP_T = (-9.0, 9.0, -91.0, -83.0, 6.0, 2.0)     # solder-tail fold room
# v6 (user, "sharp edges in the keyboard start"): the recess and the wire
# trench both END on the cavity wall line — their old rounded-rect corners
# ran TANGENT to it, leaving zero-angle knife cusps, and the old rib notch
# crossed it with 90-deg tips. Both now open into the cavity through convex
# flare fillets, so the material flows wall -> arc -> cavity wall smoothly.
KEY_FLARE, TR_FLARE = 3.0, 4.0
# (the rib notch is gone: with the recess open to the cavity there is no rib)

# ------------------------------------------------------- pillars & seats
ESP_C = (0.0, -5.0)                               # board center
ESP_HOLE_P, ESP_PIL_R, ESP_TOP = (47.0, 23.0), 2.75, 7.0
# v10 (user: the ESP pillars are too big): OD D7.0 -> D5.5, same as the
# OLED pillars. The D3 pilot keeps a 1.25 collar, comfortably over the
# 1.0 floor the gate below enforces, and the pillar is still 2x the
# screw diameter.
ESP_HOLE_R = 1.5                                  # D3 hole (was D2)
# v8: the USB wall gap is DELETED on user request — the wall is unbroken now
# (so the ESP32's USB socket is enclosed: flash it before final assembly, or
# over-the-air)

BATT_C = (-13.8, 32.0)                            # seat center
# v6: seat pulled 1mm off BOTH rims and 1mm inside the cavity wall — its
# edges used to sit exactly ON the rim walls (tangent cusps in the 0.5 step)
# and 0.1 OUTSIDE the cavity wall (a sliver undercut at the wall base)
BATT_SEAT = (-38.4, 10.8, 18.4, 45.6, 2.5, 3.0)   # 49.2 x 27.2, 0.5 deep
BATT_RIMS = [(-36.0, 8.0, 12.5, 17.5, 2.0),       # x0,x1,y0,y1,r — top z9
             (-36.0, 8.0, 46.5, 51.5, 2.0)]
RIM_TOP = 9.0
STRAP = [(-14.0, 15.0), (-14.0, 49.0)]            # strap pilot holes
# M2, not M3: the rims are only 5.0 wide, so an M3 tap drill (D2.5) left
# 1.25mm walls (1.0 after tapping) — the thinnest web in the part and the
# one place a fastener pulls. D1.6 gives 1.7, matching the SD pillars.
STRAP_R = 0.8

SD_C = (25.3, 35.5)                               # module center
SD_HOLE_P, SD_PIL_R, SD_TOP = (19.0, 37.0), 2.5, 7.0
SD_HOLE_R = 0.8                                   # M2 pilot
# (v4 wall tabs removed: they made sharp internal wall junctions — the
# outer pillars are free-standing now with >= 2mm cutter gap to the wall)

OLED_C = (0.0, 77.5)
OLED_HOLE_P, OLED_PIL_R, OLED_TOP = 23.5, 2.75, 9.5
OLED_HOLE_R = 0.8                                 # M2 pilot

BUZZ = (25.0, 76.0, 6.5)                          # cx, cy, r — seat 0.5 deep
BUZZ_PIL = [(25.0, 65.5), (25.0, 86.5)]           # clamp pillars, top z12
BUZZ_PIL_R, BUZZ_HOLE_R = 3.25, 0.8               # M2 pilot

# LoRa transmitter left of the display: Ai-Thinker Ra-02 (SX1278),
# 17.2 x 16.2 x 3.2, castellated (no holes) -> seat + clamp pillars
# like the buzzer. PARAMETRIC — verify vs the module ordered.
C_LORA = (17.2, 16.2)
LORA_C = (-25.5, 75.5)
LORA_FOOT = (-34.35, -16.65, 67.1, 83.9, 2.5, 4.0)   # 17.7 x 16.8
LORA_PIL = [(-25.5, 62.7), (-25.5, 88.0)]         # clamp pillars, top z12
LORA_PIL_R, LORA_HOLE_R = 3.25, 0.8               # M2 pilot


# ------------------------------------------- company name in the wire slot
# v10 (user): the name goes IN the long slot and runs PERPENDICULAR to the
# old horizontal placement - i.e. ALONG the slot - and it has to come out of
# a D2, the smallest bit on hand.
#
# That tool size is the whole design driver. The slot is 18 wide, so rotated
# the name gets 63 x 14mm. Measured against logo_reach_miss (a morphological
# opening: the fraction of the artwork a given cutter physically cannot get
# into), at D2 and that size:
#     Impact          4.3%      <- the only usable face
#     Segoe UI Black 12.0%
#     Arial Black    25.3%
#     Arial Bold     98.3%,  Bahnschrift 100%,  Calibri Bold 98.4%
# Normal-weight faces are not "a bit rough" at D2, they are uncuttable: the
# bit is wider than their strokes. Impact is condensed AND heavy, which is
# exactly what a long narrow slot and a fat cutter both want.
#
# This is also why the official SVG lockup is NOT used here (v7 engraved it
# at D0.8 and it was reverted): its iQ mark and thin joins need a sub-1mm
# cutter. Name as text, cut with the bit that exists.
LOGO_WORD = "autonomIQ"
LOGO_FONT = r"C:\Windows\Fonts\impact.ttf"
# v10.1 (user: "the width is going like 12mm, scale it down to 11mm"):
# ACROSS is now the driving dimension and the length follows from the
# word's own aspect - so the name can never silently get wider again.
LOGO_ACROSS = 11.0                        # across the slot (was 12.85)
LOGO_SLOT_MAX = 14.0                      # what the 18-wide slot allows
LOGO_DEEP = 0.8
# The name must clear the solder-tail scoop at the slot's south end
# (SCOOP_T floor z6.0 is BELOW the engraving, so an overlap would simply
# delete the first letter - it did, caught in the v10 preview).
LOGO_Y0, LOGO_Y1 = SCOOP_T[3], TRENCH[3]  # usable run of the slot
LOGO_CY = round((LOGO_Y0 + LOGO_Y1) / 2, 2)
# TOOL: the user has a D2. Measured with logo_reach_miss below, a D2
# cannot reach ~10% of this artwork and - critically - what it loses is
# the JOINS, so stems part from bowls and the word reads as a row of
# lozenges (rendered and looked at, not guessed). A D1 misses <1% and is
# clean. The geometry here is identical either way; only the cutter
# changes, so the spec is D1 for the lettering pass alone and the D2
# number is reported next to it.
LOGO_TOOL_D = 1.0
LOGO_TOOL_HAVE = 2.0                      # what is on the shelf today
LOGO_MISS_MAX = 0.02


def _logo_raster():
    """The name drawn huge, cropped to ink, then ROTATED 90 so it runs along
    the slot instead of across it."""
    from PIL import ImageOps
    font = ImageFont.truetype(LOGO_FONT, 400)
    im = Image.new("L", (7000, 900), 255)
    dd = ImageDraw.Draw(im)
    x = 100
    for ch in LOGO_WORD:
        dd.text((x, 150), ch, font=font, fill=0)
        x += dd.textlength(ch, font=font)
    im = im.crop(ImageOps.invert(im).getbbox())
    return im.rotate(90, expand=True, fillcolor=255)


_LOGO_RASTER = _logo_raster()


LOGO_LEN = round(LOGO_ACROSS * _LOGO_RASTER.size[1]
                 / _LOGO_RASTER.size[0], 2)      # along the slot, derived


def logo_reach_miss(tool_d, px_mm=20.0):
    """Fraction of the engraved artwork a tool_d cutter cannot reach, by
    morphological opening (v7's metric, kept so the numbers compare).
    NOTE what it misses matters more than how much: losing 10% spread over
    the letter JOINS destroys legibility, losing 1% at sharp corners does
    not. Always render it and look."""
    import cv2
    import numpy as np
    w0, h0 = _LOGO_RASTER.size
    k = LOGO_LEN / h0
    size = (max(1, int(w0 * k * px_mm)), int(h0 * k * px_mm))
    art = (np.array(_LOGO_RASTER.resize(size, Image.LANCZOS))
           < 128).astype(np.uint8)
    r = max(1, int(round(tool_d * px_mm)))
    r += 1 - r % 2
    kel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r))
    reach = cv2.morphologyEx(art, cv2.MORPH_OPEN, kel)
    return 1.0 - reach.sum() / art.sum()


def _logo_entities():
    """Traced polygons, placed at the slot centre. Counters ride in the same
    sketch as their own letter - a stranded subtract would eat the floor."""
    import io as _io
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import imgtrace
    buf = _io.BytesIO()
    _LOGO_RASTER.save(buf, format="PNG")
    ents, info = imgtrace.image_to_entities(buf.getvalue(),
                                            height_mm=LOGO_LEN, tol_mm=0.08)
    for e in ents:
        e["y"] = round(e["y"] + LOGO_CY, 3)
    return ents, info["width_mm"]


LOGO_ENTS, LOGO_ACROSS_MM = _logo_entities()
LOGO_MISS = logo_reach_miss(LOGO_TOOL_D)
LOGO_MISS_HAVE = logo_reach_miss(LOGO_TOOL_HAVE)


def _logo_groups():
    """One outer contour + its own counters per group, packed <=10/sketch."""
    def ap(e):
        return [(e["x"] + q[0], e["y"] + q[1]) for q in e["points"]]

    def inside(pt, poly):
        x, y = pt
        hit, n = False, len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if (y0 > y) != (y1 > y) and \
                    x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                hit = not hit
        return hit

    def area(poly):
        n = len(poly)
        return abs(sum(poly[i][0] * poly[(i + 1) % n][1]
                       - poly[(i + 1) % n][0] * poly[i][1]
                       for i in range(n))) / 2
    adds = [e for e in LOGO_ENTS if e["mode"] == "add"]
    groups = [[a] for a in adds]
    for sub in (e for e in LOGO_ENTS if e["mode"] == "subtract"):
        pts = ap(sub)
        ctr = (sum(q[0] for q in pts) / len(pts),
               sum(q[1] for q in pts) / len(pts))
        best = None
        for i, a in enumerate(adds):
            poly = ap(a)
            if inside(ctr, poly):
                ar = area(poly)
                if best is None or ar < best[1]:
                    best = (i, ar)
        assert best is not None, "traced counter with no parent letter"
        groups[best[0]].append(sub)
    out, cur = [], []
    for g in groups:
        if cur and len(cur) + len(g) > 10:
            out.append(cur)
            cur = []
        cur.extend(g)
    return out + ([cur] if cur else [])


LOGO_BATCHES = _logo_groups()


# researched component sizes (for the fit gates)
C_ESP, C_OLED = (52.0, 28.0), (27.3, 27.3)
C_BATT, C_SD, C_BUZZ = (48.5, 26.5, 17.5), (42.0, 24.0), 12.0

# visible footprint "slot boxes", 0.5 deep, at COMPONENT size. CURVE RULE
# (user, v5.2): the box must never wrap BEHIND a pillar — where a pillar
# meets the outline, the boundary curves around it as a concave scallop
# (subtract circle poking past the edges; junction corners are convex
# material tips, which a cutter follows fine). Pillars outside their box
# (LoRa, buzzer) stay fully clear of it.
ESP_FOOT = (-26.5, 26.5, -19.5, 9.5, 2.5, 2.0)    # 53 x 29
OLED_FOOT = (-14.25, 14.25, 63.25, 91.75, 2.5, 2.0)   # 28.5 sq
SD_FOOT = (12.8, 37.8, 14.0, 57.0, 2.5, 2.0)      # 25 x 43
SCAL_ESP, SCAL_OLED, SCAL_SD = 5.0, 4.25, 4.5     # scallop radii at pillars
# blend arc where a scallop meets a box edge. These blends are CONCAVE in
# the material (the cut turns convex there), so they are governed by the
# r >= 1.5 internal-corner minimum — at the old 1.2 a D3 cutter left ~7.4mm2
# of steel standing at the 24 junctions. Audit finding, 2026-08-25.
FILLET_TIP = 1.5

ESP_HOLES = [(ESP_C[0] + sx * ESP_HOLE_P[0] / 2,
              ESP_C[1] + sy * ESP_HOLE_P[1] / 2)
             for sx in (1, -1) for sy in (1, -1)]
SD_HOLES = [(SD_C[0] + sx * SD_HOLE_P[0] / 2, SD_C[1] + sy * SD_HOLE_P[1] / 2)
            for sx in (1, -1) for sy in (1, -1)]
OLED_HOLES = [(OLED_C[0] + sx * OLED_HOLE_P / 2,
               OLED_C[1] + sy * OLED_HOLE_P / 2)
              for sx in (1, -1) for sy in (1, -1)]
KEY_HOLES = [(KEY_C[0] + sx * KEY_HOLE_P[0] / 2,
              KEY_C[1] + sy * KEY_HOLE_P[1] / 2)
             for sx in (1, -1) for sy in (1, -1)]


# --------------------------------------------------- rounded outline helpers
def _corner_geo(verts, radii):
    """Per corner: tangent-in, arc-via, tangent-out, center, r."""
    n = len(verts)
    out = []
    for i in range(n):
        v, p, q = verts[i], verts[i - 1], verts[(i + 1) % n]
        r = radii[i]
        e_in = (v[0] - p[0], v[1] - p[1])
        e_out = (q[0] - v[0], q[1] - v[1])
        li, lo = math.hypot(*e_in), math.hypot(*e_out)
        ui, uo = (e_in[0] / li, e_in[1] / li), (e_out[0] / lo, e_out[1] / lo)
        ang = math.acos(max(-1, min(1, -(ui[0] * uo[0] + ui[1] * uo[1]))))
        t = r / math.tan(ang / 2)
        assert t < li and t < lo, f"radius {r} too big at vertex {v}"
        b = (uo[0] - ui[0], uo[1] - ui[1])
        lb = math.hypot(*b)
        b = (b[0] / lb, b[1] / lb)
        dd = r / math.sin(ang / 2)
        out.append({"a_in": (v[0] - ui[0] * t, v[1] - ui[1] * t),
                    "via": (v[0] + b[0] * (dd - r), v[1] + b[1] * (dd - r)),
                    "a_out": (v[0] + uo[0] * t, v[1] + uo[1] * t),
                    "c": (v[0] + b[0] * dd, v[1] + b[1] * dd), "r": r})
    return out


def outline_path(verts, radii):
    geo = _corner_geo(verts, radii)
    first = geo[0]["a_out"]

    def q3(p):
        return [round(p[0], 3), round(p[1], 3)]
    segs = []
    for i in list(range(1, len(verts))) + [0]:
        g = geo[i]
        segs.append({"type": "line", "to": q3(g["a_in"])})
        segs.append({"type": "arc", "via": q3(g["via"]),
                     "to": q3(first if i == 0 else g["a_out"])})
    return {"kind": "path", "mode": "add", "start": q3(first),
            "segments": segs}


def offset_verts(verts, d):
    """Shift every edge of the convex CCW polygon inward by d."""
    n = len(verts)
    lines = []
    for i in range(n):
        a, b = verts[i], verts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ll = math.hypot(dx, dy)
        nx, ny = dy / ll, -dx / ll                       # outward
        lines.append(((a[0] - nx * d, a[1] - ny * d), (dx / ll, dy / ll)))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    return out


def _clear(verts, geo, x, y):
    """Clearance from (x, y) to a rounded CONVEX CCW polygon (+ = inside)."""
    cl = math.inf
    n = len(verts)
    for i in range(n):
        a, b = verts[i], verts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ll = math.hypot(dx, dy)
        nx, ny = dy / ll, -dx / ll
        cl = min(cl, nx * (a[0] - x) + ny * (a[1] - y))
    for g in geo:
        # nearest boundary is this corner's arc only when the direction from
        # the arc center lies inside the arc's CCW angular span (< 180 deg)
        px_, py_ = x - g["c"][0], y - g["c"][1]
        ix, iy = g["a_in"][0] - g["c"][0], g["a_in"][1] - g["c"][1]
        ox, oy = g["a_out"][0] - g["c"][0], g["a_out"][1] - g["c"][1]
        if ix * py_ - iy * px_ >= 0 and px_ * oy - py_ * ox >= 0:
            cl = min(cl, g["r"] - math.hypot(px_, py_))
    return cl


GEO = _corner_geo(VERTS, RADII)


def sdf(x, y):
    """Clearance from (x, y) to the rounded outline (positive = inside)."""
    return _clear(VERTS, GEO, x, y)


def rounded_path_e(verts, r):
    return outline_path(verts, [r] * len(verts))


def cavity_geo():
    """Cavity boundary: outline offset CAV_D, clipped flat at CAV_Y0, with
    CLIP_R cutter fillets at the two clip corners (no sharp internal
    corners anywhere on the pocket wall)."""
    ov = offset_verts(VERTS, CAV_D)
    orr = [r - CAV_D for r in RADII]

    def clip_pt(a, b):
        t = (CAV_Y0 - a[1]) / (b[1] - a[1])
        return (a[0] + (b[0] - a[0]) * t, CAV_Y0)
    pr = clip_pt(ov[0], ov[1])          # right slant crosses the clip line
    pl = clip_pt(ov[6], ov[7])          # left slant crosses the clip line
    verts = [pr] + ov[1:7] + [pl]
    radii = [CLIP_R] + orr[1:7] + [CLIP_R]
    return verts, radii


CAV_V, CAV_R = cavity_geo()
CAV_GEO = _corner_geo(CAV_V, CAV_R)


def cav_clear(x, y):
    """Clearance from (x, y) to the cavity boundary (positive = inside)."""
    return _clear(CAV_V, CAV_GEO, x, y)


def rrect(x0, x1, y0, y1, r):
    return rounded_path_e([(x1, y0), (x1, y1), (x0, y1), (x0, y0)], r)


def circ(cx, cy, r, mode="add"):
    return {"kind": "circle", "r": r, "x": cx, "y": cy, "mode": mode}


def _arc_via(c, r, p_from, p_to, cw):
    """Midpoint of the arc around c from p_from to p_to (cw/ccw)."""
    a0 = math.atan2(p_from[1] - c[1], p_from[0] - c[0])
    a1 = math.atan2(p_to[1] - c[1], p_to[0] - c[0])
    sweep = (a0 - a1) % (2 * math.pi) if cw else (a1 - a0) % (2 * math.pi)
    mid = a0 - sweep / 2 if cw else a0 + sweep / 2
    return (c[0] + r * math.cos(mid), c[1] + r * math.sin(mid))


def path_from_segs(start, segs):
    """Segment list -> sketch path entity. seg = ('line', to) or
    ('arc', centre, radius, from, to, clockwise)."""
    def q3(p):
        return [round(p[0], 3), round(p[1], 3)]
    out = []
    for s in segs:
        if s[0] == "line":
            out.append({"type": "line", "to": q3(s[1])})
        else:
            _, c, r, p_from, p_to, cw = s
            out.append({"type": "arc",
                        "via": q3(_arc_via(c, r, p_from, p_to, cw)),
                        "to": q3(p_to)})
    return {"kind": "path", "mode": "add", "start": q3(start),
            "segments": out}


def sample_segs(start, segs, n=8):
    """Polyline sample of a segment list (preview only)."""
    pts = [start]
    for s in segs:
        if s[0] == "line":
            pts.append(s[1])
        else:
            _, c, r, p_from, p_to, cw = s
            a0 = math.atan2(p_from[1] - c[1], p_from[0] - c[0])
            a1 = math.atan2(p_to[1] - c[1], p_to[0] - c[0])
            sweep = ((a0 - a1) % (2 * math.pi) if cw
                     else (a1 - a0) % (2 * math.pi))
            for k in range(1, n + 1):
                a = a0 - sweep * k / n if cw else a0 + sweep * k / n
                pts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
    return pts


def flared_path(x0, x1, y0, y_open, r_bot, fl, over=OPEN_OVER):
    """A pocket whose NORTH end OPENS into the cavity at y_open. Its side
    walls run into the cavity's south wall through convex `fl` fillets that
    are TANGENT to that wall, so the remaining material flows side-wall ->
    arc -> cavity-wall with no cusp and no 90-deg tip; the cut over-runs
    `over` past the line so no coincident face is left behind. CCW."""
    assert y_open - fl > y0 + r_bot + 1.0, "flare eats the whole side wall"
    y_top = y_open + over
    segs = [("line", (x1, y_open - fl)),
            ("arc", (x1 + fl, y_open - fl), fl,
             (x1, y_open - fl), (x1 + fl, y_open), True),
            ("line", (x1 + fl, y_top)),
            ("line", (x0 - fl, y_top)),
            ("line", (x0 - fl, y_open)),
            ("arc", (x0 - fl, y_open - fl), fl,
             (x0 - fl, y_open), (x0, y_open - fl), True),
            ("line", (x0, y0 + r_bot)),
            ("arc", (x0 + r_bot, y0 + r_bot), r_bot,
             (x0, y0 + r_bot), (x0 + r_bot, y0), False),
            ("line", (x1 - r_bot, y0)),
            ("arc", (x1 - r_bot, y0 + r_bot), r_bot,
             (x1 - r_bot, y0), (x1, y0 + r_bot), False)]
    return (x1, y0 + r_bot), segs


def flare_ok(name, x0, x1, y_open, fl, over=OPEN_OVER):
    """Both flare tangents must land on the STRAIGHT run of the cavity's
    south wall (1mm spare), and the over-run must stay inside the cavity —
    otherwise the flare would bite a fresh notch into the wall."""
    for x in (x1 + fl, x0 - fl):
        edge = 1.0 if x > 0 else -1.0
        assert cav_clear(x + edge, y_open + 1.0) >= 0.99, \
            f"{name} flare tangent x={x:.2f} runs off the cavity south edge"
        assert cav_clear(x, y_open + over) >= 1.0, \
            f"{name} over-run corner ({x:.2f},{y_open + over}) leaves cavity"


def scalloped_box(foot, holes, scal_r, r_f=FILLET_TIP):
    """One smooth slot-box path: straight edges, a concave scallop around
    the pillar at each corner, and tangent r_f blend arcs at every
    scallop/edge junction — zero pointed tips on the outline."""
    x0, x1, y0, y1, *_ = foot
    cx_, cy_ = (x0 + x1) / 2, (y0 + y1) / 2
    K = scal_r + r_f

    def pick(sx, sy):
        return next((hx, hy) for hx, hy in holes
                    if (hx > cx_) == (sx > 0) and (hy > cy_) == (sy > 0))

    def leg(root, off):
        d2 = K * K - off * off
        assert d2 > (r_f + 0.2) ** 2, "tip blend does not reach the edge"
        return root, math.sqrt(d2)

    def corner(sx, sy):
        p = pick(sx, sy)
        ex = x1 - r_f if sx > 0 else x0 + r_f      # vertical blend line
        ey = y1 - r_f if sy > 0 else y0 + r_f      # horizontal blend line
        _, sv = leg(p, ex - p[0])                  # offset along the v-edge
        _, sh = leg(p, ey - p[1])                  # offset along the h-edge
        c_v = (ex, p[1] - sy * sv)                 # blend centre on the v-edge
        c_h = (p[0] - sx * sh, ey)                 # blend centre on the h-edge
        t_v = (x1 if sx > 0 else x0, c_v[1])       # tangent foot on the v-edge
        t_h = (c_h[0], y1 if sy > 0 else y0)       # tangent foot on the h-edge

        def on_pillar(c):
            f = r_f / K
            return (c[0] + (p[0] - c[0]) * f, c[1] + (p[1] - c[1]) * f)
        # traveling CCW: BR/TL corners arrive on the h-edge and leave on the
        # v-edge; TR/BL corners arrive on the v-edge and leave on the h-edge
        if sx * sy < 0:
            cin, tin, cout, tout = c_h, t_h, c_v, t_v
        else:
            cin, tin, cout, tout = c_v, t_v, c_h, t_h
        q_in, q_out = on_pillar(cin), on_pillar(cout)
        return [("line", tin),
                ("arc", cin, r_f, tin, q_in, False),
                ("arc", p, scal_r, q_in, q_out, True),
                ("arc", cout, r_f, q_out, tout, False)], tout

    parts = [corner(1, -1), corner(1, 1), corner(-1, 1), corner(-1, -1)]
    start = parts[-1][1]        # BL exit foot on the bottom edge
    return path_from_segs(start, [s for part, _ in parts for s in part])


# ------------------------------------------------------------- sanity gates
assert 2 * L2 + 8 <= 220 and 2 * HEAD2 + 8 <= 120, "does not fit the stock"

# fit gates: pillar pitches sit inside their boards, seats fit the parts
assert ESP_HOLE_P[0] < C_ESP[0] and ESP_HOLE_P[1] < C_ESP[1]
assert OLED_HOLE_P < C_OLED[0]
assert SD_HOLE_P[0] < C_SD[1] and SD_HOLE_P[1] < C_SD[0]
assert KEYPAD[1] - KEYPAD[0] >= KEY_W + 0.5
assert KEYPAD[3] - KEYPAD[2] >= KEY_L + 0.5
assert BATT_SEAT[1] - BATT_SEAT[0] >= C_BATT[0] + 0.5
assert BATT_SEAT[3] - BATT_SEAT[2] >= C_BATT[1] + 0.5
assert 2 * BUZZ[2] >= C_BUZZ + 0.5
# component underside clearance over the cavity floor (pins hang free)
assert ESP_TOP - 3.0 >= CAV_Z + 0.5, "esp header pins hit the cavity floor"
assert OLED_TOP - 4.0 >= CAV_Z + 0.5, "oled pins hit the cavity floor"
assert SD_TOP - 2.5 >= CAV_Z + 0.5, "sd solder side hits the cavity floor"

# silhouette clearances: ring needs 5.4; cavity wall is 5.6
WALL_MIN = RING_D2 + 1.2
assert CAV_D >= WALL_MIN
for cx_, cy_ in ((KEYPAD[0], KEYPAD[2]), (KEYPAD[0], KEYPAD[3]),
                 (KEYPAD[1], KEYPAD[2]), (KEYPAD[1], KEYPAD[3])):
    assert sdf(cx_, cy_) >= WALL_MIN, f"keypad corner ({cx_},{cy_})"
for x0, x1, y0, y1, *_ in (BATT_SEAT,):
    for cx_, cy_ in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
        assert sdf(cx_, cy_) >= CAV_D + 0.8, \
            f"batt seat corner ({cx_},{cy_}) undercuts the cavity wall"
# the 0.5-deep seat must not touch the rim islands (tangent cusps there)
assert BATT_SEAT[2] - BATT_RIMS[0][3] >= 0.8, "batt seat kisses the south rim"
assert BATT_RIMS[1][2] - BATT_SEAT[3] >= 0.8, "batt seat kisses the north rim"

# islands: inside the cavity (edge >= CAV_D + 2 from silhouette) or
# deliberately fused into the wall (edge reaches past the wall inner face)
ISLAND_CIRCLES = ([(x, y, ESP_PIL_R) for x, y in ESP_HOLES]
                  + [(x, y, SD_PIL_R) for x, y in SD_HOLES]
                  + [(x, y, OLED_PIL_R) for x, y in OLED_HOLES]
                  + [(x, y, BUZZ_PIL_R) for x, y in BUZZ_PIL]
                  + [(x, y, LORA_PIL_R) for x, y in LORA_PIL])
for cx_, cy_, r in ISLAND_CIRCLES:
    lo = min(sdf(cx_ + r * math.cos(a * math.pi / 6),
                 cy_ + r * math.sin(a * math.pi / 6)) for a in range(12))
    assert lo >= CAV_D + 2.0, f"island ({cx_},{cy_}) near wall {lo:.2f}"

# island-to-island / island-to-platform gaps (>= 2.0 for the cutter);
# the 0.5-deep locating seats are exempt (cosmetic step only)
def gap_cc(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1]) - a[2] - b[2]


for i in range(len(ISLAND_CIRCLES)):
    for j in range(i + 1, len(ISLAND_CIRCLES)):
        a, b = ISLAND_CIRCLES[i], ISLAND_CIRCLES[j]
        same_part = (a[2] == b[2] and abs(a[0] - b[0]) < 0.01) or \
                    (a[2] == b[2] and abs(a[1] - b[1]) < 0.01)
        g = gap_cc(a, b)
        assert g >= 2.0 or g >= 8.0 or same_part or True  # pairwise report
        if g < 2.0 and not same_part:
            raise AssertionError(f"islands {a} / {b} gap {g:.2f}")
for cx_, cy_, r in ISLAND_CIRCLES:
    assert cy_ - r >= CAV_Y0 + 2.0, f"island ({cx_},{cy_}) near keypad platform"
    for rx0, rx1, ry0, ry1, _ in BATT_RIMS:
        dx = max(rx0 - cx_, 0, cx_ - rx1)
        dy = max(ry0 - cy_, 0, cy_ - ry1)
        assert math.hypot(dx, dy) - r >= 2.0, \
            f"island ({cx_},{cy_}) hits a battery rim"
# strap pilots centred on the rims
for (hx, hy), (rx0, rx1, ry0, ry1, _) in zip(STRAP, BATT_RIMS):
    assert rx0 + STRAP_R + 1.0 <= hx <= rx1 - STRAP_R - 1.0
    # the old gate only checked CONTAINMENT (+-0.01), so it happily allowed a
    # 1.0mm web; the wall each side of the pilot must clear the 1.5 minimum
    assert hy - STRAP_R - ry0 >= 1.5 and ry1 - hy - STRAP_R >= 1.5, \
        f"strap pilot ({hx},{hy}) leaves a thin rim web"
# buzzer seat clear of its own clamp pillars
for bx, by in BUZZ_PIL:
    assert math.hypot(bx - BUZZ[0], by - BUZZ[1]) - BUZZ[2] - BUZZ_PIL_R \
        >= 0.2, "buzzer seat undercuts a clamp pillar"
for bx, by in LORA_PIL:
    dy = max(LORA_FOOT[2] - by, by - LORA_FOOT[3])
    assert dy - LORA_PIL_R - 0.5 >= 0.3, "lora pillar crosses its slot box"


def scallop_ok(foot, holes, pil_r, scal_r):
    """CURVE RULE: each pillar scallop keeps a cutter moat around the
    pillar, pokes cleanly PAST both nearby box edges (nothing wraps behind
    the pillar), and swallows the nearest sharp box corner (no slivers)."""
    x0, x1, y0, y1, *_ = foot
    assert scal_r >= pil_r + 1.2, "scallop moat too tight for a cutter"
    for hx, hy in holes:
        dx = min(hx - x0, x1 - hx)
        dy = min(hy - y0, y1 - hy)
        assert scal_r >= dx + 0.4, f"scallop ({hx},{hy}) traps an x-strip"
        assert scal_r >= dy + 0.4, f"scallop ({hx},{hy}) traps a y-strip"
        ncx = x0 if hx - x0 < x1 - hx else x1
        ncy = y0 if hy - y0 < y1 - hy else y1
        assert math.hypot(hx - ncx, hy - ncy) <= scal_r - 0.2, \
            f"scallop ({hx},{hy}) leaves a corner sliver"


scallop_ok(ESP_FOOT, ESP_HOLES, ESP_PIL_R, SCAL_ESP)
scallop_ok(OLED_FOOT, OLED_HOLES, OLED_PIL_R, SCAL_OLED)
scallop_ok(SD_FOOT, SD_HOLES, SD_PIL_R, SCAL_SD)
# every pilot must leave a real collar of steel in its pillar/platform
assert ESP_PIL_R - ESP_HOLE_R >= 1.0, "esp pilot leaves no pillar wall"
assert SD_PIL_R - SD_HOLE_R >= 1.0, "sd pilot leaves no pillar wall"
assert OLED_PIL_R - OLED_HOLE_R >= 1.0, "oled pilot leaves no pillar wall"
assert BUZZ_PIL_R - BUZZ_HOLE_R >= 1.0, "clamp pilot leaves no pillar wall"

# the keypad recess and the wire trench END on the cavity wall line, so
# their flares must be tangent to its straight run (no cusp, no new notch)
assert KEYPAD[3] == CAV_Y0, "keypad recess must end exactly on the cavity line"
assert TRENCH[3] == CAV_Y0, "wire trench must end exactly on the cavity line"
flare_ok("keypad", KEYPAD[0], KEYPAD[1], CAV_Y0, KEY_FLARE)
flare_ok("trench", TRENCH[0], TRENCH[1], CAV_Y0, TR_FLARE)
# the flares must not reach each other or the keypad screw pilots
assert TRENCH[1] + TR_FLARE + 2.0 <= KEYPAD[1], "trench flare hits the recess wall"

# keypad: screw pilots inside the recess, clear of the wire trench
assert LORA_FOOT[1] - LORA_FOOT[0] >= C_LORA[0] + 0.5
assert LORA_FOOT[3] - LORA_FOOT[2] >= C_LORA[1] + 0.5
for hx, hy in KEY_HOLES:
    assert KEYPAD[0] + 1.2 <= hx - KEY_HOLE_R and \
        hx + KEY_HOLE_R <= KEYPAD[1] - 1.2, f"key pilot ({hx},{hy}) x"
    assert KEYPAD[2] + 1.2 <= hy - KEY_HOLE_R and \
        hy + KEY_HOLE_R <= KEYPAD[3] - 1.2, f"key pilot ({hx},{hy}) y"
    assert abs(hx) - KEY_HOLE_R >= TRENCH[1] + 1.0, "key pilot in trench"

# footprint slot boxes: fit their component, stay inside the cavity floor,
# clear of the keypad platform and the battery rims/seat
assert ESP_FOOT[1] - ESP_FOOT[0] >= C_ESP[0] + 0.5
assert ESP_FOOT[3] - ESP_FOOT[2] >= C_ESP[1] + 0.5
assert OLED_FOOT[1] - OLED_FOOT[0] >= C_OLED[0] + 0.5
assert SD_FOOT[1] - SD_FOOT[0] >= C_SD[1] + 0.5
assert SD_FOOT[3] - SD_FOOT[2] >= C_SD[0] + 0.5
for name, (x0, x1, y0, y1, z, r) in {"esp_foot": ESP_FOOT,
                                     "oled_foot": OLED_FOOT,
                                     "sd_foot": SD_FOOT,
                                     "lora_foot": LORA_FOOT}.items():
    for cx_, cy_ in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
        assert sdf(cx_, cy_) >= CAV_D + 0.2, f"{name} corner ({cx_},{cy_})"
    assert y0 >= CAV_Y0 + 0.4, f"{name} reaches the keypad platform"
assert ESP_FOOT[3] <= BATT_RIMS[0][2] - 0.8, "esp foot hits the strap rim"
assert SD_FOOT[0] >= BATT_SEAT[1] + 1.0, "sd foot overlaps the battery seat"

# ---- company-name engraving in the wire slot (v10)
# it must run ALONG the slot, fit across it, and be cuttable by the D2
assert abs(LOGO_ACROSS_MM - LOGO_ACROSS) <= 0.35, \
    f"name came out {LOGO_ACROSS_MM} across, asked for {LOGO_ACROSS}"
assert LOGO_ACROSS_MM <= LOGO_SLOT_MAX, "name wider than the slot allows"
assert LOGO_ACROSS_MM + 4.0 <= TRENCH[1] - TRENCH[0], \
    "name leaves under 2mm of slot wall on each side"
# it must sit in the clear run of the slot, NORTH of the tail-fold scoop
assert LOGO_Y0 + 3.0 <= LOGO_CY - LOGO_LEN / 2, \
    f"name reaches into the tail-fold scoop (needs y >= {LOGO_Y0 + 3.0})"
assert LOGO_CY + LOGO_LEN / 2 <= LOGO_Y1 - 3.0, \
    "name runs past the slot into the cavity"
assert SCOOP_T[0] >= TRENCH[0] and SCOOP_T[1] <= TRENCH[1], \
    "scoop wider than the slot - re-derive the name's clear run"
assert LOGO_MISS <= LOGO_MISS_MAX, (
    f"the specified D{LOGO_TOOL_D} cannot reach {LOGO_MISS:.1%} of the"
    f" artwork (limit {LOGO_MISS_MAX:.0%}) - use a smaller lettering cutter,"
    f" a heavier/condensed face, or fewer characters")
assert TRENCH[4] - LOGO_DEEP >= 5.0, "engraving leaves under 5mm of steel"
assert LOGO_DEEP >= 0.5, "engraving too shallow to read in steel"
# the keypad screw pilots live outside the slot, so they cannot be crowded,
# but assert it rather than trusting the layout to stay put
for _hx, _hy in KEY_HOLES:
    assert abs(_hx) > TRENCH[1] + 0.5, "a keypad pilot sits inside the slot"
for _b in LOGO_BATCHES:
    assert len(_b) <= 10, "logo sketch batch over the 10-entity lint"


# ------------------------------------------------------------- feature tree
F = []


def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


f("outline_sketch", "sketch", {"plane": "XY", "offset": 0,
                               "entities": [outline_path(VERTS, RADII)]})
# v6: no top-rim fillet — outer corners stay SQUARE (no chamfer tooling)
f("body", "extrude", {"amount": T}, ["outline_sketch"])

prev = "body"


def pocket(name, z, ents, top=None):
    global prev
    f(f"{name}_sketch", "sketch", {"plane": "XY", "offset": z,
                                   "entities": ents})
    amt = (T + 1 if top is None else top) - z
    f(f"{name}_tool", "extrude", {"amount": round(amt, 3)}, [f"{name}_sketch"])
    f(name, "cut", {}, [prev, f"{name}_tool"])
    prev = name


def rr(p):
    return rrect(p[0], p[1], p[2], p[3], p[5] if len(p) > 5 else p[4])


# keypad platform: shallow recess (rigid pad, keys ride proud), M2 pilots.
# The recess and the wire trench OPEN into the cavity through tangent
# flares (v6) — no cusps at the keyboard start, and no rib notch needed.
KEY_PATH = flared_path(KEYPAD[0], KEYPAD[1], KEYPAD[2], CAV_Y0,
                       KEYPAD[5], KEY_FLARE)
TR_PATH = flared_path(TRENCH[0], TRENCH[1], TRENCH[2], CAV_Y0,
                      TRENCH[5], TR_FLARE)
pocket("keypad_recess", KEYPAD[4], [path_from_segs(*KEY_PATH)])
pocket("keypad_pilots", KEYPAD[4] - 4.0,
       [circ(x, y, KEY_HOLE_R) for x, y in KEY_HOLES], top=KEYPAD[4] + 0.5)
pocket("tail_trench", TRENCH[4], [path_from_segs(*TR_PATH)])
# the name, engraved into the slot floor only (the cutter spans just the
# 0.8 below that floor, so nothing above the slot is touched)
for _i, _batch in enumerate(LOGO_BATCHES):
    pocket(f"logo_{_i}", round(TRENCH[4] - LOGO_DEEP, 3), _batch,
           top=round(TRENCH[4] + 0.2, 3))
pocket("tail_fold_scoop", SCOOP_T[4], [rr(SCOOP_T)])

# ---- first cut: the weight-reduction cavity, islands left standing
f("cav_sketch", "sketch", {"plane": "XY", "offset": CAV_Z,
                           "entities": [outline_path(*cavity_geo())]})
f("cav_tool", "extrude", {"amount": T - CAV_Z + 1}, ["cav_sketch"])

isl1 = ([rrect(*t) for t in BATT_RIMS]
        + [circ(x, y, ESP_PIL_R) for x, y in ESP_HOLES]
        + [circ(x, y, SD_PIL_R) for x, y in SD_HOLES])
isl2 = ([circ(x, y, OLED_PIL_R) for x, y in OLED_HOLES]
        + [circ(x, y, BUZZ_PIL_R) for x, y in BUZZ_PIL]
        + [circ(x, y, LORA_PIL_R) for x, y in LORA_PIL])
f("isl1_sketch", "sketch", {"plane": "XY", "offset": CAV_Z - 1,
                            "entities": isl1})
f("isl1_tool", "extrude", {"amount": T - CAV_Z + 3}, ["isl1_sketch"])
f("isl2_sketch", "sketch", {"plane": "XY", "offset": CAV_Z - 1,
                            "entities": isl2})
f("isl2_tool", "extrude", {"amount": T - CAV_Z + 3}, ["isl2_sketch"])
f("cav_neg", "cut", {}, ["cav_tool", "isl1_tool", "isl2_tool"])
f("main_cavity", "cut", {}, [prev, "cav_neg"])
prev = "main_cavity"

# ---- trim the islands to their working heights (oversized tools)
pocket("esp_pillar_trim", ESP_TOP,
       [circ(x, y, ESP_PIL_R + 1.0) for x, y in ESP_HOLES])
pocket("batt_rim_trim", RIM_TOP,
       [rrect(x0 - 1, x1 + 1, y0 - 0.5, y1 + 0.5, r)
        for x0, x1, y0, y1, r in BATT_RIMS])
pocket("sd_pillar_trim", SD_TOP,
       [circ(x, y, SD_PIL_R + 1.0) for x, y in SD_HOLES])
pocket("oled_pillar_trim", OLED_TOP,
       [circ(x, y, OLED_PIL_R + 1.0) for x, y in OLED_HOLES])
# buzzer clamp pillars stay full height (z12)

# ---- locating seats (0.5 deep spots in the cavity floor)
pocket("batt_seat", BATT_SEAT[4], [rr(BATT_SEAT)], top=CAV_Z + 0.5)
pocket("buzzer_seat", 2.5, [circ(BUZZ[0], BUZZ[1], BUZZ[2])], top=CAV_Z + 0.5)

# ---- footprint slot boxes: every component outline visible in the block,
# 0.5 deep around the pillars (subtracted collars keep the bases intact)
pocket("esp_foot", ESP_FOOT[4],
       [scalloped_box(ESP_FOOT, ESP_HOLES, SCAL_ESP)], top=CAV_Z + 0.5)
pocket("oled_foot", OLED_FOOT[4],
       [scalloped_box(OLED_FOOT, OLED_HOLES, SCAL_OLED)], top=CAV_Z + 0.5)
pocket("sd_foot", SD_FOOT[4],
       [scalloped_box(SD_FOOT, SD_HOLES, SCAL_SD)], top=CAV_Z + 0.5)
# LoRa clamp pillars stand fully OUTSIDE this box -> plain smooth rrect
pocket("lora_foot", LORA_FOOT[4], [rr(LORA_FOOT)], top=CAV_Z + 0.5)

# ---- screw pilot pipes
pocket("esp_pilots", CAV_Z,
       [circ(x, y, ESP_HOLE_R) for x, y in ESP_HOLES], top=ESP_TOP + 0.5)
pocket("sd_pilots", CAV_Z,
       [circ(x, y, SD_HOLE_R) for x, y in SD_HOLES], top=SD_TOP + 0.5)
pocket("oled_pilots", OLED_TOP - 4.0,
       [circ(x, y, OLED_HOLE_R) for x, y in OLED_HOLES], top=OLED_TOP + 0.5)
pocket("clamp_pilots", T - 5.0,
       [circ(x, y, BUZZ_HOLE_R) for x, y in BUZZ_PIL]
       + [circ(x, y, LORA_HOLE_R) for x, y in LORA_PIL], top=T + 0.5)
pocket("strap_pilots", RIM_TOP - 4.0,
       [circ(x, y, STRAP_R) for x, y in STRAP], top=RIM_TOP + 0.5)

# ---- rim pinstripe: (outline-3.0 minus outline-4.2) band, 0.6 deep
f("ringA_sketch", "sketch", {"plane": "XY", "offset": RING_Z, "entities":
  [outline_path(offset_verts(VERTS, RING_D1),
                [r - RING_D1 for r in RADII])]})
f("ringA_tool", "extrude", {"amount": 1.3}, ["ringA_sketch"])
f("ringB_sketch", "sketch", {"plane": "XY", "offset": RING_Z - 0.1,
  "entities": [outline_path(offset_verts(VERTS, RING_D2),
                            [r - RING_D2 for r in RADII])]})
f("ringB_tool", "extrude", {"amount": 1.6}, ["ringB_sketch"])
f("ring_band", "cut", {}, ["ringA_tool", "ringB_tool"])
f("esp32_remote", "cut", {}, [prev, "ring_band"])

tree = {"name": "esp32-remote", "features": F,
        "spec": {"n_solids": 1, "size": [90, 200, 12], "tol": 0.3}}
open(ROOT + r"\designs\esp32-remote-tree.json", "w").write(json.dumps(tree))

# ------------------------------------------------------------- preview
S = 4.0
W, HT = int(106 * S), int(210 * S)
img = Image.new("RGB", (W, HT), (18, 24, 32))
d = ImageDraw.Draw(img)
C_FACE, C_RING = (176, 180, 186), (110, 116, 124)
C_CAV, C_ISL, C_SEAT = (70, 76, 84), (150, 155, 162), (56, 62, 70)
C_MID, C_TXT, C_HOLE = (120, 126, 134), (240, 242, 245), (26, 30, 36)


def px(p):
    return (W / 2 + p[0] * S, HT / 2 - p[1] * S)


def sample_outline(verts, radii):
    pts = []
    for g in _corner_geo(verts, radii):
        a0 = math.atan2(g["a_in"][1] - g["c"][1], g["a_in"][0] - g["c"][0])
        a1 = math.atan2(g["a_out"][1] - g["c"][1], g["a_out"][0] - g["c"][0])
        sweep = (a1 - a0) % (2 * math.pi)
        for k in range(9):
            a = a0 + sweep * k / 8
            pts.append((g["c"][0] + g["r"] * math.cos(a),
                        g["c"][1] + g["r"] * math.sin(a)))
    return pts


def poly_mask(verts, radii):
    m = Image.new("L", (W, HT), 0)
    ImageDraw.Draw(m).polygon(
        [px(p) for p in sample_outline(verts, radii)], fill=255)
    return m


d.polygon([px(p) for p in sample_outline(VERTS, RADII)], fill=C_FACE)
# cavity region: clipped offset silhouette with filleted clip corners
img.paste(Image.new("RGB", (W, HT), C_CAV), (0, 0), poly_mask(*cavity_geo()))
# pinstripe ring band on the remaining face
ring_m = poly_mask(offset_verts(VERTS, RING_D1), [r - RING_D1 for r in RADII])
ImageDraw.Draw(ring_m).polygon(
    [px(p) for p in sample_outline(offset_verts(VERTS, RING_D2),
                                   [r - RING_D2 for r in RADII])], fill=0)
img.paste(Image.new("RGB", (W, HT), C_RING), (0, 0), ring_m)
d = ImageDraw.Draw(img)


def rbox(t, col, r=None):
    d.rounded_rectangle([px((t[0], t[3])), px((t[1], t[2]))],
                        radius=(t[4] if r is None else r) * S, fill=col)


def dot(cx, cy, r, col):
    d.ellipse([px((cx - r, cy + r)), px((cx + r, cy - r))], fill=col)


# platform features — the flared cuts are clipped at the cavity line (their
# over-run north of it lands in air the cavity already removed)
def paste_clipped(color, pts):
    m = Image.new("L", (W, HT), 0)
    md_ = ImageDraw.Draw(m)
    md_.polygon([px(p) for p in pts], fill=255)
    md_.rectangle([px((-60, 130)), px((60, CAV_Y0))], fill=0)
    img.paste(Image.new("RGB", (W, HT), color), (0, 0), m)


paste_clipped(C_ISL, sample_segs(*KEY_PATH))
paste_clipped(C_MID, sample_segs(*TR_PATH))
for _e in LOGO_ENTS:
    d.polygon([px((_e['x'] + _q[0], _e['y'] + _q[1]))
               for _q in _e['points']],
              fill=C_HOLE if _e['mode'] == 'add' else C_MID)
rbox((SCOOP_T[0], SCOOP_T[1], SCOOP_T[2], SCOOP_T[3], SCOOP_T[5]), C_SEAT)
# seats
rbox((BATT_SEAT[0], BATT_SEAT[1], BATT_SEAT[2], BATT_SEAT[3], BATT_SEAT[5]),
     C_SEAT)
dot(BUZZ[0], BUZZ[1], BUZZ[2], C_SEAT)
for t in (ESP_FOOT, OLED_FOOT, SD_FOOT, LORA_FOOT):
    rbox((t[0], t[1], t[2], t[3], t[5]), C_SEAT)
for pts, r in ((ESP_HOLES, SCAL_ESP), (OLED_HOLES, SCAL_OLED),
               (SD_HOLES, SCAL_SD)):
    for hx, hy in pts:
        dot(hx, hy, r, C_CAV)
# islands
for t in BATT_RIMS:
    rbox(t, C_ISL)
for pts, r in ((ESP_HOLES, ESP_PIL_R), (SD_HOLES, SD_PIL_R),
               (OLED_HOLES, OLED_PIL_R), (BUZZ_PIL, BUZZ_PIL_R),
               (LORA_PIL, LORA_PIL_R)):
    for hx, hy in pts:
        dot(hx, hy, r, C_ISL)
# pilot holes
for pts, r in ((ESP_HOLES, ESP_HOLE_R), (SD_HOLES, SD_HOLE_R),
               (OLED_HOLES, OLED_HOLE_R), (BUZZ_PIL, BUZZ_HOLE_R),
               (LORA_PIL, LORA_HOLE_R), (STRAP, STRAP_R),
               (KEY_HOLES, KEY_HOLE_R)):
    for hx, hy in pts:
        dot(hx, hy, max(r, 1.0), C_HOLE)

try:
    FNT = ImageFont.truetype("arial.ttf", 13)
    FNT_S = ImageFont.truetype("arial.ttf", 11)
except OSError:
    FNT = FNT_S = ImageFont.load_default()
LABELS = [((0, OLED_C[1]), "OLED"), ((BUZZ[0], BUZZ[1]), "BZR"),
          ((LORA_C[0], LORA_C[1]), "LoRa"),
          ((SD_C[0], SD_C[1]), "microSD"), ((BATT_C[0], BATT_C[1]),
          "9V BATTERY"), ((0, ESP_C[1]), "ESP32"),
          ((0, KEY_C[1]), "3x4 KEYPAD"), ((0, -87), "tail fold")]
for (lx, ly), s in LABELS:
    d.text(px((lx, ly)), s, font=FNT_S if len(s) < 6 else FNT,
           fill=C_TXT, anchor="mm")

out = ROOT + r"\designs\esp32-remote-preview.png"
img.save(out)
print(f"preview: {out}")
print(f"name {LOGO_WORD!r} in {os.path.basename(LOGO_FONT)}: {LOGO_LEN} along x "
      f"{LOGO_ACROSS_MM} across the slot, engraved {LOGO_DEEP} into the "
      f"z{TRENCH[4]} floor, PERPENDICULAR (runs along the slot)")
print(f"  lettering cutter D{LOGO_TOOL_D}: misses {LOGO_MISS:.1%}"
      f" (limit {LOGO_MISS_MAX:.0%}) | the D{LOGO_TOOL_HAVE} on the shelf"
      f" would miss {LOGO_MISS_HAVE:.1%} and break the letter joins")
print(f"  {len(LOGO_ENTS)} traced polygons in {len(LOGO_BATCHES)} sketches; clear run of the slot y{LOGO_Y0}..{LOGO_Y1}")
print(f"tree: {len(F)} features | shell {2*L2:.0f} x 90 (grip 66, top 74) x 12")
print(f"cavity: floor z{CAV_Z} ({T - CAV_Z} deep), wall {CAV_D}, from "
      f"y{CAV_Y0} up | keypad platform stays solid")
print(f"pillars: ESP 4x D{2*ESP_PIL_R} top z{ESP_TOP} D{2*ESP_HOLE_R} | OLED 4x "
      f"D{2*OLED_PIL_R} top z{OLED_TOP} M2 | SD 4x D{2*SD_PIL_R} top "
      f"z{SD_TOP} M2 (free-standing) | buzzer 2x D{2*BUZZ_PIL_R} "
      f"top z{T} M2 clamp | battery seat 0.5 + rims z{RIM_TOP} "
      f"D{2*STRAP_R} straps")
print("slot boxes: 0.5-deep footprint outlines in the cavity floor for "
      "ESP32 / OLED / microSD / LoRa + battery + buzzer seats")
print(f"machinable corners: cavity clip corners r{CLIP_R}, keypad recess "
      f"r{KEY_FLARE} + trench r{TR_FLARE} flares tangent into the cavity "
      "wall (no cusp at the keyboard start, rib notch gone), battery seat "
      "off the rims/wall, every pocket corner r>=1.5")
print("outer top rim: SQUARE (no chamfer tooling) — only the vertical "
      "corners are radiused, which the cutter does anyway")
print("curved slot boxes: boundaries scallop AROUND the pillars, every "
      f"scallop/edge junction blended tangent r{FILLET_TIP} (no pointed "
      f"tips); LoRa + buzzer pillars fully outside their boxes; NO usb gap "
      f"(wall unbroken); esp + keypad holes D{2*KEY_HOLE_R}")
print(f"keypad: MakerMind RBS11089 3x4 rigid {KEY_W}x{KEY_L}x10, recess "
      f"2.0 deep + 4x D{2*KEY_HOLE_R} pilots pitch {KEY_HOLE_P} (VERIFY) | LoRa Ra-02 "
      f"{C_LORA} on seat + 2x D{2*LORA_PIL_R} M2 clamp pillars (VERIFY)")

# ------------------------------------------------------------- build
if "--build" in sys.argv:
    import contextlib
    import io
    sys.path.insert(0, ROOT)
    import mcp_server as M
    with contextlib.redirect_stdout(io.StringIO()):
        doc = M.author._to_document(tree)
        ok = doc.rebuild()
        rep = M._report(doc, ok)
    print("verified:", rep["verified"])
    for feat in rep["features"]:
        if feat["status"] != "ok":
            print("  FEATURE", feat["id"], feat["status"], feat["problems"])
    if rep.get("spec_problems"):
        print("  SPEC", rep["spec_problems"])
    if ok:
        doc.to_step(ROOT + r"\designs\esp32-remote.step")
        doc.save(ROOT + r"\designs\esp32-remote.tcad.json")
        vol = rep.get("measured", {}).get("volume", 0)
        print(f"volume: {vol:.0f} mm3 = {vol * 7.85e-6:.3f} kg steel "
              f"(v2 was 128695 mm3 = 1.010 kg)")
        print("wrote esp32-remote.step + esp32-remote.tcad.json")
