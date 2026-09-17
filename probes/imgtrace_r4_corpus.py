"""REVIEW-QUEUE section 9, ROUND FOUR - a FOURTH independent corpus for the
foreground/background rule, scored against all four rules, plus the union of
all four corpora.

Every round so far has graded its own new rule on its own pictures and every
round so far has been wrong about it: round one claimed 9 vs 7, round two
measured round one a NET REGRESSION, round three measured round two a TIE with
the ORIGINAL. So this round picks its pictures where the SHIPPED rule turns,
not where round three's did:

  * the dark-shell door, attacked from INVERSE VIDEO - the one polarity where
    reading past a thin dark shell is the wrong move (a tight-cropped white
    ring's dark ground is thin only in the corners);
  * the 64 px floor, on pictures big enough that 64 px and 1% are far apart
    in BOTH directions (art the floor now lets through, and art it now reads
    past when round two's 1% would have stopped);
  * shells that are neither clearly dark nor clearly light - mid-grey, a
    gradient, a checker, dark on two sides, on three, on one;
  * the light-pad fix pushed to its own edges: a 2 px pad, no pad at all,
    and a dark platen edge AND a light pad in the same picture.

    old  = pre-4c9ea32  ("the artwork is the MINORITY of pixels")
    r1   = 4c9ea32      ("the ground is whichever side fills the 1 px border")
    r2   = 4b3af6a      ("... read past a THIN shell of EITHER side")
    r3   = f5d9a17      ("... read past a thin shell of INK only; floor 64 px")

Ground truth per picture is which SIDE of the Otsu split is the artwork.

Run:  C:\\Python314\\python.exe probes/imgtrace_r4_corpus.py
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                               # noqa: E402  the SHIPPED rule
import _imgtrace_old as OLD                   # noqa: E402  verified == git
import _imgtrace_r1 as R1                     # noqa: E402  verified == git
import _imgtrace_r2 as R2                     # noqa: E402  verified == git


def _otsu(img):
    gray = (cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
            if img.ndim == 3 else img)
    _, m = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return m


def side_of(img, mask):
    """'bright' if the rule kept the Otsu-bright pixels, else 'dark'"""
    m = _otsu(img)
    return "bright" if int((mask == m).sum()) == m.size else "dark"


RULES = [("old", OLD._mask_from_image),
         ("r1", R1._mask_from_image),
         ("r2", R2._mask_from_image),
         ("r3", imgtrace._mask_from_image)]


# --------------------------------------------------------------------------
# helpers - EXACT bands, so "8 px frame" means eight rows
# --------------------------------------------------------------------------
def _white(h, w):
    return np.full((h, w, 3), 255, np.uint8)


def _black(h, w):
    return np.zeros((h, w, 3), np.uint8)


def _band(im, t, colour):
    im[:t] = colour
    im[-t:] = colour
    im[:, :t] = colour
    im[:, -t:] = colour
    return im


def _keyline(im, inset, colour):
    """a ONE-pixel rectangle outline at `inset` from every edge"""
    im[inset, inset:-inset] = colour
    im[-inset - 1, inset:-inset] = colour
    im[inset:-inset, inset] = colour
    im[inset:-inset, -inset - 1] = colour
    return im


BK, WH = (0, 0, 0), (255, 255, 255)


# ======================  A - the dark shell, from inverse video  ===========
def a1_inverse_ring_tight():
    """A white ANNULUS cropped to its own ink: the dark ground survives only
    in the four corners, so it is THIN by the distance transform, and the
    counter is a second dark region. Reading past that ground returns the
    NEGATIVE of the ring."""
    im = _black(400, 400)
    cv2.circle(im, (200, 200), 199, WH, -1)
    cv2.circle(im, (200, 200), 160, BK, -1)
    return im, "bright", "white ring cropped to ink; dark ground only in corners"


def a2_inverse_o_thin_black_pad():
    """inverse-video lettering with a 10 px black pad - the pad and the
    ground are ONE region, which is the case that must stay safe"""
    im = _black(600, 600)
    cv2.circle(im, (300, 300), 280, WH, -1)
    cv2.circle(im, (300, 300), 210, BK, -1)
    return im, "bright", "white O on black, 10 px pad; ground is one fat region"


def a3_inverse_keyline_1px_big():
    """a 2000 px inverse-video card: an 8 px black export band, a ONE-pixel
    white keyline, then the black card with a small white mark. The white
    inside is over 64 px and under 1% of the picture - exactly the window
    round three's floor change opened."""
    im = _black(2000, 2000)
    _keyline(im, 8, WH)
    cv2.rectangle(im, (980, 980), (1020, 1020), WH, -1)
    return im, "bright", "2000px black card, 1px white keyline, 40x40 mark"


