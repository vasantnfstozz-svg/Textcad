r"""Section 12 ROUND THREE - the three things round two's own fix pass leaves.

Round two (29bc967) keyed the export off the ACTIVE TAB's file stem, tightened
/api/spec's number check, and cleaned one file out of designs/. This probe
measures, WITHOUT touching the user's library or their running server:

  1. tests/test_api.py::test_mcp_build_design_and_verify writes into the REAL
     designs/ folder AND rings the doorbell at 127.0.0.1:8123 - the user's own
     app - on every fast-tier run.
  2. /api/spec still accepts a value the checker cannot use: n_solids and
     symmetry take ANY int, so 10**400 walks in, and `symmetry` also takes 0
     and negatives.
  3. the export's doc and its file name are read from STATE["active"] twice
     over, so they are not taken from one entry.

Run: C:\Python314\python.exe probes/section12_round3_probe.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      tempfile.mkdtemp(prefix="s12r3-hist-"))

import inspector                                          # noqa: E402
import mcp_server                                         # noqa: E402
import studio                                             # noqa: E402
from document import Document                             # noqa: E402


def part1_mcp_test_writes_into_the_library():
    print("=" * 74)
    print("1. tests/test_api.py::test_mcp_build_design_and_verify")
    print("=" * 74)
    print(f"   mcp_server.OUT               = {mcp_server.OUT}")
    print(f"   is the user's design library = "
          f"{mcp_server.OUT.resolve() == (ROOT / 'designs').resolve()}")

    # What the unpatched test leaves behind, measured in a temp folder so this
    # probe writes nothing into designs/. The NAMES are what matter.
    tmp = Path(tempfile.mkdtemp(prefix="s12r3-out-"))
    rung = []

    import urllib.request
    real_urlopen = urllib.request.urlopen

    def spy(req, *a, **kw):                  # never actually ring the doorbell
        rung.append(getattr(req, "full_url", req))
        raise OSError("probe: the doorbell was NOT sent")

    old_out = mcp_server.OUT
    mcp_server.OUT = tmp
    urllib.request.urlopen = spy
    try:
        tree = {"name": "t-washer", "features": [
            {"id": "b", "op": "disc", "params": {"radius": 20, "thickness": 4}},
            {"id": "h", "op": "with_center_hole", "params": {"radius": 10},
             "inputs": ["b"]}],
            "spec": {"n_solids": 1}}
        rep = mcp_server.build_design(tree)
        import time
        time.sleep(1.0)                      # _notify_studio is a thread
    finally:
        mcp_server.OUT = old_out
        urllib.request.urlopen = real_urlopen

    print(f"   verified                     = {rep.get('verified')}")
    wrote = sorted(p.name for p in tmp.iterdir())
    print(f"   files the test writes        = {wrote}")
    print("   ...and with OUT unpatched they land in "
          f"{(ROOT / 'designs')}")
    for n in wrote:
        live = ROOT / "designs" / n
        print(f"     designs/{n}: exists={live.exists()}"
              + (f" mtime={live.stat().st_mtime:.0f}" if live.exists() else ""))
    print(f"   DOORBELL rung at             = {rung}")


def part2_spec_numbers():
    print()
    print("=" * 74)
    print("2. /api/spec - what _spec_problem still lets through")
    print("=" * 74)
    cases = [
        ("volume", 10 ** 400), ("volume", True), ("volume", "50"),
        ("volume", -0.0), ("volume", 1e308),
        ("n_solids", 10 ** 400), ("n_solids", -3), ("n_solids", 0),
        ("symmetry", 10 ** 400), ("symmetry", 0), ("symmetry", -4),
        ("symmetry", 10 ** 9),
        ("tol", 10 ** 400), ("tol", 0), ("tol", -1),
        ("holes", {"4": 10 ** 400}), ("holes", {"4": -6}),
        ("holes", {"4": True}), ("holes", {"-4": 6}),
        ("size", [10 ** 400, None, None]), ("size", [1, 2, None]),
    ]
    for key, val in cases:
        problem = studio._spec_problem(key, val)
        v = repr(val)
        print(f"   {key:<12} {v[:28]:<30} -> "
              + ("REFUSED" if problem else "ACCEPTED"))

    # What the ACCEPTED ones then do to the verifier and to the document.
    print("\n   the accepted ones, put to inspector.verify on a real solid:")
    doc = Document(name="s12r3")
    doc.add("base", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    doc.rebuild()
    solid = doc._result_feature().part if hasattr(
        doc._result_feature(), "part") else doc._parts["base"]
    for key, val in [("n_solids", 10 ** 400), ("symmetry", 10 ** 400),
                     ("symmetry", 0), ("symmetry", -4), ("tol", -1)]:
        spec = inspector.spec_from_dict({key: val})
        try:
            fails = inspector.verify(solid, spec)
            head = (fails[0][:70] + "...") if fails else "PASSES"
            print(f"     {key}={repr(val)[:18]:<20} -> {len(fails)} fail(s): {head}")
        except Exception as e:                            # noqa: BLE001
            print(f"     {key}={repr(val)[:18]:<20} -> RAISED "
                  f"{type(e).__name__}: {e}")

    # ...and whether the whole document survives a rebuild with it in place.
    print("\n   ...and a full doc.rebuild() with the value in the spec:")
    for key, val in [("n_solids", 10 ** 400), ("symmetry", 10 ** 400),
                     ("symmetry", 0)]:
        d = Document(name="s12r3")
        d.add("base", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
        d.spec = {key: val}
        try:
            ok = d.rebuild()
            import json
            json.dumps(d.to_data())
            print(f"     {key}={repr(val)[:18]:<20} -> rebuild ok={ok}, "
                  f"saveable, spec_fails={getattr(d, 'spec_fails', None)}")
        except Exception as e:                            # noqa: BLE001
            print(f"     {key}={repr(val)[:18]:<20} -> RAISED "
                  f"{type(e).__name__}: {e}")


def part3_export_reads_active_twice():
    print()
    print("=" * 74)
    print("3. /api/export - doc and slug are two reads of STATE['active']")
    print("=" * 74)
    import inspect
    src = inspect.getsource(studio.export_step)
    body = [ln.strip() for ln in src.splitlines()
            if ln.strip().startswith(("doc = ", "slug = ", "clash = ",
                                      "path = "))]
    for ln in body:
        print(f"   {ln}")
    print("   _doc()            -> _entry() -> STATE['docs'][STATE['active']]")
    print("   _slug_of_active() -> _entry() -> STATE['docs'][STATE['active']]")
    print("   _name_clash()     -> _entry() and STATE['active'] again")
    print("   => three reads; nothing binds them to one entry.")

    # The divergence, forced: what the endpoint writes when the active tab
    # moves between the first read and the second.
    studio.STATE["docs"], studio.STATE["active"], studio.STATE["seq"] = {}, None, 0
    a = Document(name="alpha")
    a.add("base", "plate", {"width": 40, "depth": 40, "thickness": 10}, [])
    b = Document(name="beta")
    b.add("base", "plate", {"width": 10, "depth": 10, "thickness": 2}, [])
    ta = studio._new_tab(a, source="file:alpha")
    tb = studio._new_tab(b, source="file:beta")
    studio.STATE["active"] = ta
    doc = studio._doc()                       # read 1: tab A
    studio.STATE["active"] = tb               # the doorbell lands HERE
    slug = studio._slug_of_active()           # read 2: tab B
    print(f"\n   doc read from tab A  : name={doc.name!r}")
    print(f"   slug read from tab B : {slug!r}")
    print(f"   => designs/{slug}.step would hold {doc.name}'s geometry: "
          f"{slug != 'alpha'}")


if __name__ == "__main__":
    part1_mcp_test_writes_into_the_library()
    part2_spec_numbers()
    part3_export_reads_active_twice()
