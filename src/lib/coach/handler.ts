import { z } from "zod";
import { MAX_COMMANDS, SceneSnapshotSchema } from "@/lib/scene/commands";
import { applyCommands, sceneFromSnapshot } from "@/lib/scene/reducer";
import { COACH_INSTRUCTIONS, sceneContextMessage } from "@/lib/openai/system-prompt";
import {
  CONTROL_SCENE_TOOL,
  CONTROL_SCENE_TOOL_NAME,
  ControlSceneArgsSchema,
  toSceneCommand,
} from "@/lib/openai/tools";
import type { CoachError, CoachErrorCode, CoachSuccess, RejectedCommand } from "@/types/coach";
import type { SceneCommand, SceneSnapshot } from "@/types/scene";
import { mockCoach } from "./mock";
import type { RateLimiter } from "@/lib/server/rate-limit";

export const MAX_BODY_BYTES = 8 * 1024;
export const MAX_MESSAGE_CHARS = 500;
export const MAX_HISTORY_TURNS = 6;
export const MAX_REPLY_CHARS = 600;

export const CoachRequestSchema = z.object({
  message: z.string().trim().min(1).max(MAX_MESSAGE_CHARS),
  scene: SceneSnapshotSchema,
  history: z
    .array(z.object({ role: z.enum(["user", "assistant"]), content: z.string().max(1000) }))
    .max(20)
    .optional()
    .default([]),
});

// ---------------------------------------------------------------------------
// Minimal structural types for the parts of the Responses API we use, so the
// handler can be unit-tested with a fake client.
// ---------------------------------------------------------------------------
type OutputItem =
  | { type: "function_call"; call_id: string; name: string; arguments: string; [k: string]: unknown }
  | { type: "message"; content?: Array<{ type: string; text?: string }>; [k: string]: unknown }
  | { type: string; [k: string]: unknown };

export type ResponseLike = { id?: string; output: OutputItem[]; output_text?: string };

export interface ResponsesClient {
  responses: {
    create(body: Record<string, unknown>, options?: { signal?: AbortSignal }): Promise<ResponseLike>;
  };
}

export type CoachDeps = {
  mode: "openai" | "mock";
  getClient: () => ResponsesClient | null;
  model: string;
  reasoningEffort: string;
  timeoutMs: number;
  rateLimiter: RateLimiter;
  keyFor: (req: Request) => string;
  log?: (event: Record<string, unknown>) => void;
};

const USER_MESSAGES: Record<CoachErrorCode, string> = {
  bad_request: "That request couldn't be read. Try a shorter message.",
  payload_too_large: "That message is too long. Try a shorter one.",
  rate_limited: "You're sending messages quickly — wait a moment and try again.",
  coach_unavailable: "The AI coach isn't available right now. The manual controls still work.",
  coach_failed: "The coach had trouble answering. The manual controls still work.",
  coach_timeout: "The coach took too long to answer. The manual controls still work.",
};

const STATUS: Record<CoachErrorCode, number> = {
  bad_request: 400,
  payload_too_large: 413,
  rate_limited: 429,
  coach_unavailable: 503,
  coach_failed: 502,
  coach_timeout: 504,
};

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...headers },
  });
}

function errorResponse(code: CoachErrorCode, requestId: string, headers: Record<string, string> = {}) {
  const body: CoachError = { error: code, message: USER_MESSAGES[code], requestId };
  return json(body, STATUS[code], headers);
}

function outputText(response: ResponseLike): string {
  if (typeof response.output_text === "string" && response.output_text.trim()) return response.output_text.trim();
  const parts: string[] = [];
  for (const item of response.output ?? []) {
    if (item.type === "message" && Array.isArray(item.content)) {
      for (const c of item.content as Array<{ type: string; text?: string }>) {
        if (c.type === "output_text" && c.text) parts.push(c.text);
      }
    }
  }
  return parts.join("\n").trim();
}

function clampReply(text: string) {
  const clean = text.replace(/\s+\n/g, "\n").trim();
  return clean.length > MAX_REPLY_CHARS ? `${clean.slice(0, MAX_REPLY_CHARS - 1).trimEnd()}…` : clean;
}

/**
 * Validate model-proposed commands against the schema AND the current scene
 * (e.g. a "bottom" seek is rejected for the curl). Returns only commands the
 * browser reducer will also accept, in order.
 */
export function validateProposedCommands(rawCommands: unknown[], scene: SceneSnapshot) {
  const converted = rawCommands.map(toSceneCommand);
  const { results } = applyCommands(sceneFromSnapshot(scene), converted);
  const accepted: SceneCommand[] = [];
  const rejected: RejectedCommand[] = [];
  for (const r of results) {
    if (r.ok) accepted.push(r.command);
    else rejected.push({ command: r.command, reason: r.reason, detail: r.detail });
  }
  return { accepted, rejected };
}

function isAbort(error: unknown) {
  if (!(error instanceof Error)) return false;
  return error.name === "AbortError" || error.name === "APIConnectionTimeoutError" || /timed? ?out/i.test(error.message);
}

