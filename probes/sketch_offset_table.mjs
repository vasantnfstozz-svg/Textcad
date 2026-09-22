// PROBE (sketch-plane review round two, 2026-09-22): the `offset` table.
// The three functions below are LIFTED VERBATIM from static/js/sketcher.js by
// probes/sketch_offset_table.py, so this cannot drift from the shipped code.
// For each row: what editSketch reads, what create() writes, and whether
// sameSketch calls an untouched Finish a change.
let skOffsetRaw = 0;

function offsetParam(num) {
  return typeof skOffsetRaw === 'string' ? skOffsetRaw : num;
}

function stableJson(v) {
  if (Array.isArray(v)) return '[' + v.map(stableJson).join(',') + ']';
  if (v && typeof v === 'object')
    return '{' + Object.keys(v).sort().map(k =>
      JSON.stringify(k) + ':' + stableJson(v[k])).join(',') + '}';
  if (typeof v === 'number') return String(Number(v.toFixed(9)));
  return JSON.stringify(v);
}

function sameSketch(saved, next) {
  if (!saved) return false;
  if (stableJson(saved.entities || []) !== stableJson(next.entities || []))
    return false;
  if (next.plane !== undefined && saved.plane !== next.plane) return false;
  // the offset as WRITTEN, not as a number: a formula ("-wall") and the number
  // it happens to resolve to are not the same sketch — one of them survives a
  // change to the parameter and the other does not. stableJson makes -25 and
  // -25.0 the same place, as it does for every entity.
  if (next.offset !== undefined
      && stableJson(saved.offset ?? 0) !== stableJson(next.offset ?? 0)) return false;
  return true;
}

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
