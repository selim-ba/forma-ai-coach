"use client";

import { useEffect, useRef, useState } from "react";
import { AVATAR_SERVICE_URL } from "@/lib/avatar/remote";
import { useSceneStore } from "@/lib/scene/store";
import { CREATE_AVATAR_EVENT } from "@/components/avatar/AvatarMenu";

const SEEN_KEY = "forma-welcomed";
/** The header logo reopens the welcome screen with this event. */
export const SHOW_WELCOME_EVENT = "forma:welcome";

function seen() {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * First-open screen: the live 3D demo plays behind, the words sit on a scrim at the
 * bottom. Shown once per phone (and again from the logo); "Start" hands over to the app.
 */
export function Welcome() {
  const [open, setOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const dispatch = useSceneStore((s) => s.dispatch);
  const setCoachTop = useSceneStore((s) => s.setCoachTop);
  const content = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // After hydration (the server can't know whether this phone has seen it).
    const first = window.setTimeout(() => {
      if (!seen() && !new URLSearchParams(window.location.search).has("avatar")) setOpen(true);
    }, 0);
    const show = () => {
      setLeaving(false);
      setOpen(true);
    };
    window.addEventListener(SHOW_WELCOME_EVENT, show);
    return () => {
      window.clearTimeout(first);
      window.removeEventListener(SHOW_WELCOME_EVENT, show);
    };
  }, []);

  // Let the demo move behind the words, framed above them (same reframing as the open coach).
  useEffect(() => {
    if (!open) return;
    dispatch([{ type: "play" }], "manual");
    const el = content.current;
    if (!el) return;
    const update = () => setCoachTop(el.getBoundingClientRect().top - 12);
    const ro = new ResizeObserver(update);
    ro.observe(el);
    update();
    return () => {
      ro.disconnect();
      setCoachTop(null);
    };
  }, [open, dispatch, setCoachTop]);

  if (!open) return null;

  function finish(then?: () => void) {
    try {
      window.localStorage.setItem(SEEN_KEY, "1");
    } catch {
      // private mode: the welcome screen simply shows again next time
    }
    setLeaving(true);
    window.setTimeout(() => {
      setOpen(false);
      then?.();
    }, 260);
  }

  return (
    <div
      className={`welcome fixed inset-0 z-40 flex flex-col justify-end ${leaving ? "welcome-out" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="welcome-title"
      data-testid="welcome"
    >
      <div className="welcome-scrim absolute inset-0" aria-hidden />
      <div
        ref={content}
        className="relative mx-auto flex w-full max-w-md flex-col gap-5 px-6 pb-[max(1.75rem,env(safe-area-inset-bottom))]"
      >
        <div className="flex flex-col gap-3">
          <h1
            id="welcome-title"
            className="font-display text-[2.6rem] font-extrabold leading-[0.95] tracking-[-0.02em] [font-stretch:78%] text-balance"
          >
            See the movement. Ask the coach.
          </h1>
          <p className="max-w-[34ch] text-[15px] leading-relaxed text-ink-muted">
            Seven exercise demos in 3D. Turn the body, slow it down, stop at the hardest point and ask what to watch
            for.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={() => finish()}
            className="min-h-13 rounded-full bg-accent text-base font-bold text-surface shadow-lg active:brightness-95"
            data-testid="welcome-start"
            autoFocus
          >
            Start
          </button>
          {AVATAR_SERVICE_URL && (
            <button
              type="button"
              onClick={() => finish(() => window.dispatchEvent(new Event(CREATE_AVATAR_EVENT)))}
              className="min-h-12 rounded-full text-sm font-semibold text-ink active:bg-white/10"
              data-testid="welcome-create"
            >
              Make my avatar from 3 photos
            </button>
          )}
        </div>
        <p className="text-center text-[11px] text-ink-muted/70">Educational demos, not medical advice.</p>
      </div>
    </div>
  );
}
