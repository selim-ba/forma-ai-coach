import { z } from "zod";
import { CUE_IDS, MAX_CUES } from "@/types/cues";
import {
  EXERCISE_IDS,
  PHASES,
  VIEWS,
  type SceneCommand,
} from "@/types/scene";

/** Upper bound on commands accepted from a single coach reply or UI action. */
export const MAX_COMMANDS = 8;

export const SpeedSchema = z.union([z.literal(0.5), z.literal(1)]);

export const SceneCommandSchema = z.discriminatedUnion("type", [
  z.strictObject({ type: z.literal("select_exercise"), exerciseId: z.enum(EXERCISE_IDS) }),
  z.strictObject({ type: z.literal("play") }),
  z.strictObject({ type: z.literal("pause") }),
  z.strictObject({ type: z.literal("set_speed"), speed: SpeedSchema }),
  z.strictObject({ type: z.literal("set_view"), view: z.enum(VIEWS) }),
  z.strictObject({ type: z.literal("seek_phase"), phase: z.enum(PHASES) }),
  z.strictObject({ type: z.literal("reset") }),
  z.strictObject({ type: z.literal("show_cues"), cueIds: z.array(z.enum(CUE_IDS)).min(1).max(MAX_CUES) }),
  z.strictObject({ type: z.literal("clear_cues") }),
]) satisfies z.ZodType<SceneCommand>;

export const SceneSnapshotSchema = z.strictObject({
    exerciseId: z.enum(EXERCISE_IDS),
    playing: z.boolean(),
    speed: SpeedSchema,
    view: z.enum(VIEWS),
    phase: z.enum(PHASES).nullable().default(null),
    cues: z.array(z.enum(CUE_IDS)).max(MAX_CUES).default([]),
  });

const VIEW_LABEL: Record<(typeof VIEWS)[number], string> = {
  front: "front",
  side: "side",
  three_quarter: "¾",
};

/** Human-readable label for the action log. */
export function describeCommand(command: SceneCommand): string {
  switch (command.type) {
    case "select_exercise":
      return `select ${command.exerciseId.replace("_", " ")}`;
    case "set_speed":
      return `speed ${command.speed}×`;
    case "set_view":
      return `view ${VIEW_LABEL[command.view]}`;
    case "seek_phase":
      return `seek ${command.phase}`;
    case "show_cues":
      return `show ${command.cueIds.map((id) => id.split(".")[1].replace(/_/g, " ")).join(", ")}`;
    case "clear_cues":
      return "clear cues";
    default:
      return command.type;
  }
}
