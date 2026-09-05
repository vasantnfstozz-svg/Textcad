// state.js — shared UI state. One place, so every module sees the same truth.

export const S = {
  lastDoc: null,          // the latest /api/doc payload
  selected: null,         // selected feature id in the tree
  openNodes: new Set(),   // expanded tree nodes
  OPS: [],                // /api/ops catalog (cached)
  pickedFace: null,       // last face picked in the viewport {center,normal,type,id}
  // ONE COMMAND AT A TIME (user mandate 2026-08-05): while a tool's panel is
  // open, every other design tool refuses until OK/Cancel. The open tool sets
  // these; dialogs.modalGuard() enforces them everywhere.
  modalTool: null,        // e.g. 'Extrude' while its panel is open
  modalToolPanel: null,   // element id of the open panel (flashed on refusal)
  recoveredAt: null,      // the server crash note already spoken (its timestamp)
};
