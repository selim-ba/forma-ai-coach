"use client";

import { ArrowUp, ChevronDown, MessageCircle } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ActionLog } from "@/components/debug/ActionLog";
import { EXERCISE_LIST, EXERCISES } from "@/lib/exercises/catalog";
import { toSnapshot } from "@/lib/scene/reducer";
import { useSceneStore } from "@/lib/scene/store";
import type { ChatTurn, CoachError, CoachSuccess } from "@/types/coach";
import type { ExerciseId } from "@/types/scene";
import { MessageList, type ChatMessage } from "./MessageList";

/** One example per exercise, the current one first. */
function suggestionsFor(current: ExerciseId): string[] {
  const first = EXERCISES[current].coachPrompt;
  return [first, ...EXERCISE_LIST.filter((e) => e.id !== current).map((e) => e.coachPrompt)];
}

const CLIENT_TIMEOUT_MS = 30_000;
const MAX_MESSAGES = 30;
type CoachMode = "unknown" | "openai" | "mock" | "offline";

let nextMessageId = 1;

export function CoachChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"chat" | "log">("chat");
  const [mode, setMode] = useState<CoachMode>("unknown");
  const inflight = useRef(false);
  const logCount = useSceneStore((s) => s.log.length);
  const sheet = useRef<HTMLElement>(null);

  // Tell the 3D view how much of it the open sheet covers, so it can reframe the avatar.
  useEffect(() => {
    const { setCoachTop } = useSceneStore.getState();
    const el = sheet.current;
    if (!open || !el) {
      setCoachTop(null);
      return;
    }
    const update = () => setCoachTop(el.getBoundingClientRect().top);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
      setCoachTop(null);
    };
  }, [open]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/coach", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : { mode: "offline" }))
      .then((d: { mode: CoachMode }) => !cancelled && setMode(d.mode))
      .catch(() => !cancelled && setMode("offline"));
    return () => {
      cancelled = true;
    };
  }, []);

  const push = (m: Omit<ChatMessage, "id">) =>
    setMessages((prev) => [...prev, { ...m, id: nextMessageId++ }].slice(-MAX_MESSAGES));

  async function send(text: string) {
    const message = text.trim().slice(0, 500);
    if (!message || inflight.current) return;
    inflight.current = true;
    setPending(true);
    setInput("");
    setOpen(true);
    setTab("chat");

    const history: ChatTurn[] = messages
      .filter((m) => m.tone !== "error")
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.content }));
    push({ role: "user", content: message });

    const { scene, dispatch, logNote } = useSceneStore.getState();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), CLIENT_TIMEOUT_MS);

    try {
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        throw new Error("offline");
      }
      const res = await fetch("/api/coach", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message, scene: toSnapshot(scene), history }),
        signal: controller.signal,
      });
      const data = (await res.json().catch(() => null)) as CoachSuccess | CoachError | null;
      if (!res.ok || !data || "error" in data) {
        const msg = (data && "message" in data && data.message) || "The coach isn't available right now. The manual controls still work.";
        push({ role: "assistant", content: msg, tone: "error" });
        logNote("coach", `request failed (${data && "error" in data ? data.error : res.status})`, false);
        if (data && "error" in data && data.error === "coach_unavailable") setMode("offline");
        return;
      }
      // Execute validated commands exactly once, here in the response handler.
      if (data.commands.length) dispatch(data.commands, "coach");
      for (const r of data.rejected) {
        const type = (r.command as { type?: string } | null)?.type ?? "command";
        logNote("coach", `${type} (server rejected)`, false, r.detail);
      }
      push({ role: "assistant", content: data.message, source: data.source });
    } catch (error) {
      const aborted = (error as Error)?.name === "AbortError";
      const offline = (error as Error)?.message === "offline";
      push({
        role: "assistant",
        tone: "error",
        content: offline
          ? "You're offline. The manual controls still work."
          : aborted
            ? "The coach took too long to answer. The manual controls still work."
            : "Couldn't reach the coach. The manual controls still work.",
      });
      logNote("coach", offline ? "offline" : aborted ? "timeout" : "network error", false);
    } finally {
      clearTimeout(timer);
      inflight.current = false;
      setPending(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  return (
    <section
      ref={sheet}
      aria-label="Coach"
      className={`flex flex-col rounded-t-3xl border-t border-white/10 bg-surface-raised ${
        open
          ? "absolute inset-x-0 bottom-0 z-20 h-full min-h-[min(300px,calc(var(--app-height,100dvh)-200px))] shadow-[0_-12px_40px_rgba(0,0,0,0.45)]"
          : "relative"
      }`}
      data-testid="coach"
      data-open={open}
    >
      <div className="flex items-center gap-2 px-4 pt-2.5">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex min-h-11 flex-1 items-center gap-2 text-left"
          aria-expanded={open}
          data-testid="coach-toggle"
        >
          <MessageCircle size={18} className="shrink-0 text-accent" />
          <span className="text-sm font-semibold">Coach</span>
          <ModeBadge mode={mode} />
          {!open && lastAssistant && (
            <span className="ml-1 truncate text-sm text-ink-muted">{lastAssistant.content}</span>
          )}
          <ChevronDown size={18} className={`ml-auto shrink-0 text-ink-muted transition-transform ${open ? "" : "rotate-180"}`} />
        </button>
      </div>

      {open && (
        <>
          <div className="flex gap-1 px-4 pb-2" role="tablist">
            {(["chat", "log"] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                data-testid={`tab-${t}`}
                className={`min-h-9 rounded-full px-3 text-xs font-semibold uppercase tracking-wider ${
                  tab === t ? "bg-white/12 text-ink" : "text-ink-muted"
                }`}
              >
                {t === "chat" ? "Chat" : `Actions${logCount ? ` · ${logCount}` : ""}`}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-2">
            {tab === "chat" ? (
              messages.length === 0 ? (
                <Suggestions onPick={(s) => void send(s)} disabled={pending} />
              ) : (
                <MessageList messages={messages} pending={pending} />
              )
            ) : (
              <ActionLog />
            )}
          </div>
        </>
      )}

      <form onSubmit={onSubmit} className="flex items-center gap-2 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2">
        <label htmlFor="coach-input" className="sr-only">
          Ask the coach
        </label>
        <input
          id="coach-input"
          data-testid="coach-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={500}
          placeholder={mode === "offline" ? "Coach offline — use the controls above" : "Ask the coach…"}
          autoComplete="off"
          enterKeyHint="send"
          className="min-h-11 flex-1 rounded-full border border-white/10 bg-white/5 px-4 text-base text-ink placeholder:text-ink-muted focus:border-accent/60 focus:outline-none"
        />
        <button
          type="submit"
          disabled={!input.trim() || pending}
          aria-label="Send"
          data-testid="coach-send"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent text-surface disabled:opacity-40"
        >
          <ArrowUp size={20} strokeWidth={2.6} />
        </button>
      </form>
    </section>
  );
}

function Suggestions({ onPick, disabled }: { onPick: (s: string) => void; disabled: boolean }) {
  const current = useSceneStore((s) => s.scene.exerciseId);
  const [first, ...others] = suggestionsFor(current);
  return (
    <div className="flex min-w-0 flex-col gap-2 py-1">
      <p className="text-sm text-ink-muted">Try asking:</p>
      {/* The current exercise's question first, then one per other exercise in a swipeable row. */}
      <button type="button" disabled={disabled} onClick={() => onPick(first)} className="chip text-left">
        {first}
      </button>
      <div className="-mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:none]" data-testid="more-suggestions">
        {others.map((s) => (
          <button
            key={s}
            type="button"
            disabled={disabled}
            onClick={() => onPick(s)}
            className="chip shrink-0 snap-start whitespace-nowrap text-left"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function ModeBadge({ mode }: { mode: CoachMode }) {
  if (mode === "unknown") return null;
  const map = {
    openai: { label: "GPT-6.1", cls: "bg-emerald-400/15 text-emerald-300" },
    mock: { label: "Mock", cls: "bg-sky-400/15 text-sky-300" },
    offline: { label: "Offline", cls: "bg-white/10 text-ink-muted" },
  } as const;
  const m = map[mode];
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${m.cls}`} data-testid="coach-mode">
      {m.label}
    </span>
  );
}
