import { cuesFor } from "@/lib/cues/catalog";
import { EXERCISES } from "@/lib/exercises/catalog";
import { MAX_CUES } from "@/types/cues";
import type { ExerciseId, SceneSnapshot } from "@/types/scene";

const OFFER =
  "I can show a squat, a goblet squat, a split squat, a Romanian deadlift, a kettlebell swing, a bent-over row, a biceps curl, a shoulder press or a lateral raise.";

/** Which supported exercise the message names, if any (most specific first). */
function namedExercise(has: (...words: (string | RegExp)[]) => boolean): ExerciseId | null {
  if (has(/\b(split.?squats?|lunges?)\b/)) return "split_squat";
  if (has(/\bgoblet\b/, /\bkettlebell squats?\b/)) return "goblet_squat";
  if (has(/\bswings?\b/, /\bkettlebells?\b/)) return "kettlebell_swing";
  if (has(/\b(romanian|rdl|deadlifts?|hip hinge)\b/)) return "romanian_deadlift";
  if (has(/\brows?\b/, /\browing\b/)) return "bent_over_row";
  if (has(/\b(lateral|side)\s+raises?\b/, /\braises?\b/)) return "lateral_raise";
  if (has(/\b(shoulder|overhead|military)\s+press/, /\bpress(es)?\b/)) return "shoulder_press";
  if (has("squat")) return "squat";
  if (has("curl", "bicep")) return "biceps_curl";
  return null;
}

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
      message: `I can't show unsafe or anatomically impossible movement. ${OFFER}`,
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
  if (has(/\b(bench|leg press|chest press|push.?ups?|pull.?ups?|chin.?ups?|planks?|upright rows?|burpees?|jumps?|jumping|dips?)\b/)) {
    return { message: `That exercise isn't available yet. ${OFFER}`, commands: [] };
  }

  const named = namedExercise(has);
  const exerciseId: ExerciseId = named ?? scene.exerciseId;
  const commands: unknown[] = [];
  const switching = exerciseId !== scene.exerciseId || (named !== null && has(/\bshow\b/));
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
  if (has("attention", "cue", "tip", "look for", "focus", "watch", "form", "explain", "how do", "how deep")) {
    const visual = cuesFor(exerciseId).slice(0, MAX_CUES);
    commands.push({ type: "show_cues", cueIds: visual.map((c) => c.id) });
    const shown = visual.map((c) => c.label.toLowerCase()).join(", ");
    return { message: `${ex.reviewedCues[2]} ${ex.reviewedCues[3]} The highlights show: ${shown}.`, commands };
  }
  if (phase && phases[phase as keyof typeof phases] === undefined) {
    return { message: `${ex.shortTitle} doesn't have a "${phase}" marker; I'll keep the current position.`, commands };
  }
  if (commands.length === 0) {
    return {
      message: `${OFFER} I can also change the view or speed and pause at key positions.`,
      commands,
    };
  }
  return { message: `Okay — ${ex.shortTitle.toLowerCase()} demo updated.`, commands };
}
