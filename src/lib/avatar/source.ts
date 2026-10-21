import { MODEL_URL } from "@/lib/exercises/catalog";

export type AvatarSource = {
  id: string;
  url: string;
  /** Shown under the viewer so nobody mistakes the avatar for a measurement. */
  label: string;
  personal: boolean;
};

export const DEFAULT_AVATAR: AvatarSource = {
  id: "mannequin",
  url: MODEL_URL,
  label: "generic mannequin",
  personal: false,
};

/**
 * Pick the avatar from the page URL:
 *   (none) | ?avatar=mannequin  -> procedural mannequin (default, deployed)
 *   ?avatar=mhr-generic         -> generic MHR body (public/models/mhr-generic.glb)
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
  if (!id || id === "mannequin" || !/^[a-z0-9-]{1,40}$/.test(id)) return DEFAULT_AVATAR;
  if (id === "mhr-generic") {
    return { id, url: "/models/mhr-generic.glb", label: "generic MHR body", personal: false };
  }
  return { id, url: `/models/avatars/${id}.glb`, label: "approximate body shape from a photo", personal: true };
}
