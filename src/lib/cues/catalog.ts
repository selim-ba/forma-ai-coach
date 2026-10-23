import type { CueId } from "@/types/cues";
import type { ExerciseId } from "@/types/scene";

/**
 * Visual form cues: reviewed, pre-authored overlays the app draws on the
 * moving avatar. The coach only chooses *which* cue ids to show; every shape,
 * position and word is defined here, attached to joints, so nothing is
 * generated freehand. Each cue illustrates one of the exercise's reviewed
 * coaching cues and carries the same review status.
 */

/** Rig-independent joint names (mapped to MHR and mannequin bones in CueOverlay). */
export type CueJoint =
  | "pelvis"
  | "neck"
  | "head"
  | "l_shoulder"
  | "r_shoulder"
  | "l_elbow"
  | "r_elbow"
  | "l_wrist"
  | "r_wrist"
  | "l_hip"
  | "r_hip"
  | "l_knee"
  | "r_knee"
  | "l_ankle"
  | "r_ankle"
  | "l_toe"
  | "r_toe";

/** A point on the avatar: a joint plus an optional offset in metres (x: avatar's left, y: up, z: forward). */
export type Anchor = { joint: CueJoint; offset?: [number, number, number] };

export type CueShape =
  | { kind: "arrow"; from: Anchor; to: Anchor }
  | { kind: "line"; from: Anchor; to: Anchor; dashed?: boolean }
  | { kind: "ring"; at: Anchor; radius?: number };

export type CueDef = {
  id: CueId;
  exerciseId: ExerciseId;
  /** Short caption drawn next to the shapes. */
  label: string;
  labelAt: Anchor;
  /** Which reviewed catalog cue this visualises (for the coach and for reviewers). */
  illustrates: string;
  /** While playing, only shown in this part of the clip (normalized progress). Always shown when paused. */
  window?: [number, number];
  shapes: CueShape[];
};

const j = (joint: CueJoint, offset?: [number, number, number]): Anchor => ({ joint, offset });
const both = (make: (side: "l" | "r") => CueShape[]): CueShape[] => [...make("l"), ...make("r")];
/** The descent/lowering part of the squat-rhythm clips (0.3 s → 2.2 s of 4 s). */
const LOWERING: [number, number] = [0.05, 0.55];
/** The lifting part of the curl-rhythm clips (0.3 s → 1.9 s of 4 s). */
const LIFTING: [number, number] = [0.05, 0.47];

