import { z } from "zod";
import { EXERCISE_IDS, PHASES, VIEWS } from "@/types/scene";

const normalized = z.number().min(0).max(1);

export const ExerciseSchema = z.object({
  id: z.enum(EXERCISE_IDS),
  title: z.string().min(1),
  shortTitle: z.string().min(1),
  level: z.enum(["beginner", "intermediate"]),
  /** GLB that contains the clip. Both MVP clips live in one shared-rig GLB. */
  animationUrl: z.string().startsWith("/"),
  /** Name of the AnimationClip inside the GLB. */
  clipName: z.string().min(1),
  /** Clip length in seconds, as authored. Verified against the GLB by tests. */
  clipDuration: z.number().positive(),
  /** Authored phase markers as normalized progress through the clip (0..1). */
  availablePhases: z.partialRecord(z.enum(PHASES), normalized),
  availableViews: z.array(z.enum(VIEWS)).min(1),
  /** View the demo should open in when the exercise is selected manually. */
  defaultView: z.enum(VIEWS),
  /** Scene props to show with this exercise (e.g. dumbbells). */
  props: z.array(z.enum(["dumbbells"])),
  summary: z.string().min(1),
  reviewedCues: z.array(z.string().min(1)).min(3),
  limitations: z.array(z.string().min(1)).min(1),
  review: z.object({
    status: z.enum(["pending_expert_review", "reviewed"]),
    note: z.string(),
  }),
});

export type Exercise = z.infer<typeof ExerciseSchema>;
