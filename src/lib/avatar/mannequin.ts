/**
 * Procedural, rigged "Forma mannequin" and its baked exercise clips.
 *
 * Why procedural: it is 100% original (no third-party licence), every clip
 * shares one skeleton by construction, and phase markers are known exactly.
 * The output is a standard skinned glTF, so it can later be swapped for a
 * licensed or personalised GLB with the same clip names.
 *
 * Units: metres. Y up. Character faces +Z. Character's left is +X.
 * Used by scripts/build-mannequin.ts (Node) — not imported by the browser.
 */
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import {
  BONE_NAMES,
  MOTION_TIMELINES,
  POSE_FUNCTIONS,
  sampleTimeline,
  type BoneName,
  type MotionTimeline,
  type Pose,
} from "./motions";

type BoneDef = { name: BoneName; parent: BoneName | null; offset: [number, number, number] };

export const SKELETON: BoneDef[] = [
  { name: "Root", parent: null, offset: [0, 0, 0] },
  { name: "Hips", parent: "Root", offset: [0, 0.97, 0] },
  { name: "Spine", parent: "Hips", offset: [0, 0.1, 0] },
  { name: "Chest", parent: "Spine", offset: [0, 0.17, 0] },
  { name: "Neck", parent: "Chest", offset: [0, 0.23, 0] },
  { name: "Head", parent: "Neck", offset: [0, 0.08, 0] },
  { name: "LeftUpperArm", parent: "Chest", offset: [0.185, 0.18, 0] },
  { name: "LeftLowerArm", parent: "LeftUpperArm", offset: [0, -0.29, 0] },
  { name: "LeftHand", parent: "LeftLowerArm", offset: [0, -0.25, 0] },
  { name: "RightUpperArm", parent: "Chest", offset: [-0.185, 0.18, 0] },
  { name: "RightLowerArm", parent: "RightUpperArm", offset: [0, -0.29, 0] },
  { name: "RightHand", parent: "RightLowerArm", offset: [0, -0.25, 0] },
  { name: "LeftUpperLeg", parent: "Hips", offset: [0.095, -0.05, 0] },
  { name: "LeftLowerLeg", parent: "LeftUpperLeg", offset: [0, -0.42, 0] },
  { name: "LeftFoot", parent: "LeftLowerLeg", offset: [0, -0.42, 0] },
  { name: "RightUpperLeg", parent: "Hips", offset: [-0.095, -0.05, 0] },
  { name: "RightLowerLeg", parent: "RightUpperLeg", offset: [0, -0.42, 0] },
  { name: "RightFoot", parent: "RightLowerLeg", offset: [0, -0.42, 0] },
];

export const REST_HIPS_POSITION = new THREE.Vector3(0, 0.97, 0);

export function createSkeleton() {
  const bones = new Map<BoneName, THREE.Bone>();
  for (const def of SKELETON) {
    const bone = new THREE.Bone();
    bone.name = def.name;
    bone.position.set(...def.offset);
    bones.set(def.name, bone);
    if (def.parent) bones.get(def.parent)!.add(bone);
  }
  return { root: bones.get("Root")!, bones };
}

// ---------------------------------------------------------------------------
// Geometry: rigid segments, each 100% weighted to one bone (wooden-mannequin look).
// ---------------------------------------------------------------------------

type Part = {
  bone: BoneName;
  geometry: THREE.BufferGeometry;
  /** Transform in the bone's local (bind) space. */
  position?: [number, number, number];
  rotation?: [number, number, number];
  scale?: [number, number, number];
  material: 0 | 1; // 0 = body, 1 = joints/accent
};

const capsule = (radius: number, length: number) => new THREE.CapsuleGeometry(radius, length, 6, 16);
const sphere = (radius: number) => new THREE.SphereGeometry(radius, 20, 14);

