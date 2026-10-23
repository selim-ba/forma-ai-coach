import { CUES } from "@/lib/cues/catalog";
import { EXERCISES, phaseProgress } from "@/lib/exercises/catalog";
import type {
  CommandResult,
  SceneCommand,
  SceneSnapshot,
  SceneState,
} from "@/types/scene";
import { MAX_COMMANDS, SceneCommandSchema } from "./commands";

export const INITIAL_SCENE: SceneState = {
  exerciseId: "squat",
  playing: false,
  speed: 1,
  view: "front",
  phase: "start",
  viewNonce: 0,
  seek: null,
  cues: [],
};

function nextSeek(state: SceneState, progress: number) {
  return { progress, nonce: (state.seek?.nonce ?? 0) + 1 };
}

/**
 * Pure, deterministic reducer for a single *already-parsed* command.
 * Semantic checks (e.g. phase availability for the selected exercise) live here.
 */
export function reduceCommand(
  state: SceneState,
  command: SceneCommand,
): { state: SceneState; result: CommandResult } {
  const ok = (next: SceneState) => ({ state: next, result: { ok: true as const, command } });

  switch (command.type) {
    case "select_exercise":
      return ok({
        ...state,
        exerciseId: command.exerciseId,
        playing: false,
        phase: "start",
        seek: nextSeek(state, 0),
        cues: command.exerciseId === state.exerciseId ? state.cues : [],
      });
    case "play":
      return ok({ ...state, playing: true, phase: null });
    case "pause":
      return ok({ ...state, playing: false });
    case "set_speed":
      return ok({ ...state, speed: command.speed });
    case "set_view":
      return ok({ ...state, view: command.view, viewNonce: state.viewNonce + 1 });
    case "seek_phase": {
      const progress = phaseProgress(state.exerciseId, command.phase);
      if (progress === undefined) {
        const available = Object.keys(EXERCISES[state.exerciseId].availablePhases).join(", ");
        return {
          state,
          result: {
            ok: false,
            command,
            reason: "unsupported_phase",
            detail: `"${command.phase}" is not a marker for ${EXERCISES[state.exerciseId].shortTitle} (available: ${available}).`,
          },
        };
      }
      return ok({ ...state, phase: command.phase, seek: nextSeek(state, progress) });
    }
    case "reset":
      return ok({
        ...state,
        playing: false,
        speed: 1,
        view: "front",
        viewNonce: state.viewNonce + 1,
        phase: "start",
        seek: nextSeek(state, 0),
        cues: [],
      });
    case "show_cues": {
      const foreign = command.cueIds.filter((id) => CUES[id].exerciseId !== state.exerciseId);
      if (foreign.length) {
        return {
          state,
          result: {
            ok: false,
            command,
            reason: "unsupported_cue",
            detail: `${foreign.join(", ")} ${foreign.length > 1 ? "are" : "is"} not a cue for ${EXERCISES[state.exerciseId].shortTitle}.`,
          },
        };
      }
      return ok({ ...state, cues: [...new Set(command.cueIds)] });
    }
    case "clear_cues":
      return ok({ ...state, cues: [] });
  }
}

/**
 * Validate (Zod) and apply untrusted commands sequentially. Order matters:
 * `select_exercise` must precede a `seek_phase` that depends on it.
 * Invalid commands are rejected individually; valid ones still apply.
 */
export function applyCommands(
  state: SceneState,
  commands: readonly unknown[],
): { state: SceneState; results: CommandResult[] } {
  const results: CommandResult[] = [];
  let current = state;

  commands.forEach((raw, index) => {
    if (index >= MAX_COMMANDS) {
      results.push({
        ok: false,
        command: raw,
        reason: "too_many_commands",
        detail: `Only the first ${MAX_COMMANDS} commands are executed.`,
      });
      return;
    }
    const parsed = SceneCommandSchema.safeParse(raw);
    if (!parsed.success) {
      results.push({
        ok: false,
        command: raw,
        reason: "invalid_command",
        detail: parsed.error.issues[0]?.message ?? "Command failed validation.",
      });
      return;
    }
    const { state: next, result } = reduceCommand(current, parsed.data);
    current = next;
    results.push(result);
  });

  return { state: current, results };
}

export function sceneFromSnapshot(snapshot: SceneSnapshot): SceneState {
  return { ...INITIAL_SCENE, ...snapshot };
}

export function toSnapshot(state: SceneState): SceneSnapshot {
  return {
    exerciseId: state.exerciseId,
    playing: state.playing,
    speed: state.speed,
    view: state.view,
    phase: state.phase,
    cues: state.cues,
  };
}
