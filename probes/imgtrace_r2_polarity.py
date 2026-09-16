"""REVIEW-QUEUE section 9, ROUND TWO — an INDEPENDENT corpus for the
foreground/background rule.

Round one replaced "the ink is the minority half" with "the background is
whichever side fills the picture's outer BORDER" and scored 9/10 against the
old rule's 7/10 on its own corpus. This builds a different corpus, from the
cases the round-two brief names, and scores both rules on it.

Ground truth is stated per picture as which SIDE of the Otsu split is the
artwork ("dark" or "bright"); the score is whether the rule picked that side.
Run:  C:\\Python314\\python.exe probes/imgtrace_r2_polarity.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _otsu(img):
    gray = (cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
            if img.ndim == 3 else img)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return m


def old_rule(img):
    """the pre-4c9ea32 rule: the artwork is the MINORITY of pixels"""
    m = _otsu(img)
    if int(m.sum()) > m.size // 2:
        m = 1 - m
    return m.astype(np.uint8)


def new_rule(img):
    """4c9ea32: the background is whichever side fills the outer border"""
    m = _otsu(img)
    ring = np.concatenate([np.asarray(m[0]).ravel(), np.asarray(m[-1]).ravel(),
                           np.asarray(m[:, 0]).ravel(),
                           np.asarray(m[:, -1]).ravel()])
    bright_edge = float(ring.mean()) if ring.size else 0.5
    if bright_edge > 0.6:
        m = 1 - m
    elif bright_edge >= 0.4:
        if int(m.sum()) > m.size // 2:
            m = 1 - m
    return m.astype(np.uint8)


def fixed_rule(img):
    """the round-two rule: the same, read past a THIN border shell"""
    import imgtrace
    return imgtrace._mask_from_image(img)


def side_of(img, mask):
    """'bright' if the rule kept the Otsu-bright pixels, else 'dark'"""
    m = _otsu(img)
    return "bright" if int((mask == m).sum()) == m.size else "dark"


# --------------------------------------------------------------------------
# the corpus: (name, image, truth-side, one-line description)
# --------------------------------------------------------------------------
W = 400


def _white(h=W, w=W):
    return np.full((h, w, 3), 255, np.uint8)


def _black(h=W, w=W):
    return np.zeros((h, w, 3), np.uint8)


def c_margin_disc():
    im = _white()
    cv2.circle(im, (200, 200), 110, (0, 0, 0), -1)
    return im, "dark", "ordinary art, generous white margin"


def c_margin_text():
    im = _white()
    for i in range(5):
        cv2.rectangle(im, (60 + i * 60, 160), (95 + i * 60, 240), (0, 0, 0), -1)
    return im, "dark", "a word of dark letters, generous white margin"


def c_bleed_one_side():
    """a logo that runs off ONE edge (a badge cropped flush at the left)"""
    im = _white()
    cv2.circle(im, (60, 200), 150, (0, 0, 0), -1)
    return im, "dark", "art bleeding off the left edge"


def c_bleed_two_sides():
    """a banner that runs off the left AND right edges"""
    im = _white()
    cv2.rectangle(im, (-5, 150), (405, 250), (0, 0, 0), -1)
    return im, "dark", "a band bleeding off two opposite edges"


def c_bleed_four_sides():
    """an X that touches all four edges, still a minority of pixels"""
    im = _white()
    cv2.line(im, (0, 0), (399, 399), (0, 0, 0), 40)
    cv2.line(im, (399, 0), (0, 399), (0, 0, 0), 40)
    return im, "dark", "an X touching all four edges"


def c_scan_dark_frame():
    """a scan with the platen's dark edge all round — the classic scan"""
    im = _white()
    for i in range(5):
        cv2.rectangle(im, (60 + i * 60, 160), (95 + i * 60, 240), (0, 0, 0), -1)
    cv2.rectangle(im, (0, 0), (399, 399), (0, 0, 0), 12)
    return im, "dark", "dark art on paper, dark scan edge all round"


def c_printed_border():
    """a printed rule box round the art, as an exported logo sheet has"""
    im = _white()
    cv2.circle(im, (200, 200), 110, (0, 0, 0), -1)
    cv2.rectangle(im, (2, 2), (397, 397), (0, 0, 0), 5)
    return im, "dark", "dark art inside a thin printed border"