export async function handleCoachRequest(req: Request, deps: CoachDeps): Promise<Response> {
  const started = Date.now();
  const requestId = crypto.randomUUID();
  const log = deps.log ?? (() => {});

  const limit = deps.rateLimiter(deps.keyFor(req));
  if (!limit.allowed) {
    return errorResponse("rate_limited", requestId, { "retry-after": String(limit.retryAfterSec) });
  }

  const raw = await req.text();
  if (new TextEncoder().encode(raw).length > MAX_BODY_BYTES) return errorResponse("payload_too_large", requestId);
  let body: z.infer<typeof CoachRequestSchema>;
  try {
    const parsed = CoachRequestSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) return errorResponse("bad_request", requestId);
    body = parsed.data;
  } catch {
    return errorResponse("bad_request", requestId);
  }

  const history = body.history.slice(-MAX_HISTORY_TURNS);

  if (deps.mode === "mock") {
    const mock = mockCoach(body.message, body.scene);
    const { accepted, rejected } = validateProposedCommands(mock.commands, body.scene);
    const result: CoachSuccess = {
      message: mock.message,
      commands: accepted,
      rejected,
      source: "mock",
      requestId,
      latencyMs: Date.now() - started,
    };
    log({ event: "coach", source: "mock", requestId, accepted: accepted.length, rejected: rejected.length });
    return json(result);
  }

  const client = deps.getClient();
  if (!client) return errorResponse("coach_unavailable", requestId);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), deps.timeoutMs);

  try {
    const input: Record<string, unknown>[] = [
      ...history.map((turn) => ({ role: turn.role, content: turn.content })),
      { role: "developer", content: sceneContextMessage(body.scene) },
      { role: "user", content: body.message },
    ];
    const common = {
      model: deps.model,
      instructions: COACH_INSTRUCTIONS,
      tools: [CONTROL_SCENE_TOOL],
      parallel_tool_calls: false,
      reasoning: { effort: deps.reasoningEffort },
      max_output_tokens: 2000,
    };

    const first = await client.responses.create({ ...common, input }, { signal: controller.signal });
    const calls = (first.output ?? []).filter(
      (item): item is Extract<OutputItem, { type: "function_call" }> => item.type === "function_call",
    );

    let accepted: SceneCommand[] = [];
    const rejected: RejectedCommand[] = [];
    let message = outputText(first);

    if (calls.length > 0) {
      const toolOutputs: Record<string, unknown>[] = [];
      const replies: string[] = [];
      for (const call of calls) {
        if (call.name !== CONTROL_SCENE_TOOL_NAME) {
          rejected.push({ command: call.name, reason: "unknown_tool", detail: "Only control_scene is available." });
          toolOutputs.push({ type: "function_call_output", call_id: call.call_id, output: JSON.stringify({ error: "unknown tool" }) });
          continue;
        }
        let args: unknown;
        try {
          args = JSON.parse(call.arguments);
        } catch {
          args = null;
        }
        const parsedArgs = ControlSceneArgsSchema.safeParse(args);
        const proposed = parsedArgs.success ? parsedArgs.data.commands : [];
        if (parsedArgs.success && parsedArgs.data.reply?.trim()) replies.push(parsedArgs.data.reply.trim());
        if (!parsedArgs.success) {
          rejected.push({ command: args, reason: "invalid_command", detail: "Tool arguments failed validation." });
        }
        // Validate in the context of commands already accepted from earlier calls.
        const sceneSoFar = applyCommands(sceneFromSnapshot(body.scene), accepted).state;
        const remaining = Math.max(0, MAX_COMMANDS - accepted.length);
        const result = validateProposedCommands(proposed.slice(0, remaining), {
          exerciseId: sceneSoFar.exerciseId,
          playing: sceneSoFar.playing,
          speed: sceneSoFar.speed,
          view: sceneSoFar.view,
          phase: sceneSoFar.phase,
          cues: sceneSoFar.cues,
        });
        accepted = [...accepted, ...result.accepted];
        rejected.push(...result.rejected);
        if (proposed.length > remaining) {
          rejected.push({ command: proposed.slice(remaining), reason: "too_many_commands", detail: `Max ${MAX_COMMANDS} commands.` });
        }
        toolOutputs.push({
          type: "function_call_output",
          call_id: call.call_id,
          output: JSON.stringify({
            status: "validated; the browser will apply accepted commands once",
            accepted: result.accepted,
            rejected: result.rejected.map((r) => ({ reason: r.reason, detail: r.detail })),
          }),
        });
      }

      if (rejected.length === 0 && replies.length > 0) {
        // Fast path (one round trip): every proposed command validated, so the
        // reply the model wrote alongside them is accurate as-is.
        message = replies.join(" ");
      } else {
        // Slow path: something was rejected (or no reply was given). Send the
        // validated tool results back so the model can explain what happened.
        // Reasoning + function_call items are passed back as-is.
        const followUp = await client.responses.create(
          { ...common, tool_choice: "none", input: [...input, ...first.output, ...toolOutputs] },
          { signal: controller.signal },
        );
        message = outputText(followUp) || message;
      }
    }

    if (!message) message = accepted.length ? "Done — take a look." : "I can show a squat or a biceps curl. What would you like to see?";

    const result: CoachSuccess = {
      message: clampReply(message),
      commands: accepted,
      rejected,
      source: "openai",
      requestId,
      latencyMs: Date.now() - started,
    };
    log({ event: "coach", source: "openai", requestId, accepted: accepted.length, rejected: rejected.length, latencyMs: result.latencyMs });
    return json(result);
  } catch (error) {
    const timedOut = controller.signal.aborted || isAbort(error);
    // Log details server-side only; never forward provider errors to the browser.
    log({
      event: "coach_error",
      requestId,
      timedOut,
      status: (error as { status?: number })?.status,
      name: (error as Error)?.name,
      message: (error as Error)?.message?.slice(0, 300),
    });
    return errorResponse(timedOut ? "coach_timeout" : "coach_failed", requestId);
  } finally {
    clearTimeout(timer);
  }
}
