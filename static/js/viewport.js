// viewport.js — the 3D view: scene, camera, model loading (face-tagged mesh
// from /api/model), view buttons, and face/edge picking with the info panel.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { bus } from './bus.js';
import { S } from './state.js';

let scene, camera, renderer, controls;
let mesh = null;                 // the body
const edgeLines = [];            // crisp OCCT topology edges
const sketchObjs = [];           // floating 2D sketch profiles (Fusion-style)
const ghostObjs = [];            // other unconsumed solid bodies (translucent)
let hlMesh = null;               // orange overlay for a tree-selected feature
let pickHl = null;               // orange overlay for a picked face/edge
let MODEL = null;                // /api/model payload (faceId, faces, edges)
let fitRadius = 100;
const fitCenter = new THREE.Vector3();
let pickMode = false;
let placeCb = null;              // when set, the next viewport click places a shape
let planePickCb = null;          // when set, click an origin plane / face to sketch on
const originPlanes = [];         // the 3 clickable origin planes during plane-pick
let exArrow = null;              // the draggable Extrude manipulator arrow
const raycaster = new THREE.Raycaster();
const GROUND = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);   // Z=0 workplane

export function initViewport() {
  const pane = document.getElementById('viewer');
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f1115);
  camera = new THREE.PerspectiveCamera(50, 1, 0.1, 8000);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  pane.appendChild(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.12;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x223, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 1.5);
  key.position.set(1, -1, 2); scene.add(key);
  const rim = new THREE.DirectionalLight(0x88bbff, 0.5);
  rim.position.set(-2, 2, -1); scene.add(rim);
  const grid = new THREE.GridHelper(400, 40, 0x2b303c, 0x1b1f28);
  grid.rotation.x = Math.PI / 2; scene.add(grid);

  const resize = () => {
    camera.aspect = pane.clientWidth / pane.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(pane.clientWidth, pane.clientHeight);
  };
  new ResizeObserver(resize).observe(pane);
  (function animate() { requestAnimationFrame(animate);
    controls.update(); renderer.render(scene, camera); })();

  document.getElementById('vFit').onclick = () => setView('iso');
  document.getElementById('vTop').onclick = () => setView('top');
  document.getElementById('vFront').onclick = () => setView('front');
  document.getElementById('vIso').onclick = () => setView('iso');
  document.getElementById('vSelect').onclick = e => {
    pickMode = !pickMode;
    e.target.classList.toggle('on', pickMode);
    renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
    if (!pickMode) clearPick();
  };

  let downXY = null;
  renderer.domElement.addEventListener('pointerdown',
    e => downXY = [e.clientX, e.clientY]);
  renderer.domElement.addEventListener('pointerup', e => {
    if (!downXY) return;
    const moved = Math.hypot(e.clientX - downXY[0], e.clientY - downXY[1]);
    downXY = null;
    if (moved > 5) return;                 // that was an orbit-drag
    if (planePickCb) { planePickAt(e); return; }
    if (placeCb) { placeGround(e); return; }
    if (pickMode) pickAt(e);
  });
  renderer.domElement.addEventListener('pointermove', e => {
    if (planePickCb) planePickHover(e);
  });
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape' && placeCb) cancelPlacement();
    if (e.key === 'Escape' && planePickCb) endPlanePick();
  });

  // Extrude arrow drag — capture phase so we grab it BEFORE OrbitControls,
  // then disable orbit for the drag. Move/up on window so the drag survives
  // the pointer leaving the canvas.
  renderer.domElement.addEventListener('pointerdown', e => {
    if (exArrow && !exArrow.dragging && arrowGrab(e)) e.stopPropagation();
  }, true);
  window.addEventListener('pointermove', e => { if (exArrow && exArrow.dragging) arrowDrag(e); });
  window.addEventListener('pointerup', e => { if (exArrow && exArrow.dragging) arrowRelease(e); });
}

/* ---------------- click-to-place on the Z=0 ground plane ---------------- */

export function beginPlacement(label, onPlace) {
  placeCb = onPlace;
  renderer.domElement.style.cursor = 'crosshair';
  const h = document.getElementById('placeHint');
  h.textContent = `Click a point on the ground to place the ${label} · Esc to cancel`;
  h.style.display = 'block';
}

export function cancelPlacement() {
  placeCb = null;
  renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
  document.getElementById('placeHint').style.display = 'none';
}

