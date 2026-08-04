// grid3d.js — the shared adaptive-grid builder for BOTH planes we draw on:
// the design tab's ground plane (viewport.js) and the sketch plane
// (sketch3d.js). Fusion's behavior, split into two independent rules:
//   * CELL SIZE follows the CAMERA: zooming in subdivides along a 1-2-5
//     ladder down to a floor, past which subdivision stops; zooming out
//     coarsens, capped so a finite plane always shows a few cells.
//   * PLANE SIZE follows the CONTENT: the plane is a finite plate (you can
//     find its edge by zooming out) that jumps to the NEXT ladder size when
//     the geometry outgrows it — never sized by how far the camera looks.
// This module is pure geometry: callers pick step/bounds/patch, it builds
// the line objects in the local XY plane.

import * as THREE from 'three';

export const MIN_CELL_PX = 10;   // a minor cell never renders narrower

/* the 1-2-5 ladder, decade-normalized: 1 → 2 → 5 → 10 → 20 → 50 → … */
export function nextStep125(s) {
  const e = Math.floor(Math.log10(s) + 1e-9);
  const m = s / 10 ** e;
  return (m < 1.5 ? 2 : m < 3.5 ? 5 : 10) * 10 ** e;
}

/* smallest ladder step ≥ floorMm whose cells are at least MIN_CELL_PX wide,
   capped (a finite plane keeps at least a few cells when far away) */
export function gridStepFor(pxPerMm, floorMm, maxStep) {
  let step = Math.max(floorMm, 0.01);
  while (step * pxPerMm < MIN_CELL_PX && nextStep125(step) <= maxStep)
    step = nextStep125(step);
  return step;
}

/* smallest ladder value ≥ need — the plane's half-extent "sizes" */
export function planeHalfFor(need) {
  let half = 10;
  while (half < need) half = nextStep125(half);
  return half;
}

/* Build the grid lines: minor + major (10x) + origin axes, all at absolute
   world-multiples of `step` (lines never swim when the patch moves), clipped
   to bounds ∩ patch. bounds = the finite plane; patch = what the camera can
   see (so a zoomed-in view never allocates lines it cannot show).
   colors: {minor, major, axes}. Returns a THREE.Group in the local XY plane. */
export function buildGridLines({ step, bounds, patch, colors, zLift = 0 }) {
  const g = new THREE.Group();
  const clip = {
    minX: Math.max(bounds.minX, patch.minX),
    maxX: Math.min(bounds.maxX, patch.maxX),
    minY: Math.max(bounds.minY, patch.minY),
    maxY: Math.min(bounds.maxY, patch.maxY),
  };
  if (clip.minX >= clip.maxX || clip.minY >= clip.maxY) return g;
  const major = step * 10;
  const isMajor = v => Math.abs(v / major - Math.round(v / major)) < 1e-6;
  const minorPts = [], majorPts = [];
  const x0 = Math.ceil(clip.minX / step - 1e-6) * step;
  for (let x = x0; x <= clip.maxX + 1e-6; x += step)
    (isMajor(x) ? majorPts : minorPts).push([x, clip.minY], [x, clip.maxY]);
  const y0 = Math.ceil(clip.minY / step - 1e-6) * step;
  for (let y = y0; y <= clip.maxY + 1e-6; y += step)
    (isMajor(y) ? majorPts : minorPts).push([clip.minX, y], [clip.maxX, y]);
  const seg = (pts, color, z) => {
    const geo = new THREE.BufferGeometry().setFromPoints(
      pts.map(p => new THREE.Vector3(p[0], p[1], z)));
    const l = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
      color, transparent: true, opacity: 0.8, depthWrite: false }));
    g.add(l);
  };
  if (minorPts.length) seg(minorPts, colors.minor, zLift);
  if (majorPts.length) seg(majorPts, colors.major, zLift + 0.004);
  // the plane's own axes through the origin, while the origin is in view
  const axPts = [];
  if (clip.minX <= 0 && 0 <= clip.maxX) axPts.push([0, clip.minY], [0, clip.maxY]);
  if (clip.minY <= 0 && 0 <= clip.maxY) axPts.push([clip.minX, 0], [clip.maxX, 0]);
  if (axPts.length) seg(axPts, colors.axes, zLift + 0.008);
  return g;
}

