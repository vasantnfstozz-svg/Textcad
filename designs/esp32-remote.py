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
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = r"c:\Users\VasanSeenivasan\Desktop\textcad"

# ------------------------------------------------------------------ outline
T = 12.0                                     # stock/shell thickness
L2 = 91.0                                    # half length (182 total)
GRIP2, HEAD2, TOP2 = 33.0, 45.0, 37.0        # half widths: grip/head/top
VERTS = [(GRIP2, -L2), (HEAD2, 3.0), (HEAD2, 53.0), (TOP2, L2),
         (-TOP2, L2), (-HEAD2, 53.0), (-HEAD2, 3.0), (-GRIP2, -L2)]  # CCW
RADII = [10.0, 22.0, 22.0, 18.0, 18.0, 22.0, 22.0, 10.0]
RING_D1, RING_D2, RING_Z = 3.0, 4.2, 11.4    # pinstripe groove, 0.6 deep

# ------------------------------------------------------------ main cavity
CAV_D, CAV_Z = 5.6, 3.0        # wall thickness / cavity floor (9 deep)
CAV_Y0 = -31.0                 # cavity starts where the keypad platform ends

# ------------------------------------------------------------------ keypad
KEY_W, KEY_L = 52.0, 52.0     # generic 3x3 membrane — VERIFY vs ordered pad
KEYPAD = (-(KEY_W + 1) / 2, (KEY_W + 1) / 2, -84.0, -84.0 + KEY_L + 1,
          10.8, 3.0)                              # 53 x 53, 1.2 deep
TRENCH = (-9.0, 9.0, -82.0, -33.0, 7.8, 3.0)      # tail bed under the pad
SCOOP_T = (-9.0, 9.0, -82.0, -74.0, 6.0, 2.0)     # 180-deg fold room
NOTCH = (-9.0, 9.0, -34.0, -25.0, 6.0, 2.0)       # rib pass-through

# ------------------------------------------------------- pillars & seats
ESP_C = (0.0, -14.0)                              # board center
ESP_HOLE_P, ESP_PIL_R, ESP_TOP = (47.0, 23.0), 3.5, 7.0
ESP_HOLE_R = 1.0                                  # M2.5 pilot
USB = (26.0, 49.0, -21.0, -7.0, 5.5, 2.0)         # breaches the right wall

BATT_C = (-14.0, 23.0)                            # seat center
BATT_SEAT = (-39.5, 11.5, 8.5, 37.5, 2.5, 3.0)    # 51 x 29, 0.5 deep
BATT_RIMS = [(-36.0, 8.0, 3.5, 8.5, 2.0),         # x0,x1,y0,y1,r — top z9
             (-36.0, 8.0, 37.5, 42.5, 2.0)]
RIM_TOP = 9.0
STRAP = [(-14.0, 6.0), (-14.0, 40.0)]             # M3 strap pilot holes
STRAP_R = 1.25

SD_C = (25.5, 26.5)                               # module center
SD_HOLE_P, SD_PIL_R, SD_TOP = (19.0, 37.0), 2.75, 7.0
SD_HOLE_R = 0.8                                   # M2 pilot
SD_TABS = [(32.0, 40.0, 5.0, 11.0, 1.5),          # bridge outer pillars
           (32.0, 40.0, 42.0, 48.0, 1.5)]         # into the cavity wall

OLED_C = (0.0, 68.5)
OLED_HOLE_P, OLED_PIL_R, OLED_TOP = 23.5, 2.75, 9.5
OLED_HOLE_R = 0.8                                 # M2 pilot

BUZZ = (25.0, 67.0, 6.5)                          # cx, cy, r — seat 0.5 deep
BUZZ_PIL = [(25.0, 56.5), (25.0, 77.5)]           # clamp pillars, top z12
BUZZ_PIL_R, BUZZ_HOLE_R = 3.25, 0.8               # M2 pilot

# researched component sizes (for the fit gates)
C_ESP, C_OLED = (52.0, 28.0), (27.3, 27.3)
C_BATT, C_SD, C_BUZZ = (48.5, 26.5, 17.5), (42.0, 24.0), 12.0

ESP_HOLES = [(ESP_C[0] + sx * ESP_HOLE_P[0] / 2,
              ESP_C[1] + sy * ESP_HOLE_P[1] / 2)
             for sx in (1, -1) for sy in (1, -1)]
