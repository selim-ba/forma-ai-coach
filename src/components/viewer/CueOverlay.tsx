"use client";

import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { cuesFor, type Anchor, type CueDef, type CueJoint, type CueShape } from "@/lib/cues/catalog";
import { playhead, useSceneStore } from "@/lib/scene/store";
import { avatarRig } from "./AvatarModel";

/**
 * Draws the visual form cues (src/lib/cues/catalog.ts) on top of the avatar.
 * Everything follows the bones every frame, so arrows and lines move with the
 * exercise. Cues fade in/out; while playing, a cue with a time window only
 * shows during its part of the movement. Rendered on top (no depth test).
 */

const ACCENT = new THREE.Color("#ff7a45");
const GUIDE = new THREE.Color("#38bdf8");

/** Bone names per rig, MHR first, then the wooden mannequin. */
const BONES: Record<Exclude<CueJoint, "pelvis">, string[]> = {
  neck: ["c_neck", "Neck"],
  head: ["c_head", "Head"],
  l_shoulder: ["l_uparm", "LeftUpperArm"],
  r_shoulder: ["r_uparm", "RightUpperArm"],
  l_elbow: ["l_lowarm", "LeftLowerArm"],
  r_elbow: ["r_lowarm", "RightLowerArm"],
  l_wrist: ["l_wrist", "LeftHand"],
  r_wrist: ["r_wrist", "RightHand"],
  l_hip: ["l_upleg", "LeftUpperLeg"],
  r_hip: ["r_upleg", "RightUpperLeg"],
  l_knee: ["l_lowleg", "LeftLowerLeg"],
  r_knee: ["r_lowleg", "RightLowerLeg"],
  l_ankle: ["l_talocrural", "LeftFoot"],
  r_ankle: ["r_talocrural", "RightFoot"],
  l_toe: ["l_ball"],
  r_toe: ["r_ball"],
};

const boneCache = new WeakMap<THREE.Object3D, Map<string, THREE.Object3D | null>>();
function bone(rig: THREE.Object3D, names: string[]): THREE.Object3D | null {
  let cache = boneCache.get(rig);
  if (!cache) boneCache.set(rig, (cache = new Map()));
  const key = names.join("|");
  if (!cache.has(key)) cache.set(key, names.map((n) => rig.getObjectByName(n)).find(Boolean) ?? null);
  return cache.get(key) ?? null;
}

const tmpA = new THREE.Vector3();
const tmpB = new THREE.Vector3();

/** World position of a joint (+ offset). Returns false if the rig lacks it. */
function anchorPos(rig: THREE.Object3D, anchor: Anchor, out: THREE.Vector3): boolean {
  const { joint } = anchor;
  if (joint === "pelvis") {
    const l = bone(rig, BONES.l_hip);
    const r = bone(rig, BONES.r_hip);
    if (!l || !r) return false;
    out.copy(l.getWorldPosition(tmpA)).add(r.getWorldPosition(tmpB)).multiplyScalar(0.5);
  } else if ((joint === "l_toe" || joint === "r_toe") && !bone(rig, BONES[joint])) {
    // Rigs without a toe joint: a point ahead of the ankle, on the floor.
    const ankle = bone(rig, BONES[joint === "l_toe" ? "l_ankle" : "r_ankle"]);
    if (!ankle) return false;
    out.copy(ankle.getWorldPosition(tmpA)).add(tmpB.set(0, 0, 0.13));
    out.y = 0.02;
  } else {
    const b = bone(rig, BONES[joint]);
    if (!b) return false;
    b.getWorldPosition(out);
  }
  if (anchor.offset) out.add(tmpA.set(anchor.offset[0], anchor.offset[1], anchor.offset[2]));
  out.y = Math.max(out.y, 0.005); // never below the floor
  return true;
}

function material(color: THREE.Color, alphaMap?: THREE.Texture) {
  return new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0,
    depthTest: false,
    depthWrite: false,
    alphaMap: alphaMap ?? null,
  });
}

function dashTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 1;
  canvas.height = 8;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, 1, 5);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 5, 1, 3);
  const t = new THREE.CanvasTexture(canvas);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.magFilter = THREE.NearestFilter;
  return t;
}

type Built = {
  object: THREE.Object3D;
  update: (rig: THREE.Object3D, opacity: number, camera: THREE.Camera, time: number) => void;
  dispose: () => void;
};

const UP = new THREE.Vector3(0, 1, 0);

