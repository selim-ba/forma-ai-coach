import { z } from "zod";
import { CUE_IDS, MAX_CUES } from "@/types/cues";
import {
  COMMAND_TYPES,
  EXERCISE_IDS,
  PHASES,
  SPEEDS,
  VIEWS,
  type SceneCommand,
} from "@/types/scene";

export const CONTROL_SCENE_TOOL_NAME = "control_scene";

/**
 * Strict function-tool schema for the Responses API.
 *
 * Strict mode requires every property to be listed in `required` and
 * `additionalProperties: false`, so each command is a flat object whose
 * unused arguments are `null`. The server converts it to the `SceneCommand`
 * union with `toSceneCommand` and validates it again with Zod.
 */
export const CONTROL_SCENE_TOOL = {
  type: "function" as const,
  name: CONTROL_SCENE_TOOL_NAME,
  description:
    "Control the Gym3DBeta 3D exercise viewer. Commands run in order in the user's browser. " +
    "Use select_exercise before seek_phase or show_cues when switching exercise. Only phases and cue ids listed for the exercise in the catalog are valid. " +
    "Set every argument that a command type does not use to null. " +
    "Put the short user-facing answer in `reply`; it is shown as-is if every command is accepted.",
  strict: true,
  parameters: {
    type: "object",
    additionalProperties: false,
    required: ["commands", "reply"],
    properties: {
      reply: {
        type: "string",
        description: "1–3 short sentences for the user, written as if the commands have already run.",
      },
      commands: {
        type: "array",
        description: "1 to 8 scene commands, executed in order.",
        items: {
          type: "object",
          additionalProperties: false,
          required: ["type", "exerciseId", "view", "speed", "phase", "cueIds"],
          properties: {
            type: { type: "string", enum: [...COMMAND_TYPES] },
            exerciseId: {
              type: ["string", "null"],
              enum: [...EXERCISE_IDS, null],
              description: "Required for select_exercise, otherwise null.",
            },
            view: {
              type: ["string", "null"],
              enum: [...VIEWS, null],
              description: "Required for set_view, otherwise null.",
            },
            speed: {
              type: ["number", "null"],
              enum: [...SPEEDS, null],
              description: "Required for set_speed (0.5 or 1), otherwise null.",
            },
            phase: {
              type: ["string", "null"],
              enum: [...PHASES, null],
              description: "Required for seek_phase, otherwise null.",
            },
            cueIds: {
              type: ["array", "null"],
              items: { type: "string", enum: [...CUE_IDS] },
              description: `Required for show_cues: 1 to ${MAX_CUES} visual cue ids of the current exercise. Otherwise null.`,
            },
          },
        },
      },
    },
  },
};

const FlatCommandSchema = z.object({
  type: z.enum(COMMAND_TYPES),
  exerciseId: z.enum(EXERCISE_IDS).nullable().optional(),
  view: z.enum(VIEWS).nullable().optional(),
  speed: z.number().nullable().optional(),
  phase: z.enum(PHASES).nullable().optional(),
  cueIds: z.array(z.string()).nullable().optional(),
});

export const ControlSceneArgsSchema = z.object({
  commands: z.array(z.unknown()).min(1).max(32),
  /** Optional so older/partial calls still validate; strict mode always sends it. */
  reply: z.string().max(2000).optional(),
});

/**
 * Convert one flat tool-call command into the app's command union.
 * Returns the raw object unchanged when it cannot be converted, so the
 * reducer's own Zod validation reports a precise rejection.
 */
export function toSceneCommand(raw: unknown): SceneCommand | unknown {
  const parsed = FlatCommandSchema.safeParse(raw);
  if (!parsed.success) return raw;
  const c = parsed.data;
  switch (c.type) {
    case "select_exercise":
      return { type: c.type, exerciseId: c.exerciseId };
    case "set_view":
      return { type: c.type, view: c.view };
    case "set_speed":
      return { type: c.type, speed: c.speed };
    case "seek_phase":
      return { type: c.type, phase: c.phase };
    case "show_cues":
      return { type: c.type, cueIds: c.cueIds };
    default:
      return { type: c.type };
  }
}
