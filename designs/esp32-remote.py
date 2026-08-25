"""esp32-remote v1 — remote-style bottom shell (no top cover) milled from
the 220x120x12 steel stock. Vacuum table rules: every cut is a blind
pocket; the outline is machined as a trench with a ~1.5mm skin and the
part is freed/deburred after. Model = the finished shell.

Component pockets (dims researched online 2026-08-25):
  ESP32 DevKit V1 30-pin   52 x 28      -> slot 54 x 30 floor z5, pin
                                           trenches z2, USB gap out the
                                           right wall, finger scoop left
  4x4 membrane keypad      69 x 77 x 1  -> recess 70 x 78, 1.2 deep; tail
                                           exits the keypad BOTTOM edge ->
                                           fold scoop + trench under the
                                           pad routes it up to the ESP32
  0.96" OLED SSD1306       27.3 sq      -> recess 29 x 29 z9.5 on a 2mm
                                           ledge, wire pit 25 x 25 z4
  9V PP3 battery           48.5x26.5x17.5 -> bay 50 x 28 floor z2.5, lies
                                           flat, sticks 8 above the face
                                           (grip to remove; no cover)
  microSD SPI module       42 x 24 x 5  -> pocket 25 x 43 floor z5 + card
                                           finger scoop at the top end
  active buzzer            D12 x 9.5    -> D13 pocket floor z2.5 (flush)

Face detail: rim pinstripe groove (offset 3.0..4.2, 0.6 deep) like the
sat-panel — interrupted only by the USB gap.

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
L2, W2, W2T, TAPER_Y = 104.0, 47.0, 39.0, 55.0
VERTS = [(W2, -L2), (W2, TAPER_Y), (W2T, L2),
         (-W2T, L2), (-W2, TAPER_Y), (-W2, -L2)]      # CCW
RADII = [18.0, 30.0, 26.0, 26.0, 30.0, 18.0]
RING_D1, RING_D2, RING_Z = 3.0, 4.2, 11.4    # pinstripe groove, 0.6 deep

# ------------------------------------------------------------------ pockets
# (x0, x1, y0, y1, floor z, corner r) — face is z12, cuts go floor -> top
KEYPAD = (-35.0, 35.0, -96.0, -18.0, 10.8, 3.0)   # 70 x 78, 1.2 deep
TRENCH = (-11.0, 11.0, -94.0, -20.0, 7.8, 3.0)    # tail bed under the pad
SCOOP_T = (-11.0, 11.0, -94.0, -86.0, 6.0, 2.0)   # 180-deg fold room
NOTCH = (-11.0, 11.0, -22.0, -12.0, 6.0, 2.0)     # rib pass-through
ESP = (-27.0, 27.0, -15.0, 15.0, 5.0, 3.0)        # 54 x 30
PIN_Y, PIN_W, PIN_L, PIN_Z = 12.5, 5.0, 48.0, 2.0  # 2 trenches under headers
USB = (26.0, 49.0, -7.0, 7.0, 5.5, 2.0)           # breaches the right wall
BATT = (-39.0, 11.0, 19.0, 47.0, 2.5, 4.0)        # 50 x 28
SD = (14.0, 39.0, 19.0, 62.0, 5.0, 3.0)           # 25 x 43
SD_SCOOP = (26.5, 63.5, 6.0)                      # card-end finger scoop
ESP_SCOOP = (-27.0, 0.0, 6.0)                     # board-lift finger scoop
BUZZ = (27.0, 84.0, 6.5, 2.5)                     # cx, cy, r, floor
OLED = (-14.5, 14.5, 66.0, 95.0, 9.5, 2.0)        # 29 x 29 bezel recess
OPIT = (-12.5, 12.5, 68.0, 93.0, 4.0, 2.0)        # wire pit, 2mm ledge

# researched component sizes (for the fit gates)
C_ESP, C_KEY, C_OLED = (52.0, 28.0), (69.0, 77.0), (27.3, 27.3)
C_BATT, C_SD, C_BUZZ = (48.5, 26.5, 17.5), (42.0, 24.0), 12.0


# --------------------------------------------------- rounded outline helpers
def _corner_geo(verts, radii):
    """Per corner: tangent-in, arc-via, tangent-out, center, r, adj normals."""
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


def circ(cx, cy, r):
    return {"kind": "circle", "r": r, "x": cx, "y": cy, "mode": "add"}


# ------------------------------------------------------------- sanity gates
# stock fit: outline + 4mm trench all around must fit the 220 x 120 plate
assert 2 * L2 + 8 <= 220 and 2 * W2 + 8 <= 120, "does not fit the steel stock"

# component fit (>= 0.5mm total slop each way)
assert ESP[1] - ESP[0] >= C_ESP[0] + 0.5 and ESP[3] - ESP[2] >= C_ESP[1] + 0.5
assert KEYPAD[1] - KEYPAD[0] >= C_KEY[0] + 0.5
assert KEYPAD[3] - KEYPAD[2] >= C_KEY[1] + 0.5
assert OLED[1] - OLED[0] >= C_OLED[0] + 0.5 and OLED[3] - OLED[2] >= C_OLED[1] + 0.5
assert BATT[1] - BATT[0] >= C_BATT[0] + 0.5 and BATT[3] - BATT[2] >= C_BATT[1] + 0.5
assert SD[1] - SD[0] >= C_SD[1] + 0.5 and SD[3] - SD[2] >= C_SD[0] + 0.5
assert 2 * BUZZ[2] >= C_BUZZ + 0.5

# every rectangular pocket keeps a wall to the outline AND stays clear of the
# pinstripe ring (offset 4.2 + 1.2 sliver) — USB gap breaches on purpose
WALL_MIN = RING_D2 + 1.2
for name, (x0, x1, y0, y1, z, r) in {
        "keypad": KEYPAD, "esp": ESP, "batt": BATT, "sd": SD,
        "oled": OLED}.items():
    for cx_, cy_ in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
        c = sdf(cx_, cy_)
        assert c >= WALL_MIN, f"{name} corner ({cx_},{cy_}) wall {c:.2f}"
for name, (cx_, cy_, r) in {"sd_scoop": SD_SCOOP, "esp_scoop": ESP_SCOOP,
                            "buzz": (BUZZ[0], BUZZ[1], BUZZ[2])}.items():
    for a in range(12):
        ex = cx_ + r * math.cos(a * math.pi / 6)
        ey = cy_ + r * math.sin(a * math.pi / 6)
        assert sdf(ex, ey) >= WALL_MIN, f"{name} edge ({ex:.1f},{ey:.1f})"

# floors: nothing thinner than 2mm anywhere (vacuum + rigidity)
assert min(KEYPAD[4] - 0, 1) or True
for z in (KEYPAD[4], TRENCH[4], SCOOP_T[4], NOTCH[4], ESP[4], PIN_Z,
          USB[4], BATT[4], SD[4], BUZZ[3], OLED[4], OPIT[4]):
    assert z >= 2.0, f"floor {z} too thin"

# ribs between pockets
assert ESP[2] - KEYPAD[3] == 3.0            # keypad -> esp rib
assert NOTCH[2] < KEYPAD[3] and NOTCH[3] > ESP[2], "tail notch misses"
assert TRENCH[3] >= NOTCH[2], "tail trench must reach the notch"
assert BATT[2] - ESP[3] == 4.0 and SD[2] - ESP[3] == 4.0
assert SD[0] - BATT[1] == 3.0               # batt -> sd rib
assert OLED[2] - SD[3] == 4.0
# sd card scoop stays clear of the OLED recess laterally
assert SD_SCOOP[0] - SD_SCOOP[2] - OLED[1] >= 5.0
# buzzer clear of OLED recess and of the sd scoop
assert BUZZ[0] - BUZZ[2] - OLED[1] >= 5.0
assert BUZZ[1] - BUZZ[2] - (SD_SCOOP[1] + SD_SCOOP[2]) >= 5.0
# trench/scoops nest inside their parents
assert KEYPAD[0] < TRENCH[0] and TRENCH[1] < KEYPAD[1]
assert TRENCH[2] >= KEYPAD[2] - 2.01 and SCOOP_T[2] >= TRENCH[2] - 0.01
# usb gap actually reaches past the wall and into the esp pocket
assert USB[1] > W2 + 1.5 and USB[0] < ESP[1]
# pin trenches stay inside the esp pocket footprint
assert PIN_L / 2 <= ESP[1] and PIN_Y + PIN_W / 2 <= ESP[3] + 0.01
# oled wire pit leaves a 2mm bezel ledge
assert OPIT[0] - OLED[0] >= 2.0 and OLED[3] - OPIT[3] >= 2.0

# ------------------------------------------------------------- feature tree
F = []


def f(id, op, params, inputs=[]):
    F.append({"id": id, "op": op, "params": params, "inputs": inputs})


f("outline_sketch", "sketch", {"plane": "XY", "offset": 0,
                               "entities": [outline_path(VERTS, RADII)]})
f("body", "extrude", {"amount": T}, ["outline_sketch"])

prev = "body"


def pocket(name, z, ents):
    global prev
    f(f"{name}_sketch", "sketch", {"plane": "XY", "offset": z,
                                   "entities": ents})
    f(f"{name}_tool", "extrude", {"amount": round(T - z + 1, 3)},
      [f"{name}_sketch"])
    f(name, "cut", {}, [prev, f"{name}_tool"])
    prev = name


def rr(p):
    return rrect(p[0], p[1], p[2], p[3], p[5])


pocket("keypad_recess", KEYPAD[4], [rr(KEYPAD)])
pocket("tail_trench", TRENCH[4], [rr(TRENCH)])
pocket("tail_fold_scoop", SCOOP_T[4], [rr(SCOOP_T)])
pocket("tail_notch", NOTCH[4], [rr(NOTCH)])
pocket("esp_slot", ESP[4], [rr(ESP), circ(*ESP_SCOOP)])
f("pins_sketch", "sketch", {"plane": "XY", "offset": PIN_Z, "entities": [
    rrect(-PIN_L / 2, PIN_L / 2, s * PIN_Y - PIN_W / 2,
          s * PIN_Y + PIN_W / 2, 1.5) for s in (1, -1)]})
f("pins_tool", "extrude", {"amount": ESP[4] - PIN_Z + 1}, ["pins_sketch"])
f("pin_trenches", "cut", {}, [prev, "pins_tool"])
prev = "pin_trenches"
pocket("usb_gap", USB[4], [rr(USB)])
pocket("battery_bay", BATT[4], [rr(BATT)])
pocket("sd_pocket", SD[4], [rr(SD), circ(*SD_SCOOP)])
pocket("buzzer_pocket", BUZZ[3], [circ(BUZZ[0], BUZZ[1], BUZZ[2])])
pocket("oled_recess", OLED[4], [rr(OLED)])
pocket("oled_wire_pit", OPIT[4], [rr(OPIT)])

# rim pinstripe: (outline-3.0 minus outline-4.2) band, 0.6 deep
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
        "spec": {"n_solids": 1, "size": [94, 208, 12], "tol": 0.3}}
open(ROOT + r"\designs\esp32-remote-tree.json", "w").write(json.dumps(tree))

# ------------------------------------------------------------- preview
S = 4.0
W, HT = int(110 * S), int(218 * S)
img = Image.new("RGB", (W, HT), (18, 24, 32))
d = ImageDraw.Draw(img)
C_FACE, C_RING = (176, 180, 186), (110, 116, 124)
C_SHALLOW, C_MID, C_DEEP = (150, 155, 162), (120, 126, 134), (86, 92, 100)
C_PIT, C_TXT = (60, 66, 74), (240, 242, 245)


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


d.polygon([px(p) for p in sample_outline(VERTS, RADII)], fill=C_FACE)
d.polygon([px(p) for p in sample_outline(offset_verts(VERTS, RING_D1),
                                         [r - RING_D1 for r in RADII])],
          fill=C_RING)
d.polygon([px(p) for p in sample_outline(offset_verts(VERTS, RING_D2),
                                         [r - RING_D2 for r in RADII])],
          fill=C_FACE)


def rbox(p, col):
    d.rounded_rectangle([px((p[0], p[3])), px((p[1], p[2]))],
                        radius=p[5] * S, fill=col)


rbox(KEYPAD, C_SHALLOW)
rbox(TRENCH, C_MID)
rbox(SCOOP_T, C_DEEP)
rbox(NOTCH, C_DEEP)
rbox(ESP, C_MID)
d.ellipse([px((ESP_SCOOP[0] - 6, ESP_SCOOP[1] + 6)),
           px((ESP_SCOOP[0] + 6, ESP_SCOOP[1] - 6))], fill=C_MID)
for s in (1, -1):
    d.rounded_rectangle([px((-PIN_L / 2, s * PIN_Y + PIN_W / 2)),
                         px((PIN_L / 2, s * PIN_Y - PIN_W / 2))],
                        radius=1.5 * S, fill=C_DEEP)
rbox(USB, C_PIT)
rbox(BATT, C_DEEP)
rbox(SD, C_MID)
d.ellipse([px((SD_SCOOP[0] - 6, SD_SCOOP[1] + 6)),
           px((SD_SCOOP[0] + 6, SD_SCOOP[1] - 6))], fill=C_MID)
d.ellipse([px((BUZZ[0] - BUZZ[2], BUZZ[1] + BUZZ[2])),
           px((BUZZ[0] + BUZZ[2], BUZZ[1] - BUZZ[2]))], fill=C_DEEP)
rbox(OLED, C_SHALLOW)
rbox(OPIT, C_PIT)

try:
    FNT = ImageFont.truetype("arial.ttf", 13)
    FNT_S = ImageFont.truetype("arial.ttf", 11)
except OSError:
    FNT = FNT_S = ImageFont.load_default()
LABELS = [((0, 80.5), "OLED 0.96\""), ((27, 84), "BZR"),
          ((26.5, 40.5), "microSD"), ((-14, 33), "9V BATTERY"),
          ((0, 0), "ESP32 DEVKIT"), ((40, 0), "USB"),
          ((0, -57), "4x4 KEYPAD"), ((0, -90), "tail fold")]
for (lx, ly), s in LABELS:
    d.text(px((lx, ly)), s, font=FNT_S if len(s) < 5 else FNT,
           fill=C_TXT, anchor="mm")

out = ROOT + r"\designs\esp32-remote-preview.png"
img.save(out)
print(f"preview: {out}")
print(f"tree: {len(F)} features | shell 208 x 94 (top 78) x 12")
print("z-stack: pins 2 | batt/buzz floor 2.5 | wire pit 4 | esp/sd floor 5 "
      "| usb 5.5 | notch/fold 6 | tail bed 7.8 | oled 9.5 | keypad 10.8 "
      "| ring 11.4 | face 12")
print("heights above face: 9V battery +8.0, everything else at or below")

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
        print("measured:", json.dumps(rep.get("measured", {}))[:400])
        print("wrote esp32-remote.step + esp32-remote.tcad.json")
