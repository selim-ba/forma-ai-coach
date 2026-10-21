/**
 * Hand-authored, deterministic exercise motions for the Forma mannequin.
 *
 * Every pose is described as joint angles in the sagittal plane (degrees),
 * driven by a single 0..1 "effort" curve per exercise. Feet are planted by
 * forward kinematics when the clip is baked (see mannequin.ts), so the hips
 * translate to keep both ankles fixed on the floor.
 *
 * Sign convention (right-handed, Y up, character faces +Z):
 *   positive pitch about X tilts a bone's +Y axis toward +Z (forward).
 *   A bone hanging down (−Y) swings FORWARD with a NEGATIVE pitch.
 */

export type Key = { t: number; v: number };

export type MotionTimeline = {
  clipName: string;
  duration: number;
  fps: number;
  keys: Key[];
  /** Normalized marker positions; must match the exercise catalog. */
  markers: Record<string, number>;
};

/** Squat: 0.3 s stand, 1.5 s descent, 0.4 s hold, 1.5 s rise, 0.3 s stand. */
export const SQUAT_TIMELINE: MotionTimeline = {
  clipName: "squat",
  duration: 4,
  fps: 30,
  keys: [
    { t: 0, v: 0 },
    { t: 0.3, v: 0 },
    { t: 1.8, v: 1 },
    { t: 2.2, v: 1 },
    { t: 3.7, v: 0 },
    { t: 4, v: 0 },
  ],
  markers: { start: 0, middle: 1.05 / 4, bottom: 2.0 / 4 },
};

/** Curl: 0.3 s rest, 1.2 s lift, 0.4 s squeeze, 1.8 s lower, 0.3 s rest. */
export const CURL_TIMELINE: MotionTimeline = {
  clipName: "biceps_curl",
  duration: 4,
  fps: 30,
  keys: [
    { t: 0, v: 0 },
    { t: 0.3, v: 0 },
    { t: 1.5, v: 1 },
    { t: 1.9, v: 1 },
    { t: 3.7, v: 0 },
    { t: 4, v: 0 },
  ],
  markers: { start: 0, middle: 0.9 / 4, top: 1.7 / 4 },
};

export const MOTION_TIMELINES = [SQUAT_TIMELINE, CURL_TIMELINE];

const easeInOutSine = (x: number) => -(Math.cos(Math.PI * x) - 1) / 2;

export function sampleTimeline(keys: Key[], t: number): number {
  if (t <= keys[0].t) return keys[0].v;
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i];
    const b = keys[i + 1];
    if (t <= b.t) {
      const span = b.t - a.t;
      const x = span === 0 ? 1 : (t - a.t) / span;
      return a.v + (b.v - a.v) * easeInOutSine(x);
    }
  }
  return keys[keys.length - 1].v;
}

/** Local joint rotations in degrees. x = pitch (sagittal), z = roll (frontal). */
export type JointAngles = { x?: number; y?: number; z?: number };
export type Pose = Partial<Record<BoneName, JointAngles>>;

export const BONE_NAMES = [
  "Root",
  "Hips",
  "Spine",
  "Chest",
  "Neck",
  "Head",
  "LeftUpperArm",
  "LeftLowerArm",
  "LeftHand",
  "RightUpperArm",
  "RightLowerArm",
  "RightHand",
  "LeftUpperLeg",
  "LeftLowerLeg",
  "LeftFoot",
  "RightUpperLeg",
  "RightLowerLeg",
  "RightFoot",
] as const;
export type BoneName = (typeof BONE_NAMES)[number];

function symmetric(pose: Pose, angles: Record<string, JointAngles>) {
  for (const [segment, a] of Object.entries(angles)) {
    const left = `Left${segment}` as BoneName;
    const right = `Right${segment}` as BoneName;
    pose[left] = { ...a };
    // Mirror roll (frontal plane) for the right side.
    pose[right] = { ...a, z: a.z !== undefined ? -a.z : undefined, y: a.y !== undefined ? -a.y : undefined };
  }
  return pose;
}

/**
 * Bodyweight squat to just above parallel. `s` = depth (0 standing, 1 bottom).
 * World-space targets at the bottom: torso lean 38°, thigh 78° from vertical,
 * shin 34° forward, arms reaching forward to ~shoulder height for balance.
 */
export function squatPose(s: number): Pose {
  const hipsPitch = 34 * s; // pelvis/torso forward lean (world)
  const spinePitch = 4 * s;
  const torsoWorld = hipsPitch + spinePitch; // chest world pitch
  const thighWorld = -78 * s; // thigh swings forward
  const shinWorld = 34 * s; // shin leans forward (knee over toes region)
  const armWorld = -82 * s; // shoulder flexion, arms forward

  const pose: Pose = {
    Hips: { x: hipsPitch },
    Spine: { x: spinePitch },
    Chest: { x: 0 },
    Neck: { x: -22 * s }, // keep the gaze forward-down rather than at the floor
    Head: { x: -8 * s },
  };
  symmetric(pose, {
    UpperLeg: { x: thighWorld - hipsPitch },
    LowerLeg: { x: shinWorld - thighWorld },
  });
  symmetric(pose, { Foot: { x: -shinWorld } });
  symmetric(pose, {
    UpperArm: { x: armWorld - torsoWorld, z: 6 },
    LowerArm: { x: -8 },
  });
  symmetric(pose, { Hand: { x: 0 } });
  return pose;
}

/**
 * Standing two-arm dumbbell curl. `c` = curl amount (0 extended, 1 top).
 * Upper arms stay by the sides (small forward drift at the top); elbows flex
 * from ~12° to ~140°. The rest of the body is still.
 */
export function curlPose(c: number): Pose {
  const pose: Pose = {
    Hips: { x: 0 },
    Spine: { x: 0 },
    Chest: { x: 0 },
    Neck: { x: 0 },
    Head: { x: 0 },
  };
  symmetric(pose, { UpperLeg: { x: 0 }, LowerLeg: { x: 0 } });
  symmetric(pose, { Foot: { x: 0 } });
  symmetric(pose, {
    UpperArm: { x: -3 - 6 * c, z: 10 },
    LowerArm: { x: -(12 + 128 * c) },
  });
  symmetric(pose, { Hand: { x: -6 * c } });
  return pose;
}

export const POSE_FUNCTIONS: Record<string, (v: number) => Pose> = {
  squat: squatPose,
  biceps_curl: curlPose,
};
