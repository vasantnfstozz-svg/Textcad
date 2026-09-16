"""Would round four's tests go RED if its fix were reverted?

Two reverts, applied one at a time to a COPY of studio.py in a scratch tree,
each followed by the test file:

  A. the per-request pin (_active_tid goes back to plain STATE["active"])
  B. only the _name_clash half (round three's residual)

and then round THREE's own five tests, re-checked under round four's code so
the two fixes are known to compose.

Run:  C:\\Python314\\python.exe probes/section12_round4_redcheck.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

ROUND_FOUR = [
    "test_a_tab_that_arrives_mid_add_cannot_take_the_feature",
    "test_a_tab_that_arrives_mid_edit_cannot_take_the_value",
    "test_a_tab_that_arrives_mid_trace_cannot_take_the_logo",
    "test_a_tab_that_arrives_mid_save_cannot_open_the_clash_guard",
    "test_a_tab_that_arrives_mid_export_does_not_refuse_the_right_file",
    "test_the_tab_a_request_is_addressed_to_does_not_leak_to_the_next",
    "test_a_request_that_opens_a_tab_is_addressed_to_the_tab_it_opened",
    "test_a_request_may_name_the_tab_it_is_addressed_to",
]
ROUND_THREE = [
    "test_a_tab_that_arrives_mid_export_cannot_rename_the_file",
    "test_one_designs_geometry_never_lands_in_another_designs_step",
    "test_a_tab_that_arrives_mid_save_is_not_bound_to_this_designs_file",
    "test_a_step_file_the_user_made_is_put_back_not_deleted",
]

PIN = '''    pinned = _REQ_TAB.get()
    if pinned and pinned in STATE["docs"]:
        return pinned'''
NO_PIN = '''    pinned = None
    if False:
        return ""'''


def run(tree: Path, names):
    args = [PY, "-m", "pytest", "tests/test_server_layer.py", "-q",
            "--no-header", "-p", "no:cacheprovider"]
    for n in names:
        args += ["-k", n] if len(names) == 1 else []
    if len(names) > 1:
        args += ["-k", " or ".join(names)]
    r = subprocess.run(args, cwd=tree, capture_output=True, text=True)
    tail = [ln for ln in r.stdout.splitlines() if " passed" in ln
            or " failed" in ln or " error" in ln]
    failed = [ln.split("::")[-1].split()[0]
              for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
    return (tail[-1] if tail else r.stdout[-400:]), failed


def scratch():
    d = Path(tempfile.mkdtemp(prefix="tc-r4-red-"))
    for name in ("studio.py", "supervise.py", "pytest.ini", "conftest.py"):
        p = ROOT / name
        if p.exists():
            shutil.copy2(p, d / name)
    for name in ROOT.glob("*.py"):
        if not (d / name.name).exists():
            shutil.copy2(name, d / name.name)
    shutil.copytree(ROOT / "tests", d / "tests")
    for extra in ("designs", "static", "samples"):
        src = ROOT / extra
        if src.is_dir() and extra != "designs":
            shutil.copytree(src, d / extra)
    (d / "designs").mkdir(exist_ok=True)
    return d


print("baseline (round four's code, as committed)")
line, _ = run(ROOT, ROUND_FOUR + ROUND_THREE)
print("  round four + round three together:", line)

print()
print("REVERT A - the per-request pin removed (_active_tid reads the live "
      "active tab, as every route did before)")
a = scratch()
src = (a / "studio.py").read_text(encoding="utf-8")
assert PIN in src, "the pin block moved; update this probe"
(a / "studio.py").write_text(src.replace(PIN, NO_PIN), encoding="utf-8")
line, failed = run(a, ROUND_FOUR)
print("  ", line)
print("   RED:", sorted(failed))
print("   still green:", sorted(set(ROUND_FOUR) - set(failed)))

print()
print("REVERT B - only _name_clash put back to STATE[\"active\"]")
b = scratch()
src = (b / "studio.py").read_text(encoding="utf-8")
src2 = re.sub(r'if owner is not None and owner != _active_tid\(\):',
              'if owner is not None and owner != STATE["active"]:', src)
assert src2 != src, "the _name_clash line moved; update this probe"
(b / "studio.py").write_text(src2, encoding="utf-8")
line, failed = run(b, ROUND_FOUR + ROUND_THREE)
print("  ", line)
print("   RED:", sorted(failed))

print()
print("ROUND THREE'S OWN FIVE TESTS, red-checked under round four's code")
for label, sub, old, new, names, file in [
    ("C  /api/export back to two reads of the tab",
     "studio.py", "slug = _slug_of_active(e) or _design_slug(doc.name)",
     "slug = _slug_of_active() or _design_slug(doc.name)",
     ROUND_THREE[:2], "tests/test_server_layer.py"),
    ("D  /api/save back to two reads of the tab",
     "studio.py", '    e["source"] = f"file:{safe}"',
     '    _entry()["source"] = f"file:{safe}"',
     ROUND_THREE[2:3], "tests/test_server_layer.py"),
    ("E  the library-step guard removed (unlink, as round two had it)",
     "tests/conftest.py", "                p.write_bytes(data)",
     "                p.unlink(missing_ok=True)",
     ROUND_THREE[3:4], "tests/test_server_layer.py"),
    ("F  the MCP test back inside the user's library",
     "tests/test_api.py", '    monkeypatch.setattr(mcp_server, "OUT", tmp_path)',
     "    pass",
     ["test_a_test_build_lands_outside_the_library_and_rings_no_doorbell"],
     "tests/test_api.py"),
]:
    t = scratch()
    src = (t / sub).read_text(encoding="utf-8")
    assert old in src, f"{label}: the line moved; update this probe"
    (t / sub).write_text(src.replace(old, new, 1), encoding="utf-8")
    args = [PY, "-m", "pytest", file, "-q", "--no-header",
            "-p", "no:cacheprovider", "-k", " or ".join(names)]
    r = subprocess.run(args, cwd=t, capture_output=True, text=True)
    tail = [ln for ln in r.stdout.splitlines()
            if " passed" in ln or " failed" in ln or " error" in ln]
    print(f"  {label}: {tail[-1] if tail else r.stdout[-200:]}")
    shutil.rmtree(t, ignore_errors=True)

print()
print("CONTROL - round three's three race tests with BOTH the pin AND round")
print("three's own single-read fix removed (they must go red, or they were")
print("never testing anything)")
g = scratch()
src = (g / "studio.py").read_text(encoding="utf-8")
src = src.replace(PIN, NO_PIN)
src = src.replace("slug = _slug_of_active(e) or _design_slug(doc.name)",
                  "slug = _slug_of_active() or _design_slug(doc.name)", 1)
src = src.replace('    e["source"] = f"file:{safe}"',
                  '    _entry()["source"] = f"file:{safe}"', 1)
src = src.replace('if owner is not None and owner != _active_tid():',
                  'if owner is not None and owner != STATE["active"]:', 1)
(g / "studio.py").write_text(src, encoding="utf-8")
line, failed = run(g, ROUND_THREE[:3])
print("  ", line)
print("   RED:", sorted(failed))
shutil.rmtree(g, ignore_errors=True)

shutil.rmtree(a, ignore_errors=True)
shutil.rmtree(b, ignore_errors=True)
