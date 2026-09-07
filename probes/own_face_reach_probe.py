"""Probe: the own-face escape in viewport.edgeHitAt — what does it MEASURE?

`ownFaceHit` lets an edge be picked even though one of its own two faces is
nearer than it: an inside corner's line sits a hair behind those faces from
every angle, so without the escape no concave edge could ever be filleted
(2026-09-07). The escape needs a bound, or a cylinder's hidden BACK seam —
whose two faces include the one in front of it — becomes pickable through the
part.

The bound shipped as `eHit.point.distanceTo(fHit.point) <= 4 * reach`, a WORLD
distance against a threshold derived from a PIXEL width at the face hit's depth
(`reach = worldPerPixel(depth) * 5`). The code review of 2026-09-07 called that
a unit mix-up and proposed comparing in pixels instead. Neither claim is worth
anything unargued: this probe prints the numbers the rule could be decided on,
for the two cases it has to separate, at three zooms and at a grazing angle.

    C:\\Python314\\python.exe probes/own_face_reach_probe.py

Sections
  1  the pocket's inside corner — the edge the escape EXISTS for (must pass)
  2  a 3 mm bore's far wall / bottom rim — hidden geometry that shares the hit
     face (must NOT pass)
  3  the same inside corner at a grazing angle (~7 deg off edge-on)
  4  what each candidate rule would decide, per sample

Findings are printed at the end.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PORT = int(os.environ.get("TEXTCAD_PROBE_PORT", "8137"))
URL = f"http://127.0.0.1:{PORT}"

POCKET = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 40, depth: 30, thickness: 20 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 't', op: 'plate', params: { width: 20, depth: 12, thickness: 10 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'tm', op: 'move', params: { x: 0, y: 0, z: 10 }, inputs: ['t'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'c', op: 'cut', params: {}, inputs: ['b', 'tm'] }, 'add');
}
"""

BORE = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 40, depth: 30, thickness: 20 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'h', op: 'hole', params: { diameter: 3, depth: 20, through: true,
      face_center: [0, 0, 10], face_normal: [0, 0, 1], at: [0, 0] }, inputs: ['b'] }, 'add');
}
"""

# every edge of a body with its midpoint, kind and the faces it bounds
EDGES = """
(body) => {
  const b = window.__vp.bodyObjsRaw().find(x => x.id === body);
  return b.data.edges.map((e, i) => {
    const P = e.points, n = P.length;
    const mid = n % 2 === 0 ? [0, 1, 2].map(k => (P[n / 2 - 1][k] + P[n / 2][k]) / 2)
                            : P[Math.floor(n / 2)];
    return { i, id: e.id, type: e.type, mid, zs: P.map(p => p[2]) };
  });
}
"""

# put the camera exactly where we want it (distance from the target, direction)
AIM = """
([dir, dist, target]) => {
  const c = window.__vp.camera, ctl = window.__vp.getControls();
  const L = Math.hypot(...dir);
  ctl.target.set(...target);
  c.position.set(target[0] + dir[0] / L * dist,
                 target[1] + dir[1] / L * dist,
                 target[2] + dir[2] / L * dist);
  c.lookAt(ctl.target); ctl.update(); c.updateMatrixWorld(true);
  return c.position.toArray();
}
"""

WORLD_TO_SCREEN = "(p) => window.__vp.worldToScreen(p)"
REPORT = "([x, y]) => window.__vp.edgeHitReport(x, y)"


def build(page, script):
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      await postJSON('/api/new', {});
    }""")
    page.wait_for_timeout(700)
    page.evaluate(script)
    page.wait_for_timeout(1800)


def sample(page, body, edge_index, direction, dist, target=(0, 0, 0)):
    """Aim the camera, then report every edge hit at that edge's own midpoint."""
    page.evaluate(AIM, [list(direction), dist, list(target)])
    page.wait_for_timeout(120)
    edges = page.evaluate(EDGES, body)
    e = edges[edge_index]
    s = page.evaluate(WORLD_TO_SCREEN, e["mid"])
    if not s:
        return None
    rep = page.evaluate(REPORT, [s["cx"], s["cy"]])
    rep["want"] = e["id"]
    rep["dist"] = dist
    return rep


def show(title, rep):
    if rep is None:
        print(f"  {title}: off screen")
        return
    print(f"  {title}: face={rep['face']} depth={rep['faceDepth']} "
          f"mm/px={rep['mmPerPx']}  (want edge {rep['want']})")
    for h in rep["hits"][:4]:
        print(f"     edge {h['edge']:>3}  own={str(h['own']):<5} "
              f"behind={h['behind']:>8}  world={h['world']:>8}  px={h['px']:>7}")


