import type { ExerciseId, Phase } from "@/types/scene";
import type { Exercise } from "./schema";

/**
 * The exercise catalog is the authority for valid exercise IDs, phase markers
 * and coaching content. The GPT coach is only allowed to repeat these cues.
 *
 * Phase markers are authored against the clips baked by
 * research/avatar-pipeline/build_avatar.py (TIMELINES, all five exercises; the default
 * MHR body and personal avatars). The wooden mannequin (scripts/build-mannequin.ts,
 * src/lib/avatar/motions.ts) only has the squat and the curl, with the same markers.
 * Tests check these numbers against both GLBs' metadata.
 */
export const MODEL_URL = "/models/forma-mannequin.glb";

export const EXERCISES: Record<ExerciseId, Exercise> = {
  squat: {
    id: "squat",
    title: "Bodyweight squat",
    shortTitle: "Squat",
    level: "beginner",
    animationUrl: MODEL_URL,
    clipName: "squat",
    clipDuration: 4,
    availablePhases: {
      start: 0,
      middle: 0.2625, // halfway through the 1.5 s descent
      bottom: 0.5, // centre of the 0.4 s hold at depth
    },
    availableViews: ["front", "side", "three_quarter"],
    defaultView: "side",
    props: [],
    summary:
      "A beginner bodyweight squat: controlled 1.5 s descent to just above parallel, short pause, controlled rise.",
    reviewedCues: [
      "Stand with feet about shoulder-width apart, toes pointing forward or slightly out.",
      "Keep your whole foot on the floor, with weight spread across heel and mid-foot.",
      "Let your knees travel in the same direction as your toes.",
      "Send the hips back and down while keeping your chest up and back neutral.",
      "Only go as deep as you can while staying comfortable and in control.",
      "Push the floor away to stand up, and keep breathing steadily.",
    ],
    limitations: [
      "Generic demonstration body; it does not represent your body proportions.",
      "The depth shown is one demo range; comfortable depth varies from person to person.",
      "Educational visual only; not medical or injury-prevention advice. Stop if anything hurts.",
    ],
    review: {
      status: "pending_expert_review",
      note: "Conservative, widely used cues written for the MVP. Have a qualified coach review them before public use.",
    },
  },
  biceps_curl: {
    id: "biceps_curl",
    title: "Dumbbell biceps curl",
    shortTitle: "Curl",
    level: "beginner",
    animationUrl: MODEL_URL,
    clipName: "biceps_curl",
    clipDuration: 4,
    availablePhases: {
      start: 0,
      middle: 0.225, // halfway through the 1.2 s lift
      top: 0.425, // centre of the 0.4 s squeeze at the top
    },
    availableViews: ["front", "side", "three_quarter"],
    defaultView: "front",
    props: ["dumbbells"],
    summary:
      "A standing two-arm dumbbell curl with palms forward: 1.2 s lift, short pause at the top, slower 1.8 s lowering.",
    reviewedCues: [
      "Stand tall holding a light dumbbell in each hand, palms facing forward.",
      "Keep your upper arms close to your sides; only your forearms move.",
      "Curl up under control without swinging your torso or leaning back.",
      "Lower slowly until your arms are straight but relaxed.",
      "Keep your wrists neutral and your shoulders down and relaxed.",
      "Choose a weight you can lift smoothly for every repetition.",
    ],
    limitations: [
      "Generic demonstration body; it does not represent your body proportions.",
      "The curl has no separate 'bottom' marker; the start position is the arms-extended position.",
      "Educational visual only; not medical or injury-prevention advice. Stop if anything hurts.",
    ],
    review: {
      status: "pending_expert_review",
      note: "Conservative, widely used cues written for the MVP. Have a qualified coach review them before public use.",
    },
  },
  shoulder_press: {
    id: "shoulder_press",
    title: "Dumbbell shoulder press",
    shortTitle: "Press",
    level: "beginner",
    animationUrl: MODEL_URL,
    clipName: "shoulder_press",
    clipDuration: 4,
    availablePhases: {
      start: 0,
      middle: 0.225, // halfway through the 1.2 s press
      top: 0.425, // centre of the 0.4 s pause overhead
    },
    availableViews: ["front", "side", "three_quarter"],
    defaultView: "front",
    props: ["dumbbells"],
    summary:
      "A standing two-arm dumbbell shoulder press: from shoulder height, a 1.2 s press to straight arms overhead, short pause, slower 1.8 s lowering.",
    reviewedCues: [
      "Stand tall with feet hip-width apart, a light dumbbell in each hand at shoulder height, palms facing forward.",
      "Brace your stomach and squeeze your glutes so your lower back doesn't arch.",
      "Press the dumbbells up and slightly in until your arms are straight overhead, without snapping the elbows.",
      "Keep your head still and your ribs down; don't lean back to finish the press.",
      "Lower the dumbbells under control back to shoulder height.",
      "Choose a weight you can press smoothly for every repetition.",
    ],
    limitations: [
      "Generic demonstration body; it does not represent your body proportions.",
      "The press has no separate 'bottom' marker; the start position is the dumbbells at shoulder height.",
      "Educational visual only; not medical or injury-prevention advice. Stop if anything hurts.",
    ],
    review: {
      status: "pending_expert_review",
      note: "Conservative, widely used cues. Have a qualified coach review them before public use.",
    },
  },
  romanian_deadlift: {
    id: "romanian_deadlift",
    title: "Dumbbell Romanian deadlift",
    shortTitle: "Deadlift",
    level: "intermediate",
    animationUrl: MODEL_URL,
    clipName: "romanian_deadlift",
    clipDuration: 4,
    availablePhases: {
      start: 0,
      middle: 0.2625, // halfway through the 1.5 s hinge
      bottom: 0.5, // centre of the 0.4 s pause at the bottom
    },
    availableViews: ["front", "side", "three_quarter"],
    defaultView: "side",
    props: ["dumbbells"],
    summary:
      "A dumbbell Romanian deadlift: a 1.5 s hip hinge with soft knees and a flat back until the dumbbells reach about mid-shin, short pause, 1.5 s return to standing.",
    reviewedCues: [
      "Stand with feet hip-width apart, dumbbells in front of your thighs, palms facing you.",
      "Keep a slight bend in your knees throughout; this is a hip movement, not a squat.",
      "Push your hips back and let your torso tip forward with a flat back and a neutral neck.",
      "Keep the dumbbells close to your legs as they lower.",
      "Only go as low as you can while keeping your back flat, then drive your hips forward to stand tall.",
      "Use a light weight until the hinge feels natural.",
    ],
    limitations: [
      "Generic demonstration body; it does not represent your body proportions.",
      "The depth shown is one demo range; how far you can lower with a flat back varies from person to person.",
      "Educational visual only; not medical or injury-prevention advice. Stop if anything hurts.",
    ],
    review: {
      status: "pending_expert_review",
      note: "Conservative, widely used cues. Have a qualified coach review them before public use.",
    },
  },
  split_squat: {
    id: "split_squat",
    title: "Split squat (static lunge)",
    shortTitle: "Lunge",
    level: "beginner",
    animationUrl: MODEL_URL,
    clipName: "split_squat",
    clipDuration: 4,
    availablePhases: {
      start: 0,
      middle: 0.2625, // halfway through the 1.5 s descent
      bottom: 0.5, // centre of the 0.4 s pause at the bottom
    },
    availableViews: ["front", "side", "three_quarter"],
    defaultView: "side",
    props: [],
    summary:
      "A bodyweight split squat in a fixed staggered stance (left foot in front): 1.5 s lowering until the back knee is close to the floor, short pause, 1.5 s rise.",
    reviewedCues: [
      "Take a long stride: front foot flat, back heel lifted, feet about hip-width apart side to side.",
      "Keep your torso tall and most of your weight over the front foot.",
      "Lower straight down by bending both knees, as if your back knee is heading for the floor.",
      "Let your front knee travel in the same direction as your toes.",
      "Push through the whole front foot to rise back up.",
      "Hold a wall or chair for balance if you need it, and switch legs after each set.",
    ],
    limitations: [
      "Generic demonstration body; it does not represent your body proportions.",
      "Only the left-leg-forward side is shown; repeat with the right leg in front.",
      "Educational visual only; not medical or injury-prevention advice. Stop if anything hurts.",
    ],
    review: {
      status: "pending_expert_review",
      note: "Conservative, widely used cues. Have a qualified coach review them before public use.",
    },
  },
};

export const EXERCISE_LIST: Exercise[] = Object.values(EXERCISES);

export function getExercise(id: ExerciseId): Exercise {
  return EXERCISES[id];
}

export function phaseProgress(id: ExerciseId, phase: Phase): number | undefined {
  return EXERCISES[id].availablePhases[phase];
}

export function supportedPhases(id: ExerciseId): Phase[] {
  return (Object.keys(EXERCISES[id].availablePhases) as Phase[]).sort(
    (a, b) => (EXERCISES[id].availablePhases[a] ?? 0) - (EXERCISES[id].availablePhases[b] ?? 0),
  );
}
