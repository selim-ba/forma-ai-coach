/**
 * Allowlist of visual form cues (arrows, guide lines, joint rings drawn on the
 * moving avatar). Each id belongs to one exercise; the geometry and wording
 * live in src/lib/cues/catalog.ts. The coach can only pick from these ids.
 */
export const CUE_IDS = [
  "squat.knees_over_toes",
  "squat.hips_back",
  "squat.chest_up",
  "curl.elbows_pinned",
  "curl.still_torso",
  "press.straight_up",
  "press.ribs_down",
  "rdl.flat_back",
  "rdl.hips_back",
  "rdl.close_to_legs",
  "split.straight_down",
  "split.front_knee",
  "split.tall_torso",
  "goblet.elbows_down",
  "goblet.chest_up",
  "goblet.knees_over_toes",
  "swing.flat_back",
  "swing.hip_drive",
  "swing.chest_height",
  "row.flat_back",
  "row.elbows_back",
  "raise.shoulder_height",
  "raise.shoulders_down",
  "raise.no_swing",
] as const;
export type CueId = (typeof CUE_IDS)[number];

/** At most this many cues on screen at once (keeps the picture readable on a phone). */
export const MAX_CUES = 3;