function bodyParts(): Part[] {
  const parts: Part[] = [
    // Torso
    { bone: "Hips", geometry: sphere(1), position: [0, -0.01, 0], scale: [0.165, 0.12, 0.11], material: 0 },
    { bone: "Spine", geometry: sphere(1), position: [0, 0.08, 0], scale: [0.145, 0.13, 0.1], material: 0 },
    { bone: "Chest", geometry: sphere(1), position: [0, 0.1, 0], scale: [0.19, 0.17, 0.115], material: 0 },
    { bone: "Neck", geometry: new THREE.CylinderGeometry(0.045, 0.05, 0.12, 14), position: [0, 0.02, 0], material: 1 },
    { bone: "Head", geometry: sphere(1), position: [0, 0.1, 0.005], scale: [0.092, 0.118, 0.103], material: 0 },
    // Face plate shows which way the mannequin is looking (important in side view).
    { bone: "Head", geometry: sphere(1), position: [0, 0.105, 0.072], scale: [0.065, 0.045, 0.04], material: 1 },
  ];

  for (const side of ["Left", "Right"] as const) {
    const s = side === "Left" ? 1 : -1;
    parts.push(
      // Arms
      { bone: `${side}UpperArm`, geometry: sphere(0.056), material: 1 },
      { bone: `${side}UpperArm`, geometry: capsule(0.045, 0.2), position: [0, -0.145, 0], material: 0 },
      { bone: `${side}LowerArm`, geometry: sphere(0.043), material: 1 },
      { bone: `${side}LowerArm`, geometry: capsule(0.037, 0.17), position: [0, -0.125, 0], material: 0 },
      { bone: `${side}Hand`, geometry: sphere(1), position: [0, -0.075, 0], scale: [0.044, 0.08, 0.024], material: 0 },
      // Legs
      { bone: `${side}UpperLeg`, geometry: sphere(0.074), material: 1 },
      { bone: `${side}UpperLeg`, geometry: capsule(0.066, 0.29), position: [0, -0.21, 0], material: 0 },
      { bone: `${side}LowerLeg`, geometry: sphere(0.058), material: 1 },
      { bone: `${side}LowerLeg`, geometry: capsule(0.05, 0.32), position: [0, -0.21, 0], material: 0 },
      { bone: `${side}Foot`, geometry: sphere(0.046), material: 1 },
      {
        bone: `${side}Foot`,
        geometry: capsule(0.04, 0.17),
        position: [0.005 * s, -0.04, 0.065],
        rotation: [Math.PI / 2, 0, 0],
        scale: [1.15, 1, 1],
        material: 0,
      },
    );
  }
  return parts;
}

function dumbbellParts(): Part[] {
  const parts: Part[] = [];
  for (const side of ["Left", "Right"] as const) {
    const bone = `${side}Hand` as BoneName;
    // Handle runs left-right through the palm (palms face forward = supinated grip).
    parts.push(
      { bone, geometry: new THREE.CylinderGeometry(0.014, 0.014, 0.16, 10), position: [0, -0.08, 0], rotation: [0, 0, Math.PI / 2], material: 1 },
      { bone, geometry: new THREE.CylinderGeometry(0.042, 0.042, 0.028, 18), position: [0.07, -0.08, 0], rotation: [0, 0, Math.PI / 2], material: 1 },
      { bone, geometry: new THREE.CylinderGeometry(0.042, 0.042, 0.028, 18), position: [-0.07, -0.08, 0], rotation: [0, 0, Math.PI / 2], material: 1 },
    );
  }
  return parts;
}

function buildSkinnedGeometry(parts: Part[], bones: Map<BoneName, THREE.Bone>, boneOrder: BoneName[]) {
  const pieces: THREE.BufferGeometry[][] = [[], []];
  const local = new THREE.Matrix4();
  for (const part of parts) {
    const g = part.geometry.index ? part.geometry : part.geometry.toNonIndexed();
    g.deleteAttribute("uv");
    local.compose(
      new THREE.Vector3(...(part.position ?? [0, 0, 0])),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(...(part.rotation ?? [0, 0, 0]))),
      new THREE.Vector3(...(part.scale ?? [1, 1, 1])),
    );
    const bone = bones.get(part.bone)!;
    g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(bone.matrixWorld, local));
    const count = g.getAttribute("position").count;
    const boneIndex = boneOrder.indexOf(part.bone);
    const skinIndex = new Uint16Array(count * 4);
    const skinWeight = new Float32Array(count * 4);
    for (let i = 0; i < count; i++) {
      skinIndex[i * 4] = boneIndex;
      skinWeight[i * 4] = 1;
    }
    g.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(skinIndex, 4));
    g.setAttribute("skinWeight", new THREE.Float32BufferAttribute(skinWeight, 4));
    pieces[part.material].push(g);
  }
  const perMaterial = pieces.filter((p) => p.length > 0).map((p) => mergeGeometries(p, false)!);
  const merged = mergeGeometries(perMaterial, true)!;
  return merged;
}

export const BODY_COLOR = "#e9e3d8";
export const ACCENT_COLOR = "#ff7a45";
export const PROP_COLOR = "#3b4048";

