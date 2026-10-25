import type { CueId } from "./cues";

/**
 * Core scene vocabulary. These literal lists are the single source of truth for
 * every allowlist in the app (Zod schemas, the GPT tool schema, the UI).
 */
export const EXERCISE_IDS = [
  "squat",
  "biceps_curl",
  "shoulder_press",
  "romanian_deadlift",
  "split_squat",
  "kettlebell_swing",
  "lateral_raise",
] as const;
export type ExerciseId = (typeof EXERCISE_IDS)[number];

export const VIEWS = ["front", "side", "three_quarter"] as const;
export type View = (typeof VIEWS)[number];

export const PHASES = ["start", "middle", "bottom", "top"] as const;
export type Phase = (typeof PHASES)[number];

export const SPEEDS = [0.5, 1] as const;
export type Speed = (typeof SPEEDS)[number];

export const COMMAND_TYPES = [
  "select_exercise",
  "play",
  "pause",
  "set_speed",
  "set_view",
  "seek_phase",
  "reset",
  "show_cues",
  "clear_cues",
] as const;
export type CommandType = (typeof COMMAND_TYPES)[number];

export type SceneCommand =
  | { type: "select_exercise"; exerciseId: ExerciseId }
  | { type: "play" }
  | { type: "pause" }
  | { type: "set_speed"; speed: Speed }
  | { type: "set_view"; view: View }
  | { type: "seek_phase"; phase: Phase }
  | { type: "reset" }
  /** Draw these form cues on the avatar (replaces the current ones). */
  | { type: "show_cues"; cueIds: CueId[] }
  | { type: "clear_cues" };

/** A one-shot request to move the playhead (normalized 0..1 of the clip). */
export type SeekRequest = { progress: number; nonce: number };

export type SceneState = {
  exerciseId: ExerciseId;
  playing: boolean;
  speed: Speed;
  view: View;
  /** Last phase marker the playhead was moved to; null once playback resumes. */
  phase: Phase | null;
  /** Incremented every time a view preset is (re)applied so the camera re-snaps. */
  viewNonce: number;
  seek: SeekRequest | null;
  /** Visual form cues currently drawn on the avatar (all belong to exerciseId). */
  cues: CueId[];
};

/** The subset of scene state the browser sends to the coach endpoint. */
export type SceneSnapshot = Pick<SceneState, "exerciseId" | "playing" | "speed" | "view" | "phase" | "cues">;

export type CommandSource = "manual" | "coach";

export type RejectionReason =
  | "invalid_command"
  | "unsupported_phase"
  | "unsupported_cue"
  | "too_many_commands";

export type CommandResult =
  | { ok: true; command: SceneCommand }
  | { ok: false; command: unknown; reason: RejectionReason; detail: string };
