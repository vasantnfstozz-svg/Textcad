"""Would round SIX's tests go red if each half of its fix were reverted?

Four reverts, one at a time, each on a COPY of the tree, each followed by
tests/test_tab_header.py. A test that stays green under the revert of its own
fix is a positive control, not a guard, and is named as one here.

Run:  C:\\Python314\\python.exe probes/section12_round6_redcheck.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def scratch() -> Path:
    d = Path(tempfile.mkdtemp(prefix="tc-r6-red-"))
    for p in ROOT.glob("*.py"):
        shutil.copy2(p, d / p.name)
    for name in ("pytest.ini", "ruff.toml"):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, d / name)
    shutil.copytree(ROOT / "tests", d / "tests",
                    ignore=shutil.ignore_patterns("e2e", "__pycache__"))
    shutil.copytree(ROOT / "static", d / "static",
                    ignore=shutil.ignore_patterns("vendor"))
    # the loader-shape test pins the SHIPPED three.js, so it has to be here
    v = d / "static" / "vendor" / "three" / "0.160.0"
    v.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "static" / "vendor" / "three" / "0.160.0"
                 / "three.module.js", v / "three.module.js")
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
    return (tail[-1] if tail else r.stdout[-400:]), failed


# the round-five door, exactly as 66d80c1 shipped it
R5_DOOR = """  globalThis.fetch = function (input, init) {
    if (typeof input !== 'string' || !input.startsWith('/api/')) {
      return _rawFetch.call(globalThis, input, init);
    }
    const tid = S.lastDoc && S.lastDoc.active_tab;
    if (!tid) return _rawFetch.call(globalThis, input, init);
    const o = { ...(init || {}) };
    if (typeof Headers !== 'undefined' && o.headers instanceof Headers) {
      const h = new Headers(o.headers);
      h.set('X-TextCAD-Tab', tid);
      o.headers = h;
    } else {
      o.headers = { ...(o.headers || {}), 'X-TextCAD-Tab': tid };
    }
    return _rawFetch.call(globalThis, input, o);
  };"""

R6_DOOR = """  globalThis.fetch = function (input, init) {
    const isReq = typeof Request !== 'undefined' && input instanceof Request;
    const tid = S.lastDoc && S.lastDoc.active_tab;
    if (!tid || !_isApiUrl(isReq ? input.url : input)) {
      return _rawFetch.call(globalThis, input, init);
    }
    if (isReq && (!init || init.headers == null)) {"""

REVERTS = [
    ("A  the whole round-six door -> round five's string-only gate", [
        ("static/js/api.js", R6_DOOR, R5_DOOR + "\n  const _dead = function (input, init) {\n"
         "    const isReq = false;\n    if (true) {")]),
    ("B  the array-of-pairs branch of _withTab", [
        ("static/js/api.js",
         "      && (h instanceof Headers || Array.isArray(h))) {",
         "      && h instanceof Headers) {")]),
    ("C  the Request-mutation shortcut (the init route should still carry it)", [
        ("static/js/api.js",
         "    if (isReq && (!init || init.headers == null)) {",
         "    if (false) {")]),
    ("D  the same-origin test in _isApiUrl", [
        ("static/js/api.js",
         "    return abs.origin === (here ? new URL(here).origin : 'http://localhost')\n"
         "           && abs.pathname.startsWith('/api/');",
         "    return abs.pathname.startsWith('/api/');")]),
]

FILES = ["tests/test_tab_header.py"]


def main():
    base = scratch()
    line, failed = run(base, FILES)
    print(f"BASELINE (no revert): {line}")
    if failed:
        print("  already red:", failed)
    shutil.rmtree(base, ignore_errors=True)
    print()
    for label, edits in REVERTS:
        t = scratch()
        try:
            for rel, old, new in edits:
                patch(t, rel, old, new)
            line, failed = run(t, FILES)
            print(f"{label}\n   {line}")
            for f in failed:
                print(f"   RED  {f}")
            if not failed:
                print("   (nothing went red — a positive control, not a guard)")
        finally:
            shutil.rmtree(t, ignore_errors=True)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