def main():
    import uvicorn
    from playwright.sync_api import sync_playwright

    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    cfg = uvicorn.Config(studio.app, host="127.0.0.1", port=PORT, log_level="warning")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    import httpx
    for _ in range(80):
        try:
            httpx.get(f"{URL}/api/doc", timeout=1)
            break
        except Exception:
            time.sleep(0.25)

    rows = []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        page = br.new_page(viewport={"width": 1200, "height": 800})
        page.goto(URL)
        page.wait_for_function("() => !!window.__vp", timeout=20000)
        page.wait_for_timeout(1200)

        build(page, POCKET)
        edges = page.evaluate(EDGES, "c")
        inside = [e for e in edges
                  if abs(e["mid"][0]) < 11 and abs(e["mid"][1]) < 7
                  and min(e["zs"]) > 4.9]
        print(f"\n{len(inside)} inside edges of the pocket "
              f"(4 uprights + 4 floor rims expected)")

        # ---------------------------------------------------------------- 1
        # A user does not click the exact centre line of an edge: the click
        # lands a few pixels off it, and THAT is when the edge's own face ends
        # up in front of the line. Sampling the line's own midpoint only never
        # consults the escape at all (measured: 0 of 108 samples).
        print("")
        print("=== 1. every inside edge x direction x zoom x CLICK OFFSET ===")
        OFFSETS = [(0, 0), (3, 0), (-3, 0), (0, 3), (0, -3), (2, 2), (-2, -2), (4, 1)]
        for dirn, label in (((1, 1, 0.9), "iso +X+Y"), ((-1, -1, 0.9), "iso -X-Y"),
                            ((1, 0.12, 0.06), "grazing")):
            for dist in (60, 160, 400):
                page.evaluate(AIM, [list(dirn), dist, [0, 0, 0]])
                page.wait_for_timeout(100)
                for e in inside:
                    s2 = page.evaluate(WORLD_TO_SCREEN, e["mid"])
                    if not s2:
                        continue
                    for dx, dy in OFFSETS:
                        rep = page.evaluate(REPORT, [s2["cx"] + dx, s2["cy"] + dy])
                        hit = next((h for h in rep["hits"] if h["edge"] == e["id"]), None)
                        if hit is None:
                            continue
                        rows.append({"edge": e["id"], "dir": label, "dist": dist,
                                     "off": str(dx) + "," + str(dy),
                                     "reach4": round(rep["mmPerPx"] * 5 * 4, 3), **hit})
        print("  " + str(len(rows)) + " samples taken")

        # ---------------------------------------------------------------- 2
        print("\n=== 2. a 3 mm bore, clicked deep inside it (hidden far wall) ===")
        build(page, BORE)
        for dist in (60, 160, 400):
            page.evaluate(AIM, [[0.2, 0.2, 1], dist, [0, 0, 0]])
            page.wait_for_timeout(120)
            for z in (8.0, 4.0, 0.0):
                s2 = page.evaluate(WORLD_TO_SCREEN, [1.0, 0.0, z])
                if not s2:
                    continue
                rep = page.evaluate(REPORT, [s2["cx"], s2["cy"]])
                reach4 = round(rep["mmPerPx"] * 5 * 4, 3)
                for h in rep["hits"][:3]:
                    print(f"  z={z:>5} @{dist:>4}mm  edge {h['edge']:>3} "
                          f"own={str(h['own']):<5} behind={h['behind']:>8} "
                          f"world={h['world']:>8} px={h['px']:>7} 4*reach={reach4:>7}")
        br.close()

    # ------------------------------------------------------------------- 3
    print("\n=== 3. the separation the rule has to make ===")
    own = [r for r in rows if r["own"]]
    at = [r for r in own if r["world"] <= 0.05]
    away = [r for r in own if r["world"] > 0.05]
    # the escape is only CONSULTED when the edge is deeper than the face hit by
    # more than visibleEdgeHit's own 1e-3 tolerance: everything else is already
    # "in front" and never reaches ownFaceHit
    used = [r for r in rows if r["own"] and r["behind"] > 1e-3]
    print(f"  the escape is actually consulted on {len(used)} of {len(rows)} samples")
    for r in used:
        print(f"    edge {r['edge']:>3} {r['dir']:<10} {r['dist']:>4}mm "
              f"off={r.get('off', '0,0'):<7} behind={r['behind']:<11} "
              f"world={r['world']:<11} px={r['px']:<7} 4*reach={r['reach4']}")
    if used:
        # every one of these is a click ON the wanted edge (the sample point is
        # that edge's own screen position, offset by at most 4 px), so they are
        # all LEGITIMATE: whatever bound the escape uses has to accept them.
        ratio = sorted(r["world"] / (r["reach4"] / 4) for r in used)
        print(f"    behind mm: max {max(r['behind'] for r in used):.3f}")
        print(f"    world  mm: max {max(r['world'] for r in used):.3f}")
        print(f"    px       : max {max(r['px'] for r in used):.2f}"
              f"   <- every own-face hit is inside the 5 px pick threshold by")
        print(f"                            construction, so a PIXEL bound of 20 px")
        print(f"                            accepts all of them and guards nothing")
        print(f"    world / reach: median {ratio[len(ratio) // 2]:.2f}  "
              f"p90 {ratio[int(len(ratio) * 0.9)]:.2f}  max {ratio[-1]:.2f}"
              f"   <- the shipped bound is 4.00")
    hidden = [r for r in rows if not r["own"] and r["behind"] is not None]
    print(f"  hits whose face is NOT one of the edge's own: {len(hidden)}"
          f"  (the escape never applies to these)")
    if hidden:
        print(f"    behind mm: min {min(r['behind'] for r in hidden):.3f} "
              f"max {max(r['behind'] for r in hidden):.3f}")


if __name__ == "__main__":
    main()
