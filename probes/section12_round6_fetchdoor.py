"""Section 12 round SIX — hammer the input handling of round five's fetch door.

Round five (66d80c1) wrapped globalThis.fetch so that every same-origin /api/
request the page makes carries X-TextCAD-Tab. The wrapper's whole gate is

    if (typeof input !== 'string' || !input.startsWith('/api/')) pass through

which is a FAIL-OPEN: anything that is not a plain, root-relative string goes
to the network with NO header, and the server then falls back to whatever tab
is globally active — the exact hole round five closed for /api/model.

This probe RUNS the shipped module in node (the pattern tests/test_tab_header.py
already uses) and asks, for each shape of input a real caller can produce,
whether the header actually goes out. It writes nothing and starts no server.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"
API = json.dumps((JS / "api.js").as_uri())
STATE = json.dumps((JS / "state.js").as_uri())


def node(source: str):
    with tempfile.TemporaryDirectory() as td:
        h = pathlib.Path(td) / "h.mjs"
        h.write_text(source, encoding="utf-8")
        out = subprocess.run([shutil.which("node"), str(h)],
                             capture_output=True, text=True,
                             encoding="utf-8", cwd=td)
        if out.returncode != 0:
            raise SystemExit(out.stderr)
        return json.loads(out.stdout.strip())


HARNESS = """
globalThis.document = { getElementById: () => ({ style: {}, textContent: '' }) };
// the page's own origin, as the browser would have it
globalThis.location = { href: 'http://127.0.0.1:8123/', origin: 'http://127.0.0.1:8123' };
const seen = [];
globalThis.fetch = async (input, init) => {
  let url = typeof input === 'string' ? input : String(input && input.url || input);
  let hdr = null;
  const H = 'X-TextCAD-Tab';
  if (init && init.headers) {
    const h = init.headers;
    if (typeof Headers !== 'undefined' && h instanceof Headers) hdr = h.get(H);
    else if (Array.isArray(h)) { const p = h.find(x => String(x[0]).toLowerCase() === H.toLowerCase()); hdr = p ? p[1] : null; }
    else { for (const k of Object.keys(h)) if (k.toLowerCase() === H.toLowerCase()) hdr = h[k]; }
  }
  if (hdr == null && typeof Request !== 'undefined' && input instanceof Request) hdr = input.headers.get(H);
  // what ELSE survived: the content type and the body, which a POST needs
  let ct = null;
  if (init && init.headers) {
    const h = init.headers;
    if (typeof Headers !== 'undefined' && h instanceof Headers) ct = h.get('Content-Type');
    else if (Array.isArray(h)) { const p = h.find(x => String(x[0]).toLowerCase() === 'content-type'); ct = p ? p[1] : null; }
    else { for (const k of Object.keys(h)) if (k.toLowerCase() === 'content-type') ct = h[k]; }
  }
  seen.push({ url, tab: hdr, ct,
              method: (init && init.method) || (input && input.method) || null,
              body: init ? (init.body === undefined ? null : String(init.body)) : null,
              signal: !!(init && init.signal),
              keepalive: !!(init && init.keepalive) });
  return { ok: true, status: 200, json: async () => ({}), arrayBuffer: async () => new ArrayBuffer(0) };
};
const api = await import(API_URL);
const { S } = await import(STATE_URL);
S.lastDoc = { active_tab: 't7' };
CASES
console.log(JSON.stringify(seen));
"""


def run(cases: str):
    return node(HARNESS.replace("API_URL", API)
                       .replace("STATE_URL", STATE)
                       .replace("CASES", cases))


def main():
    print("=" * 72)
    print("A. the shapes of input a real caller produces")
    print("=" * 72)
    cases = """
// 1. three.js r160 FileLoader: fetch(new Request(url, {headers, credentials}))
//    In the browser the Request resolves '/api/...' against the page, so
//    req.url is ALWAYS the absolute same-origin URL — which is what node
//    requires here anyway.
await fetch(new Request('http://127.0.0.1:8123/api/feature-mesh/f3.stl',
    { headers: new Headers({}), credentials: 'same-origin' }));
// 2. a URL object
await fetch(new URL('/api/doc', 'http://127.0.0.1:8123'));
// 3. an absolute same-origin string
await fetch('http://127.0.0.1:8123/api/doc');
// 4. a relative path that is not root-relative
await fetch('api/doc');
// 5. the plain form the wrapper was written for (the control)
await fetch('/api/model?t=1');
// 6. a non-/api path (must NOT carry it)
await fetch('/static/js/main.js');
// 7. CROSS-ORIGIN /api/ — the tab id must never leave this server
await fetch('https://example.com/api/doc');
// 8. protocol-relative, also cross-origin
await fetch('//example.com/api/doc');
// 9. a Request for a non-/api path
await fetch(new Request('http://127.0.0.1:8123/static/js/main.js'));
"""
    got = run(cases)
    names = ["Request object (three.js loader)", "URL object",
             "absolute same-origin string", "relative 'api/doc'",
             "plain '/api/model' (control)", "/static/ (control: none)",
             "cross-origin /api/ (control: none)",
             "protocol-relative (control: none)",
             "Request for /static/ (control: none)"]
    for n, g in zip(names, got):
        mark = "OK " if (g["tab"] == "t7") else "NO "
        if n.endswith("none)"):
            mark = "OK " if g["tab"] is None else "NO "
        print(f"  {mark} {n:42s} url={g['url']:38s} tab={g['tab']}")

    print()
    print("=" * 72)
    print("B. init shapes on a path the wrapper DOES claim ('/api/...')")
    print("=" * 72)
    cases = """
