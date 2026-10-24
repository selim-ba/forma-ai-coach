import type { ExerciseId, Phase } from "@/types/scene";
import type { Exercise } from "./schema";

/**
 * The exercise catalog is the authority for valid exercise IDs, phase markers
 * and coaching content. The GPT coach is only allowed to repeat these cues.
 *
 * Phase markers are authored against the clips baked by
 * research/avatar-pipeline/build_avatar.py (TIMELINES, all nine exercises; the default
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
    focus: "Legs",
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
    coachPrompt: "What should I watch for in a squat?",
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
    focus: "Biceps",
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
    coachPrompt: "Show me a biceps curl from the side, slowly",
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
    focus: "Shoulders",
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
    coachPrompt: "Pause the shoulder press at the top",
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
    focus: "Hamstrings & glutes",
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
    coachPrompt: "Show the Romanian deadlift from the side",
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
    focus: "Legs",
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
    coachPrompt: "How deep should a split squat go?",
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
  goblet_squat: {
    id: "goblet_squat",
    title: "Kettlebell goblet squat",
    shortTitle: "Goblet",
    level: "beginner",
    focus: "Legs",
    animationUrl: MODEL_URL,
    clipName: "goblet_squat",
    clipDuration: 4,
    availablePhases: {
      start: 0,
      middle: 0.2625, // halfway through the 1.5 s descent
      bottom: 0.5, // centre of the 0.4 s hold at depth
    },
    availableViews: ["front", "side", "three_quarter"],
    defaultView: "three_quarter",
    props: ["kettlebell_goblet"],
    coachPrompt: "Show a goblet squat from the side",
    summary:
      "A squat holding one kettlebell by the horns against the chest: 1.5 s descent, short pause at depth, controlled rise. The weight in front helps keep the torso upright.",
    reviewedCues: [
      "Hold the kettlebell by the horns, close to your chest, elbows pointing down.",
      "Stand with feet about shoulder-width apart, toes pointing forward or slightly out.",
      "Sit down between your heels, keeping your chest up and the kettlebell close.",
      "Let your knees travel in the same direction as your toes.",
      "Keep your whole foot on the floor and push the floor away to stand up.",
      "Start with a light kettlebell and only go as deep as you can while staying in control.",
    ],
    limitations: [
      "Generic demonstration body; it does not represent your body proportions.",
      "The depth shown is one demo range; comfortable depth varies from person to person.",
      "Educational visual only; not medical or injury-prevention advice. Stop if anything hurts.",
    ],
    review: {
      status: "pending_expert_review",
      note: "Conservative, widely used cues. Have a qualified coach review them before public use.",
    },
  },
  kettlebell_swing: {
    id: "kettlebell_swing",
    title: "Kettlebell swing",
    shortTitle: "Swing",
    level: "intermediate",
    focus: "Hips & glutes",
    animationUrl: MODEL_URL,
    clipName: "kettlebell_swing",
    clipDuration: 4,
    availablePhases: {
      start: 0,
      bottom: 0.3, // the back-swing: hips loaded, kettlebell between the legs
      top: 0.55, // standing tall, kettlebell floating at chest height
    },
    availableViews: ["front", "side", "three_quarter"],
    defaultView: "side",
    props: ["kettlebell_swing"],
    coachPrompt: "Pause the kettlebell swing at the top",
    summary:
      "A two-hand Russian kettlebell swing: hike the bell back between the legs with a hip hinge, snap the hips forward so it floats to chest height, and let it fall back into the next hinge.",
    reviewedCues: [
      "Stand with feet a little wider than hip-width, both hands on the kettlebell handle.",
      "Hinge at the hips and hike the kettlebell back between your legs, keeping your back flat.",
      "Drive your hips forward powerfully to stand tall; the arms just guide the bell.",
      "Let the kettlebell float to about chest height, without lifting it with your arms.",
      "Stand tall at the top: squeeze your glutes and don't lean back.",
      "Learn the hinge with a light kettlebell first, and stop the swing under control.",
    ],
    limitations: [
      "Generic demonstration body; it does not represent your body proportions.",
      "Shown at demo speed; a real swing is one smooth, continuous rhythm driven by the hips.",
      "Educational visual only; not medical or injury-prevention advice. Stop if anything hurts.",
    ],
    review: {
      status: "pending_expert_review",
      note: "Conservative, widely used cues. Have a qualified coach review them before public use.",
    },
  },
  bent_over_row: {
    id: "bent_over_row",
    title: "Bent-over dumbbell row",
    shortTitle: "Row",
    level: "beginner",
    focus: "Back",
    animationUrl: MODEL_URL,
    clipName: "bent_over_row",
    clipDuration: 4,
    availablePhases: {
      start: 0,
      middle: 0.225, // halfway through the 1.2 s pull
      top: 0.425, // centre of the 0.4 s squeeze
    },
    availableViews: ["front", "side", "three_quarter"],
    defaultView: "side",
    props: ["dumbbells"],
    coachPrompt: "What should I watch for in a bent-over row?",
    summary:
      "A two-arm dumbbell row from a 45° hip hinge with soft knees: 1.2 s pull to the waist, short squeeze, slower 1.8 s lowering. Palms face each other.",
    reviewedCues: [
      "Hinge forward at the hips with soft knees and a flat back, dumbbells hanging under your shoulders.",
      "Pull the dumbbells towards your waist, leading with your elbows.",
      "Keep your elbows close to your body and squeeze your shoulder blades together at the top.",
      "Keep your torso still; don't jerk up to move the weight.",
      "Lower the dumbbells under control until your arms are straight.",
      "Choose a weight you can row smoothly for every repetition.",
    ],
    limitations: [
      "Generic demonstration body; it does not represent your body proportions.",
      "The torso angle shown is one demo position; hinge only as far as you can keep your back flat.",
      "Educational visual only; not medical or injury-prevention advice. Stop if anything hurts.",
    ],
    review: {
      status: "pending_expert_review",
      note: "Conservative, widely used cues. Have a qualified coach review them before public use.",
    },
  },
  lateral_raise: {
    id: "lateral_raise",
    title: "Dumbbell lateral raise",
    shortTitle: "Raise",
    level: "beginner",
    focus: "Shoulders",
    animationUrl: MODEL_URL,
    clipName: "lateral_raise",
    clipDuration: 4,
    availablePhases: {
      start: 0,
      middle: 0.225, // halfway through the 1.2 s raise
      top: 0.425, // centre of the 0.4 s pause at shoulder height
    },
    availableViews: ["front", "side", "three_quarter"],
    defaultView: "front",
    props: ["dumbbells"],
    coachPrompt: "Show me a lateral raise slowly",
    summary:
      "A standing dumbbell lateral raise: 1.2 s raise out to the sides (slightly forward) up to shoulder height with soft elbows, short pause, slower 1.8 s lowering.",
    reviewedCues: [
      "Stand tall with a light dumbbell in each hand by your sides, elbows slightly bent.",
      "Raise your arms out to the sides, slightly in front of your body, up to about shoulder height.",
      "Lead with your elbows and keep your shoulders down, away from your ears.",
      "Don't swing or lean back to lift the weights.",
      "Lower slowly under control back to your sides.",
      "Use a light weight; this is a small muscle and heavy weights encourage swinging.",
    ],
    limitations: [
      "Generic demonstration body; it does not represent your body proportions.",
      "The lateral raise has no separate 'bottom' marker; the start position is arms by the sides.",
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
