"use client";

import { useSceneController } from "@/hooks/useSceneController";
import { VIEWS, type View } from "@/types/scene";

const LABEL: Record<View, string> = { front: "Front", side: "Side", three_quarter: "¾" };

/** One-tap camera presets overlaid on the viewer. Tapping the active preset re-centres the camera. */
export function ViewPresets() {
  const { scene, setView } = useSceneController();
  return (
    <div role="radiogroup" aria-label="Camera view" className="flex gap-1 rounded-full bg-black/45 p-1 backdrop-blur-md">
      {VIEWS.map((v) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={scene.view === v}
          onClick={() => setView(v)}
          data-testid={`view-${v}`}
          className={`min-h-11 min-w-11 rounded-full px-3 text-sm font-semibold ${
            scene.view === v ? "bg-ink text-surface" : "text-ink"
          }`}
        >
          {LABEL[v]}
        </button>
      ))}
    </div>
  );
}
