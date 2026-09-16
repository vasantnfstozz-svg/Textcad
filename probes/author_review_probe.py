"""probes/author_review_probe.py — section 13 (AI author, MCP and chat) review.

Every number in the report is measured here, never inferred.

  §1  the `done` gate runs lint_tree over the WHOLE tree, the user's own
      hand-built features included: which of the 50 saved designs can the AI
      never finish an "add" job on?
  §2  the `done` gate's health question is also whole-tree: a feature that was
      already red before the job refuses `done`.
  §3  MCP build_design / design_part write straight into designs/ with
      Document.save — no owner check, no existence check, no version tree.
  §4  verify_step's verdict for requirements it never checked.
  §5  meanline.design on degenerate duty.

Read-only on designs/: nothing here writes into the user's library.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import author                      # noqa: E402
from document import Document      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DESIGNS = ROOT / "designs"


def s1_lint_the_users_library():
    print("=== S1  lint_tree(final=True) over the SAVED designs ===")
    files = sorted(DESIGNS.glob("*.tcad.json"))
    bad = []
    for p in files:
        try:
            doc = Document.from_data(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:                       # noqa: BLE001
            print(f"  (skipped {p.stem}: {e})")
            continue
        problems = author.lint_tree(doc.features, final=True)
        if problems:
            bad.append((p.stem, problems))
    for stem, problems in bad:
        print(f"  {stem}: {problems[0][:110]}")
    print(f"  -> {len(bad)} of {len(files)} designs FAIL the authoring lint "
          f"as saved")
    return bad


def s2_done_on_a_red_tree():
    print("\n=== S2  `done` when a feature the AI did not touch is red ===")
    doc = Document(name="user-design")
    doc.add("base", "plate", {"width": 40, "depth": 30, "thickness": 5})
    # the user's own broken feature, beside the body rather than on it: a
    # second plate with a nonsense dimension
    doc.add("rib", "plate", {"width": 0, "depth": 10, "thickness": 2})
    doc.rebuild()
    print("  the user's tree:", [(f.id, f.status) for f in doc.features])
    protected = frozenset(f.id for f in doc.features)
    steps = [
        {"add": {"id": "boss_sketch", "op": "sketch_on_face",
                 "params": {"face": "top", "offset": 0,
                            "entities": [{"kind": "circle", "r": 5}]},
                 "inputs": ["base"]}},
        {"add": {"id": "boss", "op": "extrude",
                 "params": {"amount": 4}, "inputs": ["boss_sketch"]}},
        {"add": {"id": "boss_join", "op": "fuse",
                 "params": {}, "inputs": ["base", "boss"]}},
    ]
    for st in steps:
        ok, text, _ = author._apply_step(doc, st, protected, keep_spec=True)
        print(f"  add {st['add']['id']:12s} -> ok={ok}  {text[:80]}")
    ok2, text2, _ = author._apply_step(doc, {"done": True}, protected,
                                       keep_spec=True)
    print(f"  done            -> ok={ok2}  {text2[:140]}")
    return ok2


def s2b_done_on_a_linted_tree():
    print("\n=== S2b  `done` on a design whose own sketch breaks the lint ===")
    doc = Document(name="user-design")
    ents = [{"kind": "circle", "r": 1, "x": i * 3, "y": 0} for i in range(12)]
    doc.add("art_sketch", "sketch", {"plane": "XY", "offset": 0,
                                     "entities": ents})
    doc.add("art", "extrude", {"amount": 2}, inputs=["art_sketch"])
    doc.rebuild()
    print("  the user's tree:", [(f.id, f.status) for f in doc.features])
    protected = frozenset(f.id for f in doc.features)
    ok, text, _ = author._apply_step(
        doc, {"add": {"id": "pin_sketch", "op": "sketch_on_face",
                      "params": {"face": "top", "offset": 0,
                                 "entities": [{"kind": "circle", "r": 2}]},
                      "inputs": ["art"]}}, protected, keep_spec=True)
    print(f"  add pin_sketch -> ok={ok}  {text[:80]}")
    ok2, text2, _ = author._apply_step(doc, {"done": True}, protected,
                                       keep_spec=True)
    print(f"  done           -> ok={ok2}  {text2[:160]}")
    return ok2


def s3_mcp_writes_over_the_library():
    print("\n=== S3  where the MCP doors write ===")
    import mcp_server
    print(f"  mcp_server.OUT = {mcp_server.OUT}")
    print(f"  == designs/ ?   {mcp_server.OUT.resolve() == DESIGNS.resolve()}")
    print(f"  _safe_name('untitled')          = {mcp_server._safe_name('untitled')!r}")
    print(f"  _safe_name('../../etc/passwd')  = {mcp_server._safe_name('../../etc/passwd')!r}")
    print(f"  _safe_name('esp32 remote')      = {mcp_server._safe_name('esp32 remote')!r}")
    for stem in ("untitled", "esp32-remote", "my-part"):
        f = DESIGNS / f"{stem}.tcad.json"
        h = DESIGNS / f"{stem}.history"
        print(f"  designs/{stem}.tcad.json exists: {f.exists()}   "
              f".history/: {h.exists()}")
    doc = author._to_document({"features": [
        {"id": "base_plate", "op": "plate",
         "params": {"width": 10, "depth": 10, "thickness": 2}}]})
    print(f"  _to_document(no name).name = {doc.name!r}  -> would write "
          f"designs/{mcp_server._safe_name(doc.name)}.tcad.json")


def s4_verify_step_claims():
    print("\n=== S4  verify_step: a verdict on requirements never checked ===")
    import inspector
    for spec in ({"size": [40, 30, 5], "wall_thickness": 2},
                 {"size": [40, 30]},
                 {"holes": {"2.5": 4}, "hole_depth": 8}):
        obj = inspector.spec_from_dict(spec)
        kept = {k: v for k, v in vars(obj).items()
                if v not in (None, {}, 0.5, 0.02, True)}
        print(f"  asked {spec}")
        print(f"    -> inspector.Spec actually checks {kept}")
        try:
            author.checked_spec(spec)
            print("    -> author.checked_spec: accepted")
        except ValueError as e:
            print(f"    -> author.checked_spec now refuses: {str(e)[:90]}")


def s5_meanline_degenerate():
    print("\n=== S5  design_compressor on degenerate duty ===")
    import meanline
    for kw in ({"mass_flow_kg_s": 0.5, "pressure_ratio": 3.0, "rpm": 0},
               {"mass_flow_kg_s": 0.5, "pressure_ratio": 1.0, "rpm": 45000},
               {"mass_flow_kg_s": 0.5, "pressure_ratio": 0.5, "rpm": 45000},
               {"mass_flow_kg_s": 0.5, "pressure_ratio": 3.0, "rpm": 45000,
                "backsweep_deg": 95.0},
               {"mass_flow_kg_s": 0.0, "pressure_ratio": 3.0, "rpm": 45000}):
        try:
            d = meanline.design(meanline.Duty(
                mass_flow=kw["mass_flow_kg_s"],
                pressure_ratio=kw["pressure_ratio"], rpm=kw["rpm"],
                backsweep_deg=kw.get("backsweep_deg", 35.0)))
            print(f"  {kw} -> designed r2={d.tip_radius}")
        except Exception as e:                       # noqa: BLE001
            print(f"  {kw} -> {type(e).__name__}: {e}")


def s6_catalogue_vs_op():
    """Every ENUM value author._ENUMS advertises, put to the op itself."""
    print("\n=== S6  the catalogue's enum values, put to the kernel ===")
    import blocks
    cat = {c["op"]: c for c in author.op_catalog()}

    def offered(op, param):
        p = next(p for p in cat[op]["params"] if p["name"] == param)
        return p.get("enum") or []

    base = blocks.plate(40, 30, 8)
    checks = [
        ("fillet", lambda v: blocks.fillet_edges(base, 2.0, edges=v),
         offered("fillet", "edges")),
        ("chamfer", lambda v: blocks.chamfer_edges(base, 1.0, edges=v),
         offered("chamfer", "edges")),
    ]
    import sketch as sk
    checks.append(("shell.open_face",
                   lambda v: sk.shell(base, thickness=1.5, open_face=v),
                   offered("shell", "open_face")))
    checks.append(("hole.kind",
                   lambda v: sk.hole(base, face="top", at=(0, 0), diameter=4,
                                     depth=3, kind=v,
                                     cbore_diameter=6, cbore_depth=1,
                                     csink_diameter=6, csink_angle=90),
                   offered("hole", "kind")))
    import pattern
    checks.append(("polar_pattern.axis",
                   lambda v: pattern.polar_pattern(base, 3, axis=v),
                   offered("polar_pattern", "axis")))
    checks.append(("rotate.axis",
                   lambda v: blocks.rotate(base, axis=v, angle_deg=30),
                   offered("rotate", "axis")))
    for name, fn, values in checks:
        for v in values:
            try:
                out = fn(v)
                vol = getattr(out, "volume", None)
                print(f"  {name:20s} {v!r:14s} -> ok  vol={vol!r}")
            except Exception as e:                    # noqa: BLE001
                print(f"  {name:20s} {v!r:14s} -> {type(e).__name__}: "
                      f"{str(e)[:70]}")


def s7_parse_and_to_document():
    print("\n=== S7  _parse / _to_document on malformed model output ===")
    for raw in ('{"add": {"id": "b", "op": "plate", '
                '"params": {"width": NaN, "depth": 10, "thickness": 2}}}',
                '{"add": {"id": "b", "op": "plate", '
                '"params": {"width": Infinity, "depth": 10, "thickness": 2}}}',
                '{"done": true, "spec": {"n_solids": 1}}'):
        try:
            step = author._parse(raw)
            print(f"  parsed -> {step}")
        except Exception as e:                        # noqa: BLE001
            print(f"  refused -> {type(e).__name__}: {e}")
            continue
        if "add" in step:
            doc = Document(name="t")
            ok, text, _ = author._apply_step(doc, step)
            print(f"    _apply_step -> ok={ok}  {text[:110]}")
    print("  -- _to_document on a features list that is not dicts --")
    for tree in ({"features": ["plate"]},
                 {"features": [{"id": "b"}]},
                 {"features": [{"id": "b", "op": "plate",
                                "params": {"width": 10, "depth": 10,
                                           "thickness": 2}}],
                  "spec": "one solid"}):
        try:
            author._to_document(tree)
            print(f"  {str(tree)[:60]:62s} -> built")
        except Exception as e:                        # noqa: BLE001
            print(f"  {str(tree)[:60]:62s} -> {type(e).__name__}: "
                  f"{str(e)[:60]}")


if __name__ == "__main__":
    s1_lint_the_users_library()
    s2_done_on_a_red_tree()
    s2b_done_on_a_linted_tree()
    s3_mcp_writes_over_the_library()
    s4_verify_step_claims()
    s5_meanline_degenerate()
    s6_catalogue_vs_op()
    s7_parse_and_to_document()
