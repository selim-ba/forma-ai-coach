import { MODEL_URL } from "@/lib/exercises/catalog";

export type AvatarSource = {
  id: string;
  url: string;
  /** Shown under the viewer so nobody mistakes the avatar for a measurement. */
  label: string;
  personal: boolean;
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

/** What the app shows when no ?avatar= is given. */
export const DEFAULT_AVATAR: AvatarSource = MHR_GENERIC_AVATAR;

/**
 * Pick the avatar from the page URL:
 *   (none) | ?avatar=mhr-generic -> generic MHR body (default, deployed)
 *   ?avatar=mannequin            -> procedural wooden mannequin
 *   ?avatar=<name>              -> personal avatar (public/models/avatars/<name>.glb, git-ignored, local only)
 * Any GLB must provide the `squat` and `biceps_curl` clips.
 */
export function resolveAvatar(search: string): AvatarSource {
  const source = pickAvatar(search);
  // In development, bust any cached copy so a freshly regenerated GLB always shows up.
  if (process.env.NODE_ENV !== "production") return { ...source, url: `${source.url}?v=${Date.now()}` };
  return source;
}

function pickAvatar(search: string): AvatarSource {
  const id = new URLSearchParams(search).get("avatar");
  if (!id || !/^[a-z0-9-]{1,40}$/.test(id)) return DEFAULT_AVATAR;
  if (id === "mannequin") return MANNEQUIN_AVATAR;
  if (id === "mhr-generic") return MHR_GENERIC_AVATAR;
  return { id, url: `/models/avatars/${id}.glb`, label: "approximate body shape from a photo", personal: true };
}
