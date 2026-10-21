"use client";

import { useSceneStore } from "@/lib/scene/store";

const time = (ms: number) =>
  new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

/** Visible event/action log for demos: every command, who sent it, and whether it ran. */
export function ActionLog() {
  const log = useSceneStore((s) => s.log);
  if (log.length === 0) {
    return <p className="py-6 text-center text-sm text-ink-muted">No actions yet. Tap a control or ask the coach.</p>;
  }
  return (
    <ol className="flex flex-col gap-1 font-mono text-[12px]" data-testid="action-log">
      {[...log].reverse().map((entry) => (
        <li
          key={entry.id}
          className="flex items-baseline gap-2 rounded-lg bg-white/5 px-2.5 py-1.5"
          data-source={entry.source}
          data-ok={entry.ok}
        >
          <span className="shrink-0 text-ink-muted tabular-nums">{time(entry.at)}</span>
          <span
            className={`shrink-0 rounded px-1 text-[10px] font-bold uppercase ${
              entry.source === "coach" ? "bg-accent/20 text-accent" : "bg-white/10 text-ink-muted"
            }`}
          >
            {entry.source}
          </span>
          <span className={entry.ok ? "text-ink" : "text-amber-300 line-through decoration-amber-300/60"}>{entry.label}</span>
          {!entry.ok && entry.detail && <span className="truncate text-amber-200/80">{entry.detail}</span>}
        </li>
      ))}
    </ol>
  );
}