def a4_inverse_keyline_1px_small():
    """the same picture at 400 px, where the white inside CLEARS 1% too"""
    im = _black(400, 400)
    _keyline(im, 4, WH)
    cv2.rectangle(im, (170, 170), (230, 230), WH, -1)
    return im, "bright", "400px black card, 1px white keyline, 60x60 mark"


def a5_inverse_video_white_margin():
    """inverse-video art exported with a thin WHITE margin - the light shell
    round three now refuses to read past"""
    im = _white(500, 500)
    im[10:-10, 10:-10] = 0
    cv2.circle(im, (250, 250), 170, WH, -1)
    cv2.circle(im, (250, 250), 90, BK, -1)
    return im, "bright", "white ring on a black card with a 10 px white margin"


def a6_inverse_art_touches_all_edges():
    """white art running off all four edges with a dark middle: the dark
    ground exists ONLY where the art does not reach"""
    im = _black(500, 500)
    im[:, 150:350] = WH
    im[150:350, :] = WH
    return im, "bright", "white cross to all four edges; dark ground in corners"


# ======================  B - the light-pad fix at its own edges  ===========
def b1_plate_holes_pad_2px():
    """the round-three P0 picture at its thinnest pad: a part silhouette
    with bolt holes and a TWO-pixel light pad"""
    im = _white(1200, 1200)
    cv2.rectangle(im, (2, 2), (1197, 1197), BK, -1)
    for r in range(3):
        for c in range(3):
            cv2.circle(im, (250 + c * 350, 250 + r * 350), 90, WH, -1)
    return im, "dark", "1200px dark plate, 9 bolt holes, 2 px light pad"


def b2_plate_holes_no_pad():
    """the same plate with NO pad: the ink runs off all four edges"""
    im = _white(1200, 1200)
    cv2.rectangle(im, (0, 0), (1199, 1199), BK, -1)
    for r in range(3):
        for c in range(3):
            cv2.circle(im, (250 + c * 350, 250 + r * 350), 90, WH, -1)
    return im, "dark", "1200px dark plate, 9 bolt holes, no pad at all"


def b3_scan_edge_and_paper_pad():
    """the canonical scan: an 8 px dark platen edge, 40 px of white paper,
    then dark art. The fix must not break this one."""
    im = _white(800, 800)
    _band(im, 8, BK)
    cv2.circle(im, (400, 400), 260, BK, -1)
    cv2.circle(im, (400, 400), 120, WH, -1)
    return im, "dark", "8 px platen edge + 40 px paper + a dark ring"


def b4_scan_edge_paper_pad_ink_majority():
    """the same, but the ink is the MAJORITY inside the paper - which is
    what a tight-cropped logo looks like once a scan edge is added"""
    im = _white(800, 800)
    _band(im, 8, BK)
    cv2.rectangle(im, (60, 60), (739, 739), BK, -1)
    cv2.rectangle(im, (200, 200), (600, 600), WH, -1)
    return im, "dark", "platen edge + paper + an ink-majority dark plate"


# ======================  C - shells that are neither dark nor light  =======
def c1_gradient_border():
    """a 30 px border fading from black at the edge to white inside"""
    im = _white(600, 600)
    for t in range(30):
        v = int(255 * t / 29.0)
        im[t, t:600 - t] = v
        im[599 - t, t:600 - t] = v
        im[t:600 - t, t] = v
        im[t:600 - t, 599 - t] = v
    cv2.circle(im, (300, 300), 180, BK, -1)
    return im, "dark", "dark-to-light gradient border, dark disc inside"


def c2_midgrey_shell():
    """a 20 px MID-GREY band: Otsu has to put it on one side or the other"""
    im = _white(600, 600)
    _band(im, 20, (128, 128, 128))
    cv2.circle(im, (300, 300), 180, BK, -1)
    return im, "dark", "20 px mid-grey band, dark disc inside"


