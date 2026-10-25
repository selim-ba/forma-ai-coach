"use client";

import { Camera, Sparkles, Trash2, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { DEMO_AVATARS, isDemoAvatar } from "@/lib/avatar/demo";
import { AVATAR_SERVICE_URL, deleteRemoteAvatar, myAvatarId } from "@/lib/avatar/remote";
import { useSceneStore } from "@/lib/scene/store";
import { AvatarCreator } from "./AvatarCreator";

type ServiceInfo = { enabled: boolean; codeRequired: boolean };

/**
 * Top-left viewer control. With the generic body: "Create my avatar" (when the avatar
 * service is configured) and a shortcut back to the last avatar this phone made.
 * With a personal avatar: delete it, or go back to the generic body.
 */
export function MyAvatarButton() {
  const source = useSceneStore((s) => s.avatarSource);
  const [service, setService] = useState<ServiceInfo | null>(null);
  const [creating, setCreating] = useState(false);
  const [menu, setMenu] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

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

  if (source.remote && isDemoAvatar(source.id)) {
    // Demo backups: switch between them or go back; never delete (they are the demo fallback).
    return (
      <div className="relative">
        <button
          type="button"
          onClick={() => setMenu((m) => !m)}
          className="flex min-h-9 items-center gap-1.5 rounded-full bg-black/45 px-3 text-xs font-semibold text-ink backdrop-blur-md"
          aria-expanded={menu}
          data-testid="demo-avatar-menu"
        >
          <Sparkles size={15} /> Demo avatar
        </button>
        {menu && (
          <div className="absolute left-0 top-11 z-10 flex w-56 flex-col gap-1 rounded-2xl border border-white/10 bg-surface-raised p-1.5 shadow-xl">
            {DEMO_AVATARS.filter((d) => d.id !== source.id).map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => window.location.assign(`/?avatar=${d.id}`)}
                className="flex min-h-11 items-center gap-2 rounded-xl px-3 text-left text-sm font-semibold text-ink active:bg-white/10"
              >
                <Sparkles size={16} /> {d.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => window.location.assign("/")}
              className="flex min-h-11 items-center gap-2 rounded-xl px-3 text-left text-sm text-ink-muted active:bg-white/10"
            >
              Back to the generic body
            </button>
          </div>
        )}
      </div>
    );
  }

  if (source.remote) {
    return (
      <div className="relative">
        <button
          type="button"
          onClick={() => {
            setMenu((m) => !m);
            setConfirmDelete(false);
          }}
          className="flex min-h-9 items-center gap-1.5 rounded-full bg-black/45 px-3 text-xs font-semibold text-ink backdrop-blur-md"
          aria-expanded={menu}
          data-testid="my-avatar-menu"
        >
          <UserRound size={15} /> My avatar
        </button>
        {menu && (
          <div className="absolute left-0 top-11 z-10 flex w-56 flex-col gap-1 rounded-2xl border border-white/10 bg-surface-raised p-1.5 shadow-xl">
            <button
              type="button"
              onClick={async () => {
                if (!confirmDelete) return setConfirmDelete(true);
                await deleteRemoteAvatar(source.id).catch(() => undefined);
                window.location.assign("/");
              }}
              className={`flex min-h-11 items-center gap-2 rounded-xl px-3 text-left text-sm font-semibold ${
                confirmDelete ? "bg-red-500/20 text-red-200" : "text-ink active:bg-white/10"
              }`}
              data-testid="my-avatar-delete"
            >
              <Trash2 size={16} /> {confirmDelete ? "Tap again to delete" : "Delete my avatar"}
            </button>
            <button
              type="button"
              onClick={() => window.location.assign("/")}
              className="flex min-h-11 items-center gap-2 rounded-xl px-3 text-left text-sm text-ink-muted active:bg-white/10"
            >
              Back to the generic body
            </button>
          </div>
        )}
      </div>
    );
  }

  if (source.id === "mannequin" || !AVATAR_SERVICE_URL) return null;
  return (
    <>
      <div className="relative flex flex-col items-start gap-1.5">
        <div className="flex items-center gap-1.5">
          {service?.enabled && (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="flex min-h-9 items-center gap-1.5 whitespace-nowrap rounded-full bg-accent px-3 text-xs font-bold text-surface shadow-lg"
              data-testid="create-avatar"
            >
              <Camera size={15} /> Create my avatar
            </button>
          )}
          <button
            type="button"
            onClick={() => setMenu((m) => !m)}
            aria-expanded={menu}
            aria-label="Demo avatars"
            className="flex size-9 items-center justify-center rounded-full bg-black/45 text-ink backdrop-blur-md"
            data-testid="demo-avatars"
          >
            <Sparkles size={15} />
          </button>
        </div>
        {menu && (
          <div className="absolute left-0 top-11 z-10 flex w-56 flex-col gap-1 rounded-2xl border border-white/10 bg-surface-raised p-1.5 shadow-xl">
            <p className="px-3 pb-1 pt-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-muted">Demo avatars</p>
            {DEMO_AVATARS.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => window.location.assign(`/?avatar=${d.id}`)}
                className="flex min-h-11 items-center gap-2 rounded-xl px-3 text-left text-sm font-semibold text-ink active:bg-white/10"
                data-testid={`demo-${d.id}`}
              >
                <Sparkles size={16} /> {d.label}
              </button>
            ))}
          </div>
        )}
        {saved && (
          <button
            type="button"
            onClick={() => window.location.assign(`/?avatar=${saved}`)}
            className="flex min-h-8 items-center gap-1.5 rounded-full bg-black/45 px-3 text-xs font-semibold text-ink backdrop-blur-md"
          >
            <UserRound size={14} /> Open my avatar
          </button>
        )}
      </div>
      {creating && service && (
        <AvatarCreator codeRequired={service.codeRequired} onClose={() => setCreating(false)} />
      )}
    </>
  );
}
