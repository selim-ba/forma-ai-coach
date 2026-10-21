"use client";

import { OrbitControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef, type ComponentRef } from "react";
import * as THREE from "three";
import { useSceneStore } from "@/lib/scene/store";
import type { View } from "@/types/scene";

export const CAMERA_TARGET = new THREE.Vector3(0, 0.88, 0.1);

/** Spherical presets around the target. The mannequin faces +Z. */
const PRESETS: Record<View, { azimuthDeg: number; elevationDeg: number }> = {
  front: { azimuthDeg: 0, elevationDeg: 6 },
  side: { azimuthDeg: -90, elevationDeg: 4 }, // camera on the mannequin's right: it faces screen-right
  three_quarter: { azimuthDeg: -40, elevationDeg: 12 },
};

/**
 * Distance that fits a ~1.95 m tall subject (plus forward reach) in the
 * viewport for the current aspect ratio — portrait phones need more distance.
 */
function fitDistance(fovDeg: number, aspect: number) {
  const halfHeight = 1.08;
  const halfWidth = 0.78;
  const vHalf = THREE.MathUtils.degToRad(fovDeg / 2);
  const hHalf = Math.atan(Math.tan(vHalf) * aspect);
  return Math.max(halfHeight / Math.tan(vHalf), halfWidth / Math.tan(hHalf)) + 0.4;
}

function presetPosition(view: View, distance: number) {
  const { azimuthDeg, elevationDeg } = PRESETS[view];
  const az = THREE.MathUtils.degToRad(azimuthDeg);
  const el = THREE.MathUtils.degToRad(elevationDeg);
  return new THREE.Vector3(
    CAMERA_TARGET.x + distance * Math.cos(el) * Math.sin(az),
    CAMERA_TARGET.y + distance * Math.sin(el),
    CAMERA_TARGET.z + distance * Math.cos(el) * Math.cos(az),
  );
}

export function CameraControls() {
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null);
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const size = useThree((s) => s.size);
  const view = useSceneStore((s) => s.scene.view);
  const viewNonce = useSceneStore((s) => s.scene.viewNonce);
  const tween = useRef<{ from: THREE.Vector3; to: THREE.Vector3; t: number } | null>(null);
  const distance = fitDistance(camera.fov, size.width / Math.max(1, size.height));

  // Snap on first mount, tween on later preset changes (including re-selecting the same preset).
  const first = useRef(true);
  useEffect(() => {
    const to = presetPosition(view, distance);
    if (first.current) {
      camera.position.copy(to);
      camera.lookAt(CAMERA_TARGET);
      first.current = false;
      return;
    }
    tween.current = { from: camera.position.clone(), to, t: 0 };
  }, [view, viewNonce, distance, camera]);

  useFrame((_, delta) => {
    const tw = tween.current;
    if (!tw) return;
    tw.t = Math.min(1, tw.t + delta / 0.6);
    const k = 1 - Math.pow(1 - tw.t, 3);
    // Interpolate on a sphere around the target so the camera orbits rather than cutting through the body.
    const a = tw.from.clone().sub(CAMERA_TARGET);
    const b = tw.to.clone().sub(CAMERA_TARGET);
    const sa = new THREE.Spherical().setFromVector3(a);
    const sb = new THREE.Spherical().setFromVector3(b);
    let dTheta = sb.theta - sa.theta;
    if (dTheta > Math.PI) dTheta -= 2 * Math.PI;
    if (dTheta < -Math.PI) dTheta += 2 * Math.PI;
    const s = new THREE.Spherical(
      THREE.MathUtils.lerp(sa.radius, sb.radius, k),
      THREE.MathUtils.lerp(sa.phi, sb.phi, k),
      sa.theta + dTheta * k,
    );
    camera.position.copy(new THREE.Vector3().setFromSpherical(s).add(CAMERA_TARGET));
    camera.lookAt(CAMERA_TARGET);
    controls.current?.update();
    if (tw.t >= 1) tween.current = null;
  });

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      target={CAMERA_TARGET}
      enablePan={false}
      enableDamping
      dampingFactor={0.12}
      rotateSpeed={0.8}
      minDistance={distance * 0.55}
      maxDistance={distance * 1.5}
      minPolarAngle={THREE.MathUtils.degToRad(35)}
      maxPolarAngle={THREE.MathUtils.degToRad(100)}
      onStart={() => {
        tween.current = null; // the user's finger always wins over a preset tween
      }}
    />
  );
}