def c3_checker_border():
    """a border of alternating 25 px dark and light blocks"""
    im = _white(600, 600)
    for i in range(0, 600, 50):
        im[:12, i:i + 25] = BK
        im[-12:, i:i + 25] = BK
        im[i:i + 25, :12] = BK
        im[i:i + 25, -12:] = BK
    cv2.circle(im, (300, 300), 180, BK, -1)
    return im, "dark", "dashed dark border, dark disc inside"


def c4_dark_two_sides():
    """a dark rule down the left and right only - the border reads ~half"""
    im = _white(600, 600)
    im[:, :12] = BK
    im[:, -12:] = BK
    cv2.circle(im, (300, 300), 180, BK, -1)
    return im, "dark", "dark rules left+right, dark disc inside"


def c5_dark_three_sides():
    """a scan edge on three sides (the document sat against one corner)"""
    im = _white(600, 600)
    im[:12] = BK
    im[:, :12] = BK
    im[:, -12:] = BK
    cv2.circle(im, (300, 300), 180, BK, -1)
    return im, "dark", "dark edge on three sides, dark disc inside"


def c6_dark_one_side():
    """a dark edge on ONE side only"""
    im = _white(600, 600)
    im[:12] = BK
    cv2.circle(im, (300, 300), 180, BK, -1)
    return im, "dark", "dark edge on one side, dark disc inside"


def c7_dark_shell_ink_majority_three_sides():
    """the dangerous combination: a partial scan edge AND ink-majority art,
    which is what a cropped logo dropped onto a scan looks like"""
    im = _white(600, 600)
    im[:12] = BK
    im[:, :12] = BK
    cv2.rectangle(im, (40, 40), (559, 559), BK, -1)
    cv2.rectangle(im, (150, 150), (450, 450), WH, -1)
    return im, "dark", "dark edge on two sides + ink-majority plate"


# ======================  D - the 64 px floor on big sheets  ================
def d1_sheet4000_small_logo():
    """a 4000 px sheet with a 20 px platen edge and a logo at 0.06% of it -
    far under round two's 1% floor, over round three's 64 px"""
    im = _white(4000, 4000)
    _band(im, 20, BK)
    cv2.rectangle(im, (1900, 1900), (2100, 2100), BK, -1)
    return im, "dark", "4000px sheet, 20 px edge, 200x200 dark logo"


def d2_sheet4000_art_just_over_floor():
    """the same sheet with art of 100 px - just over the 64 px floor"""
    im = _white(4000, 4000)
    _band(im, 20, BK)
    cv2.rectangle(im, (1995, 1995), (2005, 2005), BK, -1)
    return im, "dark", "4000px sheet, 20 px edge, 10x10 dark mark (100 px)"


def d3_sheet4000_tight_crop():
    """a 4000 px tight crop with no edge at all, ink the majority"""
    im = _white(4000, 4000)
    cv2.circle(im, (2000, 2000), 1999, BK, -1)
    cv2.circle(im, (2000, 2000), 700, WH, -1)
    return im, "dark", "4000px dark ring cropped to ink, no border shell"


def d4_sheet1200_art_between_64_and_1pct():
    """1200 px sheet, 10 px platen edge, art of 900 px: over 64, under the
    14 400 px that round two's 1% floor demanded"""
    im = _white(1200, 1200)
    _band(im, 10, BK)
    cv2.rectangle(im, (585, 585), (615, 615), BK, -1)
    return im, "dark", "1200px sheet, 10 px edge, 30x30 dark mark (900 px)"


def d5_sheet4000_shell_20px_is_under_5pct():
    """a 4000 px sheet where a FAT 150 px dark edge is still under the 5%
    (200 px) threshold - a frame this heavy is a mount board, not an edge"""
    im = _white(4000, 4000)
    _band(im, 150, BK)
    cv2.circle(im, (2000, 2000), 1500, BK, -1)
    return im, "dark", "4000px sheet, 150 px dark mount, dark disc inside"


# ======================  E - the baselines that must never move  ==========
def e1_plain_dark_art_margin():
    im = _white(600, 600)
    cv2.circle(im, (300, 300), 180, BK, -1)
    cv2.circle(im, (300, 300), 70, WH, -1)
    return im, "dark", "ordinary dark ring, generous white margin"


def e2_dark_disc_tight_crop():
    im = _white(400, 400)
    cv2.circle(im, (200, 200), 199, BK, -1)
    return im, "dark", "a dark disc cropped to its own bbox (round one's P0)"


def e3_inverse_video_generous():
    im = _black(600, 600)
    cv2.circle(im, (300, 300), 180, WH, -1)
    cv2.circle(im, (300, 300), 70, BK, -1)
    return im, "bright", "white ring on black, generous margin"


