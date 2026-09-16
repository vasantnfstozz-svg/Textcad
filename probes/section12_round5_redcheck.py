"""Would round five's tests go RED if each fix were reverted - and are round
four's and the browser half's tests earned too?

Six reverts, one at a time, each on a COPY of the tree, each followed by
tests/test_tab_header.py (and, for the pin, tests/test_server_layer.py). A
test that stays green under the revert of its own fix is a positive control,
not a guard, and has to be named as one.

Run:  C:\\Python314\\python.exe probes/section12_round5_redcheck.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def scratch() -> Path:
    d = Path(tempfile.mkdtemp(prefix="tc-r5-red-"))
    for p in ROOT.glob("*.py"):
        shutil.copy2(p, d / p.name)
    for name in ("pytest.ini", "ruff.toml"):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, d / name)
    shutil.copytree(ROOT / "tests", d / "tests",
                    ignore=shutil.ignore_patterns("e2e", "__pycache__"))
    shutil.copytree(ROOT / "static", d / "static",
                    ignore=shutil.ignore_patterns("vendor"))
    (d / "designs").mkdir(exist_ok=True)
    return d


def patch(tree: Path, rel: str, old: str, new: str):
    p = tree / rel
    s = p.read_text(encoding="utf-8")
    assert s.count(old) == 1, f"{rel}: anchor found {s.count(old)}x"
    p.write_text(s.replace(old, new), encoding="utf-8")


def run(tree: Path, files):
    r = subprocess.run([PY, "-m", "pytest", *files, "-q", "--no-header",
                        "-p", "no:cacheprovider"],
                       cwd=tree, capture_output=True, text=True)
    failed = sorted({ln.split("::")[-1].split()[0]
                     for ln in r.stdout.splitlines() if ln.startswith("FAILED")})
    tail = [ln for ln in r.stdout.splitlines()
            if " passed" in ln or " failed" in ln or " error" in ln]
    return (tail[-1] if tail else r.stdout[-300:]), failed


REVERTS = [
    ("A  tabHeaders() (the browser half, ab6ad83)", [
        ("static/js/api.js",
         "  const tid = S.lastDoc && S.lastDoc.active_tab;\n"
         "  return tid ? { ...base, 'X-TextCAD-Tab': tid } : base;",
         "  return base;")]),
    ("B  the page-wide fetch door (round five)", [
        ("static/js/api.js",
         "if (typeof _rawFetch === 'function' && !globalThis.__textcadTabFetch) {",
         "if (false) {")]),
    ("C  active_tab / the tab strip naming the answer's tab (round five)", [
        ("studio.py", '        "active_tab": _active_tid(),',
         '        "active_tab": STATE["active"],'),
        ("studio.py", "    here = _active_tid()", '    here = STATE["active"]'),
        ("studio.py", '    return {"tabs": _tabs_json(), "active_tab": _active_tid()}',
         '    return {"tabs": _tabs_json(), "active_tab": STATE["active"]}')]),
    ("D  one rule for the header in both middlewares (round five)", [
        ("studio.py",
         "        busy = _job_on(_addressed_tab(request) or STATE[\"active\"]) is not None",
         "        busy = _job_on(request.headers.get(TAB_HEADER)\n"
         "                       or STATE[\"active\"]) is not None")]),
    ("E  the arrival's deliberate follow (round five)", [
        ("static/js/api.js",
         "  if (open) await postJSON('/api/tabs/switch', { id: a.tab },\n"
         "                           `opening ${a.name}…`);",
         "  void open;")]),
    ("F  the per-request pin itself (round four)", [
        ("studio.py",
         '    pinned = _REQ_TAB.get()\n'
         '    if pinned and pinned in STATE["docs"]:\n'
         '        return pinned',
         "    pinned = None\n    if False:\n        return \"\"")]),
]

for label, edits in REVERTS:
    tree = scratch()
    for rel, old, new in edits:
        patch(tree, rel, old, new)
    files = ["tests/test_tab_header.py"]
    if label.startswith(("D", "F")):
        files.append("tests/test_server_layer.py")
    tail, failed = run(tree, files)
    print(f"\nrevert {label}\n  {tail}")
    for f in failed:
        print("   RED ", f)
    if not failed:
        print("   (nothing went red)")
    shutil.rmtree(tree, ignore_errors=True)
