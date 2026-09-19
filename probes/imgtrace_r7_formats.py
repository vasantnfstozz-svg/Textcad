"""ROUND SEVEN — the pipeline AROUND the loops: what the decode and the two
knobs the browser never sends do with pictures nobody has traced yet.

Four rounds hunted the geometry of loops. This asks the other half:

  * a 16-bit PNG, a 1-bit PNG, a palette PNG, a CMYK-ish JPG;
  * an alpha channel that is REAL, and one that is uniform-but-not-opaque
    (`min(alpha) < 250` is the whole test for "real alpha");
  * a 1 pixel picture, a 1-pixel-wide picture, an empty file, a truncated
    file, a file that is not an image at all;
  * art that touches the border on one, two, three, four sides;
  * `min_channel_mm` and `connect_pieces`, the two knobs only the API and the
    MCP door can set: what do they do at the ends of their range.

Every answer is judged by ONE rule: a sentence the user can act on, or a
sketch that is the artwork. A traceback, a hang, or a silent rectangle where
the logo was, is a finding.

Run:  C:/Python314/python.exe probes/imgtrace_r7_formats.py
"""
from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402


def enc(img, ext=".png", params=None):
    ok, buf = cv2.imencode(ext, img, params or [])
    assert ok, ext
    return buf.tobytes()


def disc(w=400, h=300, r=90, val=255, bg=0, dtype=np.uint8):
    m = np.full((h, w), bg, dtype)
    cv2.circle(m, (w // 2, h // 2), r, int(val), -1)
    return m


def say(name, fn, *a, **k):
    t0 = time.time()
    try:
        ents, info = fn(*a, **k)
    except ValueError as exc:
        print(f"  {name:<34} REFUSED  ({time.time() - t0:.2f}s)  {exc}")
        return None
    except Exception as exc:                                # noqa: BLE001
        print(f"  {name:<34} !! {type(exc).__name__}: "
              f"{str(exc)[:110]}  ({time.time() - t0:.2f}s)")
        return "RAW"
    print(f"  {name:<34} ok  {info.get('contours')} pieces, "
          f"{info.get('holes')} holes, "
          f"{info['width_mm']} x {info['height_mm']} mm  "
          f"({time.time() - t0:.2f}s)")
    return ents, info


def sec_a():
    print("A. PIXEL FORMATS  (a 90 px disc in a 400x300 picture, 20 mm tall)")
    truth = "expect ~1 piece, roughly 13.3 x 13.3 mm"
    print(f"     {truth}")
    say("8-bit grey", imgtrace.image_to_entities, enc(disc()), 20.0)
    d16 = disc(dtype=np.uint16) * 257
    say("16-bit grey PNG", imgtrace.image_to_entities, enc(d16), 20.0)
    d16c = cv2.merge([d16, d16, d16])
    say("16-bit RGB PNG", imgtrace.image_to_entities, enc(d16c), 20.0)
    a16 = cv2.merge([d16, d16, d16, np.full(d16.shape, 65535, np.uint16)])
    say("16-bit RGBA PNG (opaque)", imgtrace.image_to_entities, enc(a16), 20.0)
    one = (disc() > 0).astype(np.uint8) * 255
    say("1-bit-style PNG (0/255)", imgtrace.image_to_entities, enc(one), 20.0)
    say("JPEG", imgtrace.image_to_entities, enc(cv2.merge([disc()] * 3),
                                                ".jpg"), 20.0)

def sec_b():
    print("\nB. THE ALPHA TEST  (`min(alpha) < 250` is the whole rule)")
    bgr = cv2.merge([disc()] * 3)
    real = cv2.merge([bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2],
                      (disc() > 0).astype(np.uint8) * 255])
    say("real alpha (disc cut out)", imgtrace.image_to_entities,
        enc(real), 20.0)
    for av in (249, 230, 200, 129):
        flat = cv2.merge([bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2],
                          np.full(disc().shape, av, np.uint8)])
        say(f"UNIFORM alpha {av} (no real alpha)",
            imgtrace.image_to_entities, enc(flat), 20.0)

def sec_c():
    print("\nC. BROKEN AND DEGENERATE INPUT")
    say("empty bytes", imgtrace.image_to_entities, b"", 20.0)
    say("not an image", imgtrace.image_to_entities, b"hello, world" * 40, 20.0)
    good = enc(disc())
    say("truncated PNG", imgtrace.image_to_entities, good[:len(good) // 2],
        20.0)
    say("1 x 1 pixel", imgtrace.image_to_entities,
        enc(np.full((1, 1), 255, np.uint8)), 20.0)
    say("1 px wide, 400 tall", imgtrace.image_to_entities,
        enc(np.full((400, 1), 255, np.uint8)), 20.0)
    say("all one colour", imgtrace.image_to_entities,
        enc(np.full((200, 200), 128, np.uint8)), 20.0)

def sec_d():
    print("\nD. ART THAT TOUCHES THE BORDER")
    for sides, box in (("1 side (left)", (0, 60, 200, 240)),
                       ("2 sides (L+T)", (0, 0, 200, 240)),
                       ("3 sides", (0, 0, 200, 300)),
                       ("4 sides (full bleed)", (0, 0, 400, 300))):
        m = np.zeros((300, 400), np.uint8)
        cv2.rectangle(m, (box[0], box[1]), (box[2] - 1, box[3] - 1), 255, -1)
        say(sides, imgtrace.image_to_entities, enc(m), 20.0)

def sec_e():
    print("\nE. THE TWO KNOBS THE BROWSER NEVER SENDS")
    m = np.zeros((300, 400), np.uint8)
    cv2.circle(m, (140, 150), 70, 255, -1)
    cv2.circle(m, (280, 150), 70, 255, -1)
    two = enc(m)
    say("connect_pieces off", imgtrace.image_to_entities, two, 20.0, 0.15,
        0.0, False)
    say("connect_pieces on", imgtrace.image_to_entities, two, 20.0, 0.15,
        0.0, True)
    for ch in (0.0, 0.5, 2.0, 8.0, 40.0, 500.0):
        say(f"min_channel_mm = {ch:g}", imgtrace.image_to_entities, two,
            20.0, 0.15, ch, False)
    say("min_channel_mm = -3 (negative)", imgtrace.image_to_entities, two,
        20.0, 0.15, -3.0, False)

def sec_f():
    print("\nF. min_channel_mm AGAINST A TALL PICTURE AT A SMALL HEIGHT")
    tall = np.zeros((2000, 1500), np.uint8)
    cv2.circle(tall, (750, 1000), 700, 255, -1)
    say("2000 px art, 2 mm tall, channel 6", imgtrace.image_to_entities,
        enc(tall), 2.0, 0.15, 6.0, False)


SECTIONS = {"A": sec_a, "B": sec_b, "C": sec_c, "D": sec_d, "E": sec_e,
            "F": sec_f}


if __name__ == "__main__":
    for key in (sys.argv[1:] or ["A", "B", "C", "D", "E", "F"]):
        SECTIONS[key]()
