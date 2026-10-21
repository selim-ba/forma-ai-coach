"use client";

import dynamic from "next/dynamic";
import { CoachChat } from "@/components/coach/CoachChat";
import { ExerciseTabs, PlaybackControls } from "@/components/controls/PlaybackControls";
import { ViewPresets } from "@/components/viewer/ViewPresets";
import { useVisualViewport } from "@/hooks/useVisualViewport";
import { EXERCISES } from "@/lib/exercises/catalog";
import { useSceneStore } from "@/lib/scene/store";

const AvatarCanvas = dynamic(() => import("@/components/viewer/AvatarCanvas"), {
  ssr: false,
  loading: () => (
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="h-28 w-12 animate-pulse rounded-full bg-white/10" />
    </div>
  ),
});

const PHASE_LABEL = { start: "Start", middle: "Middle", bottom: "Bottom", top: "Top" } as const;

export function FormaApp() {
  useVisualViewport();
  const scene = useSceneStore((s) => s.scene);
  const avatarStatus = useSceneStore((s) => s.avatar.status);
  const avatarLabel = useSceneStore((s) => s.avatarSource.label);
  const exercise = EXERCISES[scene.exerciseId];

  return (
    <div
      className="app-root"
      data-testid="app"
      data-exercise={scene.exerciseId}
      data-playing={scene.playing}
      data-speed={scene.speed}
      data-view={scene.view}
      data-phase={scene.phase ?? ""}
      data-avatar={avatarStatus}
    >
      <header className="app-header flex items-center gap-3 px-4 pb-2 pt-[max(0.5rem,env(safe-area-inset-top))]">
        <span className="text-lg font-black tracking-tight">
          forma<span className="text-accent">.</span>
        </span>
        <div className="ml-auto">
          <ExerciseTabs />
        </div>
      </header>

      <main className="app-viewer relative min-h-0 overflow-hidden" style={{ touchAction: "none" }}>
        <div className="viewer-bg absolute inset-0" />
        <AvatarCanvas />
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-3">
          <div className="flex flex-col items-start gap-1.5">
            {scene.phase && !scene.playing && (
              <span className="rounded-full bg-accent px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-surface" data-testid="phase-badge">
                {PHASE_LABEL[scene.phase]}
              </span>
            )}
            {scene.speed !== 1 && (
              <span className="rounded-full bg-black/45 px-2.5 py-1 text-[11px] font-bold tabular-nums text-ink backdrop-blur-md">
                {scene.speed}×
              </span>
            )}
          </div>
          <div className="pointer-events-auto">
            <ViewPresets />
          </div>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-2 px-4 text-center">
          <p className="text-sm font-semibold text-ink" data-testid="exercise-title">
            {exercise.title} <span className="font-normal capitalize text-ink-muted">· {exercise.level}</span>
          </p>
          <p className="text-[11px] leading-tight text-ink-muted/80">
            Drag to rotate · {avatarLabel} · not medical advice
          </p>
        </div>
      </main>

      <div className="app-panel relative flex flex-col">
        <div className="px-4 pb-3 pt-3">
          <PlaybackControls />
        </div>
        <CoachChat />
      </div>
    </div>
  );
}