function placeGround(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const hit = new THREE.Vector3();
  const cb = placeCb;
  cancelPlacement();
  if (raycaster.ray.intersectPlane(GROUND, hit)) {
    cb(Math.round(hit.x * 100) / 100, Math.round(hit.y * 100) / 100);
  } else {
    cb(0, 0);                              // ray parallel to ground — fall back
  }
}

/* ---------------- pick a plane (or planar face) to sketch on (Fusion) ------- */

export function beginPlanePick(onPick) {
  planePickCb = onPick;
  renderer.domElement.style.cursor = 'pointer';
  const h = document.getElementById('placeHint');
  h.textContent = 'Select a plane or planar face · Esc to cancel';
  h.style.display = 'block';
  buildOriginPlanes();
}

function endPlanePick() {
  planePickCb = null;
  renderer.domElement.style.cursor = pickMode ? 'crosshair' : '';
  document.getElementById('placeHint').style.display = 'none';
  clearOriginPlanes();
}

function makeLabelSprite(text, color) {
  const c = document.createElement('canvas'); c.width = 128; c.height = 72;
  const ctx = c.getContext('2d');
  ctx.font = 'bold 44px Segoe UI, Arial, sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = '#' + color.toString(16).padStart(6, '0');
  ctx.fillText(text, 64, 38);
  const tex = new THREE.CanvasTexture(c);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex,
    transparent: true, depthTest: false }));
  const h = Math.max(fitRadius * 0.32, 16);
  sp.scale.set(h * (128 / 72), h, 1);
  sp.renderOrder = 1000;
  return sp;
}

function buildOriginPlanes() {
  clearOriginPlanes();
  const s = Math.max(fitRadius * 1.15, 55);      // half-size of each plane quad
  const defs = [
    { plane: 'XY', rot: [0, 0, 0], color: 0x4d7fff, lpos: [s * 0.72, s * 0.72, 0] },
    { plane: 'XZ', rot: [Math.PI / 2, 0, 0], color: 0x43c579, lpos: [s * 0.72, 0, s * 0.72] },
    { plane: 'YZ', rot: [0, Math.PI / 2, 0], color: 0xff6b6b, lpos: [0, s * 0.72, s * 0.72] },
  ];
  for (const d of defs) {
    const geo = new THREE.PlaneGeometry(2 * s, 2 * s);
    const mat = new THREE.MeshBasicMaterial({ color: d.color, transparent: true,
      opacity: 0.16, side: THREE.DoubleSide, depthWrite: false });
    const m = new THREE.Mesh(geo, mat);
    m.rotation.set(...d.rot);
    m.position.copy(fitCenter);
    m.userData.plane = d.plane; m.userData.base = 0.16;
    m.renderOrder = 998;
    scene.add(m); originPlanes.push(m);
    const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: d.color, transparent: true, opacity: 0.6 }));
    edge.rotation.set(...d.rot); edge.position.copy(fitCenter);
    edge.renderOrder = 999; scene.add(edge); originPlanes.push(edge);
    const label = makeLabelSprite(d.plane, d.color);
    label.position.set(fitCenter.x + d.lpos[0], fitCenter.y + d.lpos[1],
                       fitCenter.z + d.lpos[2]);
    scene.add(label); originPlanes.push(label);
  }
}

function clearOriginPlanes() {
  for (const o of originPlanes) {
    scene.remove(o);
    if (o.geometry) o.geometry.dispose();
    if (o.material && o.material.map) o.material.map.dispose();
  }
  originPlanes.length = 0;
}

function ndcFrom(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  return new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
}

function planePickHover(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const quads = originPlanes.filter(o => o.userData.plane);
  const hit = raycaster.intersectObjects(quads, false)[0];
  for (const q of quads) q.material.opacity = q.userData.base;
  renderer.domElement.style.cursor = 'pointer';
  if (hit) { hit.object.material.opacity = 0.4; }
  else if (mesh && raycaster.intersectObject(mesh, false).length)
    renderer.domElement.style.cursor = 'crosshair';   // hovering a face
}

function planePickAt(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const quads = originPlanes.filter(o => o.userData.plane);
  const pHit = raycaster.intersectObjects(quads, false)[0];
  const fHit = mesh ? raycaster.intersectObject(mesh, false)[0] : null;
  const cb = planePickCb;
  // a planar face closer than the plane quad wins (you clicked the solid)
  if (fHit && (!pHit || fHit.distance < pHit.distance - 1e-3) && MODEL) {
    const fid = MODEL.faceId[fHit.face.a];
    const info = MODEL.faces.find(f => f.id === fid);
    if (info && info.type === 'PLANE' && info.center) {
      endPlanePick(); cb('face', info); return;
    }
  }
  if (pHit) { const pl = pHit.object.userData.plane; endPlanePick(); cb('plane', pl); return; }
  // clicked empty space — keep waiting (don't cancel)
}

