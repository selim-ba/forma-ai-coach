"use client";

import { useCallback } from "react";
import { useShallow } from "zustand/react/shallow";
import { getExercise } from "@/lib/exercises/catalog";
import { useSceneStore } from "@/lib/scene/store";
import type { ExerciseId, Phase, SceneCommand, Speed, View } from "@/types/scene";

/** Manual-control helpers. Every UI action goes through the same validated dispatch as the coach. */
export function useSceneController() {
  const { scene, dispatch } = useSceneStore(useShallow((s) => ({ scene: s.scene, dispatch: s.dispatch })));

  const run = useCallback((commands: SceneCommand[]) => dispatch(commands, "manual"), [dispatch]);

  return {
    scene,
    selectExercise: (id: ExerciseId) =>
      run([
        { type: "select_exercise", exerciseId: id },
        { type: "set_view", view: getExercise(id).defaultView },
        { type: "play" },
      ]),
    togglePlay: () => run([{ type: scene.playing ? "pause" : "play" }]),
    replay: () => run([{ type: "seek_phase", phase: "start" }, { type: "play" }]),
    setSpeed: (speed: Speed) => run([{ type: "set_speed", speed }]),
    setView: (view: View) => run([{ type: "set_view", view }]),
    seekPhase: (phase: Phase) => run([{ type: "seek_phase", phase }, { type: "pause" }]),
    reset: () => run([{ type: "reset" }]),
  };
}
