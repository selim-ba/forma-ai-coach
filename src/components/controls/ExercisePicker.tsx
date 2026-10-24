"use client";

import { Check, ChevronDown, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { EXERCISES } from "@/lib/exercises/catalog";
import type { Exercise } from "@/lib/exercises/schema";
import { useSceneController } from "@/hooks/useSceneController";
import { useSceneStore } from "@/lib/scene/store";
import type { ExerciseId } from "@/types/scene";

/** Grouped by equipment, lower body before upper body inside each group. */
const GROUPS: { name: string; ids: ExerciseId[] }[] = [
  { name: "Bodyweight", ids: ["squat", "split_squat"] },
  { name: "Dumbbells", ids: ["romanian_deadlift", "bent_over_row", "biceps_curl", "shoulder_press", "lateral_raise"] },
  { name: "Kettlebell", ids: ["goblet_squat", "kettlebell_swing"] },
];

/** The card name: the group heading already says the equipment. */
function cardName(title: string): string {
  const name = title.replace(/\b(bodyweight|dumbbell|kettlebell)\s+/gi, "").trim();
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/**
 * Header button showing the current exercise; opens a sheet with every exercise
 * grouped by equipment (replaces the horizontal tab row, which hid most of the
 * exercises off-screen on a phone).
 */
export function ExercisePicker() {
  const { scene, selectExercise } = useSceneController();
  const missing = useSceneStore((s) => s.avatar.missing);
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const sheet = useRef<HTMLDivElement>(null);
  const current = EXERCISES[scene.exerciseId];

  useEffect(() => {
    if (!open) return;
    sheet.current?.querySelector<HTMLElement>('[aria-current="true"]')?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };

  const pick = (id: ExerciseId) => {
    if (id !== scene.exerciseId) selectExercise(id);
    close();
  };

  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        data-testid="exercise-picker"
        className="flex min-h-10 max-w-full items-center gap-1.5 rounded-full bg-white/8 py-1 pl-4 pr-3 text-sm font-semibold active:bg-white/15"
      >
        <span className="truncate">{current.title}</span>
        <ChevronDown size={16} className="shrink-0 text-ink-muted" aria-hidden />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex flex-col" data-testid="exercise-sheet">
          <button
            type="button"
            aria-label="Close"
            tabIndex={-1}
            onClick={close}
            className="absolute inset-0 bg-black/55 backdrop-blur-[2px] picker-backdrop"
          />
          <div
            ref={sheet}
            role="dialog"
            aria-modal="true"
            aria-label="Choose an exercise"
            className="picker-sheet relative flex max-h-[88dvh] flex-col overflow-hidden rounded-b-3xl border-b border-white/10 bg-surface-raised shadow-2xl"
          >
            <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-[max(0.75rem,env(safe-area-inset-top))]">
              <h2 className="text-base font-bold">Choose an exercise</h2>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="flex size-9 items-center justify-center rounded-full bg-white/8 active:bg-white/15"
              >
                <X size={18} />
              </button>
            </div>
            <div className="no-scrollbar flex flex-col gap-4 overflow-y-auto px-4 pb-5 pt-1">
              {GROUPS.map((g) => (
                <section key={g.name} className="flex flex-col gap-2">
                  <h3 className="text-[11px] font-bold uppercase tracking-[0.12em] text-ink-muted">{g.name}</h3>
                  <div className="grid grid-cols-2 gap-2">
                    {g.ids.map((id) => (
                      <ExerciseCard
                        key={id}
                        exercise={EXERCISES[id]}
                        active={id === scene.exerciseId}
                        unavailable={(missing?.includes(id) ?? false) && id !== scene.exerciseId}
                        onPick={() => pick(id)}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function ExerciseCard({
  exercise,
  active,
  unavailable,
  onPick,
}: {
  exercise: Exercise;
  active: boolean;
  unavailable: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      disabled={unavailable}
      aria-current={active}
      data-testid={`exercise-${exercise.id}`}
      className={`relative flex min-h-[4.5rem] flex-col items-start justify-between gap-1 rounded-2xl border px-3 py-2.5 text-left transition-colors disabled:opacity-40 ${
        active ? "border-accent bg-accent/12" : "border-white/8 bg-white/4 active:bg-white/10"
      }`}
    >
      <span className="pr-5 text-sm font-semibold leading-snug">{cardName(exercise.title)}</span>
      <span className="text-xs text-ink-muted">
        {unavailable ? "Not in this avatar" : `${exercise.focus} · ${exercise.level === "beginner" ? "Beginner" : "Intermediate"}`}
      </span>
      {active && <Check size={16} className="absolute right-2.5 top-2.5 text-accent" aria-hidden />}
    </button>
  );
}
