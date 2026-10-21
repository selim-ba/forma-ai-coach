/**
 * Minimal in-memory sliding-window rate limiter.
 *
 * Good enough for a demo on a single server instance. On serverless hosting
 * each instance keeps its own window, so treat it as a speed bump, not a
 * security control; use a shared store (e.g. Upstash/Redis) before going public.
 */
export type RateLimiter = (key: string) => { allowed: boolean; retryAfterSec: number };

export function createRateLimiter({
  limit,
  windowMs,
  now = () => Date.now(),
  maxKeys = 5000,
}: {
  limit: number;
  windowMs: number;
  now?: () => number;
  maxKeys?: number;
}): RateLimiter {
  const hits = new Map<string, number[]>();

  return (key: string) => {
    const t = now();
    const recent = (hits.get(key) ?? []).filter((ts) => t - ts < windowMs);
    if (recent.length >= limit) {
      hits.set(key, recent);
      const retryAfterSec = Math.max(1, Math.ceil((windowMs - (t - recent[0])) / 1000));
      return { allowed: false, retryAfterSec };
    }
    recent.push(t);
    hits.set(key, recent);
    if (hits.size > maxKeys) {
      // Drop the oldest key to bound memory.
      const oldest = hits.keys().next().value;
      if (oldest !== undefined) hits.delete(oldest);
    }
    return { allowed: true, retryAfterSec: 0 };
  };
}

export function clientKey(req: Request): string {
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return req.headers.get("x-real-ip") ?? "local";
}
