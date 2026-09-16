"""Section 11 round three, PART A item 3 — the Spec dialog's seven boxes.

Round two made every number box refuse a value Number() cannot read.  Round
three has to answer three things by MEASUREMENT, not by reading:

  * does EVERY box refuse consistently, or only some of them?
  * does an EMPTY box still mean "no requirement", rather than a refusal?
  * can a requirement still be CLEARED on purpose?  (A guard that will not
    let the user remove a spec value is a new bug.)

The shipped static/js/dialogs.js is run in node against a fake DOM: its
neighbours are stubs, the handler is the real bytes.

Usage:  C:\\Python314\\python.exe probes/spec_dialog_boxes_probe.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"

STUBS = {
    "api.js": """
export const posted = [];
export function setBusy() {} export function clearBusy() {}
export function isBusy() { return false; }
export async function getJSON() { return {}; }
export async function postJSON(url, body) { posted.push([url, body]);
  return { ok: true, spec: (body && body.spec) || {}, spec_problems: [],
           features: [], active_tab: 't1', name: 'x' }; }
export function noteRecovery() { return false; }
export function noteArrival() { return false; }
""",
    "viewport.js": """
export function loadMesh() {} export function clearMesh() {}
export function cancelPlanePick() {}
""",
    "ask.js": "export async function askText() { return null; }\n",
    "icons.js": "export const OP_ICONS = {}; export const TOOL_NAMES = {};\n",
    "tool.js": """
export function cancelTool() {} export function uid(b) { return b + '1'; }
export function toolSessionOpen() { return false; }
""",
}

BOOT = r"""
const els = new Map();
const mk = id => ({ id, value: '', innerHTML: '', textContent: '',
  classList: { add() {}, remove() {} }, style: {}, offsetWidth: 0,
  querySelectorAll: () => [], showModal() { this.open = true; },
  close() { this.open = false; }, onsubmit: null, onclick: null, open: false });
globalThis.document = {
  getElementById: id => { if (!els.has(id)) els.set(id, mk(id)); return els.get(id); },
  querySelectorAll: () => [], addEventListener() {},
};
globalThis.window = { addEventListener() {} };
const { bus } = await import('./bus.js');
const { posted } = await import('./api.js');
const { initDialogs } = await import('./dialogs.js');
const said = [];
bus.on('msg', (_w, t) => said.push(t));
initDialogs();
const form = document.getElementById('specForm');

const BOXES = ['spN', 'spSym', 'spTip', 'spSX', 'spSY', 'spSZ', 'spTol', 'spHoles'];
async function submit(values) {
  for (const b of BOXES) document.getElementById(b).value = values[b] ?? '';
  const dlg = document.getElementById('specDialog');
  dlg.open = true;
  said.length = 0; posted.length = 0;
  await form.onsubmit({ submitter: { value: 'ok' }, preventDefault() {} });
  return { sent: posted.length ? posted[0][1].spec : null,
           refused: posted.length === 0, dialogStillOpen: dlg.open,
           said: said.slice() };
}

const out = [];
const add = (name, r) => out.push({ case: name, ...r });

// every box in turn, with a value Number() cannot read
const LABEL = { spN: 'solid bodies', spSym: 'symmetry', spTip: 'tip radius',
                spSX: 'size X', spSY: 'size Y', spSZ: 'size Z',
                spTol: 'tolerance', spHoles: 'holes' };
for (const b of BOXES) {
  add(`only ${b} = "two"`, await submit({ [b]: 'two', ...{} }));
}
add('all seven empty (no requirement at all)', await submit({}));
add('a full spec', await submit({ spN: '1', spSym: '2', spTip: '0.4',
  spSX: '60', spSY: '40', spSZ: '20', spTol: '0.05', spHoles: '{"4": 6}' }));
add('CLEARING n_solids on purpose (its box emptied)',
    await submit({ spSX: '60', spSY: '40', spSZ: '20' }));
add('clearing EVERYTHING on purpose', await submit({}));
add('a German decimal comma in tolerance', await submit({ spTol: '0,05' }));
add('1e999 in tip radius', await submit({ spTip: '1e999' }));
add('0 in n_solids (a real, meaningful value)', await submit({ spN: '0' }));
add('a negative tolerance', await submit({ spTol: '-0.05' }));
add('two boxes wrong at once', await submit({ spN: 'two', spTol: 'tight' }));
add('only size Y filled', await submit({ spSY: '40' }));
add('holes not JSON', await submit({ spHoles: '4:6' }));
console.log(JSON.stringify(out, null, 1));
"""


def main() -> int:
    if not shutil.which("node"):
        print("node is not on PATH")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="spec_boxes_"))
    for name in ("dialogs.js", "bus.js", "state.js"):
        shutil.copy(JS / name, tmp / name)
    for name, body in STUBS.items():
        (tmp / name).write_text(body, encoding="utf-8")
    (tmp / "boot.mjs").write_text(BOOT, encoding="utf-8")
    r = subprocess.run([shutil.which("node"), str(tmp / "boot.mjs")],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=str(tmp))
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        return 1
    for row in json.loads(r.stdout):
        print(f"{row['case']:<44} refused={str(row['refused']):<5} "
              f"open={str(row['dialogStillOpen']):<5} sent={json.dumps(row['sent'])}")
        for s in row["said"]:
            print(f"{'':<44}   {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
