// state.js — shared UI state. One place, so every module sees the same truth.

export const S = {
  lastDoc: null,          // the latest /api/doc payload
  selected: null,         // selected feature id in the tree
  openNodes: new Set(),   // expanded tree nodes
  OPS: [],                // /api/ops catalog (cached)
  pickedFace: null,       // last face picked in the viewport {center,normal,type,id}
};
