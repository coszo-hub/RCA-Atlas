import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { sceneSignature } from "./renderGate.js";

function world() {
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(30, 1.5, 0.1, 100);
  const mat = new THREE.ShaderMaterial({ uniforms: { uExag: { value: 6 }, uGlass: { value: new THREE.Vector3() } } });
  const mesh = new THREE.Mesh(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3)), mat);
  scene.add(mesh); camera.position.set(0, 5, 10); camera.updateMatrixWorld();
  return { scene, camera, mat, mesh, sig: () => sceneSignature(scene, camera, 800, 600) };
}

describe("sceneSignature", () => {
  it("is stable while nothing changes", () => {
    const w = world();
    expect(w.sig()).toBe(w.sig());
  });
  it("changes with the camera, canvas size, uniforms, visibility, transforms, geometry and new objects", () => {
    const w = world(), changes = [
      () => { w.camera.position.x += 0.01; w.camera.updateMatrixWorld(); },
      () => w.camera.setViewOffset(800, 600, 4, 0, 800, 600),
      () => { w.mat.uniforms.uExag.value = 5.9; },
      () => { w.mat.uniforms.uGlass.value.z = 2; },
      () => { w.mat.opacity = 0.5; },
      () => { w.mesh.visible = false; },
      () => { w.mesh.visible = true; w.mesh.position.y = 1; },
      () => { w.mesh.geometry.attributes.position.needsUpdate = true; },
      () => { w.mesh.geometry = new THREE.BufferGeometry(); },
      () => w.scene.add(new THREE.Mesh(new THREE.BufferGeometry(), w.mat)),
    ];
    let last = w.sig();
    for (const change of changes) {
      change();
      const next = w.sig();
      expect(next).not.toBe(last);
      last = next;
    }
    expect(sceneSignature(w.scene, w.camera, 801, 600)).not.toBe(last);
  });
});
