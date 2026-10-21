import "server-only";
import OpenAI from "openai";

/**
 * Server-only OpenAI client. Never import this from a client component:
 * `server-only` makes the build fail if that happens.
 */
let cached: OpenAI | null = null;

export function getOpenAIConfig() {
  return {
    apiKey: process.env.OPENAI_API_KEY ?? "",
    model: process.env.OPENAI_MODEL || "gpt-6.1-sol",
    reasoningEffort: (process.env.OPENAI_REASONING_EFFORT || "low") as "low" | "medium" | "high",
    timeoutMs: Number(process.env.OPENAI_TIMEOUT_MS || 20000),
  };
}

export function getOpenAIClient(): OpenAI | null {
  const { apiKey, timeoutMs } = getOpenAIConfig();
  if (!apiKey || apiKey === "replace_me") return null;
  cached ??= new OpenAI({ apiKey, timeout: timeoutMs, maxRetries: 1 });
  return cached;
}
