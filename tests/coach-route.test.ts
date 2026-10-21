import { describe, expect, it, vi } from "vitest";
import { handleCoachRequest, type CoachDeps, type ResponseLike, type ResponsesClient } from "@/lib/coach/handler";
import { createRateLimiter } from "@/lib/server/rate-limit";
import { CONTROL_SCENE_TOOL } from "@/lib/openai/tools";
import { COMMAND_TYPES, EXERCISE_IDS, PHASES, VIEWS } from "@/types/scene";
import type { CoachError, CoachSuccess } from "@/types/coach";

const scene = { exerciseId: "biceps_curl", playing: false, speed: 1, view: "front", phase: null } as const;

function request(body: unknown, headers: Record<string, string> = {}) {
  return new Request("http://localhost/api/coach", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

/** Flat tool-call command as GPT emits it under strict mode. */
const flat = (c: Record<string, unknown>) => ({ exerciseId: null, view: null, speed: null, phase: null, ...c });

function toolCall(commands: unknown[], callId = "call_1", reply?: string): ResponseLike {
  return {
    id: "resp_1",
    output: [
      { type: "reasoning", id: "rs_1", summary: [] },
      {
        type: "function_call",
        id: "fc_1",
        call_id: callId,
        name: "control_scene",
        arguments: JSON.stringify(reply === undefined ? { commands } : { commands, reply }),
      },
    ],
  };
}
const text = (t: string): ResponseLike => ({
  id: "resp_2",
  output: [{ type: "message", content: [{ type: "output_text", text: t }] }],
});

function fakeClient(...responses: (ResponseLike | Error)[]) {
  const create = vi.fn(async () => {
    const next = responses.shift();
    if (!next) throw new Error("unexpected extra call");
    if (next instanceof Error) throw next;
    return next;
  });
  return { client: { responses: { create } } as unknown as ResponsesClient, create };
}

function deps(overrides: Partial<CoachDeps> = {}): CoachDeps {
  return {
    mode: "openai",
    getClient: () => null,
    model: "gpt-6.1-sol",
    reasoningEffort: "low",
    timeoutMs: 5000,
    rateLimiter: createRateLimiter({ limit: 100, windowMs: 60_000 }),
    keyFor: () => "test",
    ...overrides,
  };
}

async function call(body: unknown, d: CoachDeps) {
  const res = await handleCoachRequest(request(body), d);
  return { status: res.status, body: (await res.json()) as CoachSuccess & CoachError };
}

describe("POST /api/coach — OpenAI tool loop", () => {
  it("returns validated commands and the follow-up message, correlating call_id", async () => {
    const { client, create } = fakeClient(
      toolCall([
        flat({ type: "select_exercise", exerciseId: "squat" }),
        flat({ type: "set_view", view: "side" }),
        flat({ type: "play" }),
      ]),
      text("Here's a side-view squat."),
    );
    const { status, body } = await call({ message: "Show a squat from the side", scene }, deps({ getClient: () => client }));
    expect(status).toBe(200);
    expect(body.commands).toEqual([
      { type: "select_exercise", exerciseId: "squat" },
      { type: "set_view", view: "side" },
      { type: "play" },
    ]);
    expect(body.message).toBe("Here's a side-view squat.");
    expect(body.source).toBe("openai");

    expect(create).toHaveBeenCalledTimes(2);
    const second = (create.mock.calls[1] as unknown as [Record<string, unknown>])[0];
    const input = second.input as Record<string, unknown>[];
    const output = input.find((i) => i.type === "function_call_output")!;
    expect(output.call_id).toBe("call_1");
    // Reasoning and function_call items are passed back unchanged.
    expect(input.some((i) => i.type === "reasoning")).toBe(true);
    expect(input.some((i) => i.type === "function_call")).toBe(true);
    expect(second.tool_choice).toBe("none");
  });

  it("uses the tool's reply and skips the second call when every command is valid", async () => {
    const { client, create } = fakeClient(
      toolCall([flat({ type: "set_speed", speed: 0.5 }), flat({ type: "play" })], "call_9", "Playing at half speed."),
    );
    const { status, body } = await call({ message: "Play it slowly", scene }, deps({ getClient: () => client }));
    expect(status).toBe(200);
    expect(create).toHaveBeenCalledTimes(1);
    expect(body.message).toBe("Playing at half speed.");
    expect(body.commands).toEqual([{ type: "set_speed", speed: 0.5 }, { type: "play" }]);
  });

  it("falls back to the explaining follow-up call when a command is rejected, even with a reply", async () => {
    const { client, create } = fakeClient(
      toolCall([flat({ type: "seek_phase", phase: "bottom" })], "call_8", "Paused at the bottom."),
      text("The curl has no bottom marker; it starts with your arms extended."),
    );
    const { body } = await call({ message: "Pause at the bottom", scene }, deps({ getClient: () => client }));
    expect(create).toHaveBeenCalledTimes(2);
    expect(body.message).toMatch(/no bottom marker/);
    expect(body.commands).toEqual([]);
  });

  it("drops semantically invalid commands (curl has no bottom) and reports them", async () => {
    const { client } = fakeClient(
      toolCall([flat({ type: "seek_phase", phase: "bottom" }), flat({ type: "pause" })]),
      text("The curl has no bottom marker."),
    );
    const { body } = await call({ message: "Pause at the bottom", scene }, deps({ getClient: () => client }));
    expect(body.commands).toEqual([{ type: "pause" }]);
    expect(body.rejected).toHaveLength(1);
    expect(body.rejected[0].reason).toBe("unsupported_phase");
  });

  it("rejects commands missing required arguments or with invented values", async () => {
    const { client } = fakeClient(
      toolCall([
        flat({ type: "select_exercise" }),
        flat({ type: "set_speed", speed: 3 }),
        { type: "rotate_bone", bone: "LeftKnee", degrees: -90 },
        flat({ type: "play" }),
      ]),
      text("Playing."),
    );
    const { body } = await call({ message: "play", scene }, deps({ getClient: () => client }));
    expect(body.commands).toEqual([{ type: "play" }]);
    expect(body.rejected.map((r) => r.reason)).toEqual(["invalid_command", "invalid_command", "invalid_command"]);
  });

  it("handles malformed JSON arguments without throwing", async () => {
    const { client } = fakeClient(
      { output: [{ type: "function_call", call_id: "c", name: "control_scene", arguments: "{not json" }] },
      text("Sorry, try again."),
    );
    const { status, body } = await call({ message: "play", scene }, deps({ getClient: () => client }));
    expect(status).toBe(200);
    expect(body.commands).toEqual([]);
  });

  it("returns text-only answers with no commands", async () => {
    const { client, create } = fakeClient(text("Keep your upper arms close to your sides."));
    const { body } = await call({ message: "What should I pay attention to?", scene }, deps({ getClient: () => client }));
    expect(body.commands).toEqual([]);
    expect(body.message).toMatch(/upper arms/);
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("sends the catalog-grounded instructions, the tool and the scene state", async () => {
    const { client, create } = fakeClient(text("ok"));
    await call({ message: "hi", scene }, deps({ getClient: () => client }));
    const first = (create.mock.calls[0] as unknown as [Record<string, unknown>])[0];
    expect(first.model).toBe("gpt-6.1-sol");
    expect(String(first.instructions)).toContain("Keep your upper arms close to your sides");
    expect(first.tools).toEqual([CONTROL_SCENE_TOOL]);
    const input = first.input as { role?: string; content?: string }[];
    const sceneMessage = input.find((m) => m.role === "developer")?.content ?? "";
    expect(sceneMessage).toContain('"exerciseId":"biceps_curl"');
    expect(input.at(-1)).toEqual({ role: "user", content: "hi" });
  });

  it("maps provider failures to a sanitized 502 and never leaks details", async () => {
    const { client } = fakeClient(Object.assign(new Error("401 Incorrect API key sk-live-123"), { status: 401 }));
    const log = vi.fn();
    const { status, body } = await call({ message: "play", scene }, deps({ getClient: () => client, log }));
    expect(status).toBe(502);
    expect(body.error).toBe("coach_failed");
    expect(JSON.stringify(body)).not.toContain("sk-live");
    expect(log).toHaveBeenCalledWith(expect.objectContaining({ event: "coach_error", status: 401 }));
  });

  it("maps timeouts to 504", async () => {
    const slow: ResponsesClient = {
      responses: {
        create: (_body, opts) =>
          new Promise((_, reject) => {
            opts?.signal?.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
          }),
      },
    };
    const { status, body } = await call({ message: "play", scene }, deps({ getClient: () => slow, timeoutMs: 20 }));
    expect(status).toBe(504);
    expect(body.error).toBe("coach_timeout");
  });

  it("returns 503 when no API key is configured", async () => {
    const { status, body } = await call({ message: "play", scene }, deps());
    expect(status).toBe(503);
    expect(body.error).toBe("coach_unavailable");
  });
});

describe("POST /api/coach — input limits", () => {
  it("rejects oversized, malformed and invalid bodies", async () => {
    const d = deps({ mode: "mock" });
    expect((await call("{oops", d)).status).toBe(400);
    expect((await call({ message: "", scene }, d)).status).toBe(400);
    expect((await call({ message: "x".repeat(501), scene }, d)).status).toBe(400);
    expect((await call({ message: "hi", scene: { ...scene, exerciseId: "deadlift" } }, d)).status).toBe(400);
    expect((await call({ message: "hi", scene, junk: "y".repeat(9000) }, d)).status).toBe(413);
  });

  it("rate-limits per client key", async () => {
    const d = deps({ mode: "mock", rateLimiter: createRateLimiter({ limit: 2, windowMs: 60_000 }) });
    expect((await call({ message: "play", scene }, d)).status).toBe(200);
    expect((await call({ message: "play", scene }, d)).status).toBe(200);
    const res = await handleCoachRequest(request({ message: "play", scene }), d);
    expect(res.status).toBe(429);
    expect(Number(res.headers.get("retry-after"))).toBeGreaterThan(0);
  });
});

describe("mock coach — IMPLEMENTATION_PLAN test prompts", () => {
  const d = deps({ mode: "mock" });
  const squatScene = { ...scene, exerciseId: "squat" } as const;
  const cases: [string, typeof scene | typeof squatScene, unknown[]][] = [
    ["Show a squat from the side.", scene, [{ type: "select_exercise", exerciseId: "squat" }, { type: "set_view", view: "side" }, { type: "play" }]],
    ["Pause at the lowest point.", squatScene, [{ type: "seek_phase", phase: "bottom" }, { type: "pause" }]],
    ["Play it slowly.", squatScene, [{ type: "set_speed", speed: 0.5 }, { type: "play" }]],
    ["Show me a biceps curl from the front.", squatScene, [{ type: "select_exercise", exerciseId: "biceps_curl" }, { type: "set_view", view: "front" }, { type: "play" }]],
    ["Explain what I should look for in a squat.", squatScene, []],
    ["Show me a deadlift.", squatScene, []],
    ["Make the knees bend backwards.", squatScene, []],
    ["Rotate the camera and replay.", squatScene, [{ type: "set_view", view: "side" }, { type: "seek_phase", phase: "start" }, { type: "play" }]],
  ];
  it.each(cases)("%s", async (message, s, expected) => {
    const { status, body } = await call({ message, scene: s }, d);
    expect(status).toBe(200);
    expect(body.commands).toEqual(expected);
    expect(body.rejected).toEqual([]);
    expect(body.message.length).toBeGreaterThan(0);
  });

  it("explanations come from catalog cues", async () => {
    const { body } = await call({ message: "Explain what I should look for in a squat.", scene: squatScene }, d);
    expect(body.message).toContain("knees travel in the same direction as your toes");
  });
});

describe("control_scene tool schema", () => {
  it("is strict and its enums match the app allowlists", () => {
    const items = CONTROL_SCENE_TOOL.parameters.properties.commands.items;
    expect(CONTROL_SCENE_TOOL.strict).toBe(true);
    expect([...CONTROL_SCENE_TOOL.parameters.required].sort()).toEqual(
      Object.keys(CONTROL_SCENE_TOOL.parameters.properties).sort(),
    );
    expect(items.additionalProperties).toBe(false);
    expect([...items.required].sort()).toEqual(Object.keys(items.properties).sort());
    expect(items.properties.type.enum).toEqual([...COMMAND_TYPES]);
    expect(items.properties.exerciseId.enum).toEqual([...EXERCISE_IDS, null]);
    expect(items.properties.view.enum).toEqual([...VIEWS, null]);
    expect(items.properties.phase.enum).toEqual([...PHASES, null]);
    expect(items.properties.speed.enum).toEqual([0.5, 1, null]);
  });
});
