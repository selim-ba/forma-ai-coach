import { describe, expect, it } from "vitest";
import { CUES, cuesFor } from "@/lib/cues/catalog";
import { EXERCISE_LIST, EXERCISES } from "@/lib/exercises/catalog";
import { CONTROL_SCENE_TOOL } from "@/lib/openai/tools";
import { CUE_IDS } from "@/types/cues";

describe("visual cue catalog", () => {
  it("defines every allowlisted cue exactly once, under its own id", () => {
    expect(Object.keys(CUES).sort()).toEqual([...CUE_IDS].sort());
    for (const [id, cue] of Object.entries(CUES)) expect(cue.id).toBe(id);
  });

  it("gives every exercise at least two cues, each illustrating one of its reviewed cues", () => {
    for (const e of EXERCISE_LIST) {
      const cues = cuesFor(e.id);
      expect(cues.length, e.id).toBeGreaterThanOrEqual(2);
      for (const c of cues) expect(EXERCISES[c.exerciseId].reviewedCues, c.id).toContain(c.illustrates);
    }
  });

  it("uses sane time windows and has at least one shape", () => {
    for (const c of Object.values(CUES)) {
      expect(c.shapes.length, c.id).toBeGreaterThan(0);
      if (c.window) {
        expect(c.window[0]).toBeGreaterThanOrEqual(0);
        expect(c.window[1]).toBeLessThanOrEqual(1);
        expect(c.window[0]).toBeLessThan(c.window[1]);
      }
    }
  });

  it("exposes the same cue ids in the strict GPT tool schema", () => {
    const items = CONTROL_SCENE_TOOL.parameters.properties.commands.items;
    expect(items.required).toContain("cueIds");
    expect(items.properties.cueIds.items.enum).toEqual([...CUE_IDS]);
  });
});