/* View footprint on a plane, ANCHORED at the view-centre ray's hit: the
   px/mm scale and the bbox are measured there, and corner hits are clamped
   to a screen-scale radius around it — at tilted views the horizon corners
   hit the plane hundreds of metres out, and a bbox centred on THAT reads a
   uselessly tiny px/mm (a coarse grid on a close-up view — a real bug the
   ground grid had at iso). Returns null when the view is (nearly) edge-on
   or looking away — callers keep their current grid.
   hitToLocal: world Vector3 -> {x,y} in the plane's 2D; pxPerMmAt: {x,y} ->
   screen px per mm at that point (null when unprojectable). */
const _ray = new THREE.Raycaster();
export function viewFootprintOn({ camera, dom, plane, hitToLocal, pxPerMmAt }) {
  const rect = dom.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  // a camera posed THIS frame (setView, tween) has a stale matrixWorld until
  // the next render — raycasting then reads the OLD pose and the grid built
  // for a view the user is no longer in (the boot grid was missing entirely)
  camera.updateMatrixWorld();
  _ray.setFromCamera(new THREE.Vector2(0, 0), camera);
  if (Math.abs(_ray.ray.direction.dot(plane.normal)) < 0.02) return null;
  const centre = new THREE.Vector3();
  if (!_ray.ray.intersectPlane(plane, centre)) return null;
  const anchor = hitToLocal(centre);
  const pxPerMm = pxPerMmAt(anchor);
  if (!pxPerMm) return null;
  const R = 0.75 * Math.hypot(rect.width, rect.height) / pxPerMm;
  let minX = anchor.x, maxX = anchor.x, minY = anchor.y, maxY = anchor.y;
  for (const [nx, ny] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
    _ray.setFromCamera(new THREE.Vector2(nx, ny), camera);
    const hit = new THREE.Vector3();
    let p = null;
    if (Math.abs(_ray.ray.direction.dot(plane.normal)) >= 0.02
        && _ray.ray.intersectPlane(plane, hit)) p = hitToLocal(hit);
    if (p) {                                 // clamp horizon-distance hits
      const dx = p.x - anchor.x, dy = p.y - anchor.y;
      const len = Math.hypot(dx, dy);
      const k = len > R ? R / len : 1;
      minX = Math.min(minX, anchor.x + dx * k);
      maxX = Math.max(maxX, anchor.x + dx * k);
      minY = Math.min(minY, anchor.y + dy * k);
      maxY = Math.max(maxY, anchor.y + dy * k);
    } else {                                 // over the horizon: full radius
      minX = Math.min(minX, anchor.x - R); maxX = Math.max(maxX, anchor.x + R);
      minY = Math.min(minY, anchor.y - R); maxY = Math.max(maxY, anchor.y + R);
    }
  }
  return { minX, maxX, minY, maxY, cx: anchor.x, cy: anchor.y, pxPerMm };
}

/* quantize a view footprint OUTWARD to major multiples (stable while the
   camera drifts), with a hard cap on the number of cells per axis */
export function patchFor(fp, step, maxCells = 260) {
  const major = step * 10;
  const capX = Math.min((fp.maxX - fp.minX) * 1.3, maxCells * step) / 2;
  const capY = Math.min((fp.maxY - fp.minY) * 1.3, maxCells * step) / 2;
  return {
    minX: Math.floor((fp.cx - capX) / major) * major,
    maxX: Math.ceil((fp.cx + capX) / major) * major,
    minY: Math.floor((fp.cy - capY) / major) * major,
    maxY: Math.ceil((fp.cy + capY) / major) * major,
  };
}
