"""Section 11 (tool framework core) review probe — measurements, not opinions.

Run:  C:\\Python314\\python.exe probes/tool_framework_probe.py
"""
import json
import os
import sys

os.environ.setdefault("TEXTCAD_NO_BROWSER", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import toolplan                                    # noqa: E402
from document import Document                      # noqa: E402


def build(*feats):
    d = Document(name="probe")
    for fid, op, params, inputs in feats:
        d.add(fid, op, params, inputs)
    d.rebuild()
    return d


def head(t):
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


# ---------------------------------------------------------------- 1. HTTP ---
def s1_plan_http_failures():
    head("1. what the BROWSER sees when /api/tool/plan does not answer {ok:...}")
    from fastapi.testclient import TestClient

    import studio
    c = TestClient(studio.app)
    c.post("/api/feature/add", json={"id": "b", "op": "plate",
                                     "params": {"width": 60, "depth": 40,
                                                "thickness": 20}, "inputs": []})
    cases = [
        ("chain sent as a word", {"tool": "fillet", "body_id": "b",
                                  "chain": "yes-please"}),
        ("face_area as a word", {"tool": "extrude", "body_id": "b",
                                 "face_center": [0, 0, 10], "face_area": "big"}),
        ("offset null", {"tool": "sketch", "plane": "XY", "offset": None}),
        ("unknown tool", {"tool": "nope"}),
        ("no input at all", {"tool": "extrude"}),
    ]
    for name, body in cases:
        r = c.post("/api/tool/plan", json=body)
        j = r.json()
        says = j.get("error")
        print(f"  {name:24s} HTTP {r.status_code}  ok={j.get('ok')!r}  "
              f"panel would say: 'cannot start: {says}.'")


# ------------------------------------------------------- 2. default target ---
def s2_default_target():
    head("2. _default_target / _latest_descendant")
    d = build(
        ("a", "plate", {"width": 60, "depth": 40, "thickness": 10}, []),
        ("b", "plate", {"width": 20, "depth": 20, "thickness": 5,
                        "x": 100}, []),
        ("sa", "sketch_on_face", {"face": "top",
                                  "entities": [{"kind": "circle", "r": 4}]}, ["a"]),
    )
    print("  bodies:", [f.id for f in toolplan._solids(d)])
    print("  face sketch on 'a'   ->", toolplan._default_target(d, "sa"))
    d2 = build(
        ("a", "plate", {"width": 60, "depth": 40, "thickness": 10}, []),
        ("s", "sketch", {"plane": "XY", "offset": 20,
                         "entities": [{"kind": "circle", "r": 4}]}, []),
    )
    print("  plane sketch, 1 body ->", toolplan._default_target(d2, "s"))

    # the host body walked through a STRUCK consumer
    d3 = build(
        ("a", "plate", {"width": 60, "depth": 40, "thickness": 10}, []),
        ("f", "fillet", {"radius": 2, "edges": "all"}, ["a"]),
        ("sa", "sketch_on_face", {"face": "top",
                                  "entities": [{"kind": "circle", "r": 4}]}, ["a"]),
    )
    print("  host filleted        ->", toolplan._default_target(d3, "sa"),
          "(expect f)")
    d3.strike("f")
    d3.rebuild()
    print("  fillet struck out    ->", toolplan._default_target(d3, "sa"),
          "(expect a)")


# ---------------------------------------------------------------- 3. loops ---
def s3_loops():
    head("3. _loops: is the OUTER wire told from the holes reliably?")
    d = build(("a", "plate", {"width": 40, "depth": 40, "thickness": 5}, []),
              ("s", "sketch", {"plane": "XY", "entities": [
                  {"kind": "circle", "r": 15},
                  {"kind": "circle", "r": 5, "mode": "cut"}]}, []))
    import sketch as sk
    prof = d._parts["s"]
    pl = sk.sketch_plane("XY", 0)
    for f in prof.faces():
        outer = f.outer_wire()
        lens = [round(w.length, 9) for w in f.wires()]
        print(f"  face: outer.length={outer.length:.9f}  wires={lens}")
        loops = toolplan._loops([f], pl)
        print(f"        holes found: {len(loops[0]['holes'])} (expect 1)")


# --------------------------------------------------------------- 4. limits ---
def s4_limits_centre():
    head("4. _limits centre: the arrow's anchor on a mixed straight/curved profile")
    import sketch as sk
    # a keyhole: a big circle and a small square, both 'add', far apart
    d = build(("s", "sketch", {"plane": "XY", "entities": [
        {"kind": "circle", "r": 10, "x": -20},
        {"kind": "rectangle", "w": 20, "h": 20, "x": 20}]}, []))
    prof = d._parts["s"]
    pl = sk.sketch_plane("XY", 0)
    faces = list(prof.faces())
    loops = toolplan._loops(faces, pl)
    limits, centre = toolplan._limits(loops)
    area_c = [0.0, 0.0]
    tot = 0.0
    for f in faces:
        a = f.area
        c = pl.to_local_coords(f.center())
        area_c[0] += a * c.X
        area_c[1] += a * c.Y
        tot += a
    area_c = [area_c[0] / tot, area_c[1] / tot]
    print(f"  _limits centre (sample average): {centre}")
    print(f"  true AREA centroid             : [{area_c[0]:.4f}, {area_c[1]:.4f}]")
    print(f"  arrow is off by                : "
          f"{abs(centre[0] - area_c[0]):.4f} mm in x")
    print(f"  outer_radius={limits['outer_radius']}")


# ------------------------------------------------------------ 5. pick_body ---
def s5_pick_body():
    head("5. _pick_body: the sentence for each kind of missing body")
    d = build(("a", "plate", {"width": 60, "depth": 40, "thickness": 10}, []),
              ("s", "sketch", {"plane": "XY",
                               "entities": [{"kind": "circle", "r": 4}]}, []))
    for bid in ("a", "s", "nope", None):
        try:
            part, out = toolplan._pick_body(d, bid, "shell")
            print(f"  body_id={bid!r:8s} -> part={type(part).__name__:10s} id={out!r}")
        except Exception as e:                              # noqa: BLE001
            print(f"  body_id={bid!r:8s} -> {type(e).__name__}: {e}")


if __name__ == "__main__":
    s1_plan_http_failures()
    s2_default_target()
    s3_loops()
    s4_limits_centre()
    s5_pick_body()
    print("\n(json check)", json.dumps({"ok": True})[:10])
