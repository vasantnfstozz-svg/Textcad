// icons.js — icons + display names for every operation. No dependencies, so
// any module (tree, ribbon, sketcher) can import it freely.

export const OP_ICONS = {
  plate: '▭', disc: '●', ball: '⚪', cone: '△', tube: '◎',
  polygon_plate: '⬡', hex_plate: '⬡',
  revolve_profile: '↻', curved_blade: '⤳', with_center_hole: '⊙',
  with_bolt_circle: '⁘', polar_pattern: '✳', move: '↗',
  rotate: '⟳', mirror: '⇋', scale: '⤢', linear_pattern: '⋯',
  fillet: '◠', chamfer: '◣', shell: '▢',
  fuse: '∪', cut: '−', intersect: '∩',
  sketch: '✎', extrude: '⬆', revolve: '↻', loft: '⏢', sweep: '〜',
  sketch_on_face: '✎',
};

export const TOOL_NAMES = {
  sketch: 'Sketch', extrude: 'Extrude', revolve: 'Revolve', loft: 'Loft',
  sweep: 'Sweep',
  plate: 'Plate', disc: 'Disc', ball: 'Ball', cone: 'Cone', tube: 'Tube',
  hex_plate: 'Hex', polygon_plate: 'Polygon', revolve_profile: 'Turn profile',
  curved_blade: 'Blade', with_center_hole: 'Hole',
  with_bolt_circle: 'Bolt circle', fillet: 'Fillet', chamfer: 'Chamfer',
  shell: 'Shell', move: 'Move', rotate: 'Rotate', scale: 'Scale',
  mirror: 'Mirror', polar_pattern: 'Polar', linear_pattern: 'Linear',
  fuse: 'Join', cut: 'Cut', intersect: 'Intersect',
};
