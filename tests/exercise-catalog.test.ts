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

  it("squat has a bottom marker; curl has a top but no bottom", () => {
    expect(EXERCISES.squat.availablePhases.bottom).toBeDefined();
    expect(EXERCISES.biceps_curl.availablePhases.top).toBeDefined();
    expect(EXERCISES.biceps_curl.availablePhases.bottom).toBeUndefined();
  });

  it("markers and durations match the authored motion timelines", () => {
    for (const e of EXERCISE_LIST) {
      const timeline = MOTION_TIMELINES.find((t) => t.clipName === e.clipName);
      expect(timeline, e.clipName).toBeDefined();
      expect(e.clipDuration).toBe(timeline!.duration);
      for (const [phase, value] of Object.entries(e.availablePhases)) {
        expect(value, `${e.id}.${phase}`).toBeCloseTo(timeline!.markers[phase], 6);
      }
    }
  });

  it("matches the generated GLB metadata (run `npm run assets:build` after changing motions)", () => {
    const metaPath = resolve(__dirname, "../public/models/forma-mannequin.meta.json");
    expect(existsSync(metaPath)).toBe(true);
    const meta = JSON.parse(readFileSync(metaPath, "utf8")) as {
      clips: { name: string; duration: number; markers: Record<string, number> }[];
    };
    for (const e of EXERCISE_LIST) {
      const clip = meta.clips.find((c) => c.name === e.clipName);
      expect(clip, e.clipName).toBeDefined();
      expect(clip!.duration).toBeCloseTo(e.clipDuration, 3);
      for (const [phase, value] of Object.entries(e.availablePhases)) {
        expect(clip!.markers[phase]).toBeCloseTo(value as number, 6);
      }
    }
  });

  it("every exercise carries a medical-scope limitation and pending-review flag is explicit", () => {
    for (const e of EXERCISE_LIST) {
      expect(e.limitations.some((l) => /not medical/i.test(l))).toBe(true);
      expect(["pending_expert_review", "reviewed"]).toContain(e.review.status);
    }
  });
});
