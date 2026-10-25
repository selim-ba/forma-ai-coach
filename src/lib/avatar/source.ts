import { MODEL_URL } from "@/lib/exercises/catalog";
import { AVATAR_SERVICE_URL, REMOTE_AVATAR_ID, remoteGlbUrl } from "./remote";

export type AvatarSource = {
  id: string;
  url: string;
  /** Shown under the viewer so nobody mistakes the avatar for a measurement. */
  label: string;
  personal: boolean;
  /** Made by the avatar service from the person's photos (temporary, deletable). */
  remote?: boolean;
};

export const MANNEQUIN_AVATAR: AvatarSource = {
  id: "mannequin",
  url: MODEL_URL,
  label: "generic mannequin",
  personal: false,
};

export const MHR_GENERIC_AVATAR: AvatarSource = {
  id: "mhr-generic",
  url: "/models/mhr-generic.glb",
  label: "generic body",
  personal: false,
};

export const MHR_GENERIC_FEMALE_AVATAR: AvatarSource = {
  id: "mhr-generic-f",
  url: "/models/mhr-generic-f.glb",
  label: "generic body",
  personal: false,
};

/** What the app shows when no ?avatar= is given (before the viewer's man/woman choice). */
export const DEFAULT_AVATAR: AvatarSource = MHR_GENERIC_AVATAR;

export type GenericBody = "male" | "female";
const BODY_KEY = "forma-body";

/** The default body this phone last chose (a per-device convenience; never required). */
export function preferredBody(): GenericBody {
  try {
    return window.localStorage.getItem(BODY_KEY) === "female" ? "female" : "male";
  } catch {
    return "male";
  }
}

export function setPreferredBody(body: GenericBody): void {
  try {
    window.localStorage.setItem(BODY_KEY, body);
  } catch {
    // private mode etc.: the choice just isn't remembered
  }
}

export function isGenericBody(source: AvatarSource): boolean {
  return source.id === MHR_GENERIC_AVATAR.id || source.id === MHR_GENERIC_FEMALE_AVATAR.id;
}

/**
 * Pick the avatar from the page URL:
 *   (none)                       -> generic body, man or woman as last chosen on this phone
 *   ?avatar=mhr-generic(-f)      -> generic MHR body, man (default) or woman
 *   ?avatar=mannequin            -> procedural wooden mannequin
 *   ?avatar=r-<24 hex>           -> personal avatar made by the avatar service (services/avatar)
 *   ?avatar=<name>              -> personal avatar (public/models/avatars/<name>.glb, git-ignored, local only)
 * MHR GLBs (build_avatar.py) have every catalog clip; the mannequin only the squat and the
 * curl (the viewer marks the other exercises unavailable).
 */
export function resolveAvatar(search: string): AvatarSource {
  const source = pickAvatar(search);
  // In development, bust any cached copy so a freshly regenerated GLB always shows up.
  if (process.env.NODE_ENV !== "production") return { ...source, url: `${source.url}?v=${Date.now()}` };
  return source;
}

function pickAvatar(search: string): AvatarSource {
  const id = new URLSearchParams(search).get("avatar");
  if (!id || !/^[a-z0-9-]{1,40}$/.test(id)) {
    return typeof window !== "undefined" && preferredBody() === "female" ? MHR_GENERIC_FEMALE_AVATAR : DEFAULT_AVATAR;
  }
  if (id === "mannequin") return MANNEQUIN_AVATAR;
  if (id === "mhr-generic") return MHR_GENERIC_AVATAR;
  if (id === "mhr-generic-f") return MHR_GENERIC_FEMALE_AVATAR;
  if (REMOTE_AVATAR_ID.test(id) && AVATAR_SERVICE_URL) {
    return { id, url: remoteGlbUrl(id), label: "approximate body from your photos", personal: true, remote: true };
  }
  return { id, url: `/models/avatars/${id}.glb`, label: "approximate body shape from a photo", personal: true };
}