/* ---------------- draggable Extrude arrow (Fusion-style) ---------------- */

export function beginExtrudeArrow(originArr, normalArr, amount, onChange, onCommit) {
  endExtrudeArrow();
  const O = new THREE.Vector3(...originArr);
  const N = new THREE.Vector3(...normalArr).normalize();
  const arrow = new THREE.ArrowHelper(N, O, 1, 0xffb85c);
  for (const m of [arrow.line.material, arrow.cone.material]) {
    m.depthTest = false; m.transparent = true;      // always visible, on top of the solid
  }
  arrow.line.renderOrder = 1002; arrow.cone.renderOrder = 1002;
  arrow.renderOrder = 1001;
  const hit = new THREE.Mesh(                    // fat invisible grab cylinder
    new THREE.CylinderGeometry(Math.max(fitRadius * 0.05, 3),
                               Math.max(fitRadius * 0.05, 3), 1, 10),
    new THREE.MeshBasicMaterial({ visible: false }));
  scene.add(arrow); scene.add(hit);
  exArrow = { arrow, hit, O, N, amount: amount || 1, onChange, onCommit,
              dragging: false, grab: 0 };
  updateArrow();
}

export function endExtrudeArrow() {
  if (!exArrow) return;
  scene.remove(exArrow.arrow); scene.remove(exArrow.hit);
  exArrow.hit.geometry.dispose();
  exArrow = null;
}

export function hasExtrudeArrow() { return !!exArrow; }

/* keep the arrow in sync when the distance is typed in the value box */
export function setExtrudeArrowAmount(a) {
  if (exArrow && !exArrow.dragging) { exArrow.amount = a; updateArrow(); }
}

/* screen (client) coords of the arrow tip — for driving/aiming the drag */
export function extrudeArrowTipScreen() {
  if (!exArrow) return null;
  const a = exArrow.amount;
  const dir = a >= 0 ? exArrow.N : exArrow.N.clone().negate();
  const tip = exArrow.O.clone().add(dir.clone().multiplyScalar(Math.max(Math.abs(a), 0.5)));
  const v = tip.project(camera);
  const r = renderer.domElement.getBoundingClientRect();
  return { x: r.left + (v.x * 0.5 + 0.5) * r.width,
           y: r.top + (-v.y * 0.5 + 0.5) * r.height };
}

function updateArrow() {
  const a = exArrow.amount;
  const len = Math.max(Math.abs(a), 0.5);
  const dir = a >= 0 ? exArrow.N : exArrow.N.clone().negate();
  const head = Math.min(len * 0.32, Math.max(fitRadius * 0.14, 6));
  exArrow.arrow.setDirection(dir);
  exArrow.arrow.setLength(len, head, head * 0.62);
  const mid = exArrow.O.clone().add(dir.clone().multiplyScalar(len / 2));
  exArrow.hit.position.copy(mid);
  exArrow.hit.scale.set(1, len, 1);
  exArrow.hit.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
}

/* signed distance along the axis (O + s·N) nearest to the pointer ray */
function projectAmount(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  const rp = raycaster.ray.origin, rd = raycaster.ray.direction;
  const r = new THREE.Vector3().subVectors(exArrow.O, rp);
  const b = exArrow.N.dot(rd), c = rd.dot(rd);
  const d = exArrow.N.dot(r), ee = rd.dot(r);
  const denom = c - b * b;                        // a = N·N = 1
  if (Math.abs(denom) < 1e-6) return exArrow.amount;
  return (b * ee - c * d) / denom;
}

function arrowGrab(e) {
  raycaster.setFromCamera(ndcFrom(e), camera);
  if (!raycaster.intersectObject(exArrow.hit, false).length) return false;
  exArrow.dragging = true;
  controls.enabled = false;
  exArrow.grab = exArrow.amount - projectAmount(e);
  return true;
}

function arrowDrag(e) {
  exArrow.amount = projectAmount(e) + exArrow.grab;
  updateArrow();
  exArrow.onChange(exArrow.amount);
}

function arrowRelease() {
  exArrow.dragging = false;
  controls.enabled = true;
  exArrow.onCommit(exArrow.amount);
}

export function setView(dir) {
  const d = fitRadius * 2.4, c = fitCenter;
  const views = {
    iso:   [c.x + d * 0.7, c.y - d * 0.7, c.z + d * 0.55],
    top:   [c.x, c.y, c.z + d],
    front: [c.x, c.y - d, c.z + d * 0.001],
  };
  camera.position.set(...views[dir]); controls.target.copy(c);
}

