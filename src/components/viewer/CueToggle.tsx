"use client";

import { Sparkles } from "lucide-react";
import { cuesFor } from "@/lib/cues/catalog";
import { useSceneStore } from "@/lib/scene/store";
import { MAX_CUES } from "@/types/cues";

/** Manual switch for the visual form cues; goes through the same validated commands as the coach. */
export function CueToggle() {
  const exerciseId = useSceneStore((s) => s.scene.exerciseId);
  const on = useSceneStore((s) => s.scene.cues.length > 0);
  const dispatch = useSceneStore((s) => s.dispatch);
  const available = cuesFor(exerciseId);
  if (!available.length) return null;
  return (
    <button
      type="button"
      onClick={() =>
        dispatch(
          on ? [{ type: "clear_cues" }] : [{ type: "show_cues", cueIds: available.slice(0, MAX_CUES).map((c) => c.id) }],
          "manual",
        )
      }
      aria-pressed={on}
      className={`flex min-h-9 items-center gap-1.5 rounded-full px-3 text-xs font-semibold backdrop-blur-md ${
        on ? "bg-accent text-surface" : "bg-black/45 text-ink"
      }`}
      data-testid="cue-toggle"
    >
      <Sparkles size={14} /> Form cues
    </button>
  );
}