/** Build a three.js object for one shape, with an update() that re-anchors it every frame. */
function buildShape(shape: CueShape): Built {
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const dir = new THREE.Vector3();
  const q = new THREE.Quaternion();

  if (shape.kind === "ring") {
    const geo = new THREE.TorusGeometry(shape.radius ?? 0.06, 0.01, 8, 40);
    const mat = material(ACCENT);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.renderOrder = 999;
    return {
      object: mesh,
      update(rig, opacity, camera, time) {
        mesh.visible = opacity > 0.01 && anchorPos(rig, shape.at, from);
        mesh.position.copy(from);
        mesh.quaternion.copy(camera.quaternion);
        mesh.scale.setScalar(1 + 0.12 * Math.sin(time * 4));
        mat.opacity = opacity;
      },
      dispose: () => (geo.dispose(), mat.dispose()),
    };
  }

  if (shape.kind === "line") {
    const geo = new THREE.CylinderGeometry(0.009, 0.009, 1, 8, 1, true).translate(0, 0.5, 0);
    const dashes = shape.dashed ? dashTexture() : undefined;
    const mat = material(GUIDE, dashes);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.renderOrder = 998;
    return {
      object: mesh,
      update(rig, opacity) {
        const ok = anchorPos(rig, shape.from, from) && anchorPos(rig, shape.to, to);
        dir.subVectors(to, from);
        const length = dir.length();
        mesh.visible = ok && opacity > 0.01 && length > 1e-3;
        if (!mesh.visible) return;
        mesh.position.copy(from);
        mesh.quaternion.copy(q.setFromUnitVectors(UP, dir.divideScalar(length)));
        mesh.scale.set(1, length, 1);
        if (dashes) dashes.repeat.set(1, length / 0.07);
        mat.opacity = opacity * 0.9;
      },
      dispose: () => (geo.dispose(), mat.dispose(), dashes?.dispose()),
    };
  }

  // Arrow: shaft + head, tip exactly at `to`.
  const head = 0.085;
  const shaftGeo = new THREE.CylinderGeometry(0.014, 0.014, 1, 10).translate(0, 0.5, 0);
  const headGeo = new THREE.ConeGeometry(0.04, head, 16).translate(0, -head / 2, 0);
  const mat = material(ACCENT);
  const shaft = new THREE.Mesh(shaftGeo, mat);
  const tip = new THREE.Mesh(headGeo, mat);
  shaft.renderOrder = tip.renderOrder = 999;
  const group = new THREE.Group();
  group.add(shaft, tip);
  return {
    object: group,
    update(rig, opacity, _camera, time) {
      const ok = anchorPos(rig, shape.from, from) && anchorPos(rig, shape.to, to);
      dir.subVectors(to, from);
      const length = dir.length();
      group.visible = ok && opacity > 0.01 && length > head;
      if (!group.visible) return;
      // A gentle "flow" along the arrow: it grows from its tail and settles.
      const grow = 0.85 + 0.15 * (0.5 + 0.5 * Math.sin(time * 3));
      const end = to.clone().sub(from).multiplyScalar(grow).add(from);
      dir.subVectors(end, from).normalize();
      q.setFromUnitVectors(UP, dir);
      shaft.position.copy(from);
      shaft.quaternion.copy(q);
      shaft.scale.set(1, Math.max(length * grow - head, 1e-3), 1);
      tip.position.copy(end);
      tip.quaternion.copy(q);
      mat.opacity = opacity;
    },
    dispose: () => (shaftGeo.dispose(), headGeo.dispose(), mat.dispose()),
  };
}

function CueView({ def, active }: { def: CueDef; active: boolean }) {
  // Build shapes and their group in ONE memo: React may run a memo twice in development,
  // and three.js objects can only have one parent.
  const { built, group } = useMemo(() => {
    const shapes = def.shapes.map(buildShape);
    const g = new THREE.Group();
    shapes.forEach((b) => g.add(b.object));
    return { built: shapes, group: g };
  }, [def]);
  useEffect(() => () => built.forEach((b) => b.dispose()), [built]);

  const label = useRef<THREE.Group>(null);
  const labelDiv = useRef<HTMLDivElement>(null);
  const opacity = useRef(0);
  const labelPos = useMemo(() => new THREE.Vector3(), []);

  useFrame(({ camera, clock }, delta) => {
    const rig = avatarRig.current;
    const playing = useSceneStore.getState().scene.playing;
    const inWindow = !def.window || (playhead.progress >= def.window[0] && playhead.progress <= def.window[1]);
    const target = active && rig && (!playing || inWindow) ? 1 : 0;
    opacity.current = THREE.MathUtils.damp(opacity.current, target, 8, delta);
    if (!rig) return;
    for (const b of built) b.update(rig, opacity.current, camera, clock.elapsedTime);
    if (label.current && anchorPos(rig, def.labelAt, labelPos)) label.current.position.copy(labelPos);
    if (labelDiv.current) {
      labelDiv.current.style.opacity = String(opacity.current);
      labelDiv.current.style.display = opacity.current < 0.02 ? "none" : "block";
    }
  });

  return (
    <>
      <primitive object={group} />
      <group ref={label}>
        <Html center zIndexRange={[15, 0]} style={{ pointerEvents: "none" }}>
          <div
            ref={labelDiv}
            className="whitespace-nowrap rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-semibold text-white shadow-lg backdrop-blur-md"
            style={{ opacity: 0, display: "none" }}
            data-testid={`cue-${def.id}`}
          >
            {def.label}
          </div>
        </Html>
      </group>
    </>
  );
}

export function CueOverlay() {
  const exerciseId = useSceneStore((s) => s.scene.exerciseId);
  const active = useSceneStore((s) => s.scene.cues);
  const defs = useMemo(() => cuesFor(exerciseId), [exerciseId]);
  return (
    <>
      {defs.map((def) => (
        <CueView key={def.id} def={def} active={active.includes(def.id)} />
      ))}
    </>
  );
}