def e4_hairline_1px_frame():
    im = _white(600, 600)
    _band(im, 1, BK)
    cv2.circle(im, (300, 300), 180, BK, -1)
    cv2.circle(im, (300, 300), 70, WH, -1)
    return im, "dark", "the 1 px frame an exporter leaves, dark ring inside"


def e5_tall_banner_4px_edge():
    """1600 x 120: min(shape) is 120, so 5% is 6 px"""
    im = _white(120, 1600)
    _band(im, 4, BK)
    for i in range(6):
        cv2.rectangle(im, (200 + i * 200, 30), (200 + i * 200 + 90, 90),
                      BK, -1)
    return im, "dark", "1600x120 banner, 4 px dark edge, dark blocks"


def e6_letter_o_light_pad():
    """the most ordinary padded art there is: one letter with a counter"""
    im = _white(500, 500)
    cv2.circle(im, (250, 250), 244, BK, -1)
    cv2.circle(im, (250, 250), 150, WH, -1)
    return im, "dark", "a dark O with a 6 px light pad"


CASES = [a1_inverse_ring_tight, a2_inverse_o_thin_black_pad,
         a3_inverse_keyline_1px_big, a4_inverse_keyline_1px_small,
         a5_inverse_video_white_margin, a6_inverse_art_touches_all_edges,
         b1_plate_holes_pad_2px, b2_plate_holes_no_pad,
         b3_scan_edge_and_paper_pad, b4_scan_edge_paper_pad_ink_majority,
         c1_gradient_border, c2_midgrey_shell, c3_checker_border,
         c4_dark_two_sides, c5_dark_three_sides, c6_dark_one_side,
         c7_dark_shell_ink_majority_three_sides,
         d1_sheet4000_small_logo, d2_sheet4000_art_just_over_floor,
         d3_sheet4000_tight_crop, d4_sheet1200_art_between_64_and_1pct,
         d5_sheet4000_shell_20px_is_under_5pct,
         e1_plain_dark_art_margin, e2_dark_disc_tight_crop,
         e3_inverse_video_generous, e4_hairline_1px_frame,
         e5_tall_banner_4px_edge, e6_letter_o_light_pad]


def score(cases, title):
    got_all = {n: 0 for n, _ in RULES}
    judged = 0
    print(f"\n=== {title} ===")
    print(f"{'case':38s} {'truth':7s} "
          + " ".join(f"{n:7s}" for n, _ in RULES) + "  note")
    print("-" * 112)
    for name, im, truth, desc in cases:
        if truth is None:
            continue
        got = []
        for _n, rule in RULES:
            try:
                got.append(side_of(im, rule(im)))
            except Exception as exc:                        # noqa: BLE001
                got.append(f"ERR:{type(exc).__name__}"[:7])
        judged += 1
        for (n, _), g in zip(RULES, got):
            got_all[n] += g == truth
        flags = []
        if got[0] == truth and got[3] != truth:
            flags.append("r3<old")
        if got[2] == truth and got[3] != truth:
            flags.append("r3<r2")
        if got[3] == truth and got[0] != truth:
            flags.append("r3>old")
        print(f"{name:38s} {truth:7s} "
              + " ".join(f"{g:7s}" for g in got)
              + f"  {';'.join(flags):16s} {desc}")
    print("-" * 112)
    print(f"judged {judged}:  "
          + ",  ".join(f"{n} {got_all[n]}" for n, _ in RULES))
    return judged, got_all


def r4_cases():
    for fn in CASES:
        im, truth, desc = fn()
        yield fn.__name__, im, truth, desc


def main():
    import imgtrace_r3_corpus as C3
    total = {n: 0 for n, _ in RULES}
    grand = 0
    for cases, title in ((C3.r1_cases(), "round ONE's corpus"),
                         (C3.r2_cases(), "round TWO's corpus"),
                         (C3.r3_cases(), "round THREE's corpus"),
                         (r4_cases(), "round FOUR's corpus (this one)")):
        j, s = score(cases, title)
        grand += j
        for n in total:
            total[n] += s[n]
    print("\n" + "=" * 112)
    print(f"ALL FOUR CORPORA, {grand} judged pictures:  "
          + ",  ".join(f"{n} {total[n]}" for n, _ in RULES))


if __name__ == "__main__":
    main()
