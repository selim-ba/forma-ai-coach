"use client";

import { isGenericBody, MHR_GENERIC_FEMALE_AVATAR, setPreferredBody, type GenericBody } from "@/lib/avatar/source";
import { useSceneStore } from "@/lib/scene/store";

const OPTIONS: { body: GenericBody; label: string }[] = [
  { body: "male", label: "Man" },
  { body: "female", label: "Woman" },
];

/** Man / woman switch for the generic body; remembered on this phone. */
export function BodySwitch() {
  const source = useSceneStore((s) => s.avatarSource);
  if (!isGenericBody(source)) return null;
  const current: GenericBody = source.id === MHR_GENERIC_FEMALE_AVATAR.id ? "female" : "male";
  return (
    <div role="group" aria-label="Body" className="flex rounded-full bg-black/45 p-0.5 backdrop-blur-md" data-testid="body-switch">
      {OPTIONS.map((o) => (
        <button
          key={o.body}
          type="button"
          aria-pressed={o.body === current}
          onClick={() => {
            if (o.body === current) return;
            setPreferredBody(o.body);
            window.location.assign("/");
          }}
          className={`min-h-8 rounded-full px-3 text-xs font-semibold ${
            o.body === current ? "bg-ink text-surface" : "text-ink-muted active:bg-white/10"
          }`}
          data-testid={`body-${o.body}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
