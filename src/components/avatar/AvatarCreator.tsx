"use client";

import { Camera, Check, Loader2, RotateCcw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { preferredBody, type GenericBody } from "@/lib/avatar/source";
import {
  fetchRemoteStatus,
  prepareJpeg,
  rememberMyAvatar,
  type RemoteAvatarStatus,
} from "@/lib/avatar/remote";

type View = "front" | "side" | "back";
const VIEWS: View[] = ["front", "side", "back"];

const STEP_TEXT: Record<View, { title: string; tip: string }> = {
  front: {
    title: "Front",
    tip: "Facing the camera, head to toe in the frame, arms slightly away from the body.",
  },
  side: {
    title: "Side",
    tip: "Turned sideways, same spot and distance, arms relaxed by the sides.",
  },
  back: {
    title: "Back",
    tip: "Back to the camera, same spot and distance, arms slightly away from the body.",
  },
};

type Phase =
  | { name: "intro" }
  | { name: "photo"; view: View }
  | { name: "review" }
  | { name: "uploading" }
  | { name: "processing"; id: string; status: RemoteAvatarStatus | null }
  | { name: "error"; message: string; retryFrom: "review" | "intro" };

const STAGES = [
  { key: "upload", label: "Uploading photos" },
  { key: "shape", label: "Reading body shape and look" },
  { key: "build", label: "Animating nine exercises" },
] as const;

/**
 * Full-screen flow: consent → three guided photos → upload → progress → open the avatar.
 * Photos are re-encoded on the phone (smaller, no location metadata) and sent through
 * /api/avatar; the service deletes them as soon as the avatar is built.
 */
export function AvatarCreator({ codeRequired, onClose }: { codeRequired: boolean; onClose: () => void }) {
  const [phase, setPhase] = useState<Phase>({ name: "intro" });
  const [consent, setConsent] = useState(false);
  const [body, setBody] = useState<GenericBody>(() => preferredBody());
  const [code, setCode] = useState(() => {
    try {
      return localStorage.getItem("forma.accessCode") ?? "";
    } catch {
      return "";
    }
  });
  const [photos, setPhotos] = useState<Partial<Record<View, { blob: Blob; preview: string }>>>({});
  const [started, setStarted] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const fileInput = useRef<HTMLInputElement>(null);
  const pendingView = useRef<View>("front");

  // Start a worker now: it takes about a minute to boot, roughly the time the photos take.
  useEffect(() => {
    void fetch("/api/avatar?warm=1", { method: "POST" }).catch(() => undefined);
  }, []);

  // Free the preview URLs when the flow closes.
  const previews = useRef<string[]>([]);
  useEffect(() => () => previews.current.forEach((u) => URL.revokeObjectURL(u)), []);

  // Poll the service while the avatar is being made.
  const processingId = phase.name === "processing" ? phase.id : null;
  useEffect(() => {
    if (!processingId) return;
    let cancelled = false;
    const controller = new AbortController();
    async function poll() {
      while (!cancelled) {
        try {
          const status = await fetchRemoteStatus(processingId!, controller.signal);
          if (cancelled) return;
          if (!status) {
            setPhase({ name: "error", message: "The avatar disappeared from the service. Please try again.", retryFrom: "review" });
            return;
          }
          if (status.state === "done") {
            rememberMyAvatar(processingId!);
            window.location.assign(`/?avatar=${processingId}`);
            return;
          }
          if (status.state === "error") {
            setPhase({ name: "error", message: status.message, retryFrom: "intro" });
            return;
          }
          setPhase({ name: "processing", id: processingId!, status });
        } catch {
          // A dropped request on mobile data: keep polling.
        }
        await new Promise((r) => setTimeout(r, 2500));
      }
    }
    void poll();
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(tick);
    };
  }, [processingId]);

  function takePhoto(view: View) {
    pendingView.current = view;
    fileInput.current?.click();
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const view = pendingView.current;
    try {
      const blob = await prepareJpeg(file);
      const preview = URL.createObjectURL(blob);
      previews.current.push(preview);
      setPhotos((p) => ({ ...p, [view]: { blob, preview } }));
    } catch {
      setPhase({ name: "error", message: "That photo couldn't be read. Please take it again.", retryFrom: "review" });
    }
  }

  async function upload() {
    setPhase({ name: "uploading" });
    setStarted(Date.now());
    const form = new FormData();
    for (const v of VIEWS) form.append(v, photos[v]!.blob, `${v}.jpg`);
    form.append("body", body);
    if (codeRequired) form.append("code", code);
    try {
      const res = await fetch("/api/avatar", { method: "POST", body: form });
      const data = (await res.json().catch(() => ({}))) as { id?: string; message?: string; error?: string };
      if (!res.ok || !data.id) {
        setPhase({
          name: "error",
          message: data.message ?? "The upload failed. Please try again.",
          retryFrom: data.error === "bad_code" ? "intro" : "review",
        });
        return;
      }
      try {
        if (codeRequired) localStorage.setItem("forma.accessCode", code);
      } catch {
        // ignore
      }
      setPhase({ name: "processing", id: data.id, status: null });
    } catch {
      setPhase({ name: "error", message: "No connection. Check your signal and try again.", retryFrom: "review" });
    }
  }

  const stepIndex = phase.name === "photo" ? VIEWS.indexOf(phase.view) : -1;
  const elapsed = started ? Math.max(0, Math.round((now - started) / 1000)) : 0;
  const stageKey =
    phase.name === "uploading" ? "upload" : phase.name === "processing" ? (phase.status?.stage === "build" ? "build" : "shape") : null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Create my avatar"
      className="fixed inset-x-0 z-50 flex flex-col bg-surface"
      style={{ top: "var(--app-top, 0px)", height: "var(--app-height, 100dvh)" }}
      data-testid="avatar-creator"
    >
      <input ref={fileInput} type="file" accept="image/*" capture="environment" className="hidden" onChange={onFile} />

      <div className="flex items-center gap-3 px-4 pb-2 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <h2 className="text-lg font-bold">Create my avatar</h2>
        {phase.name !== "uploading" && phase.name !== "processing" && (
          <button type="button" onClick={onClose} className="icon-btn ml-auto h-10 w-10" aria-label="Close">
            <X size={20} />
          </button>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        {phase.name === "intro" && (
          <div className="flex flex-col gap-4 pt-2">
            <p className="text-sm text-ink-muted">
              Three full-body photos (front, side and back) turn into a 3D avatar with your approximate body shape and
              look, doing all nine exercises. It takes a few minutes.
            </p>
            <ul className="flex flex-col gap-1.5 text-sm text-ink-muted">
              <li>• Ask someone to take the photos from about 3 m away, at hip height.</li>
              <li>• Head to toe in the frame, fitted clothes, plain background if possible.</li>
              <li>• Same spot, distance and light for all three.</li>
            </ul>
            <div className="flex flex-col gap-1.5 text-sm">
              <span className="text-ink-muted">Hair and clothing cut</span>
              <div role="group" aria-label="Hair and clothing cut" className="flex rounded-full bg-white/8 p-0.5">
                {(["male", "female"] as const).map((b) => (
                  <button
                    key={b}
                    type="button"
                    aria-pressed={body === b}
                    onClick={() => setBody(b)}
                    className={`min-h-10 flex-1 rounded-full text-sm font-semibold ${
                      body === b ? "bg-ink text-surface" : "text-ink-muted active:bg-white/10"
                    }`}
                    data-testid={`avatar-body-${b}`}
                  >
                    {b === "male" ? "Man" : "Woman"}
                  </button>
                ))}
              </div>
              <span className="text-xs text-ink-muted/80">Your body shape always comes from the photos.</span>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-xs leading-relaxed text-ink-muted">
              <p className="mb-1 font-semibold text-ink">Your photos</p>
              The photos are sent to a cloud server (Modal, in the US) that builds the avatar, and are deleted as soon as
              it is ready. The avatar itself is deleted after 24 hours, or right away with the Delete button. Anyone with
              the avatar&apos;s link can see it. It&apos;s an approximate body shape for exercise demos — not a measurement and not
              medical advice. Only photograph people who agree.
            </div>
            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                className="mt-0.5 h-5 w-5 accent-[var(--color-accent)]"
                data-testid="avatar-consent"
              />
              <span>I agree, and the person in the photos agrees, to this use of the photos.</span>
            </label>
            {codeRequired && (
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-ink-muted">Access code</span>
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  autoComplete="off"
                  autoCapitalize="none"
                  className="min-h-11 rounded-xl border border-white/10 bg-white/5 px-3 text-base focus:border-accent/60 focus:outline-none"
                  data-testid="avatar-code"
                />
              </label>
            )}
            <button
              type="button"
              disabled={!consent || (codeRequired && !code.trim())}
              onClick={() => setPhase({ name: "photo", view: "front" })}
              className="min-h-12 rounded-2xl bg-accent text-base font-bold text-surface disabled:opacity-40"
              data-testid="avatar-start"
            >
              Start
            </button>
          </div>
        )}

        {phase.name === "photo" && (
          <div className="flex flex-col gap-4 pt-2">
            <StepDots index={stepIndex} />
            <div className="flex items-center gap-4">
              <Silhouette view={phase.view} />
              <div className="flex-1">
                <p className="text-base font-semibold">
                  {stepIndex + 1}/3 · {STEP_TEXT[phase.view].title}
                </p>
                <p className="mt-1 text-sm text-ink-muted">{STEP_TEXT[phase.view].tip}</p>
              </div>
            </div>
            {photos[phase.view] ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={photos[phase.view]!.preview}
                alt={`${STEP_TEXT[phase.view].title} photo`}
                className="mx-auto max-h-[40vh] rounded-2xl object-contain"
              />
            ) : (
              <div className="flex h-40 items-center justify-center rounded-2xl border border-dashed border-white/15 text-sm text-ink-muted">
                No photo yet
              </div>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => takePhoto(phase.view)}
                className={`flex min-h-12 flex-1 items-center justify-center gap-2 rounded-2xl text-base font-bold ${
                  photos[phase.view] ? "bg-white/10 text-ink" : "bg-accent text-surface"
                }`}
                data-testid={`avatar-take-${phase.view}`}
              >
                {photos[phase.view] ? <RotateCcw size={18} /> : <Camera size={20} />}
                {photos[phase.view] ? "Retake" : "Take photo"}
              </button>
              {photos[phase.view] && (
                <button
                  type="button"
                  onClick={() =>
                    setPhase(stepIndex < 2 ? { name: "photo", view: VIEWS[stepIndex + 1] } : { name: "review" })
                  }
                  className="flex min-h-12 flex-1 items-center justify-center gap-2 rounded-2xl bg-accent text-base font-bold text-surface"
                  data-testid="avatar-next"
                >
                  <Check size={20} /> Use it
                </button>
              )}
            </div>
          </div>
        )}

        {phase.name === "review" && (
          <div className="flex flex-col gap-4 pt-2">
            <p className="text-sm text-ink-muted">Tap a photo to retake it.</p>
            <div className="grid grid-cols-3 gap-2">
              {VIEWS.map((v) => (
                <button key={v} type="button" onClick={() => setPhase({ name: "photo", view: v })} className="flex flex-col gap-1">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={photos[v]?.preview} alt={`${v} photo`} className="aspect-[3/4] w-full rounded-xl object-cover" />
                  <span className="text-center text-xs text-ink-muted">{STEP_TEXT[v].title}</span>
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => void upload()}
              className="min-h-12 rounded-2xl bg-accent text-base font-bold text-surface"
              data-testid="avatar-create"
            >
              Create my avatar
            </button>
          </div>
        )}

        {(phase.name === "uploading" || phase.name === "processing") && (
          <div className="flex flex-col items-center gap-6 pt-10 text-center" aria-live="polite">
            <Loader2 size={40} className="animate-spin text-accent" />
            <div>
              <p className="text-base font-semibold">
                {phase.name === "processing" && phase.status?.message ? phase.status.message : "Uploading your photos…"}
              </p>
              <p className="mt-1 text-sm tabular-nums text-ink-muted">
                {elapsed}s · usually about 2 minutes, a little longer for the first one of the day
              </p>
            </div>
            <ol className="flex w-full max-w-xs flex-col gap-2 text-left text-sm">
              {STAGES.map((s, i) => {
                const current = STAGES.findIndex((x) => x.key === stageKey);
                const state = i < current ? "done" : i === current ? "now" : "next";
                return (
                  <li key={s.key} className={`flex items-center gap-2 ${state === "next" ? "text-ink-muted/60" : "text-ink"}`}>
                    {state === "done" ? (
                      <Check size={16} className="text-accent" />
                    ) : state === "now" ? (
                      <Loader2 size={16} className="animate-spin text-accent" />
                    ) : (
                      <span className="inline-block h-4 w-4 rounded-full border border-white/20" />
                    )}
                    {s.label}
                  </li>
                );
              })}
            </ol>
            <p className="text-xs text-ink-muted">You can keep this screen open; the avatar opens by itself.</p>
          </div>
        )}

        {phase.name === "error" && (
          <div className="flex flex-col items-center gap-4 pt-10 text-center" role="alert">
            <p className="text-base font-semibold">Couldn&apos;t make the avatar</p>
            <p className="text-sm text-ink-muted">{phase.message}</p>
            <button
              type="button"
              onClick={() => setPhase(phase.retryFrom === "intro" ? { name: "intro" } : { name: "review" })}
              className="btn-secondary"
            >
              {phase.retryFrom === "intro" ? "Start again" : "Back to the photos"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function StepDots({ index }: { index: number }) {
  return (
    <div className="flex gap-1.5" aria-hidden="true">
      {VIEWS.map((v, i) => (
        <span key={v} className={`h-1.5 flex-1 rounded-full ${i <= index ? "bg-accent" : "bg-white/10"}`} />
      ))}
    </div>
  );
}

/** Simple pose guide: who stands how, for each of the three photos. */
function Silhouette({ view }: { view: View }) {
  const side = view === "side";
  return (
    <svg viewBox="0 0 60 120" className="h-28 w-14 shrink-0 text-ink-muted" aria-hidden="true">
      <g fill="currentColor" opacity={0.85}>
        <circle cx="30" cy="12" r="8" />
        {side ? (
          <>
            <rect x="23" y="22" width="14" height="40" rx="6" />
            <rect x="25" y="26" width="8" height="34" rx="4" opacity={0.6} />
            <rect x="24" y="60" width="12" height="54" rx="5" />
          </>
        ) : (
          <>
            <rect x="18" y="22" width="24" height="40" rx="7" />
            <rect x="7" y="25" width="7" height="36" rx="3.5" transform="rotate(14 10 25)" />
            <rect x="46" y="25" width="7" height="36" rx="3.5" transform="rotate(-14 50 25)" />
            <rect x="19" y="60" width="10" height="54" rx="5" />
            <rect x="31" y="60" width="10" height="54" rx="5" />
          </>
        )}
      </g>
      {view === "back" && <path d="M30 4 v16" stroke="#0e1013" strokeWidth="1.5" />}
    </svg>
  );
}
