"""REVIEW-QUEUE section 9 ROUND TWO — an INDEPENDENT re-check of the three
designs that trace an image, old imgtrace against new.

Round one claims the three generators produce identical output except
esp32-remote's logo, which goes from wrong to right. This rebuilds each
recipe from the generator's own source (same font, same crop, same
height_mm / tol_mm) and compares contour counts, hole counts, point counts,
the artwork bbox and the composed sketch AREA.

Run:  C:\\Python314\\python.exe probes/imgtrace_r2_designs.py
"""
from __future__ import annotations

import importlib.util
import io
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import imgtrace                                                    # noqa: E402
import sketch as sk                                                # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "imgtrace_old", os.path.join(HERE, "_imgtrace_old.py"))
imgtrace_old = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(imgtrace_old)

BAHN = r"C:\Windows\Fonts\bahnschrift.ttf"
IMPACT = r"C:\Windows\Fonts\impact.ttf"


def _png(im):
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def autonomiq_panel():
    """designs/autonomiq-panel-profile.py, the lettering block"""
    font = ImageFont.truetype(BAHN, 220)
    img = Image.new("L", (3000, 500), 255)
    d = ImageDraw.Draw(img)
    x = 60
    for ch in "autonom":
        d.text((x, 120), ch, font=font, fill=0)
        x += d.textlength(ch, font=font) + 55
    img = img.crop(ImageOps.invert(img).getbbox())
    return _png(img), dict(height_mm=16.0, tol_mm=0.12)


def cam_cover_caption():
    """designs/cam-cover-plaque.py text_block(), the pair plaque caption"""
    lines = ["PORSCHE", "FLAT SIX", "CAM COVERS"]
    font = ImageFont.truetype(BAHN, 200)
    pad, lead = 40, int(200 * 1.30)
    img = Image.new("L", (4200, lead * len(lines) + 2 * pad), 255)
    d = ImageDraw.Draw(img)
    widths = [d.textlength(s, font=font) for s in lines]
    for i, s in enumerate(lines):
        d.text((pad + (max(widths) - widths[i]) / 2, pad + i * lead), s,
               font=font, fill=0)
    img = img.crop(ImageOps.invert(img).getbbox())
    return _png(img), dict(height_mm=22.0, tol_mm=0.10)


def esp32_logo():
    """designs/esp32-remote.py _logo_raster() + _logo_entities()"""
    font = ImageFont.truetype(IMPACT, 400)
    im = Image.new("L", (7000, 900), 255)
    dd = ImageDraw.Draw(im)
    x = 100
    for ch in "autonomIQ":
        dd.text((x, 150), ch, font=font, fill=0)
        x += dd.textlength(ch, font=font)
    im = im.crop(ImageOps.invert(im).getbbox())
    im = im.rotate(90, expand=True, fillcolor=255)
    across = 11.0
    length = round(across * im.size[1] / im.size[0], 2)
    return _png(im), dict(height_mm=length, tol_mm=0.08)


def keychain_blob():
    """the rocky-keychain family: a photo-ish blob with a highlight split"""
    import cv2
    import numpy as np
    img = np.full((700, 900, 3), 250, np.uint8)
    cv2.ellipse(img, (450, 350), (330, 230), 12, 0, 360, (20, 20, 20), -1)
    cv2.ellipse(img, (330, 250), (90, 50), -25, 0, 360, (245, 245, 245), -1)
    cv2.circle(img, (620, 300), 45, (250, 250, 250), -1)
    ok, b = cv2.imencode(".png", img)
    assert ok
    return b.tobytes(), dict(height_mm=35.0, tol_mm=0.15)


def alpha_donut():
    import numpy as np
    import cv2
    a = np.zeros((600, 600, 4), np.uint8)
    cv2.circle(a, (300, 300), 260, (0, 0, 0, 255), -1)
    cv2.circle(a, (300, 300), 120, (0, 0, 0, 0), -1)
    ok, b = cv2.imencode(".png", a)
    assert ok
    return b.tobytes(), dict(height_mm=40.0, tol_mm=0.15)


RECIPES = [autonomiq_panel, cam_cover_caption, esp32_logo, keychain_blob,
           alpha_donut]


def run(mod, data, kw):
    try:
        ents, info = mod.image_to_entities(data, **kw)
    except Exception as e:                                    # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        area = round(sk.make_sketch("XY", 0, ents).area, 3)
    except Exception as e:                                    # noqa: BLE001
        area = f"sketch {type(e).__name__}"
    return {"contours": info["contours"], "holes": info["holes"],
            "points": info["points"], "w": info["width_mm"],
            "h": info["height_mm"], "area": area}


def main():
    for fn in RECIPES:
        data, kw = fn()
        a = run(imgtrace_old, data, kw)
        b = run(imgtrace, data, kw)
        same = a == b
        print(f"=== {fn.__name__}  ({kw})")
        print(f"    OLD  {a}")
        print(f"    NEW  {b}")
        print(f"    -> {'IDENTICAL' if same else 'CHANGED'}")
        if not same and "error" not in a and "error" not in b:
            for k in a:
                if a[k] != b[k]:
                    print(f"       {k}: {a[k]} -> {b[k]}")
        print()


if __name__ == "__main__":
    main()