export function createMannequin() {
  const { root, bones } = createSkeleton();
  const group = new THREE.Group();
  group.name = "FormaMannequin";
  group.add(root);
  group.updateMatrixWorld(true);

  const boneOrder = BONE_NAMES.slice() as BoneName[];
  const skeleton = new THREE.Skeleton(boneOrder.map((n) => bones.get(n)!));

  const bodyMaterial = new THREE.MeshStandardMaterial({ name: "Body", color: BODY_COLOR, roughness: 0.62, metalness: 0 });
  const accentMaterial = new THREE.MeshStandardMaterial({ name: "Joint", color: ACCENT_COLOR, roughness: 0.45, metalness: 0 });
  const propMaterial = new THREE.MeshStandardMaterial({ name: "Prop", color: PROP_COLOR, roughness: 0.35, metalness: 0.4 });

  const body = new THREE.SkinnedMesh(buildSkinnedGeometry(bodyParts(), bones, boneOrder), [bodyMaterial, accentMaterial]);
  body.name = "Mannequin";
  const dumbbellGeometry = buildSkinnedGeometry(dumbbellParts(), bones, boneOrder);
  dumbbellGeometry.clearGroups();
  const dumbbells = new THREE.SkinnedMesh(dumbbellGeometry, propMaterial);
  dumbbells.name = "Dumbbells";

  for (const mesh of [body, dumbbells]) {
    mesh.frustumCulled = false;
    group.add(mesh);
    mesh.bind(skeleton, new THREE.Matrix4());
  }

  return { group, root, bones, skeleton, body, dumbbells };
}

// ---------------------------------------------------------------------------
// Animation baking
// ---------------------------------------------------------------------------

const DEG = Math.PI / 180;

function applyPose(bones: Map<BoneName, THREE.Bone>, pose: Pose) {
  for (const name of BONE_NAMES) {
    const a = pose[name] ?? {};
    bones.get(name)!.quaternion.setFromEuler(new THREE.Euler((a.x ?? 0) * DEG, (a.y ?? 0) * DEG, (a.z ?? 0) * DEG, "XYZ"));
  }
}

/**
 * Pose the skeleton and translate the hips so both ankles stay exactly where
 * they are in the rest pose (feet planted). Returns ankle drift for QA.
 */
export function solvePlantedPose(bones: Map<BoneName, THREE.Bone>, pose: Pose) {
  const hips = bones.get("Hips")!;
  const root = bones.get("Root")!;
  applyPose(bones, pose);

  hips.position.copy(REST_HIPS_POSITION);
  root.updateMatrixWorld(true);
  const restAnkleL = new THREE.Vector3(0.095, 0.08, 0);
  const restAnkleR = new THREE.Vector3(-0.095, 0.08, 0);
  const ankleL = bones.get("LeftFoot")!.getWorldPosition(new THREE.Vector3());
  const ankleR = bones.get("RightFoot")!.getWorldPosition(new THREE.Vector3());
  const delta = restAnkleL.clone().sub(ankleL).add(restAnkleR.clone().sub(ankleR)).multiplyScalar(0.5);
  hips.position.add(delta);
  root.updateMatrixWorld(true);

  const driftL = bones.get("LeftFoot")!.getWorldPosition(new THREE.Vector3()).distanceTo(restAnkleL);
  const driftR = bones.get("RightFoot")!.getWorldPosition(new THREE.Vector3()).distanceTo(restAnkleR);
  return Math.max(driftL, driftR);
}

export function bakeClip(timeline: MotionTimeline, bones: Map<BoneName, THREE.Bone>) {
  const poseFn = POSE_FUNCTIONS[timeline.clipName];
  const frames = Math.round(timeline.duration * timeline.fps) + 1;
  const times = new Float32Array(frames);
  const quats = new Map<BoneName, Float32Array>(BONE_NAMES.map((n) => [n, new Float32Array(frames * 4)]));
  const hipsPos = new Float32Array(frames * 3);
  let maxDrift = 0;

  for (let f = 0; f < frames; f++) {
    const t = Math.min(f / timeline.fps, timeline.duration);
    times[f] = t;
    const pose = poseFn(sampleTimeline(timeline.keys, t));
    maxDrift = Math.max(maxDrift, solvePlantedPose(bones, pose));
    for (const name of BONE_NAMES) {
      bones.get(name)!.quaternion.toArray(quats.get(name)!, f * 4);
    }
    bones.get("Hips")!.position.toArray(hipsPos, f * 3);
  }

  const tracks: THREE.KeyframeTrack[] = BONE_NAMES.map(
    (name) => new THREE.QuaternionKeyframeTrack(`${name}.quaternion`, times, quats.get(name)!),
  );
  tracks.push(new THREE.VectorKeyframeTrack("Hips.position", times, hipsPos));
  const clip = new THREE.AnimationClip(timeline.clipName, timeline.duration, tracks);
  return { clip, maxDrift };
}

export function bakeAllClips(bones: Map<BoneName, THREE.Bone>) {
  return MOTION_TIMELINES.map((timeline) => ({ timeline, ...bakeClip(timeline, bones) }));
}

/** Restore the bind pose (all identity rotations, rest hips). */
export function resetToBindPose(bones: Map<BoneName, THREE.Bone>) {
  for (const def of SKELETON) {
    const bone = bones.get(def.name)!;
    bone.position.set(...def.offset);
    bone.quaternion.identity();
  }
  bones.get("Root")!.updateMatrixWorld(true);
}
