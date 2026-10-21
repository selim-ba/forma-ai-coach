#!/usr/bin/env node
/**
 * Dependency-free GLB validator for the avatar asset.
 *
 *   npm run assets:validate [path/to/model.glb]
 *
 * Checks: valid GLB container, size budget, a skinned mesh, required bones,
 * required animation clips with expected durations, the bind-pose height and
 * that the feet sit on the floor. Prints a summary that can be pasted into ASSETS.md.
 */
import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

const file = resolve(process.argv[2] ?? "public/models/forma-mannequin.glb");
const REQUIRED_CLIPS = { squat: 4, biceps_curl: 4 };
const REQUIRED_BONES = ["Hips", "Spine", "Chest", "Head", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "LeftUpperArm", "LeftLowerArm", "LeftHand"];
const SIZE_BUDGET = 10 * 1024 * 1024; // README: ~5–10 MB total assets (target, not benchmark)

const errors = [];
const warn = [];
const ok = (m) => console.log(`  ✓ ${m}`);

const buf = readFileSync(file);
const bytes = statSync(file).size;
console.log(`Validating ${file}`);

if (buf.readUInt32LE(0) !== 0x46546c67) errors.push("not a GLB (bad magic)");
if (buf.readUInt32LE(4) !== 2) errors.push(`unsupported glTF version ${buf.readUInt32LE(4)}`);
const jsonLen = buf.readUInt32LE(12);
if (buf.readUInt32LE(16) !== 0x4e4f534a) errors.push("first chunk is not JSON");
const gltf = JSON.parse(buf.subarray(20, 20 + jsonLen).toString("utf8"));

if (bytes > SIZE_BUDGET) errors.push(`file is ${(bytes / 1048576).toFixed(1)} MiB (> 10 MiB budget)`);
else ok(`size ${(bytes / 1024).toFixed(1)} KiB (budget 10 MiB)`);

if (gltf.extensionsRequired?.length) warn.push(`requires extensions: ${gltf.extensionsRequired.join(", ")} (decoder needed on device)`);

const skins = gltf.skins ?? [];
if (!skins.length) errors.push("no skins — avatar is not rigged");
else ok(`${skins.length} skin(s), ${skins[0].joints.length} joints`);

const nodeNames = new Set((gltf.nodes ?? []).map((n) => n.name));
const missingBones = REQUIRED_BONES.filter((b) => !nodeNames.has(b));
if (missingBones.length) errors.push(`missing bones: ${missingBones.join(", ")}`);
else ok(`required bones present`);

const skinnedMeshes = (gltf.nodes ?? []).filter((n) => n.mesh !== undefined && n.skin !== undefined);
if (!skinnedMeshes.length) errors.push("no skinned mesh node");
else ok(`skinned meshes: ${skinnedMeshes.map((n) => n.name).join(", ")}`);

const clips = gltf.animations ?? [];
for (const [name, expected] of Object.entries(REQUIRED_CLIPS)) {
  const clip = clips.find((a) => a.name === name);
  if (!clip) {
    errors.push(`missing animation clip "${name}"`);
    continue;
  }
  let duration = 0;
  for (const s of clip.samplers) duration = Math.max(duration, gltf.accessors[s.input].max?.[0] ?? 0);
  if (Math.abs(duration - expected) > 0.05) errors.push(`clip "${name}" lasts ${duration.toFixed(2)} s, catalog expects ${expected} s`);
  const animated = new Set(clip.channels.map((c) => gltf.nodes[c.target.node].name));
  ok(`clip "${name}": ${duration.toFixed(2)} s, ${clip.channels.length} channels, ${animated.size} nodes`);
  // Every clip must drive every joint so switching clips never leaves a stale pose.
  const joints = skins[0]?.joints.map((j) => gltf.nodes[j].name) ?? [];
  const undriven = joints.filter((j) => !animated.has(j) && j !== "Root");
  if (undriven.length) warn.push(`clip "${name}" does not drive: ${undriven.join(", ")}`);
}

// Bind-pose bounds of the body mesh POSITION accessor.
const bodyNode = skinnedMeshes[0];
if (bodyNode) {
  const prim = gltf.meshes[bodyNode.mesh].primitives[0];
  const acc = gltf.accessors[prim.attributes.POSITION];
  let min = acc.min, max = acc.max;
  for (const p of gltf.meshes[bodyNode.mesh].primitives.slice(1)) {
    const a = gltf.accessors[p.attributes.POSITION];
    min = min.map((v, i) => Math.min(v, a.min[i]));
    max = max.map((v, i) => Math.max(v, a.max[i]));
  }
  const height = max[1] - min[1];
  if (height < 1.4 || height > 2.1) errors.push(`bind-pose height ${height.toFixed(2)} m — check units/scale`);
  else ok(`bind-pose height ${height.toFixed(3)} m (units look like metres)`);
  if (Math.abs(min[1]) > 0.02) errors.push(`feet are ${min[1].toFixed(3)} m from the floor in bind pose`);
  else ok(`feet on floor in bind pose (min y ${min[1].toFixed(4)})`);
}

for (const w of warn) console.log(`  ! ${w}`);
if (errors.length) {
  for (const e of errors) console.error(`  ✗ ${e}`);
  process.exit(1);
}
console.log("Asset OK.");