// headers as a Headers instance
await fetch('/api/x', { method: 'POST', headers: new Headers({ 'Content-Type': 'application/json' }), body: '{}' });
// headers as an ARRAY OF PAIRS — a legal fetch init
await fetch('/api/y', { method: 'POST', headers: [['Content-Type', 'application/json']], body: '{}' });
// a frozen init
await fetch('/api/z', Object.freeze({ method: 'POST', headers: Object.freeze({ 'Content-Type': 'application/json' }), body: '{}' }));
// init carrying signal / keepalive
const ac = new AbortController();
await fetch('/api/s', { signal: ac.signal, keepalive: true });
// init absent, and init null
await fetch('/api/n1');
await fetch('/api/n2', null);
"""
    got = run(cases)
    names = ["headers: Headers", "headers: array of pairs", "frozen init",
             "signal + keepalive", "no init", "init null"]
    for n, g in zip(names, got):
        print(f"  {n:26s} tab={str(g['tab']):6s} content-type={str(g['ct']):18s} "
              f"body={str(g['body']):5s} signal={g['signal']} keepalive={g['keepalive']}")

    print()
    print("=" * 72)
    print("C. is the door installed once? (a second import must not re-wrap)")
    print("=" * 72)
    out = node(f"""
globalThis.document = {{ getElementById: () => ({{ style: {{}}, textContent: '' }}) }};
let depth = 0;
globalThis.fetch = async (u, o) => {{ depth++; return {{ ok: true, json: async () => ({{}}) }}; }};
await import({API});
const before = globalThis.fetch;
await import({API} + '?again=1');
const {{ S }} = await import({STATE});
S.lastDoc = {{ active_tab: 't7' }};
await fetch('/api/doc');
console.log(JSON.stringify({{ rewrapped: before !== globalThis.fetch, rawCalls: depth }}));
""")
    print(f"  re-import re-wrapped the door: {out['rewrapped']}  "
          f"raw fetch reached {out['rawCalls']} time(s) for one call")

    print()
    print("=" * 72)
    print("D. which STL loader calls exist, and do they carry a tab?")
    print("=" * 72)
    vp = (ROOT / "static" / "js" / "viewport.js").read_text(encoding="utf-8")
    for i, line in enumerate(vp.splitlines(), 1):
        if "STLLoader" in line and "loadAsync" in line.replace(" ", ""):
            print(f"  viewport.js:{i}: {line.strip()}")
    three = (ROOT / "static" / "vendor" / "three" / "0.160.0"
             / "three.module.js").read_text(encoding="utf-8")
    print("  three r160 FileLoader transport: "
          f"{'new Request(...) + fetch(req)' if 'const req = new Request(' in three else 'unknown'}"
          f"; XMLHttpRequest present: {'XMLHttpRequest' in three}")

    print()
    print("=" * 72)
    print("E. does /api/feature-mesh honour the header, and what does a")
    print("   headerless load get while ANOTHER tab is the active one?")
    print("=" * 72)
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient  # noqa: PLC0415

    import studio  # noqa: PLC0415
    c = TestClient(studio.app)
    mine = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/feature/add", json={
        "id": "base", "op": "plate", "inputs": [],
        "params": {"width": 20, "depth": 20, "thickness": 5}})
    other = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/feature/add", json={
        "id": "base", "op": "plate", "inputs": [],
        "params": {"width": 60, "depth": 60, "thickness": 30}})
    # exactly what a second browser window (or a doorbell) leaves behind:
    # the page is on `mine`, the server's active tab is `other`
    assert studio.STATE["active"] == other

    def bbox(body: bytes):
        """The STL's own bounding box, read from the binary triangles."""
        import struct  # noqa: PLC0415
        n = struct.unpack("<I", body[80:84])[0]
        lo = [1e30] * 3
        hi = [-1e30] * 3
        for i in range(n):
            off = 84 + i * 50 + 12
            for v in range(3):
                p = struct.unpack("<3f", body[off + v * 12:off + v * 12 + 12])
                for k in range(3):
                    lo[k] = min(lo[k], p[k])
                    hi[k] = max(hi[k], p[k])
        return [round(hi[k] - lo[k], 3) for k in range(3)]

    with_h = c.get("/api/feature-mesh/base.stl",
                   headers={"X-TextCAD-Tab": mine})
    without = c.get("/api/feature-mesh/base.stl")          # the loader's call
    print(f"  the page is on {mine}; STATE['active'] is {other}")
    print(f"  WITH    the header: {with_h.status_code} "
          f"{len(with_h.content)} bytes  bbox={bbox(with_h.content)}")
    print(f"  WITHOUT the header: {without.status_code} "
          f"{len(without.content)} bytes  bbox={bbox(without.content)}")
    print("  -> same design: "
          f"{bbox(with_h.content) == bbox(without.content)}")

    # and /api/model, which round five DID fix, for contrast
    m_with = c.get("/api/model", headers={"X-TextCAD-Tab": mine}).json()
    m_none = c.get("/api/model").json()
    print(f"  /api/model WITH header  -> active_tab-equivalent body count "
          f"{len(m_with.get('bodies', []))}, "
          f"first body id {m_with['bodies'][0]['id'] if m_with.get('bodies') else None}")
    print(f"  (the wrapper always sends the header on /api/model — "
          f"headerless would give {len(m_none.get('bodies', []))} bodies of "
          f"the OTHER design)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
