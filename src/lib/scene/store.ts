import { create } from "zustand";
import { DEFAULT_AVATAR, type AvatarSource } from "@/lib/avatar/source";
import type { CommandResult, CommandSource, ExerciseId, SceneState } from "@/types/scene";
import { describeCommand } from "./commands";
import { applyCommands, INITIAL_SCENE } from "./reducer";

export type LogEntry = {
  id: number;
  batchId: number;
  at: number;
  source: CommandSource;
  label: string;
  ok: boolean;
  detail?: string;
};

export type AvatarStatus = {
  status: "loading" | "ready" | "error";
  error?: string;
  /** Exercises whose clip this avatar doesn't have (e.g. the mannequin only has squat and curl). */
  missing?: ExerciseId[];
};

type SceneStore = {
  scene: SceneState;
  avatar: AvatarStatus;
  avatarSource: AvatarSource;
  log: LogEntry[];
  /** Validate and apply commands exactly once, recording each in the action log. */
  dispatch: (commands: readonly unknown[], source: CommandSource) => CommandResult[];
  setAvatarStatus: (status: AvatarStatus) => void;
  setAvatarSource: (source: AvatarSource) => void;
  logNote: (source: CommandSource, label: string, ok: boolean, detail?: string) => void;
};

const MAX_LOG = 60;
let nextId = 1;
let nextBatch = 1;

function labelFor(result: CommandResult): string {
  if (result.ok) return describeCommand(result.command);
  const type = (result.command as { type?: unknown } | null)?.type;
  return typeof type === "string" ? type : "unknown command";
}

export const useSceneStore = create<SceneStore>((set, get) => ({
  scene: INITIAL_SCENE,
  avatar: { status: "loading" },
  avatarSource: DEFAULT_AVATAR,
  log: [],
  dispatch: (commands, source) => {
    const { state, results } = applyCommands(get().scene, commands);
    const batchId = nextBatch++;
    const at = Date.now();
    const entries: LogEntry[] = results.map((r) => ({
      id: nextId++,
      batchId,
      at,
      source,
      label: labelFor(r),
      ok: r.ok,
      detail: r.ok ? undefined : r.detail,
    }));
    set({ scene: state, log: [...get().log, ...entries].slice(-MAX_LOG) });
    return results;
  },
  setAvatarStatus: (avatar) => set({ avatar }),
  setAvatarSource: (avatarSource) => set({ avatarSource }),
  logNote: (source, label, ok, detail) =>
    set({
      log: [
        ...get().log,
        { id: nextId++, batchId: nextBatch++, at: Date.now(), source, label, ok, detail },
      ].slice(-MAX_LOG),
    }),
}));

/**
 * Mutable playhead written by the render loop every frame and read by the
 * progress bar via requestAnimationFrame — avoids 60 React renders a second.
 */
export const playhead = { progress: 0, duration: 0 };
