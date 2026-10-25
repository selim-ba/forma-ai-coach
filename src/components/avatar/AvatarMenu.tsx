"use client";

import { Camera, Check, ChevronDown, Sparkles, Trash2, UserRound, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { DEMO_AVATARS, isDemoAvatar } from "@/lib/avatar/demo";
import { AVATAR_SERVICE_URL, deleteRemoteAvatar, myAvatarId } from "@/lib/avatar/remote";
import { MHR_GENERIC_FEMALE_AVATAR, isGenericBody, setPreferredBody, type AvatarSource, type GenericBody } from "@/lib/avatar/source";
import { useSceneStore } from "@/lib/scene/store";
import { AvatarCreator } from "./AvatarCreator";

type ServiceInfo = { enabled: boolean; codeRequired: boolean };

/** Other parts of the app (the welcome screen) open the creator with this event. */
export const CREATE_AVATAR_EVENT = "forma:create-avatar";

function currentLabel(source: AvatarSource): string {
  if (source.id === "mannequin") return "Mannequin";
  if (isGenericBody(source)) return source.id === MHR_GENERIC_FEMALE_AVATAR.id ? "Woman" : "Man";
  const demo = DEMO_AVATARS.find((d) => d.id === source.id);
  if (demo) return demo.label;
  return "My avatar";
}

/**
 * Top-left viewer control: one chip naming the current avatar. It opens a sheet with the
 * default body (man / woman), avatar creation from photos, and the kept demo avatars.
 */
export function AvatarMenu() {
  const source = useSceneStore((s) => s.avatarSource);
  const [service, setService] = useState<ServiceInfo | null>(null);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!AVATAR_SERVICE_URL) return;
    let cancelled = false;
    fetch("/api/avatar", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : { enabled: false, codeRequired: false }))
      .then((info: ServiceInfo) => {
        if (cancelled) return;
        setService(info);
        setSaved(myAvatarId());
      })
      .catch(() => !cancelled && setService({ enabled: false, codeRequired: false }));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onCreate = () => setCreating(true);
    window.addEventListener(CREATE_AVATAR_EVENT, onCreate);
    return () => window.removeEventListener(CREATE_AVATAR_EVENT, onCreate);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function close() {
    setOpen(false);
    setConfirmDelete(false);
    trigger.current?.focus();
  }

  const go = (search: string) => window.location.assign(`/${search}`);
  const pickBody = (body: GenericBody) => {
    setPreferredBody(body);
    go("");
  };
  const mine = source.remote && !isDemoAvatar(source.id);
  const body: GenericBody | null = isGenericBody(source)
    ? source.id === MHR_GENERIC_FEMALE_AVATAR.id
      ? "female"
      : "male"
    : null;

  return (
    <>
      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="flex min-h-9 items-center gap-1.5 rounded-full bg-black/45 py-1 pl-2.5 pr-2 text-xs font-semibold text-ink backdrop-blur-md active:bg-black/60"
        data-testid="avatar-menu"
      >
        {source.remote ? <Sparkles size={14} /> : <UserRound size={14} />}
        <span>{currentLabel(source)}</span>
        <ChevronDown size={14} className="text-ink-muted" aria-hidden />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex flex-col" data-testid="avatar-sheet">
          <button type="button" aria-label="Close" tabIndex={-1} onClick={close} className="picker-backdrop absolute inset-0 bg-black/55" />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Avatar"
            className="picker-sheet relative flex max-h-[88dvh] flex-col overflow-hidden rounded-b-3xl border-b border-white/10 bg-surface-raised shadow-2xl"
          >
            <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-[max(0.75rem,env(safe-area-inset-top))]">
              <h2 className="font-display text-xl font-extrabold tracking-tight">Avatar</h2>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="flex size-9 items-center justify-center rounded-full bg-white/8 active:bg-white/15"
              >
                <X size={18} />
              </button>
            </div>

            <div className="no-scrollbar flex flex-col gap-5 overflow-y-auto px-4 pb-5 pt-1">
              <section className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold text-ink-muted">Default body</h3>
                <div className="grid grid-cols-2 gap-2">
                  {(["male", "female"] as const).map((b) => (
                    <button
                      key={b}
                      type="button"
                      onClick={() => (body === b ? close() : pickBody(b))}
                      aria-current={body === b}
                      className={`relative flex min-h-14 items-center rounded-2xl border px-3 text-left text-sm font-semibold ${
                        body === b ? "border-accent bg-accent/12" : "border-white/8 bg-white/4 active:bg-white/10"
                      }`}
                      data-testid={`body-${b}`}
                    >
                      {b === "male" ? "Man" : "Woman"}
                      {body === b && <Check size={16} className="absolute right-3 text-accent" aria-hidden />}
                    </button>
                  ))}
                </div>
              </section>

              {(service?.enabled || mine || saved) && (
                <section className="flex flex-col gap-2">
                  <h3 className="text-sm font-semibold text-ink-muted">From your photos</h3>
                  {service?.enabled && (
                    <button
                      type="button"
                      onClick={() => {
                        setOpen(false);
                        setCreating(true);
                      }}
                      className="flex min-h-14 items-center gap-3 rounded-2xl bg-accent px-4 text-left text-surface active:brightness-95"
                      data-testid="create-avatar"
                    >
                      <Camera size={18} />
                      <span className="flex flex-col">
                        <span className="text-sm font-bold">Create my avatar</span>
                        <span className="text-xs opacity-75">Three photos, ready in about 4 minutes</span>
                      </span>
                    </button>
                  )}
                  {saved && saved !== source.id && (
                    <button
                      type="button"
                      onClick={() => go(`?avatar=${saved}`)}
                      className="flex min-h-12 items-center gap-2 rounded-2xl border border-white/8 bg-white/4 px-3 text-left text-sm font-semibold active:bg-white/10"
                    >
                      <UserRound size={16} /> Open my avatar
                    </button>
                  )}
                  {mine && (
                    <button
                      type="button"
                      onClick={async () => {
                        if (!confirmDelete) return setConfirmDelete(true);
                        await deleteRemoteAvatar(source.id).catch(() => undefined);
                        go("");
                      }}
                      className={`flex min-h-12 items-center gap-2 rounded-2xl px-3 text-left text-sm font-semibold ${
                        confirmDelete ? "bg-red-500/20 text-red-200" : "border border-white/8 bg-white/4 text-ink active:bg-white/10"
                      }`}
                      data-testid="my-avatar-delete"
                    >
                      <Trash2 size={16} /> {confirmDelete ? "Tap again to delete it for good" : "Delete my avatar"}
                    </button>
                  )}
                </section>
              )}

              {AVATAR_SERVICE_URL && (
                <section className="flex flex-col gap-2">
                  <h3 className="text-sm font-semibold text-ink-muted">Demo avatars</h3>
                  <div className="grid grid-cols-2 gap-2">
                    {DEMO_AVATARS.map((d) => (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => (d.id === source.id ? close() : go(`?avatar=${d.id}`))}
                        aria-current={d.id === source.id}
                        className={`relative flex min-h-14 items-center gap-2 rounded-2xl border px-3 text-left text-sm font-semibold ${
                          d.id === source.id ? "border-accent bg-accent/12" : "border-white/8 bg-white/4 active:bg-white/10"
                        }`}
                        data-testid={`demo-${d.id}`}
                      >
                        <Sparkles size={15} className="shrink-0 text-ink-muted" aria-hidden />
                        {d.label}
                        {d.id === source.id && <Check size={16} className="absolute right-3 text-accent" aria-hidden />}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-ink-muted/80">Made from AI-generated photos and kept for demos.</p>
                </section>
              )}
            </div>
          </div>
        </div>
      )}

      {creating && service && <AvatarCreator codeRequired={service.codeRequired} onClose={() => setCreating(false)} />}
    </>
  );
}