SD_HOLES = [(SD_C[0] + sx * SD_HOLE_P[0] / 2, SD_C[1] + sy * SD_HOLE_P[1] / 2)
            for sx in (1, -1) for sy in (1, -1)]
OLED_HOLES = [(OLED_C[0] + sx * OLED_HOLE_P / 2,
               OLED_C[1] + sy * OLED_HOLE_P / 2)
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


GEO = _corner_geo(VERTS, RADII)


def sdf(x, y):
    """Clearance from (x, y) to the rounded outline (positive = inside)."""
    cl = math.inf
    n = len(VERTS)
    for i in range(n):
        a, b = VERTS[i], VERTS[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ll = math.hypot(dx, dy)
        nx, ny = dy / ll, -dx / ll
        cl = min(cl, nx * (a[0] - x) + ny * (a[1] - y))
    for g in GEO:
        # nearest boundary is this corner's arc only when the direction from
        # the arc center lies inside the arc's CCW angular span (< 180 deg)
        px_, py_ = x - g["c"][0], y - g["c"][1]
        ix, iy = g["a_in"][0] - g["c"][0], g["a_in"][1] - g["c"][1]
        ox, oy = g["a_out"][0] - g["c"][0], g["a_out"][1] - g["c"][1]
        if ix * py_ - iy * px_ >= 0 and px_ * oy - py_ * ox >= 0:
            cl = min(cl, g["r"] - math.hypot(px_, py_))
    return cl


def rounded_path_e(verts, r):
    return outline_path(verts, [r] * len(verts))


def rrect(x0, x1, y0, y1, r):
    return rounded_path_e([(x1, y0), (x1, y1), (x0, y1), (x0, y0)], r)


def circ(cx, cy, r, mode="add"):
    return {"kind": "circle", "r": r, "x": cx, "y": cy, "mode": mode}


def poly(pts):
    return {"kind": "polygon", "mode": "add",
            "points": [[round(x, 3), round(y, 3)] for x, y in pts]}


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
        assert sdf(cx_, cy_) >= WALL_MIN, f"batt seat corner ({cx_},{cy_})"

# islands: inside the cavity (edge >= CAV_D + 2 from silhouette) or
# deliberately fused into the wall (edge reaches past the wall inner face)
ISLAND_CIRCLES = ([(x, y, ESP_PIL_R) for x, y in ESP_HOLES]
                  + [(x, y, SD_PIL_R) for x, y in SD_HOLES]
                  + [(x, y, OLED_PIL_R) for x, y in OLED_HOLES]
                  + [(x, y, BUZZ_PIL_R) for x, y in BUZZ_PIL])
for cx_, cy_, r in ISLAND_CIRCLES:
    lo = min(sdf(cx_ + r * math.cos(a * math.pi / 6),
                 cy_ + r * math.sin(a * math.pi / 6)) for a in range(12))
    fused = any(t[0] - 0.1 <= cx_ <= t[1] + 0.1 and t[2] <= cy_ <= t[3]
                for t in SD_TABS)
    assert lo >= CAV_D + 2.0 or fused, f"island ({cx_},{cy_}) near wall {lo:.2f}"

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
    assert ry0 + STRAP_R - 0.01 <= hy <= ry1 - STRAP_R + 0.01
# buzzer seat clear of its own clamp pillars
for bx, by in BUZZ_PIL:
    assert math.hypot(bx - BUZZ[0], by - BUZZ[1]) - BUZZ[2] - BUZZ_PIL_R \
        >= 0.2, "buzzer seat undercuts a clamp pillar"
assert USB[1] > HEAD2 + 1.5, "usb gap must breach the wall"

# ------------------------------------------------------------- feature tree
F = []


def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


f("outline_sketch", "sketch", {"plane": "XY", "offset": 0,
                               "entities": [outline_path(VERTS, RADII)]})
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


# keypad platform (unchanged from v2)
pocket("keypad_recess", KEYPAD[4], [rr(KEYPAD)])
pocket("tail_trench", TRENCH[4], [rr(TRENCH)])
pocket("tail_fold_scoop", SCOOP_T[4], [rr(SCOOP_T)])
pocket("tail_notch", NOTCH[4], [rr(NOTCH)])

# ---- first cut: the weight-reduction cavity, islands left standing
f("cav_sketch", "sketch", {"plane": "XY", "offset": CAV_Z, "entities":
  [outline_path(offset_verts(VERTS, CAV_D), [r - CAV_D for r in RADII])]})
f("cav_tool0", "extrude", {"amount": T - CAV_Z + 1}, ["cav_sketch"])
f("cav_clip_sketch", "sketch", {"plane": "XY", "offset": CAV_Z - 1,
  "entities": [poly([(-60, -120), (60, -120), (60, CAV_Y0), (-60, CAV_Y0)])]})
f("cav_clip_tool", "extrude", {"amount": T - CAV_Z + 3}, ["cav_clip_sketch"])
f("cav_clipped", "cut", {}, ["cav_tool0", "cav_clip_tool"])

isl1 = ([rrect(*t) for t in BATT_RIMS]
        + [circ(x, y, ESP_PIL_R) for x, y in ESP_HOLES]
        + [circ(x, y, SD_PIL_R) for x, y in SD_HOLES])
isl2 = ([rrect(*t) for t in SD_TABS]
        + [circ(x, y, OLED_PIL_R) for x, y in OLED_HOLES]
        + [circ(x, y, BUZZ_PIL_R) for x, y in BUZZ_PIL])
f("isl1_sketch", "sketch", {"plane": "XY", "offset": CAV_Z - 1,
                            "entities": isl1})
f("isl1_tool", "extrude", {"amount": T - CAV_Z + 3}, ["isl1_sketch"])
f("isl2_sketch", "sketch", {"plane": "XY", "offset": CAV_Z - 1,
                            "entities": isl2})
f("isl2_tool", "extrude", {"amount": T - CAV_Z + 3}, ["isl2_sketch"])
f("cav_neg", "cut", {}, ["cav_clipped", "isl1_tool", "isl2_tool"])
f("main_cavity", "cut", {}, [prev, "cav_neg"])
prev = "main_cavity"

# ---- trim the islands to their working heights (oversized tools)
pocket("esp_pillar_trim", ESP_TOP,
       [circ(x, y, ESP_PIL_R + 1.0) for x, y in ESP_HOLES])
pocket("batt_rim_trim", RIM_TOP,
       [rrect(x0 - 1, x1 + 1, y0 - 0.5, y1 + 0.5, r)
        for x0, x1, y0, y1, r in BATT_RIMS])
pocket("sd_shelf_trim", SD_TOP,
       [rrect(12.5, 40.0, 4.5, 11.5, 1.5), rrect(12.5, 40.0, 41.5, 48.5, 1.5)])
pocket("oled_pillar_trim", OLED_TOP,
       [circ(x, y, OLED_PIL_R + 1.0) for x, y in OLED_HOLES])
# buzzer clamp pillars stay full height (z12)

# ---- locating seats (0.5 deep spots in the cavity floor)
pocket("batt_seat", BATT_SEAT[4], [rr(BATT_SEAT)], top=CAV_Z + 0.5)
pocket("buzzer_seat", 2.5, [circ(BUZZ[0], BUZZ[1], BUZZ[2])], top=CAV_Z + 0.5)

# ---- screw pilot pipes
pocket("esp_pilots", CAV_Z,
       [circ(x, y, ESP_HOLE_R) for x, y in ESP_HOLES], top=ESP_TOP + 0.5)
pocket("sd_pilots", CAV_Z,
       [circ(x, y, SD_HOLE_R) for x, y in SD_HOLES], top=SD_TOP + 0.5)
pocket("oled_pilots", OLED_TOP - 4.0,
       [circ(x, y, OLED_HOLE_R) for x, y in OLED_HOLES], top=OLED_TOP + 0.5)
pocket("buzzer_pilots", T - 5.0,
       [circ(x, y, BUZZ_HOLE_R) for x, y in BUZZ_PIL], top=T + 0.5)
pocket("strap_pilots", RIM_TOP - 4.0,
       [circ(x, y, STRAP_R) for x, y in STRAP], top=RIM_TOP + 0.5)

# ---- usb gap through the right wall
pocket("usb_gap", USB[4], [rr(USB)])

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
        "spec": {"n_solids": 1, "size": [90, 182, 12], "tol": 0.3}}
open(ROOT + r"\designs\esp32-remote-tree.json", "w").write(json.dumps(tree))

# ------------------------------------------------------------- preview
S = 4.0
W, HT = int(106 * S), int(192 * S)
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
# cavity region = offset silhouette clipped to y >= CAV_Y0
cav_m = poly_mask(offset_verts(VERTS, CAV_D), [r - CAV_D for r in RADII])
ImageDraw.Draw(cav_m).rectangle([px((-60, CAV_Y0)), px((60, -120))], fill=0)
img.paste(Image.new("RGB", (W, HT), C_CAV), (0, 0), cav_m)
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


# platform features
rbox((KEYPAD[0], KEYPAD[1], KEYPAD[2], KEYPAD[3], KEYPAD[5]), C_ISL)
rbox((TRENCH[0], TRENCH[1], TRENCH[2], TRENCH[3], TRENCH[5]), C_MID)
rbox((SCOOP_T[0], SCOOP_T[1], SCOOP_T[2], SCOOP_T[3], SCOOP_T[5]), C_SEAT)
rbox((NOTCH[0], NOTCH[1], NOTCH[2], NOTCH[3], NOTCH[5]), C_SEAT)
# seats
rbox((BATT_SEAT[0], BATT_SEAT[1], BATT_SEAT[2], BATT_SEAT[3], BATT_SEAT[5]),
     C_SEAT)
dot(BUZZ[0], BUZZ[1], BUZZ[2], C_SEAT)
# islands
for t in BATT_RIMS:
    rbox(t, C_ISL)
for t in SD_TABS:
    rbox(t, C_ISL)
for pts, r in ((ESP_HOLES, ESP_PIL_R), (SD_HOLES, SD_PIL_R),
               (OLED_HOLES, OLED_PIL_R), (BUZZ_PIL, BUZZ_PIL_R)):
    for hx, hy in pts:
        dot(hx, hy, r, C_ISL)
# usb gap
rbox((USB[0], USB[1], USB[2], USB[3], USB[5]), C_HOLE)
# pilot holes
for pts, r in ((ESP_HOLES, ESP_HOLE_R), (SD_HOLES, SD_HOLE_R),
               (OLED_HOLES, OLED_HOLE_R), (BUZZ_PIL, BUZZ_HOLE_R),
               (STRAP, STRAP_R)):
    for hx, hy in pts:
        dot(hx, hy, max(r, 1.0), C_HOLE)

try:
    FNT = ImageFont.truetype("arial.ttf", 13)
    FNT_S = ImageFont.truetype("arial.ttf", 11)
except OSError:
    FNT = FNT_S = ImageFont.load_default()
LABELS = [((0, OLED_C[1]), "OLED"), ((BUZZ[0], BUZZ[1]), "BZR"),
          ((SD_C[0], SD_C[1]), "microSD"), ((BATT_C[0], BATT_C[1]),
          "9V BATTERY"), ((0, ESP_C[1]), "ESP32"), ((41, -14), "USB"),
          ((0, -57.5), "3x3 KEYPAD"), ((0, -78), "tail fold")]
for (lx, ly), s in LABELS:
    d.text(px((lx, ly)), s, font=FNT_S if len(s) < 6 else FNT,
           fill=C_TXT, anchor="mm")

out = ROOT + r"\designs\esp32-remote-preview.png"
img.save(out)
print(f"preview: {out}")
print(f"tree: {len(F)} features | shell 182 x 90 (grip 66, top 74) x 12")
print(f"cavity: floor z{CAV_Z} ({T - CAV_Z} deep), wall {CAV_D}, from "
      f"y{CAV_Y0} up | keypad platform stays solid")
print(f"pillars: ESP 4x D{2*ESP_PIL_R} top z{ESP_TOP} M2.5 | OLED 4x "
      f"D{2*OLED_PIL_R} top z{OLED_TOP} M2 | SD 4x D{2*SD_PIL_R} top "
      f"z{SD_TOP} M2 (outer pair wall-tabbed) | buzzer 2x D{2*BUZZ_PIL_R} "
      f"top z{T} M2 clamp | battery seat 0.5 + rims z{RIM_TOP} M3 straps")

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
