import { handleCoachRequest, type ResponsesClient } from "@/lib/coach/handler";
import { getOpenAIClient, getOpenAIConfig } from "@/lib/openai/client";
import { clientKey, createRateLimiter } from "@/lib/server/rate-limit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// GPT calls can take several seconds; keep serverless hosts (e.g. Vercel) from cutting them off.
export const maxDuration = 30;

const rateLimiter = createRateLimiter({
  limit: Number(process.env.COACH_RATE_LIMIT_PER_MIN || 12),
  windowMs: 60_000,
});

export async function POST(req: Request) {
  const config = getOpenAIConfig();
  return handleCoachRequest(req, {
    mode: process.env.COACH_MODE === "mock" ? "mock" : "openai",
    // The SDK client satisfies the narrow structural interface the handler uses.
    getClient: () => getOpenAIClient() as unknown as ResponsesClient | null,
    model: config.model,
    reasoningEffort: config.reasoningEffort,
    timeoutMs: config.timeoutMs,
    rateLimiter,
    keyFor: clientKey,
    log: (event) => console.info(JSON.stringify(event)),
  });
}

/** Lightweight status probe so the UI can show whether the coach is configured. */
export async function GET() {
  const mode = process.env.COACH_MODE === "mock" ? "mock" : getOpenAIClient() ? "openai" : "offline";
  return Response.json({ mode }, { headers: { "cache-control": "no-store" } });
}
