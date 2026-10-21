import { EXERCISES } from "@/lib/exercises/catalog";
import type { ExerciseId, SceneSnapshot } from "@/types/scene";

/**
 * Deterministic, keyword-based stand-in for GPT, used when COACH_MODE=mock
 * (local development without an API key, automated e2e tests, offline demo
 * rehearsal). Its output goes through exactly the same validation as GPT's.
 * It is clearly labelled "mock" in the UI and is not the product's coach.
 */
export function mockCoach(message: string, scene: SceneSnapshot): { message: string; commands: unknown[] } {
  const text = message.toLowerCase();
  const has = (...words: (string | RegExp)[]) =>
    words.some((w) => (typeof w === "string" ? text.includes(w) : w.test(text)));

  if (has(/backwards?|hyperextend|wrong way|\bbreak\b|\bsnap\b/)) {
    return {
      message:
        "I can't show unsafe or anatomically impossible movement. I can show the squat or biceps curl with good control instead.",
      commands: [],
    };
  }
  if (has("pain", "hurt", "injur", "sore knee", "doctor")) {
    return {
      message:
        "I can't assess pain or injuries. Please stop if something hurts and check with a doctor or physiotherapist.",
      commands: [],
    };
  }
  if (has(/\b(deadlifts?|bench|lunges?|push.?ups?|pull.?ups?|planks?|rows?|rowing|press(es)?|burpees?|jumps?|jumping)\b/)) {
    return {
      message: "That exercise isn't available yet. I can show a beginner squat or a dumbbell biceps curl.",
      commands: [],
    };
  }

  let exerciseId: ExerciseId = scene.exerciseId;
  const commands: unknown[] = [];
  if (has("squat")) exerciseId = "squat";
  if (has("curl", "bicep")) exerciseId = "biceps_curl";
  const switching = exerciseId !== scene.exerciseId || (has(/\bshow\b/) && has("squat", "curl", "bicep"));
  if (switching) commands.push({ type: "select_exercise", exerciseId });

  if (has("three quarter", "3/4", "¾", "angle")) commands.push({ type: "set_view", view: "three_quarter" });
  else if (has("side", "profile")) commands.push({ type: "set_view", view: "side" });
  else if (has("front")) commands.push({ type: "set_view", view: "front" });
  else if (has("rotate", "turn")) {
    const order = ["front", "side", "three_quarter"] as const;
    commands.push({ type: "set_view", view: order[(order.indexOf(scene.view) + 1) % order.length] });
  }

  if (has("slow", "half speed", "0.5")) commands.push({ type: "set_speed", speed: 0.5 });
  else if (has("normal speed", "full speed", "faster", "1x", "1×")) commands.push({ type: "set_speed", speed: 1 });

  const phases = EXERCISES[exerciseId].availablePhases;
  let phase: string | null = null;
  if (has("bottom", "lowest", "deepest")) phase = "bottom";
  else if (has(/\btop\b/, "highest", "squeeze")) phase = "top";
  else if (has("middle", "halfway")) phase = "middle";
  const wantsPause = has("pause", "stop", "freeze", "hold");
  const wantsReset = has("reset");
  const wantsReplay = has("replay", "again", "restart", "from the start");

  if (wantsReset) commands.push({ type: "reset" });
  if (phase) commands.push({ type: "seek_phase", phase });
  if (wantsReplay) commands.push({ type: "seek_phase", phase: "start" });

  if (phase || (wantsPause && !wantsReplay)) {
    commands.push({ type: "pause" });
  } else if (switching || wantsReplay || has("play", /\bshow\b/, /\bstart\b/, /\bgo\b/, "slow", "continue", "resume")) {
    commands.push({ type: "play" });
  }

  const ex = EXERCISES[exerciseId];
  if (has("attention", "cue", "tip", "look for", "focus", "watch", "form", "explain", "how do")) {
    return { message: `${ex.reviewedCues[2]} ${ex.reviewedCues[3]}`, commands };
  }
  if (phase && phases[phase as keyof typeof phases] === undefined) {
    return { message: `${ex.shortTitle} doesn't have a "${phase}" marker; I'll keep the current position.`, commands };
  }
  if (commands.length === 0) {
    return {
      message: "I can show a squat or a biceps curl, change the view or speed, and pause at key positions.",
      commands,
    };
  }
  return { message: `Okay — ${ex.shortTitle.toLowerCase()} demo updated.`, commands };
}
