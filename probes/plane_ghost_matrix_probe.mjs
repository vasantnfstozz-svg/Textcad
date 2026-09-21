// Probe: three.js Matrix4.makeBasis + setPosition give a frame matrix whose
// position is the plane origin moved along z by the offset (the sketch-plane
// ghost). Run: node probes/plane_ghost_matrix_probe.mjs
import * as THREE from '../static/vendor/three/0.160.0/three.module.js';
const X = new THREE.Vector3(1, 0, 0), Y = new THREE.Vector3(0, 0, -1), Z = new THREE.Vector3(0, 1, 0);
const O = new THREE.Vector3(5, 0, 7);
const m = new THREE.Matrix4().makeBasis(X, Y, Z);
const at = O.clone().add(Z.clone().multiplyScalar(-3));
m.setPosition(at);
const p = new THREE.Vector3().setFromMatrixPosition(m);
const local = new THREE.Vector3(2, 4, 0).applyMatrix4(m);   // plane-local (2,4) -> world
console.log(JSON.stringify({ pos: p.toArray(), local: local.toArray(),
  attr: new THREE.Float32BufferAttribute([0, 0, 0, 1, 1, 1], 3).count }));
