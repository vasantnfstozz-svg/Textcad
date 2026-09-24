// icons.js — icons + display names for every operation. No dependencies, so
// any module (tree, ribbon, sketcher) can import it freely.

export const OP_ICONS = {
  plate: '▭', disc: '●', ball: '⚪', cone: '△', tube: '◎',
  polygon_plate: '⬡', hex_plate: '⬡',
  revolve_profile: '↻', with_center_hole: '⊙',
  with_bolt_circle: '⁘', polar_pattern: '✳', move: '↗',
  rotate: '⟳', mirror: '⇋', scale: '⤢', linear_pattern: '⋯',
  fillet: '◠', chamfer: '◣', shell: '▢', hole: '◎',
  fuse: '∪', cut: '−', intersect: '∩',
  sketch: '✎', extrude: '⬆', revolve: '↻', loft: '⏢', sweep: '〜',
  sketch_on_face: '✎', extrude_face: '⬆', revolve_face: '↻', sweep_face: '〜', import_stl: '▲',
  import_step: '◈',
  offset_plane: '▱',                    // a construction plane (Fusion's Construct menu)
  // not an op: the Modify tab's router button (Fusion's Press Pull) — the
  // feature it makes is Extrude's or Fillet's, so no tree row ever carries it
  press_pull: '⇕',
};

export const TOOL_NAMES = {
  sketch: 'Sketch', extrude: 'Extrude', revolve: 'Revolve', loft: 'Loft',
  sweep: 'Sweep', extrude_face: 'Extrude face', revolve_face: 'Revolve face',
  sweep_face: 'Sweep face',
  // Fusion-style primitive names (op ids unchanged underneath: plate=box, etc.)
  plate: 'Box', disc: 'Cylinder', ball: 'Sphere', cone: 'Cone', tube: 'Pipe',
  hex_plate: 'Hex', polygon_plate: 'Polygon', revolve_profile: 'Turn profile',
  // `with_center_hole` bores the CENTRE of a body with no face and no
  // handles; the Hole TOOL (`hole`, Create tab) is the one the spec means.
  // Two buttons named "Hole" sent the user to the wrong one.
  with_center_hole: 'Centre bore',
  with_bolt_circle: 'Bolt circle', fillet: 'Fillet', chamfer: 'Chamfer', hole: 'Hole',
  shell: 'Shell', move: 'Move', rotate: 'Rotate', scale: 'Scale',
  mirror: 'Mirror', polar_pattern: 'Circular', linear_pattern: 'Rectangular',   // …Pattern (the group's name)
  fuse: 'Join', cut: 'Cut', intersect: 'Intersect',
  import_stl: 'Import STL', import_step: 'Import STEP',
  offset_plane: 'Offset Plane',
  press_pull: 'Press Pull',                 // Fusion's name; a router, see OP_ICONS
};
