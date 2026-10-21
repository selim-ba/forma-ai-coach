"use client";

import { Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";
import { EXERCISE_LIST, EXERCISES, supportedPhases } from "@/lib/exercises/catalog";
import { playhead } from "@/lib/scene/store";
import { useSceneController } from "@/hooks/useSceneController";
import { PHASES, SPEEDS, type Phase } from "@/types/scene";

const PHASE_LABEL: Record<Phase, string> = { start: "Start", middle: "Middle", bottom: "Bottom", top: "Top" };

function ProgressBar() {
  const { scene, seekPhase } = useSceneController();
  const fill = useRef<HTMLDivElement>(null);
  const markers = EXERCISES[scene.exerciseId].availablePhases;

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      if (fill.current) fill.current.style.transform = `scaleX(${playhead.progress})`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="relative h-6" aria-hidden="true">
      <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 overflow-hidden rounded-full bg-white/10">
        <div ref={fill} className="h-full w-full origin-left bg-accent" style={{ transform: "scaleX(0)" }} />
      </div>
      {(Object.entries(markers) as [Phase, number][]).map(([phase, p]) => (
        <button
          key={phase}
          type="button"
          tabIndex={-1}
          onClick={() => seekPhase(phase)}
          className="absolute top-1/2 h-6 w-6 -translate-x-1/2 -translate-y-1/2"
          style={{ left: `${p * 100}%` }}
        >
          <span
            className={`mx-auto block h-3 w-3 rounded-full border-2 border-surface ${
              scene.phase === phase ? "bg-accent" : "bg-ink-muted"
            }`}
          />
        </button>
      ))}
    </div>
  );
}

export function PlaybackControls() {
  const { scene, togglePlay, replay, setSpeed, seekPhase } = useSceneController();
  const available = supportedPhases(scene.exerciseId);

  return (
    <section aria-label="Playback controls" className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <button type="button" onClick={replay} className="icon-btn" aria-label="Replay from start" data-testid="replay">
          <RotateCcw size={20} strokeWidth={2.2} />
        </button>
        <button
          type="button"
          onClick={togglePlay}
          className="flex min-h-12 flex-1 items-center justify-center gap-2 rounded-2xl bg-accent text-base font-bold text-surface active:brightness-90"
          aria-label={scene.playing ? "Pause" : "Play"}
          data-testid="play-toggle"
        >
          {scene.playing ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" />}
          {scene.playing ? "Pause" : "Play"}
        </button>
        <div role="radiogroup" aria-label="Playback speed" className="flex rounded-2xl bg-white/5 p-1">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={scene.speed === s}
              onClick={() => setSpeed(s)}
              data-testid={`speed-${s}`}
              className={`min-h-10 min-w-12 rounded-xl px-2 text-sm font-semibold tabular-nums ${
                scene.speed === s ? "bg-white/15 text-ink" : "text-ink-muted"
              }`}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>

      <ProgressBar />

      <div className="grid grid-cols-4 gap-1" role="group" aria-label="Jump to phase">
        {PHASES.map((phase) => {
          const enabled = available.includes(phase);
          return (
            <button
              key={phase}
              type="button"
              disabled={!enabled}
              onClick={() => seekPhase(phase)}
              data-testid={`phase-${phase}`}
              className={`min-h-11 rounded-xl text-xs font-semibold uppercase tracking-wider ${
                scene.phase === phase
                  ? "bg-accent/20 text-accent"
                  : enabled
                    ? "bg-white/5 text-ink active:bg-white/10"
                    : "bg-transparent text-ink-muted/40"
              }`}
              title={enabled ? `Pause at ${PHASE_LABEL[phase].toLowerCase()}` : `No ${phase} marker for this exercise`}
            >
              {PHASE_LABEL[phase]}
            </button>
          );
        })}
      </div>
    </section>
  );
}

/** Compact exercise switch, shown in the header to leave room for the 3D view. */
export function ExerciseTabs() {
  const { scene, selectExercise } = useSceneController();
  return (
    <div role="tablist" aria-label="Exercise" className="flex gap-0.5 rounded-full bg-white/6 p-0.5">
      {EXERCISE_LIST.map((e) => {
        const active = e.id === scene.exerciseId;
        return (
          <button
            key={e.id}
            role="tab"
            type="button"
            aria-selected={active}
            data-testid={`exercise-${e.id}`}
            onClick={() => selectExercise(e.id)}
            className={`min-h-10 rounded-full px-3.5 text-sm font-semibold transition-colors ${
              active ? "bg-ink text-surface" : "text-ink-muted active:bg-white/10"
            }`}
          >
            {e.shortTitle}
          </button>
        );
      })}
    </div>
  );
}
