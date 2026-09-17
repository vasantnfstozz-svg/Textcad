"""Review probe for 15eff19 / 6aa8ec3 / eed6a33 — the REQUIRED sentinel, the
plain_cause translations and the pattern kind gate. Measurement only, no
kernel work beyond one plate.

Run:  C:\\Python314\\python.exe probes/s10_required_review_probe.py
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import author                              # noqa: E402
import blocks                              # noqa: E402
import document                            # noqa: E402
from document import (CREATORS, MODIFIERS, KNOWN_OPS, REQUIRED,  # noqa: E402
                      op_params, required_params)


def hdr(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


# --- §1 census: every op's signature vs what op_params claims ----------------
hdr("§1 signature census — kinds, required, defaults that ARE None")
odd = []
for op in sorted(KNOWN_OPS):
    fn = CREATORS.get(op) or MODIFIERS.get(op)
    if fn is None:
        print(f"{op:16s} (no function — 'move')  required={required_params(op)}")
        continue
    sig = list(inspect.signature(fn).parameters.values())
    kinds = {p.name: p.kind.name for p in sig}
    var = [n for n, k in kinds.items() if k in ("VAR_POSITIONAL", "VAR_KEYWORD")]
    kwonly = [n for n, k in kinds.items() if k == "KEYWORD_ONLY"]
    req = required_params(op)
    none_def = [n for n, d in op_params(op) if d is None]
    print(f"{op:16s} required={req}")
    if var:
        print(f"{'':16s}   *args/**kwargs: {var}")
        odd.append((op, "var", var))
    if kwonly:
        print(f"{'':16s}   keyword-only:   {kwonly}")
        odd.append((op, "kwonly", kwonly))
    if none_def:
        print(f"{'':16s}   default IS None: {none_def}")
print(f"\nops with a required parameter: {sum(1 for o in KNOWN_OPS if required_params(o))} of {len(KNOWN_OPS)}")
print("odd signatures:", odd or "none")


# --- §2 can the sentinel escape? --------------------------------------------
hdr("§2 does REQUIRED reach JSON")
cat = author.op_catalog()
blob = json.dumps(cat)
print("op_catalog json ok, len", len(blob))
print("'REQUIRED' literal in the json:", "REQUIRED" in blob)
# and the MCP doorbell's shape
import mcp_server                            # noqa: E402
try:
    payload = {"operations": author.op_catalog()}
    json.dumps(payload)
    print("mcp payload json ok")
except Exception as e:                        # pragma: no cover
    print("MCP JSON FAILS:", e)
print("mcp_server has op_catalog at", mcp_server.__file__ is not None)


# --- §3 the catalogue text ---------------------------------------------------
hdr("§3 _catalog_text lines")
txt = author._catalog_text()
for line in txt.splitlines():
    print(line)


# --- §4 plain_cause: does the translation fire on OUR OWN bug? --------------
hdr("§4 plain_cause on TypeErrors raised INSIDE an op")


def _inner_helper(a, b):
    return a + b


def _inner_kw(a, *, mode):
    return a


cases = []


def grab(fn, *a, **k):
    try:
        fn(*a, **k)
    except TypeError as e:
        cases.append((str(e), blocks.plain_cause(e)))


grab(_inner_helper, 1)                       # our own bug: missing positional
grab(_inner_kw, 1)                           # our own bug: missing kw-only
grab(_inner_helper, 1, 2, c=3)               # our own bug: unexpected keyword


class _Thing:
    def method(self, a, b):
        return a


grab(_Thing().method, 1)                     # qualified name -> should NOT match
try:
    import build123d as b3d
    b3d.Box(10, 10)
except TypeError as e:
    cases.append((str(e), blocks.plain_cause(e)))
try:
    b3d.extrude(None, amount=1, nope=2)
except TypeError as e:
    cases.append((str(e), blocks.plain_cause(e)))

for raw, out in cases:
    flag = "  <-- TRANSLATED" if not out.startswith("TypeError") else ""
    print(f"raw : {raw}\nsaid: {out}{flag}\n")


# --- §5 plural wording -------------------------------------------------------
hdr("§5 plural wording for 1, 2, 3 and 4 missing parameters")
import re                                    # noqa: E402


def _f1(a):
    pass


def _f2(a, b):
    pass


def _f3(a, b, c):
    pass


def _f4(a, b, c, d):
    pass


for fn in (_f1, _f2, _f3, _f4):
    try:
        fn()
    except TypeError as e:
        print(f"{str(e)!r}\n  -> {blocks.plain_cause(e)}")
print("re module used:", bool(re))
