"""How much did the Trim fix cost the user per click, and where does it go?

Measures trim_apply on the library's biggest sketches with the new work
switched off one piece at a time.
"""
import json, glob, os, time
import sketch as S
import sketch_trim as T

SKETCHES = []
for path in sorted(glob.glob("designs/*.tcad.json")):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for f in data.get("features", []):
        ents = (f.get("params") or {}).get("entities")
        if ents and len(ents) >= 10:
            SKETCHES.append((os.path.basename(path)[:-len(".tcad.json")],
                             f.get("id"), ents))
SKETCHES.sort(key=lambda s: -len(s[2]))
SKETCHES = SKETCHES[:4]

real_guard = T._refuse_if_the_trim_broke_it
real_cluster_order = S.compose_order


def timed(fn):
    t0 = time.perf_counter()
    try:
        fn()
        err = None
    except Exception as ex:
        err = f"{type(ex).__name__}: {str(ex)[:60]}"
    return time.perf_counter() - t0, err


print(f"{'sketch':34s} {'n':>3s} {'pieces':>8s} {'apply':>8s} "
      f"{'-guard':>8s} {'-order':>8s} {'-both':>8s}")
for name, fid, ents in SKETCHES:
    t_pieces, _ = timed(lambda: T.trim_pieces(ents))
    pieces = T.trim_pieces(ents)
    pid = next((p for p in pieces if not p["whole"]), pieces[0])["id"]

    t_full, err = timed(lambda: T.trim_apply(ents, pid))

    T._refuse_if_the_trim_broke_it = lambda *a, **k: None
    t_noguard, _ = timed(lambda: T.trim_apply(ents, pid))
    T._refuse_if_the_trim_broke_it = real_guard

    S.compose_order = lambda es: list(range(len(es)))
    t_noorder, _ = timed(lambda: T.trim_apply(ents, pid))

    T._refuse_if_the_trim_broke_it = lambda *a, **k: None
    t_neither, _ = timed(lambda: T.trim_apply(ents, pid))
    T._refuse_if_the_trim_broke_it = real_guard
    S.compose_order = real_cluster_order

    print(f"{name + '/' + str(fid):34s} {len(ents):3d} {t_pieces:7.2f}s "
          f"{t_full:7.2f}s {t_noguard:7.2f}s {t_noorder:7.2f}s "
          f"{t_neither:7.2f}s  {err or ''}")