function disposeModel() {
  if (mesh) { scene.remove(mesh); mesh.geometry.dispose(); mesh = null; }
  for (const l of edgeLines) { scene.remove(l); l.geometry.dispose(); }
  edgeLines.length = 0;
  for (const o of sketchObjs) { scene.remove(o); o.geometry.dispose(); }
  sketchObjs.length = 0;
  for (const o of ghostObjs) { scene.remove(o); o.geometry.dispose(); }
  ghostObjs.length = 0;
  clearPickHighlight();
}

function addBodies(bodies) {
  // other unconsumed solid bodies — shown translucent so positioning a second
  // body (before it is fused/cut) is not blind. Not pickable.
  for (const b of bodies || []) {
    if (!b.positions || !b.positions.length) continue;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(b.positions, 3));
    g.setIndex(b.indices);
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
      color: 0x8aa0b8, metalness: 0.1, roughness: 0.6, transparent: true,
      opacity: 0.32, depthWrite: false }));
    scene.add(m); ghostObjs.push(m);
    const eg = new THREE.EdgesGeometry(g, 25);
    const el = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({
      color: 0x6b7f96, transparent: true, opacity: 0.5 }));
    scene.add(el); ghostObjs.push(el);
  }
}

function addSketches(sketches) {
  for (const s of sketches || []) {
    if (s.positions.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position',
        new THREE.Float32BufferAttribute(s.positions, 3));
      g.setIndex(s.indices);
      g.computeVertexNormals();
      const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
        color: 0x43c579, transparent: true, opacity: 0.18,
        side: THREE.DoubleSide, depthWrite: false }));
      scene.add(m); sketchObjs.push(m);
    }
    for (const line of s.outlines || []) {
      const g = new THREE.BufferGeometry().setFromPoints(
        line.map(p => new THREE.Vector3(p[0], p[1], p[2])));
      const l = new THREE.Line(g, new THREE.LineBasicMaterial({
        color: 0x43c579 }));
      scene.add(l); sketchObjs.push(l);
    }
  }
}

export async function loadMesh(fit = false) {
  clearHighlight(); clearPick();
  try {
    const m = await (await fetch('/api/model?t=' + Date.now())).json();
    disposeModel();
    addSketches(m.sketches);
    addBodies(m.bodies);
    if (!m.positions || !m.positions.length) {
      MODEL = null;
      if (fit && (sketchObjs.length || ghostObjs.length))
        fitToObjects([...sketchObjs, ...ghostObjs]);
      return;
    }
    MODEL = m;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position',
      new THREE.Float32BufferAttribute(m.positions, 3));
    geo.setIndex(m.indices);
    geo.computeVertexNormals();
    mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      color: 0x5ba7f7, metalness: 0.25, roughness: 0.42 }));
    scene.add(mesh);
    for (const e of m.edges) {
      const g = new THREE.BufferGeometry().setFromPoints(
        e.points.map(p => new THREE.Vector3(p[0], p[1], p[2])));
      const line = new THREE.Line(g, new THREE.LineBasicMaterial({
        color: 0x0c2a4a, transparent: true, opacity: 0.55 }));
      line.userData.edgeId = e.id;
      scene.add(line); edgeLines.push(line);
    }
    geo.computeBoundingSphere();
    fitRadius = geo.boundingSphere.radius || 100;
    fitCenter.copy(geo.boundingSphere.center);
    if (fit) {
      if (ghostObjs.length) { fitToObjects([mesh, ...ghostObjs]); }
      else {
        camera.near = fitRadius / 100; camera.far = fitRadius * 100;
        camera.updateProjectionMatrix(); setView('iso');
      }
    }
  } catch (e) { /* no model yet */ }
}

export function clearMesh() {
  disposeModel(); MODEL = null; S.selected = null; clearHighlight();
}

function fitToObjects(objs) {
  const box = new THREE.Box3();
  for (const o of objs) box.expandByObject(o);
  if (box.isEmpty()) return;
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  fitRadius = sphere.radius || 100;
  fitCenter.copy(sphere.center);
  camera.near = fitRadius / 100; camera.far = fitRadius * 100;
  camera.updateProjectionMatrix(); setView('iso');
}

/* ---------------- feature overlay (tree row click) ---------------- */

export function clearHighlight() {
  if (hlMesh) { scene.remove(hlMesh); hlMesh.geometry.dispose(); hlMesh = null; }
}

