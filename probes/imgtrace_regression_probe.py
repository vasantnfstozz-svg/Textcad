"""probes/imgtrace_regression_probe.py - REVIEW-QUEUE section 9 fix pass.

The three traced designs (rocky-keychain, rocky-balboa, spiderman-logo) and
the three generator scripts that call imgtrace directly (designs/esp32-
remote.py, designs/cam-cover-plaque.py, designs/autonomiq-panel-profile.py)
all feed it the SAME kind of picture: dark art on a light ground, cropped to
its own ink. This reproduces that recipe - including esp32-remote's exact one
(Impact 400pt "autonomIQ", cropped, rotated 90) - and checks the fix pass
changed NOTHING about what comes out.

Run it once on the parent commit and once here; the printed lines must match.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import imgtrace  # noqa: E402
import sketch as sk  # noqa: E402

if "--old" in sys.argv:          # the version committed at HEAD, for a diff
    import importlib.util
    import subprocess
    import tempfile
    src = subprocess.run([r"C:\Program Files\Git\cmd\git.exe", "-C", ROOT,
                          "show", "HEAD:imgtrace.py"],
                         capture_output=True, text=True, check=True).stdout
    tmp = os.path.join(tempfile.mkdtemp(), "imgtrace_old.py")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(src)
    spec = importlib.util.spec_from_file_location("imgtrace_old", tmp)
    imgtrace = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imgtrace)
    print("(using imgtrace.py as committed at HEAD)")


def png_of(pil):
    import io
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


def rasters():
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    out = []

    def pick(*names):
        for n in names:
            p = os.path.join(r"C:\Windows\Fonts", n)
            if os.path.exists(p):
                return p
        return None

    # the fonts the generator scripts really name
    impact = pick("impact.ttf", "arialbd.ttf", "arial.ttf")
    bahn = pick("bahnschrift.ttf", "arial.ttf", "impact.ttf")
    if impact is None or bahn is None:
        print("no TrueType font found - skipping the text rasters")
        return out

    # designs/esp32-remote.py _logo_raster(), verbatim
    font = ImageFont.truetype(impact, 400)
    im = Image.new("L", (7000, 900), 255)
    dd = ImageDraw.Draw(im)
    x = 100
    for ch in "autonomIQ":
        dd.text((x, 150), ch, font=font, fill=0)
        x += dd.textlength(ch, font=font)
    im = im.crop(ImageOps.invert(im).getbbox())
    out.append(("esp32-remote logo (rotated 90)",
                png_of(im.rotate(90, expand=True, fillcolor=255)), 57.0, 0.08))

    # designs/autonomiq-panel-profile.py letters (bahnschrift 220)
    panel = ImageFont.truetype(bahn, 220)
    im = Image.new("L", (4000, 900), 255)
    dd = ImageDraw.Draw(im)
    x = 60
    for ch in "autonom":
        dd.text((x, 120), ch, font=panel, fill=0)
        x += dd.textlength(ch, font=panel) + 55
    im = im.crop(ImageOps.invert(im).getbbox())
    out.append(("autonomiq-panel letters", png_of(im), 16.0, 0.12))

    # designs/cam-cover-plaque.py caption block (bahnschrift 200)
    small = ImageFont.truetype(bahn, 200)
    im = Image.new("L", (2400, 900), 255)
    dd = ImageDraw.Draw(im)
    for i, s in enumerate(["PORSCHE", "FLAT SIX", "CAM COVER"]):
        dd.text((60, 60 + i * 260), s, font=small, fill=0)
    im = im.crop(ImageOps.invert(im).getbbox())
    out.append(("cam-cover caption", png_of(im), 12.0, 0.10))
    return out


def shapes():
    out = []
    d = np.zeros((400, 400, 4), np.uint8)
    cv2.circle(d, (200, 200), 150, (10, 10, 10, 255), -1)
    cv2.circle(d, (200, 200), 60, (0, 0, 0, 0), -1)
    ok, b = cv2.imencode(".png", d)
    out.append(("alpha donut", b.tobytes(), 50.0, 0.15))

    s = np.zeros((800, 800, 4), np.uint8)
    sp = []
    for i in range(10):
        r = 350 if i % 2 == 0 else 140
        a = i * np.pi / 5
        sp.append([400 + r * np.cos(a), 400 + r * np.sin(a)])
    cv2.fillPoly(s, [np.array(sp, np.int32)], (0, 0, 0, 255))
    ok, b = cv2.imencode(".png", s)
    out.append(("alpha star", b.tobytes(), 25.0, 0.15))

    k = np.full((600, 900, 3), 255, np.uint8)
    cv2.ellipse(k, (450, 300), (350, 200), 0, 0, 360, (0, 0, 0), -1)
    cv2.circle(k, (330, 250), 60, (255, 255, 255), -1)
    cv2.circle(k, (570, 250), 60, (255, 255, 255), -1)
    ok, b = cv2.imencode(".png", k)
    out.append(("keychain-style blob on white", b.tobytes(), 40.0, 0.15))
    return out


def main():
    for name, data, h, tol in rasters() + shapes():
        ents, info = imgtrace.image_to_entities(data, height_mm=h, tol_mm=tol)
        face = sk.make_sketch("XY", 0, ents)
        digest = hashlib.sha1(
            json.dumps(ents, sort_keys=True).encode()).hexdigest()[:12]
        print(f"{name:34s} {info['contours']:3d}c {info['holes']:3d}h "
              f"{info['points']:5d}pts  {info['width_mm']:8.2f} x "
              f"{info['height_mm']:7.2f}  area {face.area:10.3f}  {digest}")


if __name__ == "__main__":
    main()
