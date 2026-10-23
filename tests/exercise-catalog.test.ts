import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { MOTION_TIMELINES } from "@/lib/avatar/motions";
import { EXERCISE_LIST, EXERCISES } from "@/lib/exercises/catalog";
import { ExerciseSchema } from "@/lib/exercises/schema";
import { EXERCISE_IDS } from "@/types/scene";

describe("exercise catalog", () => {
  it("has exactly the allowlisted exercises, each schema-valid", () => {
    expect(Object.keys(EXERCISES).sort()).toEqual([...EXERCISE_IDS].sort());
    for (const e of EXERCISE_LIST) {
      const parsed = ExerciseSchema.safeParse(e);
      expect(parsed.success, `${e.id}: ${parsed.error?.message}`).toBe(true);
    }
  });

  it("phase markers are normalized, ordered and start at 0", () => {
    for (const e of EXERCISE_LIST) {
      const values = Object.values(e.availablePhases) as number[];
      expect(e.availablePhases.start).toBe(0);
      for (const v of values) expect(v).toBeGreaterThanOrEqual(0);
      for (const v of values) expect(v).toBeLessThanOrEqual(1);
    }
  });

  it("lowering exercises have a bottom marker; lifting ones a top and no bottom", () => {
    for (const id of ["squat", "romanian_deadlift", "split_squat", "goblet_squat"] as const) {
      expect(EXERCISES[id].availablePhases.bottom, id).toBeDefined();
      expect(EXERCISES[id].availablePhases.top, id).toBeUndefined();
    }
    for (const id of ["biceps_curl", "shoulder_press", "bent_over_row", "lateral_raise"] as const) {
      expect(EXERCISES[id].availablePhases.top, id).toBeDefined();
      expect(EXERCISES[id].availablePhases.bottom, id).toBeUndefined();
    }
    // The swing has both ends: the back-swing (bottom) comes before the float (top).
    const swing = EXERCISES.kettlebell_swing.availablePhases;
    expect(swing.bottom).toBeLessThan(swing.top!);
  });

  it("dumbbell exercises show the dumbbells, kettlebell exercises exactly one kettlebell", () => {
    for (const e of EXERCISE_LIST) {
      expect(e.props.includes("dumbbells"), e.id).toBe(/dumbbell/i.test(e.title));
      const bells = e.props.filter((p) => p.startsWith("kettlebell"));
      expect(bells.length, e.id).toBe(/kettlebell/i.test(e.title) ? 1 : 0);
    }
  });

  it("gives every exercise its own 'Try asking' prompt", () => {
    const prompts = EXERCISE_LIST.map((e) => e.coachPrompt);
    expect(new Set(prompts).size).toBe(prompts.length);
  });

  type Meta = { clips: { name: string; duration: number; markers: Record<string, number> }[] };
  const readMeta = (file: string) => {
    const path = resolve(__dirname, "../public/models", file);
    expect(existsSync(path), file).toBe(true);
    return JSON.parse(readFileSync(path, "utf8")) as Meta;
  };
  const expectClipMatches = (meta: Meta, e: (typeof EXERCISE_LIST)[number]) => {
    const clip = meta.clips.find((c) => c.name === e.clipName);
    expect(clip, e.clipName).toBeDefined();
    expect(clip!.duration).toBeCloseTo(e.clipDuration, 3);
    for (const [phase, value] of Object.entries(e.availablePhases)) {
      expect(clip!.markers[phase], `${e.id}.${phase}`).toBeCloseTo(value as number, 6);
    }
  };

  it("matches the default body's GLB metadata (rebuild with research/avatar-pipeline/build_avatar.py)", () => {
    const meta = readMeta("mhr-generic.meta.json");
    for (const e of EXERCISE_LIST) expectClipMatches(meta, e);
  });

  it("the wooden mannequin's clips (squat, curl) match its timelines and GLB metadata", () => {
    const meta = readMeta("forma-mannequin.meta.json");
    const withClip = EXERCISE_LIST.filter((e) => MOTION_TIMELINES.some((t) => t.clipName === e.clipName));
    expect(withClip.map((e) => e.id).sort()).toEqual(["biceps_curl", "squat"]);
    for (const e of withClip) {
      const timeline = MOTION_TIMELINES.find((t) => t.clipName === e.clipName)!;
      expect(e.clipDuration).toBe(timeline.duration);
      for (const [phase, value] of Object.entries(e.availablePhases)) {
        expect(value, `${e.id}.${phase}`).toBeCloseTo(timeline.markers[phase], 6);
      }
      expectClipMatches(meta, e);
    }
  });

  it("every exercise carries a medical-scope limitation and pending-review flag is explicit", () => {
    for (const e of EXERCISE_LIST) {
      expect(e.limitations.some((l) => /not medical/i.test(l))).toBe(true);
      expect(["pending_expert_review", "reviewed"]).toContain(e.review.status);
    }
  });
});