def c_vignette():
    """dark art on paper, photographed with a strong lens vignette"""
    im = _white()
    cv2.circle(im, (200, 200), 100, (0, 0, 0), -1)
    yy, xx = np.mgrid[0:W, 0:W].astype(float)
    r = np.hypot(yy - 199.5, xx - 199.5) / 199.5
    fall = np.clip(1.0 - 1.15 * np.clip(r - 0.45, 0, None) ** 1.4, 0, 1)
    im = (im.astype(float) * fall[:, :, None]).astype(np.uint8)
    return im, "dark", "dark art on paper with a heavy photo vignette"


def c_inverse_video_small():
    im = _black()
    cv2.circle(im, (200, 200), 110, (255, 255, 255), -1)
    return im, "bright", "inverse video (white art on black), art a minority"


def c_inverse_video_big():
    im = _black()
    cv2.circle(im, (200, 200), 190, (255, 255, 255), -1)
    return im, "bright", "inverse video, art the MAJORITY of the picture"


def c_tight_crop_disc():
    im = _white()
    cv2.circle(im, (200, 200), 199, (0, 0, 0), -1)
    return im, "dark", "a disc cropped to its own ink (78% ink)"


def c_tight_crop_letter():
    """an 'O' trimmed to its ink: touches all four edges, hollow middle"""
    im = _white()
    cv2.ellipse(im, (200, 200), (199, 199), 0, 0, 360, (0, 0, 0), 60)
    return im, "dark", "a ring trimmed to its ink (frame-shaped, no margin)"


def c_tight_crop_word():
    """a word trimmed to its ink — the esp32-remote / cam-cover recipe"""
    im = _white()
    for i in range(5):
        cv2.rectangle(im, (i * 80, 0), (60 + i * 80, 399), (0, 0, 0), -1)
    cv2.rectangle(im, (0, 170), (399, 230), (0, 0, 0), -1)
    return im, "dark", "a word trimmed to its ink, bars touching every edge"


def c_all_one_colour():
    return np.full((W, W, 3), 128, np.uint8), None, "a picture of one colour"


def c_border_exactly_split():
    """left half of the picture solid ink, right half paper: the border ring
    is half dark and half light and the areas are equal"""
    im = _white()
    cv2.rectangle(im, (0, 0), (199, 399), (0, 0, 0), -1)
    return im, "dark", "half ink / half paper: the border is split"


def c_photo_shadow_one_edge():
    """a phone photo of a sheet: a shadow darkens one edge only"""
    im = _white()
    cv2.circle(im, (200, 200), 100, (0, 0, 0), -1)
    im[:, :70] = (40, 40, 40)
    return im, "dark", "dark art on paper with a shadow down one edge"


CASES = [c_margin_disc, c_margin_text, c_bleed_one_side, c_bleed_two_sides,
         c_bleed_four_sides, c_scan_dark_frame, c_printed_border, c_vignette,
         c_inverse_video_small, c_inverse_video_big, c_tight_crop_disc,
         c_tight_crop_letter, c_tight_crop_word, c_all_one_colour,
         c_border_exactly_split, c_photo_shadow_one_edge]


def main():
    old_ok = new_ok = fix_ok = judged = 0
    print(f"{'case':26s} {'truth':7s} {'old':7s} {'r1':7s} {'r2':7s}  verdict")
    print("-" * 86)
    for fn in CASES:
        im, truth, desc = fn()
        o = side_of(im, old_rule(im))
        n = side_of(im, new_rule(im))
        x = side_of(im, fixed_rule(im))
        if truth is None:
            print(f"{fn.__name__[2:]:26s} {'-':7s} {o:7s} {n:7s} {x:7s}  "
                  f"(no answer) {desc}")
            continue
        judged += 1
        old_ok += o == truth
        new_ok += n == truth
        fix_ok += x == truth
        tag = []
        if o == truth and n != truth:
            tag.append("r1 LOST")
        if n == truth and o != truth:
            tag.append("r1 won")
        if x == truth and n != truth:
            tag.append("r2 RESTORES")
        if n == truth and x != truth:
            tag.append("r2 BROKE")
        print(f"{fn.__name__[2:]:26s} {truth:7s} {o:7s} {n:7s} {x:7s}  "
              f"{' '.join(tag):12s} {desc}")
    print("-" * 86)
    print(f"judged {judged}:  old rule {old_ok}, round one {new_ok}, "
          f"round two {fix_ok}")


if __name__ == "__main__":
    main()
