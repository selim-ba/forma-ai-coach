import type { RejectionReason, SceneCommand, SceneSnapshot } from "./scene";

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type CoachRequestBody = {
  message: string;
  scene: SceneSnapshot;
  history?: ChatTurn[];
};

export type RejectedCommand = { command: unknown; reason: RejectionReason | "unknown_tool"; detail: string };

export type CoachSuccess = {
  message: string;
  commands: SceneCommand[];
  rejected: RejectedCommand[];
  source: "openai" | "mock";
  requestId: string;
  latencyMs: number;
};

export type CoachErrorCode =
  | "bad_request"
  | "payload_too_large"
  | "rate_limited"
  | "coach_unavailable"
  | "coach_failed"
  | "coach_timeout";

export type CoachError = { error: CoachErrorCode; message: string; requestId: string };
