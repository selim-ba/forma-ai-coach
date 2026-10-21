"use client";

import { useEffect, useRef } from "react";

export type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  tone?: "error" | "info";
  source?: "openai" | "mock";
};

export function MessageList({ messages, pending }: { messages: ChatMessage[]; pending: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length, pending]);

  return (
    <ol className="flex flex-col gap-2" aria-live="polite" data-testid="message-list">
      {messages.map((m) => (
        <li
          key={m.id}
          className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[15px] leading-snug ${
            m.role === "user"
              ? "self-end rounded-br-md bg-ink text-surface"
              : m.tone === "error"
                ? "self-start rounded-bl-md border border-amber-400/30 bg-amber-400/10 text-amber-100"
                : "self-start rounded-bl-md bg-white/8 text-ink"
          }`}
          data-role={m.role}
        >
          {m.content}
          {m.source === "mock" && (
            <span className="ml-2 align-middle text-[10px] font-semibold uppercase tracking-wider text-ink-muted">mock</span>
          )}
        </li>
      ))}
      {pending && (
        <li className="self-start rounded-2xl rounded-bl-md bg-white/8 px-3.5 py-2.5 text-ink-muted" aria-label="Coach is typing">
          <span className="inline-flex gap-1">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.2s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.1s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
          </span>
        </li>
      )}
      <div ref={end} />
    </ol>
  );
}
