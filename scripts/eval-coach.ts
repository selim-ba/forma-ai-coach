/**
 * Live evaluation of the coach against the IMPLEMENTATION_PLAN test prompts.
 *
 *   npm run dev                 # in one terminal (real GPT: OPENAI_API_KEY in .env.local)
 *   npm run coach:eval          # in another
 *
 * Sends the 8 prompts in sequence, carrying the scene state forward exactly
 * like the browser does (validated commands applied with the same reducer),
 * and checks the resulting scene — not the exact wording or command list.
 * Gate (hour 13): at least 5 prompts produce valid, allowlisted actions.
 */
import { applyCommands, INITIAL_SCENE, toSnapshot } from "../src/lib/scene/reducer";
import type { ChatTurn, CoachError, CoachSuccess } from "../src/types/coach";
import type { SceneState } from "../src/types/scene";

const BASE = process.env.COACH_URL ?? "http://localhost:3000";

type Check = (r: { before: SceneState; after: SceneState; body: CoachSuccess }) => string | null;

const cases: { prompt: string; check: Check }[] = [
  {
    prompt: "Show a squat from the side.",
    check: ({ after }) =>
      after.exerciseId === "squat" && after.view === "side" && after.playing ? null : "expected squat, side view, playing",
  },
  {
    prompt: "Pause at the lowest point.",
    check: ({ after }) => (after.phase === "bottom" && !after.playing ? null : "expected paused at bottom"),
  },
  {
    prompt: "Play it slowly.",
    check: ({ after }) => (after.speed === 0.5 && after.playing ? null : "expected 0.5× and playing"),
  },
  {
    prompt: "Show me a biceps curl from the front.",
    check: ({ after }) =>
      after.exerciseId === "biceps_curl" && after.view === "front" && after.playing ? null : "expected curl, front, playing",
  },
  {
    prompt: "Explain what I should look for in a squat.",
    check: ({ body }) => (body.message.length > 20 ? null : "expected a catalog-based explanation"),
  },
  {
    prompt: "Show me a deadlift.",
    check: ({ body }) =>
      body.commands.some((c) => c.type === "select_exercise")
        ? "must not switch exercise for an unsupported request"
        : /squat|curl/i.test(body.message)
          ? null
          : "expected an offer of the supported exercises",
  },
  {
    prompt: "Make the knees bend backwards.",
    check: ({ body }) => (body.commands.length === 0 ? null : "must not change the scene for an unsafe request"),
  },
  {
    prompt: "Rotate the camera and replay.",
    check: ({ before, after, body }) =>
      body.commands.some((c) => c.type === "set_view") && after.playing && after.viewNonce > before.viewNonce
        ? null
        : "expected a view change and playback",
  },
];

let scene: SceneState = INITIAL_SCENE;
const history: ChatTurn[] = [];
let passed = 0;
let mode = "?";
const latencies: number[] = [];

try {
  const status = (await (await fetch(`${BASE}/api/coach`)).json()) as { mode: string };
  mode = status.mode;
} catch {
  console.error(`✗ Can't reach ${BASE}. Start the app with \`npm run dev\` first.`);
  process.exit(1);
}
console.log(`Coach mode: ${mode}${mode !== "openai" ? "  (not GPT — set OPENAI_API_KEY and COACH_MODE=openai for a live run)" : ""}\n`);

for (const [i, { prompt, check }] of cases.entries()) {
  const started = Date.now();
  const res = await fetch(`${BASE}/api/coach`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message: prompt, scene: toSnapshot(scene), history: history.slice(-6) }),
  });
  const ms = Date.now() - started;
  const body = (await res.json()) as CoachSuccess | CoachError;
  if (!res.ok || "error" in body) {
    console.log(`${i + 1}. ✗ "${prompt}"  HTTP ${res.status} ${"error" in body ? body.error : ""} (${ms} ms)`);
    if (res.status === 429) console.log("   rate-limited: raise COACH_RATE_LIMIT_PER_MIN for evals");
    continue;
  }
  latencies.push(ms);
  const before = scene;
  const { state: after, results } = applyCommands(scene, body.commands);
  const clientRejected = results.filter((r) => !r.ok).length;
  const problem =
    body.rejected.length > 0
      ? `model proposed ${body.rejected.length} invalid command(s): ${body.rejected.map((r) => r.detail).join("; ")}`
      : clientRejected > 0
        ? "client reducer rejected a server-accepted command"
        : check({ before, after, body });
  if (!problem) passed++;
  scene = after;
  history.push({ role: "user", content: prompt }, { role: "assistant", content: body.message });

  const cmds = body.commands.map((c) => Object.values(c).join(":")).join(", ") || "—";
  console.log(`${i + 1}. ${problem ? "✗" : "✓"} "${prompt}"  (${ms} ms)`);
  console.log(`   commands: ${cmds}`);
  console.log(`   reply:    ${body.message}`);
  if (problem) console.log(`   problem:  ${problem}`);
}

const sorted = [...latencies].sort((a, b) => a - b);
const p50 = sorted[Math.floor(sorted.length / 2)] ?? 0;
console.log(`\n${passed}/${cases.length} passed · median latency ${p50} ms · max ${sorted.at(-1) ?? 0} ms`);
console.log(passed >= 5 ? "Gate (≥5 valid) ✓" : "Gate (≥5 valid) ✗");
process.exit(passed >= 5 ? 0 : 1);
