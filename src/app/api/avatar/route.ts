import { timingSafeEqual } from "node:crypto";
import { clientKey, createRateLimiter } from "@/lib/server/rate-limit";

/**
 * Forwards the three avatar photos to the avatar service (services/avatar on Modal),
 * adding the shared token that only this server knows. The browser then follows
 * progress and downloads the avatar from the service directly, by its random id.
 *
 *   GET  /api/avatar          -> { enabled, codeRequired }
 *   POST /api/avatar          multipart: front, side, back (JPEG), code?  -> { id }
 *   POST /api/avatar?warm=1   start a worker early (no photos)
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const MAX_PHOTO_BYTES = 4 * 1024 * 1024;
const VIEWS = ["front", "side", "back"] as const;

const createLimiter = createRateLimiter({ limit: Number(process.env.AVATAR_RATE_LIMIT_PER_HOUR || 6), windowMs: 3_600_000 });
const warmLimiter = createRateLimiter({ limit: 30, windowMs: 3_600_000 });

function config() {
  const url = (process.env.AVATAR_SERVICE_URL ?? "").replace(/\/+$/, "");
  const token = process.env.AVATAR_TOKEN ?? "";
  const code = process.env.AVATAR_ACCESS_CODE ?? "";
  const enabled = Boolean(url && token && process.env.NEXT_PUBLIC_AVATAR_SERVICE_URL);
  return { url, token, code, enabled };
}

function codeMatches(given: string, expected: string) {
  const a = Buffer.from(given.trim().toLowerCase());
  const b = Buffer.from(expected.trim().toLowerCase());
  return a.length === b.length && timingSafeEqual(a, b);
}

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  Response.json(body, { status, headers: { "cache-control": "no-store", ...headers } });

export async function GET() {
  const { enabled, code } = config();
  return json({ enabled, codeRequired: Boolean(code) });
}

export async function POST(req: Request) {
  const { url, token, code, enabled } = config();
  if (!enabled) return json({ error: "disabled", message: "Avatar creation isn't set up on this server." }, 503);

  if (new URL(req.url).searchParams.get("warm") === "1") {
    if (!warmLimiter(clientKey(req)).allowed) return json({ ok: false }, 429);
    // Fire and forget: the worker takes about a minute to start; nobody waits for it here.
    await fetch(`${url}/warm`, { method: "POST", headers: { "X-Avatar-Token": token }, signal: AbortSignal.timeout(10_000) }).catch(
      () => undefined,
    );
    return json({ ok: true });
  }

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return json({ error: "bad_request", message: "The photos didn't arrive. Please try again." }, 400);
  }
  // Rate-limit before checking the code, so wrong codes can't be tried endlessly either.
  const limit = createLimiter(clientKey(req));
  if (!limit.allowed) {
    return json({ error: "rate_limited", message: "Too many attempts from this device. Try again later." }, 429, {
      "retry-after": String(limit.retryAfterSec),
    });
  }
  if (code && !codeMatches(String(form.get("code") ?? ""), code)) {
    return json({ error: "bad_code", message: "That access code isn't right." }, 403);
  }

  const upstream = new FormData();
  for (const view of VIEWS) {
    const file = form.get(view);
    if (!(file instanceof Blob) || file.size === 0 || file.size > MAX_PHOTO_BYTES || !file.type.startsWith("image/")) {
      return json({ error: "bad_photo", message: `The ${view} photo is missing or too large.` }, 400);
    }
    upstream.append(view, file, `${view}.jpg`);
  }
  upstream.append("keep", "false");

  try {
    const res = await fetch(`${url}/avatars`, {
      method: "POST",
      headers: { "X-Avatar-Token": token },
      body: upstream,
      signal: AbortSignal.timeout(50_000),
    });
    if (!res.ok) {
      console.error(JSON.stringify({ event: "avatar_upstream_error", status: res.status }));
      return json({ error: "upstream", message: "The avatar service is unavailable. Please try again." }, 502);
    }
    const { id } = (await res.json()) as { id: string };
    console.info(JSON.stringify({ event: "avatar_created", id }));
    return json({ id });
  } catch {
    return json({ error: "upstream", message: "The avatar service didn't answer. Please try again." }, 502);
  }
}
