r"""probes/trim_profile.py — where Trim's time actually goes.

LAUNCH-PLAN section 10 P2: "Trim is slow on a big sketch". Recorded
2026-09-11: hovering `rocky-balboa/field_sketch` (23 entities) cost 6.1 s in
`trim_pieces`, a click 15.4 s; `esp32-remote/sketch28` (45 entities) 3.0 s to
hover.

This probe reproduces those numbers on the user's own designs (READ ONLY) and
breaks the cost down by PHASE, with COUNTS as well as seconds — the box runs
several OpenCASCADE agents at once and the wall clock swings, but the counts
do not.

    C:\Python314\python.exe probes/trim_profile.py                  # both
    C:\Python314\python.exe probes/trim_profile.py rocky-balboa field_sketch

Phases counted:
  outline   — _outline(): one wire.position_at() KERNEL call per sample point
  pairs     — the O(n^2) loop: boxes tested, boxes that overlap, segment
              pairs actually multiplied out by _poly_intersections
  slice     — cutting each outline into pieces
  compose   — sketch.compose / compose_order (the click path only)
"""
from __future__ import annotations
import cProfile
import json
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                            # noqa: E402
import sketch as sk                                           # noqa: E402
import sketch_trim as tr                                      # noqa: E402

C: dict = {}


def reset():
    C.clear()
    C.update(outline_calls=0, sample_pts=0, outline_s=0.0,
             box_tests=0, seg_pairs=0, isect_calls=0,
             isect_s=0.0, slice_calls=0, slice_s=0.0,
             compose_calls=0, compose_s=0.0, order_calls=0, order_s=0.0,
             entity_calls=0, entity_s=0.0)


def instrument():
    """Wrap the hot functions with counters. Behaviour unchanged."""
    _outline, _poly, _slice = tr._outline, tr._poly_intersections, tr._slice_pts
    _compose, _order, _ent = sk.compose, sk.compose_order, sk._entity
    _pieces_raw = tr._pieces_raw

    def outline(e, idx):
        t = time.perf_counter()
        o = _outline(e, idx)
        C["outline_s"] += time.perf_counter() - t
        C["outline_calls"] += 1
        C["sample_pts"] += len(o["pts"])
        return o

    def poly(a, b):
        t = time.perf_counter()
        C["isect_calls"] += 1
        C["seg_pairs"] += len(a["pts"]) * len(b["pts"])
        r = _poly(a, b)
        C["isect_s"] += time.perf_counter() - t
        return r

    def slice_pts(o, p0, p1):
        t = time.perf_counter()
        r = _slice(o, p0, p1)
        C["slice_s"] += time.perf_counter() - t
        C["slice_calls"] += 1
        return r

    def compose(entities, note=True):
        t = time.perf_counter()
        r = _compose(entities, note=note)
        C["compose_s"] += time.perf_counter() - t
        C["compose_calls"] += 1
        return r

    def order(entities):
        t = time.perf_counter()
        r = _order(entities)
        C["order_s"] += time.perf_counter() - t
        C["order_calls"] += 1
        return r

    def entity(e):
        t = time.perf_counter()
        r = _ent(e)
        C["entity_s"] += time.perf_counter() - t
        C["entity_calls"] += 1
        return r

    def pieces_raw(entities):
        n = len(entities)
        C["box_tests"] += n * (n - 1) // 2
        return _pieces_raw(entities)

    tr._outline = outline
    tr._poly_intersections = poly
    tr._slice_pts = slice_pts
    tr._pieces_raw = pieces_raw
    sk.compose = compose
    sk.compose_order = order
    sk._entity = entity


def load(design: str, sketch_id: str) -> list:
    d = json.loads((ROOT / "designs" / f"{design}.tcad.json")
                   .read_text(encoding="utf-8"))
    f = next(f for f in d["features"] if f.get("id") == sketch_id)
    return f["params"]["entities"]


def report(tag: str, secs: float):
    print(f"  {tag}: {secs * 1000:8.0f} ms wall")
    print(f"     outline  {C['outline_s'] * 1000:7.0f} ms  "
          f"{C['outline_calls']:3d} wires, {C['sample_pts']:6d} kernel "
          f"position_at() calls")
    print(f"     pairs    {C['isect_s'] * 1000:7.0f} ms  "
          f"{C['box_tests']:4d} box tests -> {C['isect_calls']:4d} "
          f"intersected, {C['seg_pairs']:>12,d} segment pairs")
    print(f"     slice    {C['slice_s'] * 1000:7.0f} ms  "
          f"{C['slice_calls']:4d} pieces cut")
    print(f"     compose  {C['compose_s'] * 1000:7.0f} ms  "
          f"{C['compose_calls']:3d} compose + {C['order_calls']} order "
          f"({C['order_s'] * 1000:.0f} ms)")
    print(f"     _entity  {C['entity_s'] * 1000:7.0f} ms  "
          f"{C['entity_calls']:3d} builds (inside the above)")


def midmost_piece(pieces):
    """A stable, real piece to click: the first non-whole piece there is."""
    return next((p for p in pieces if not p["whole"]), pieces[0])


def run(design: str, sketch_id: str, do_profile: bool = True):
    ents = load(design, sketch_id)
    print(f"\n=== {design}/{sketch_id} — {len(ents)} entities ===")

    reset()
    t = time.perf_counter()
    pieces = tr.trim_pieces(ents)
    hover = time.perf_counter() - t
    report("HOVER trim_pieces", hover)
    print(f"     -> {len(pieces)} pieces")

    pid = midmost_piece(pieces)["id"]
    reset()
    t = time.perf_counter()
    try:
        res = tr.trim_apply(ents, pid)
        msg = res["message"]
    except Exception as ex:                                   # noqa: BLE001
        msg = f"(refused: {ex})"
    click = time.perf_counter() - t
    report(f"CLICK trim_apply({pid})", click)
    print(f"     -> {msg}")

    if do_profile:
        for what, fn in (("trim_pieces", lambda: tr.trim_pieces(ents)),
                         (f"trim_apply({pid})",
                          lambda: tr.trim_apply(ents, pid))):
            pr = cProfile.Profile()
            pr.enable()
            try:
                fn()
            except Exception:                                 # noqa: BLE001
                pass
            pr.disable()
            print(f"     --- cProfile of {what}, top 16 by TOTAL time ---")
            st = pstats.Stats(pr, stream=sys.stdout)
            st.sort_stats("tottime")
            st.print_stats(16)
    return hover, click


if __name__ == "__main__":
    instrument()
    np.seterr(all="ignore")
    if len(sys.argv) >= 3:
        run(sys.argv[1], sys.argv[2])
    else:
        run("rocky-balboa", "field_sketch", do_profile=True)
        run("esp32-remote", "sketch28", do_profile=False)