export async function showFeatureOverlay(fid) {
  clearHighlight();
  try {
    const geo = await new STLLoader()
      .loadAsync('/api/feature-mesh/' + fid + '.stl?t=' + Date.now());
    geo.computeVertexNormals();
    if (S.selected !== fid) return;        // selection moved on while loading
    hlMesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      color: 0xffb85c, emissive: 0x8a5a1a, transparent: true, opacity: 0.6,
      depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 }));
    scene.add(hlMesh);
  } catch (e) { /* feature not built (suppressed / rolled back) */ }
}

/* ---------------- face / edge picking ---------------- */

function clearPickHighlight() {
  if (pickHl) { scene.remove(pickHl); pickHl.geometry.dispose(); pickHl = null; }
}
function clearPick() {
  clearPickHighlight();
  S.pickedFace = null;
  document.getElementById('pickInfo').style.display = 'none';
}

function pickAt(e) {
  if (!mesh || !MODEL) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  raycaster.params.Line.threshold = fitRadius / 60;

  const eHits = raycaster.intersectObjects(edgeLines, false);
  const fHit = raycaster.intersectObject(mesh, false)[0];
  if (eHits.length && (!fHit || eHits[0].distance <= fHit.distance + 1e-3)) {
    selectEdge(eHits[0].object.userData.edgeId);
  } else if (fHit) {
    selectFace(MODEL.faceId[fHit.face.a]);
  }
}

function selectFace(fid) {
  clearPickHighlight();
  const m = MODEL, pos = m.positions, keep = [];
  for (let t = 0; t < m.indices.length; t += 3) {
    const a = m.indices[t];
    if (m.faceId[a] === fid)
      for (const vi of [m.indices[t], m.indices[t + 1], m.indices[t + 2]])
        keep.push(pos[vi * 3], pos[vi * 3 + 1], pos[vi * 3 + 2]);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(keep, 3));
  g.computeVertexNormals();
  pickHl = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
    color: 0xffb85c, emissive: 0x8a5a1a, side: THREE.DoubleSide,
    transparent: true, opacity: 0.75, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -3 }));
  scene.add(pickHl);
  const info = m.faces.find(f => f.id === fid) || {};
  // remember the picked face so the Sketch tab can sketch on it (planar only)
  S.pickedFace = (info.center && info.type === 'PLANE') ? info : null;
  showPick(`<b>Face ${fid}</b> — ${info.type}`,
    [['area', (info.area ?? '?') + ' mm²'],
     info.radius != null ? ['radius', info.radius + ' mm'] : null,
     info.center ? ['center', info.center.join(', ')] : null]);
  if (info.center && info.type === 'PLANE') {   // sketching needs a FLAT face
    const btn = document.createElement('button');
    btn.textContent = '✎ Sketch on this face';
    btn.style.cssText = 'margin-top:7px;width:100%;background:var(--accent);' +
      'color:#08111e;border:none;border-radius:6px;padding:6px;cursor:pointer;' +
      'font:inherit;font-weight:700';
    btn.onclick = () => bus.emit('sketch-on-face', info);
    document.getElementById('pickInfo').appendChild(btn);
  } else if (info.center) {
    const note = document.createElement('div');
    note.style.cssText = 'margin-top:7px;color:var(--dim);font-size:11px;line-height:1.4';
    note.textContent = `Sketching needs a FLAT face — this one is ${info.type}. ` +
      'For a slot/pocket here: sketch on a plane at the right offset, extrude, then Cut.';
    document.getElementById('pickInfo').appendChild(note);
  }
}

function selectEdge(eid) {
  clearPickHighlight();
  S.pickedFace = null;                 // an edge pick is not a sketchable face
  const e = MODEL.edges.find(x => x.id === eid);
  const g = new THREE.BufferGeometry().setFromPoints(
    e.points.map(p => new THREE.Vector3(p[0], p[1], p[2])));
  pickHl = new THREE.Line(g, new THREE.LineBasicMaterial({
    color: 0xffb85c, linewidth: 3, depthTest: false }));
  pickHl.renderOrder = 999;
  scene.add(pickHl);
  showPick(`<b>Edge ${eid}</b> — ${e.type}`, [['length', e.length + ' mm']]);
}

function showPick(title, rows) {
  const el = document.getElementById('pickInfo');
  el.innerHTML = title + rows.filter(Boolean)
    .map(r => `<br><span class="k">${r[0]}:</span> ${r[1]}`).join('');
  el.style.display = 'block';
}