export const CUES: Record<CueId, CueDef> = {
  "squat.knees_over_toes": {
    id: "squat.knees_over_toes",
    exerciseId: "squat",
    label: "Knees follow the toes",
    labelAt: j("l_knee", [0.2, 0.05, 0.12]),
    illustrates: "Let your knees travel in the same direction as your toes.",
    shapes: both((s) => [
      { kind: "line", from: j(`${s}_toe`), to: j(`${s}_toe`, [0, 0.55, 0]), dashed: true },
      { kind: "ring", at: j(`${s}_knee`, [0, 0, 0.05]) },
    ]),
  },
  "squat.hips_back": {
    id: "squat.hips_back",
    exerciseId: "squat",
    label: "Hips back and down",
    labelAt: j("pelvis", [0, 0.2, -0.42]),
    illustrates: "Send the hips back and down while keeping your chest up and back neutral.",
    window: LOWERING,
    shapes: [{ kind: "arrow", from: j("pelvis", [0, 0.02, -0.12]), to: j("pelvis", [0, -0.16, -0.4]) }],
  },
  "squat.chest_up": {
    id: "squat.chest_up",
    exerciseId: "squat",
    label: "Chest up, back neutral",
    labelAt: j("neck", [0, 0.12, -0.18]),
    illustrates: "Send the hips back and down while keeping your chest up and back neutral.",
    shapes: [{ kind: "line", from: j("pelvis", [0, 0, -0.08]), to: j("neck", [0, 0, -0.06]) }],
  },
  "curl.elbows_pinned": {
    id: "curl.elbows_pinned",
    exerciseId: "biceps_curl",
    label: "Elbows stay by your sides",
    labelAt: j("l_elbow", [0.22, 0, 0]),
    illustrates: "Keep your upper arms close to your sides; only your forearms move.",
    shapes: both((s) => [
      { kind: "line", from: j(`${s}_shoulder`), to: j(`${s}_elbow`) },
      { kind: "ring", at: j(`${s}_elbow`) },
    ]),
  },
  "curl.still_torso": {
    id: "curl.still_torso",
    exerciseId: "biceps_curl",
    label: "No swinging",
    labelAt: j("neck", [0, 0.15, -0.2]),
    illustrates: "Curl up under control without swinging your torso or leaning back.",
    shapes: [{ kind: "line", from: j("pelvis", [0, -0.05, -0.12]), to: j("pelvis", [0, 0.7, -0.12]), dashed: true }],
  },
  "press.straight_up": {
    id: "press.straight_up",
    exerciseId: "shoulder_press",
    label: "Press straight up",
    labelAt: j("r_wrist", [-0.22, -0.18, 0]),
    illustrates: "Press the dumbbells up and slightly in until your arms are straight overhead, without snapping the elbows.",
    window: LIFTING,
    shapes: both((s) => [{ kind: "arrow", from: j(`${s}_wrist`, [0, 0.08, 0]), to: j(`${s}_wrist`, [0, 0.3, 0]) }]),
  },
  "press.ribs_down": {
    id: "press.ribs_down",
    exerciseId: "shoulder_press",
    label: "Ribs down, no leaning back",
    labelAt: j("pelvis", [0.25, 0.25, 0]),
    illustrates: "Keep your head still and your ribs down; don't lean back to finish the press.",
    shapes: [{ kind: "line", from: j("pelvis", [0, -0.05, -0.12]), to: j("pelvis", [0, 0.75, -0.12]), dashed: true }],
  },
  "rdl.flat_back": {
    id: "rdl.flat_back",
    exerciseId: "romanian_deadlift",
    label: "Flat back",
    labelAt: j("neck", [0, 0.16, 0]),
    illustrates: "Push your hips back and let your torso tip forward with a flat back and a neutral neck.",
    shapes: [{ kind: "line", from: j("pelvis", [0, 0.02, -0.1]), to: j("head", [0, 0, -0.08]) }],
  },
  "rdl.hips_back": {
    id: "rdl.hips_back",
    exerciseId: "romanian_deadlift",
    label: "Hips back",
    labelAt: j("pelvis", [0, 0.12, -0.38]),
    illustrates: "Push your hips back and let your torso tip forward with a flat back and a neutral neck.",
    window: LOWERING,
    shapes: [{ kind: "arrow", from: j("pelvis", [0, 0, -0.1]), to: j("pelvis", [0, 0, -0.34]) }],
  },
  "rdl.close_to_legs": {
    id: "rdl.close_to_legs",
    exerciseId: "romanian_deadlift",
    label: "Weights close to the legs",
    labelAt: j("r_knee", [-0.25, 0, 0.2]),
    illustrates: "Keep the dumbbells close to your legs as they lower.",
    shapes: both((s) => [{ kind: "line", from: j(`${s}_wrist`), to: j(`${s}_wrist`, [0, -1.2, 0]), dashed: true }]),
  },
  "split.straight_down": {
    id: "split.straight_down",
    exerciseId: "split_squat",
    label: "Lower straight down",
    labelAt: j("pelvis", [0.3, 0, 0]),
    illustrates: "Lower straight down by bending both knees, as if your back knee is heading for the floor.",
    window: LOWERING,
    shapes: [{ kind: "arrow", from: j("pelvis", [0, -0.05, 0]), to: j("pelvis", [0, -0.3, 0]) }],
  },
  "split.front_knee": {
    id: "split.front_knee",
    exerciseId: "split_squat",
    label: "Front knee follows the toes",
    labelAt: j("l_knee", [0.22, 0.05, 0.1]),
    illustrates: "Let your front knee travel in the same direction as your toes.",
    shapes: [
      { kind: "line", from: j("l_toe"), to: j("l_toe", [0, 0.55, 0]), dashed: true },
      { kind: "ring", at: j("l_knee", [0, 0, 0.05]) },
    ],
  },
  "split.tall_torso": {
    id: "split.tall_torso",
    exerciseId: "split_squat",
    label: "Torso tall",
    labelAt: j("neck", [0, 0.15, -0.2]),
    illustrates: "Keep your torso tall and most of your weight over the front foot.",
    shapes: [{ kind: "line", from: j("pelvis", [0, 0, -0.1]), to: j("neck", [0, 0, -0.08]) }],
  },
  "goblet.elbows_down": {
    id: "goblet.elbows_down",
    exerciseId: "goblet_squat",
    label: "Elbows down, bell close",
    labelAt: j("l_elbow", [0.24, -0.04, 0.05]),
    illustrates: "Hold the kettlebell by the horns, close to your chest, elbows pointing down.",
    shapes: both((s) => [
      { kind: "ring", at: j(`${s}_elbow`) },
      { kind: "line", from: j(`${s}_elbow`), to: j(`${s}_elbow`, [0, -0.22, 0]), dashed: true },
    ]),
  },
  "goblet.chest_up": {
    id: "goblet.chest_up",
    exerciseId: "goblet_squat",
    label: "Chest up",
    labelAt: j("neck", [0, 0.12, -0.18]),
    illustrates: "Sit down between your heels, keeping your chest up and the kettlebell close.",
    shapes: [{ kind: "line", from: j("pelvis", [0, 0, -0.08]), to: j("neck", [0, 0, -0.06]) }],
  },
  "goblet.knees_over_toes": {
    id: "goblet.knees_over_toes",
    exerciseId: "goblet_squat",
    label: "Knees follow the toes",
    labelAt: j("r_knee", [-0.2, 0.05, 0.12]),
    illustrates: "Let your knees travel in the same direction as your toes.",
    shapes: both((s) => [
      { kind: "line", from: j(`${s}_toe`), to: j(`${s}_toe`, [0, 0.55, 0]), dashed: true },
      { kind: "ring", at: j(`${s}_knee`, [0, 0, 0.05]) },
    ]),
  },
  "swing.flat_back": {
    id: "swing.flat_back",
    exerciseId: "kettlebell_swing",
    label: "Hinge, flat back",
    labelAt: j("neck", [0, 0.16, 0]),
    illustrates: "Hinge at the hips and hike the kettlebell back between your legs, keeping your back flat.",
    shapes: [{ kind: "line", from: j("pelvis", [0, 0.02, -0.1]), to: j("head", [0, 0, -0.08]) }],
  },
  "swing.hip_drive": {
    id: "swing.hip_drive",
    exerciseId: "kettlebell_swing",
    label: "Snap the hips forward",
    labelAt: j("pelvis", [0, 0.14, -0.42]),
    illustrates: "Drive your hips forward powerfully to stand tall; the arms just guide the bell.",
    window: [0.28, 0.56],
    shapes: [{ kind: "arrow", from: j("pelvis", [0, 0, -0.4]), to: j("pelvis", [0, 0, -0.13]) }],
  },
  "swing.chest_height": {
    id: "swing.chest_height",
    exerciseId: "kettlebell_swing",
    label: "Floats to chest height",
    labelAt: j("neck", [0.22, -0.1, 0.55]),
    illustrates: "Let the kettlebell float to about chest height, without lifting it with your arms.",
    window: [0.4, 0.7],
    shapes: [{ kind: "line", from: j("neck", [0, -0.16, 0.12]), to: j("neck", [0, -0.16, 0.8]), dashed: true }],
  },
  "row.flat_back": {
    id: "row.flat_back",
    exerciseId: "bent_over_row",
    label: "Flat back, soft knees",
    labelAt: j("neck", [0, 0.16, 0]),
    illustrates: "Hinge forward at the hips with soft knees and a flat back, dumbbells hanging under your shoulders.",
    shapes: [{ kind: "line", from: j("pelvis", [0, 0.02, -0.1]), to: j("head", [0, 0, -0.08]) }],
  },
  "row.elbows_back": {
    id: "row.elbows_back",
    exerciseId: "bent_over_row",
    label: "Lead with the elbows",
    labelAt: j("l_elbow", [0.24, 0.12, 0]),
    illustrates: "Pull the dumbbells towards your waist, leading with your elbows.",
    window: LIFTING,
    shapes: both((s) => [{ kind: "arrow", from: j(`${s}_elbow`, [0, 0.04, 0]), to: j(`${s}_elbow`, [0, 0.26, -0.06]) }]),
  },
  "raise.shoulder_height": {
    id: "raise.shoulder_height",
    exerciseId: "lateral_raise",
    label: "Up to shoulder height",
    labelAt: j("l_shoulder", [0.35, -0.13, 0.25]),
    illustrates: "Raise your arms out to the sides, slightly in front of your body, up to about shoulder height.",
    shapes: [{ kind: "line", from: j("l_shoulder", [0.72, 0, 0.22]), to: j("r_shoulder", [-0.72, 0, 0.22]), dashed: true }],
  },
  "raise.shoulders_down": {
    id: "raise.shoulders_down",
    exerciseId: "lateral_raise",
    label: "Shoulders down",
    labelAt: j("l_shoulder", [0.34, 0.16, 0]),
    illustrates: "Lead with your elbows and keep your shoulders down, away from your ears.",
    shapes: both((s) => [{ kind: "arrow", from: j(`${s}_shoulder`, [0, 0.24, 0]), to: j(`${s}_shoulder`, [0, 0.07, 0]) }]),
  },
  "raise.no_swing": {
    id: "raise.no_swing",
    exerciseId: "lateral_raise",
    label: "No swinging",
    labelAt: j("pelvis", [-0.32, 0.25, -0.12]),
    illustrates: "Don't swing or lean back to lift the weights.",
    shapes: [{ kind: "line", from: j("pelvis", [0, -0.05, -0.12]), to: j("pelvis", [0, 0.7, -0.12]), dashed: true }],
  },
};

export function cuesFor(exerciseId: ExerciseId): CueDef[] {
  return Object.values(CUES).filter((c) => c.exerciseId === exerciseId);
}
