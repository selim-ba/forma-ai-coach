import { describe, expect, it } from "vitest";
import { SceneCommandSchema } from "@/lib/scene/commands";
import { applyCommands, INITIAL_SCENE } from "@/lib/scene/reducer";
import type { SceneState } from "@/types/scene";

const run = (commands: unknown[], state: SceneState = INITIAL_SCENE) => applyCommands(state, commands);

describe("SceneCommandSchema", () => {
  it("accepts every allowlisted command shape", () => {
    const valid = [
      { type: "select_exercise", exerciseId: "squat" },
      { type: "select_exercise", exerciseId: "biceps_curl" },
      { type: "play" },
      { type: "pause" },
      { type: "set_speed", speed: 0.5 },
      { type: "set_speed", speed: 1 },
      { type: "set_view", view: "three_quarter" },
      { type: "seek_phase", phase: "bottom" },
      { type: "reset" },
    ];
    for (const c of valid) expect(SceneCommandSchema.safeParse(c).success, JSON.stringify(c)).toBe(true);
  });

  it("rejects unknown types, bad IDs, out-of-range speeds and extra keys", () => {
    const invalid = [
      { type: "select_exercise", exerciseId: "deadlift" },
      { type: "set_speed", speed: 2 },
      { type: "set_speed", speed: 0.25 },
      { type: "set_speed", speed: "1" },
      { type: "set_view", view: "top" },
      { type: "seek_phase", phase: "lockout" },
      { type: "eval", code: "alert(1)" },
      { type: "play", bones: [{ name: "Knee", rotation: 180 }] },
      null,
      "play",
    ];
    for (const c of invalid) expect(SceneCommandSchema.safeParse(c).success, JSON.stringify(c)).toBe(false);
  });
});

describe("applyCommands", () => {
  it("runs the README demo sequence in order", () => {
    const { state, results } = run([
      { type: "select_exercise", exerciseId: "squat" },
      { type: "set_view", view: "side" },
      { type: "set_speed", speed: 0.5 },
      { type: "seek_phase", phase: "bottom" },
      { type: "pause" },
    ]);
    expect(results.every((r) => r.ok)).toBe(true);
    expect(state).toMatchObject({ exerciseId: "squat", view: "side", speed: 0.5, phase: "bottom", playing: false });
    expect(state.seek?.progress).toBe(0.5);
  });

  it("selecting an exercise resets to its start, paused", () => {
    const playing = run([{ type: "play" }]).state;
    const { state } = run([{ type: "select_exercise", exerciseId: "biceps_curl" }], playing);
    expect(state).toMatchObject({ exerciseId: "biceps_curl", playing: false, phase: "start" });
    expect(state.seek?.progress).toBe(0);
  });

  it("rejects phases the current exercise does not define, but keeps valid commands", () => {
    const { state, results } = run([
      { type: "select_exercise", exerciseId: "biceps_curl" },
      { type: "seek_phase", phase: "bottom" },
      { type: "play" },
    ]);
    expect(results.map((r) => r.ok)).toEqual([true, false, true]);
    expect(results[1]).toMatchObject({ ok: false, reason: "unsupported_phase" });
    expect(state).toMatchObject({ exerciseId: "biceps_curl", playing: true });
  });

  it("validates seek_phase against the exercise selected earlier in the same batch", () => {
    const curl = run([{ type: "select_exercise", exerciseId: "biceps_curl" }]).state;
    const { results } = run(
      [
        { type: "select_exercise", exerciseId: "squat" },
        { type: "seek_phase", phase: "bottom" },
      ],
      curl,
    );
    expect(results.every((r) => r.ok)).toBe(true);
  });

  it("issues a fresh seek nonce each time so repeated seeks re-apply", () => {
    const a = run([{ type: "seek_phase", phase: "bottom" }]).state;
    const b = run([{ type: "seek_phase", phase: "bottom" }], a).state;
    expect(b.seek!.nonce).toBeGreaterThan(a.seek!.nonce);
  });

  it("re-selecting the same view bumps viewNonce (camera re-centres)", () => {
    const a = run([{ type: "set_view", view: "side" }]).state;
    const b = run([{ type: "set_view", view: "side" }], a).state;
    expect(b.viewNonce).toBe(a.viewNonce + 1);
  });

  it("reset restores defaults but keeps the selected exercise", () => {
    const changed = run([
      { type: "select_exercise", exerciseId: "biceps_curl" },
      { type: "set_view", view: "side" },
      { type: "set_speed", speed: 0.5 },
      { type: "play" },
    ]).state;
    const { state } = run([{ type: "reset" }], changed);
    expect(state).toMatchObject({ exerciseId: "biceps_curl", view: "front", speed: 1, playing: false, phase: "start" });
  });

  it("caps the number of commands per batch", () => {
    const many = Array.from({ length: 12 }, () => ({ type: "play" }));
    const { results } = run(many);
    expect(results.filter((r) => r.ok)).toHaveLength(8);
    expect(results.filter((r) => !r.ok && r.reason === "too_many_commands")).toHaveLength(4);
  });

  it("never mutates the input state", () => {
    const before = structuredClone(INITIAL_SCENE);
    run([{ type: "set_view", view: "side" }, { type: "play" }]);
    expect(INITIAL_SCENE).toEqual(before);
  });
});
