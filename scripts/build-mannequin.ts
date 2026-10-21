/**
 * Builds public/models/forma-mannequin.glb: a rigged, skinned mannequin with
 * two embedded, shared-skeleton clips ("squat", "biceps_curl"), plus a
 * metadata/QA report in public/models/forma-mannequin.meta.json.
 *
 *   npm run assets:build
 *
 * QA checks performed while baking (build fails if any is violated):
 *   - ankles stay planted (drift < 5 mm)
 *   - lowest skinned vertex stays within [-1 cm, +2 cm] of the floor
 *   - hands (and, for the curl, the inner dumbbell plates) never penetrate
 *     the torso ellipsoids or the thigh capsules
 */
import { mkdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import { bakeAllClips, createMannequin, resetToBindPose, solvePlantedPose } from "../src/lib/avatar/mannequin";
import { POSE_FUNCTIONS, sampleTimeline, type BoneName } from "../src/lib/avatar/motions";

// GLTFExporter (binary mode) relies on FileReader, which Node does not ship.
class NodeFileReader {
  result: ArrayBuffer | string | null = null;
  onloadend: (() => void) | null = null;
  readAsArrayBuffer(blob: Blob) {
    void blob.arrayBuffer().then((buf) => {
      this.result = buf;
      this.onloadend?.();
    });
  }
  readAsDataURL(blob: Blob) {
    void blob.arrayBuffer().then((buf) => {
      this.result = `data:${blob.type || "application/octet-stream"};base64,${Buffer.from(buf).toString("base64")}`;
      this.onloadend?.();
    });
  }
}
(globalThis as unknown as { FileReader: unknown }).FileReader ??= NodeFileReader;

const OUT = resolve(process.cwd(), "public/models/forma-mannequin.glb");
const META = resolve(process.cwd(), "public/models/forma-mannequin.meta.json");

function fail(message: string): never {
  console.error(`✗ ${message}`);
  process.exit(1);
}

const { group, bones, body, dumbbells } = createMannequin();
const baked = bakeAllClips(bones);

// ---------------------------------------------------------------------------
// QA over every baked frame
// ---------------------------------------------------------------------------
const v = new THREE.Vector3();
function minSkinnedY(mesh: THREE.SkinnedMesh, stride = 3) {
  mesh.skeleton.update();
  const count = mesh.geometry.getAttribute("position").count;
  let min = Infinity;
  for (let i = 0; i < count; i += stride) {
    mesh.getVertexPosition(i, v);
    min = Math.min(min, v.y);
  }
  return min;
}
const world = (name: BoneName) => bones.get(name)!.getWorldPosition(new THREE.Vector3());

// Collision proxies — must mirror the body parts in src/lib/avatar/mannequin.ts.
const TORSO = [
  { bone: "Hips", center: new THREE.Vector3(0, -0.01, 0), radii: new THREE.Vector3(0.165, 0.12, 0.11) },
  { bone: "Spine", center: new THREE.Vector3(0, 0.08, 0), radii: new THREE.Vector3(0.145, 0.13, 0.1) },
  { bone: "Chest", center: new THREE.Vector3(0, 0.1, 0), radii: new THREE.Vector3(0.19, 0.17, 0.115) },
] as const;
const THIGH_RADIUS = 0.066;

/** > 1 means the sphere (point + margin) is outside the inflated ellipsoid. */
function ellipsoidClearance(pointWorld: THREE.Vector3, margin: number) {
  let min = Infinity;
  for (const e of TORSO) {
    const local = bones.get(e.bone as BoneName)!.worldToLocal(pointWorld.clone()).sub(e.center);
    const d = Math.hypot(local.x / (e.radii.x + margin), local.y / (e.radii.y + margin), local.z / (e.radii.z + margin));
    min = Math.min(min, d);
  }
  return min;
}
/** Surface gap in metres between the point sphere and the nearest thigh capsule. */
function thighClearance(pointWorld: THREE.Vector3, margin: number) {
  let min = Infinity;
  for (const side of ["Left", "Right"] as const) {
    const seg = new THREE.Line3(world(`${side}UpperLeg`), world(`${side}LowerLeg`));
    const closest = seg.closestPointToPoint(pointWorld, true, new THREE.Vector3());
    min = Math.min(min, closest.distanceTo(pointWorld) - THIGH_RADIUS - margin);
  }
  return min;
}
function probePoints(withDumbbells: boolean) {
  const points: { p: THREE.Vector3; margin: number }[] = [];
  for (const side of ["Left", "Right"] as const) {
    const hand = bones.get(`${side}Hand`)!;
    points.push({ p: hand.localToWorld(new THREE.Vector3(0, -0.075, 0)), margin: 0.03 });
    if (withDumbbells) {
      const inward = side === "Left" ? -0.07 : 0.07; // plate nearest the body
      points.push({ p: hand.localToWorld(new THREE.Vector3(inward, -0.08, 0)), margin: 0.035 });
    }
  }
  return points;
}

const report: Record<string, unknown>[] = [];
for (const { timeline, clip, maxDrift } of baked) {
  if (maxDrift > 0.005) fail(`${clip.name}: ankle drift ${maxDrift.toFixed(4)} m exceeds 5 mm`);
  const poseFn = POSE_FUNCTIONS[timeline.clipName];
  let floorMin = Infinity;
  let floorMax = -Infinity;
  let minTorsoClearance = Infinity; // ellipsoid units, must stay > 1
  let minThighClearance = Infinity; // metres, must stay > 0
  let minHipsY = Infinity;
  let maxReachZ = -Infinity;
  let minBackZ = Infinity;
  const frames = Math.round(timeline.duration * timeline.fps);
  for (let f = 0; f <= frames; f += 2) {
    const t = f / timeline.fps;
    solvePlantedPose(bones, poseFn(sampleTimeline(timeline.keys, t)));
    const lowest = minSkinnedY(body);
    floorMin = Math.min(floorMin, lowest);
    floorMax = Math.max(floorMax, lowest);
    for (const { p, margin } of probePoints(timeline.clipName === "biceps_curl")) {
      minTorsoClearance = Math.min(minTorsoClearance, ellipsoidClearance(p, margin));
      minThighClearance = Math.min(minThighClearance, thighClearance(p, margin));
    }
    minHipsY = Math.min(minHipsY, world("Hips").y);
    maxReachZ = Math.max(maxReachZ, world("LeftHand").z);
    minBackZ = Math.min(minBackZ, world("Hips").z - 0.12);
  }
  if (floorMin < -0.01 || floorMax > 0.02) {
    fail(`${clip.name}: lowest vertex left the floor band (${floorMin.toFixed(3)}..${floorMax.toFixed(3)} m)`);
  }
  if (minTorsoClearance <= 1) fail(`${clip.name}: a hand/dumbbell penetrates the torso (clearance ${minTorsoClearance.toFixed(3)})`);
  if (minThighClearance <= 0) fail(`${clip.name}: a hand/dumbbell penetrates a thigh (gap ${(minThighClearance * 100).toFixed(1)} cm)`);
  report.push({
    name: clip.name,
    duration: clip.duration,
    fps: timeline.fps,
    markers: timeline.markers,
    qa: {
      ankleDriftM: +maxDrift.toFixed(5),
      lowestVertexM: [+floorMin.toFixed(4), +floorMax.toFixed(4)],
      torsoClearance: +minTorsoClearance.toFixed(3),
      thighGapM: +minThighClearance.toFixed(3),
      minHipsHeightM: +minHipsY.toFixed(3),
      maxHandReachZ: +maxReachZ.toFixed(3),
      minBackZ: +minBackZ.toFixed(3),
    },
  });
  console.log(
    `✓ ${clip.name}: ${clip.duration}s, drift ${(maxDrift * 1000).toFixed(2)} mm, floor ${floorMin.toFixed(3)}..${floorMax.toFixed(3)} m, ` +
      `torso clearance ${minTorsoClearance.toFixed(2)}, thigh gap ${(minThighClearance * 100).toFixed(1)} cm`,
  );
}

// Export in bind pose with the clips embedded.
resetToBindPose(bones);
group.updateMatrixWorld(true);

const exporter = new GLTFExporter();
const glb = (await exporter.parseAsync(group, {
  binary: true,
  animations: baked.map((b) => b.clip),
  onlyVisible: false,
})) as ArrayBuffer;

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, Buffer.from(glb));
const bytes = statSync(OUT).size;

const bounds = new THREE.Box3().setFromObject(group);
writeFileSync(
  META,
  JSON.stringify(
    {
      generator: "scripts/build-mannequin.ts",
      license: "Original procedural asset, part of this repository (see ASSETS.md).",
      units: "metres",
      up: "+Y",
      forward: "+Z",
      bindPose: "standing, arms hanging straight down",
      bytes,
      meshes: [body.name, dumbbells.name],
      vertexCount: body.geometry.getAttribute("position").count + dumbbells.geometry.getAttribute("position").count,
      bones: [...bones.keys()],
      boundsBindPose: { min: bounds.min.toArray().map((n) => +n.toFixed(3)), max: bounds.max.toArray().map((n) => +n.toFixed(3)) },
      clips: report,
    },
    null,
    2,
  ) + "\n",
);
console.log(`✓ wrote ${OUT} (${(bytes / 1024).toFixed(1)} KiB)`);
