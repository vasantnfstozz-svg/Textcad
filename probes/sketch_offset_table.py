"""The sketch `offset` table, run through the SHIPPED functions (sketch-plane
review round two, 2026-09-22).

`offsetParam`, `stableJson` and `sameSketch` are LIFTED VERBATIM out of
static/js/sketcher.js into probes/sketch_offset_table.mjs, so the probe cannot
drift from the code it is asking about. For each shape an `offset` can have,
it prints the number the editor DRAWS at, the value a Finish WRITES back, and
whether an untouched Finish is recognised as no change at all.

    python probes/sketch_offset_table.py
"""
import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
MJS = ROOT / "probes" / "sketch_offset_table.mjs"

HEAD = """// PROBE (sketch-plane review round two, 2026-09-22): the `offset` table.
// The three functions below are LIFTED VERBATIM from static/js/sketcher.js by
// probes/sketch_offset_table.py, so this cannot drift from the shipped code.
// For each row: what editSketch reads, what create() writes, and whether
// sameSketch calls an untouched Finish a change.
let skOffsetRaw = 0;

"""

TAIL = """

const rows = [
  ['a number',                 { offset: -25 },        {}],
  ['a number as a STRING',     { offset: '4' },        { offset: 4 }],
  ['-0',                       { offset: -0 },         {}],
  ['20.0',                     { offset: 20.0 },       {}],
  ['a formula',                { offset: '-wall' },    { offset: -4 }],
  ['a formula that FAILS',     { offset: '-wal' },     { offset: null }],
  ['no offset key at all',     {},                     {}],
  ['offset: null',             { offset: null },       {}],
  ['no `resolved` at all',     { offset: '-wall' },    null],
];
const out = [];
for (const [what, params, resolved] of rows) {
  const feature = { params, ...(resolved ? { resolved } : {}) };
  // the two expressions editSketch reads the offset with
  const rawOffset = feature.params.offset ?? 0;
  const offNum = Number(feature.resolved?.offset ?? rawOffset) || 0;
  skOffsetRaw = rawOffset;
  const written = offsetParam(offNum);          // what a face-sketch Finish writes
  const noop = sameSketch(params, { entities: [], offset: written });
  out.push({ what, drawnAt: offNum, written, untouchedFinishWritesNothing: noop });
}
console.log(JSON.stringify(out, null, 1));
"""


def lift(src: str, name: str) -> str:
    """The whole text of `function name(...) {...}`, braces balanced."""
    i = src.index(f"function {name}(")
    k = src.index("{", i)
    depth = 0
    while True:
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    return src[i:k + 1]


def main() -> None:
    src = (ROOT / "static" / "js" / "sketcher.js").read_text(encoding="utf-8")
    body = "\n\n".join(lift(src, n) for n in
                       ("offsetParam", "stableJson", "sameSketch"))
    MJS.write_text(HEAD + body + TAIL, encoding="utf-8")
    node = shutil.which("node")
    if not node:
        print("node is not on PATH")
        return
    r = subprocess.run([node, str(MJS)], capture_output=True, text=True)
    print(r.stdout or r.stderr)
    for row in json.loads(r.stdout or "[]"):
        if not row["untouchedFinishWritesNothing"]:
            print("!! an untouched Finish would WRITE for:", row["what"])


if __name__ == "__main__":
    main()
