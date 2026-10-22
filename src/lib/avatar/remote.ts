/**
 * Browser-side helpers for personal avatars made by the avatar service
 * (services/avatar, on Modal). Creating one goes through our own /api/avatar
 * route, which holds the service token; progress, the GLB and deletion are
 * read straight from the service by the avatar's unguessable id.
 */
export const AVATAR_SERVICE_URL = (process.env.NEXT_PUBLIC_AVATAR_SERVICE_URL ?? "").replace(/\/+$/, "");
export const REMOTE_AVATAR_ID = /^r-[0-9a-f]{24}$/;
/** The last avatar this browser created, so the person can reopen it. */
export const MY_AVATAR_KEY = "forma.myAvatar";

export type RemoteAvatarStatus = {
  id: string;
  state: "queued" | "working" | "done" | "error";
  stage: "queued" | "shape" | "build" | "done" | "error";
  message: string;
  warnings?: string[] | null;
  views?: string[] | null;
  heightM?: number | null;
  seconds?: number | null;
  /** Unix seconds; null for kept avatars. */
  expires: number | null;
};

export const remoteGlbUrl = (id: string) => `${AVATAR_SERVICE_URL}/avatars/${id}/model.glb`;

export async function fetchRemoteStatus(id: string, signal?: AbortSignal): Promise<RemoteAvatarStatus | null> {
  const res = await fetch(`${AVATAR_SERVICE_URL}/avatars/${id}`, { cache: "no-store", signal });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`status ${res.status}`);
  return (await res.json()) as RemoteAvatarStatus;
}

export async function deleteRemoteAvatar(id: string): Promise<void> {
  await fetch(`${AVATAR_SERVICE_URL}/avatars/${id}`, { method: "DELETE" });
  forgetMyAvatar(id);
}

export function rememberMyAvatar(id: string) {
  try {
    localStorage.setItem(MY_AVATAR_KEY, id);
  } catch {
    // Private mode or storage disabled: the link in the address bar still works.
  }
}

export function myAvatarId(): string | null {
  try {
    const id = localStorage.getItem(MY_AVATAR_KEY);
    return id && REMOTE_AVATAR_ID.test(id) ? id : null;
  } catch {
    return null;
  }
}

export function forgetMyAvatar(id?: string) {
  try {
    if (!id || localStorage.getItem(MY_AVATAR_KEY) === id) localStorage.removeItem(MY_AVATAR_KEY);
  } catch {
    // ignore
  }
}

/**
 * Re-encode a camera photo as an upright JPEG no larger than maxSide pixels.
 * Keeps uploads small (three photos stay well under the 4.5 MB request limit)
 * and drops the photo's metadata (location, device) along the way.
 */
export async function prepareJpeg(file: Blob, maxSide = 2048, quality = 0.88): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const width = Math.round(bitmap.width * scale);
  const height = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
  if (!blob) throw new Error("Couldn't read the photo");
  return blob;
}
