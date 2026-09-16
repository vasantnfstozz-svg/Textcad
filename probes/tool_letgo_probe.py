"""Section 11 round three, PART A — does round two's let-go FALSE-FIRE?

Round two pinned its P0 fix with SOURCE-TEXT assertions plus a server test
that no tool request moves the active tab.  Neither of those runs tabMoved,
and tabMoved sits on the path of EVERY doc-updated in the app — every
rebuild, every write, every undo, every rename.  So this probe runs the
SHIPPED static/js/tool.js in node, with the real bus.js and state.js beside
it and stubbed api.js / viewport.js, opens a real session and fires the
doc-updated payloads the product actually produces.

Usage:  C:\\Python314\\python.exe probes/tool_letgo_probe.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"

API_STUB = """
export const calls = [];
export const said = [];
export function setBusy() {}
export function clearBusy() {}
export function isBusy() { return false; }
export async function getJSON(u) { calls.push([u]); return {}; }
export async function postJSON(url, body) {
  calls.push([url, body]);
  return { features: [], active_tab: 't3', name: 'bracket' };
}
export async function planRequest(req) {
  calls.push(['/api/tool/plan', req]);
  return { ok: true, input: 'plate1', target_body: 'plate1', edges: [] };
}
export function noteRecovery() { return false; }
export function noteArrival() { return false; }
"""

VIEWPORT_STUB = """
export const holdViewport = async fn => await fn();
export function cancelPlanePick() {}
export function beginProfilePick() {}
export function cancelProfilePick() {}
export function beginEdgePick() {}
export function endEdgePick() {}
export function clearPick() {}
export function pickWhat() { return 'a sketch'; }
export function profilePickArmed() { return false; }
export function loadMesh() {}
export function setExtrudeArrowAmount() {}
"""

# the bus stub records what the panel SAYS, then hands the event on to the
# real handlers — the real bus.js with one line of instrumentation is not
# honest enough, so the real bus is used and 'msg' is simply listened to.
BOOT = """
/* the browser globals tool.js touches AT IMPORT TIME (its Esc listener) */
const els = new Map();
globalThis.els = els;
globalThis.document = {
  getElementById: id => {
    if (!els.has(id)) els.set(id, {
      id, value: '', innerHTML: '', disabled: false, title: '',
      style: { display: 'none' }, options: [],
      firstElementChild: { textContent: '' },
      onchange: null, oninput: null, onclick: null });
    return els.get(id);
  },
  addEventListener() {},
};
globalThis.window = { addEventListener() {} };
const { bus } = await import('./bus.js');
const { said } = await import('./api.js');
bus.on('msg', (_who, text) => said.push(text));
await import('./probe.mjs');
"""


def main() -> int:
    if not shutil.which("node"):
        print("node is not on PATH")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="tool_letgo_"))
    for name in ("tool.js", "bus.js", "state.js"):
        shutil.copy(JS / name, tmp / name)
    (tmp / "api.js").write_text(API_STUB, encoding="utf-8")
    (tmp / "viewport.js").write_text(VIEWPORT_STUB, encoding="utf-8")
    shutil.copy(Path(__file__).parent / "js" / "tool_letgo_probe.mjs",
                tmp / "probe.mjs")
    (tmp / "boot.mjs").write_text(BOOT, encoding="utf-8")
    out = subprocess.run([shutil.which("node"), str(tmp / "boot.mjs")],
                         capture_output=True, text=True, encoding="utf-8",
                         cwd=str(tmp))
    if out.returncode != 0:
        print(out.stdout)
        print(out.stderr, file=sys.stderr)
        return 1
    rows = json.loads(out.stdout)
    bad = []
    for r in rows:
        mark = ""
        if r.get("letGo") is True:
            mark = "  <-- LET GO"
        print(f"{r['case']:<34} {json.dumps({k: v for k, v in r.items() if k != 'case'})}{mark}")
        if r.get("said"):
            for s in r["said"]:
                print(f"{'':<34}   \"{s}\"")
    # every case up to 'another design arrived' is the SAME design in front
    same_design = [r for r in rows[:8] if r.get("letGo")]
    if same_design:
        bad.append(f"FALSE FIRE on the same design: {[r['case'] for r in same_design]}")
    for note in bad:
        print("!!", note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
