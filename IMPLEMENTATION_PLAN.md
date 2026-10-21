# Forma — 20-Hour Implementation Plan

**Objective:** A reproducible, mobile-first demo of a conversational AI coach controlling a rigged animated 3D humanoid on an iPhone 13. **Not** a personalized reconstruction system in the first 20 hours.

## Engineering principles

- **Vertical slice first:** generic avatar + a single working squat + manual controls before any AI integration.
- **Reliability > novelty:** two well-tested exercises beat ten broken ones.
- **Deterministic animation:** LLM selects vetted actions; it never writes bone transforms or fabricates exercise biomechanics.
- **Frontend = one Next.js codebase:** use App Router route handlers; do not add FastAPI/database/authentication for MVP.
- **Mobile first:** test on the physical iPhone, not just browser responsive mode.
- **SAM 3D Body/MHR is optional research only** and must not block deployment.

## Schedule and exit gates

| Hours | Deliverable | Acceptance gate |
|---|---|---|
| 0–2 | Next.js scaffold, landing screen, mobile shell | Page loads on Mac and HTTPS preview on iPhone |
| 2–5 | Three.js/R3F canvas, asset acquisition, orbit controls | Rigged avatar visible and smoothly touch-rotatable |
| 5–8 | First reviewed squat clip, playback state machine | Play/pause/replay/speed/side view work without errors |
| 8–10 | Biceps curl, exercise catalog, phase metadata | Switch between both clips; no bind-pose glitches |
| 10–13 | Next.js API route, GPT-6.1 Sol, schemas | At least five test prompts yield valid allowlisted actions |
| 13–15 | Chat panel, commands integrated into reducer | Commands modify visible 3D state exactly once |
| 15–17 | Device testing, error handling, network fallback | Safari portrait/landscape and API failure cases pass |
| 17–19 | Visual polish, logging, deployment, README | Demo URL loads on iPhone and manual controls always work |
| 19–20 | Full rehearsal, video backup and bug fixes | 60-second script completes twice without intervention |

### Hard decision gates

- **Hour 3:** If avatar asset cannot be imported, use a known compatible rigged GLB instead of custom reconstruction.
- **Hour 6:** If exercise clip retargeting is broken, prioritize one correct squat and substitute the second exercise only if ready.
- **Hour 11:** If GPT tool calling becomes unreliable, use strict structured outputs for the same validated command schema; do not ship arbitrary textual parsing.
- **Hour 17:** Freeze features. Fix iPhone Safari layout, performance, command execution and demo reliability.

## Implementation tasks in dependency order

### A. Scaffold and mobile UI
- Create Next.js TypeScript App Router project.
- Install `three`, `@react-three/fiber`, `@react-three/drei`, `openai`, `zod`, `zustand`, `lucide-react`.
- Build responsive split layout: viewport (60–70% of mobile vertical area), exercise controls, chat drawer.
- Set CSS safe-area padding (`env(safe-area-inset-bottom)`), avoid scroll capture inside 3D canvas.
- Provide loading skeleton for model assets and a 3D error state.

### B. Rig and motion (critical path)
- Acquire a licensed GLB/FBX character with skeleton; document source and permissions.
- Acquire squat and curl motions; inspect them for obvious form errors and meaningful phase positions.
- In Blender, verify rest pose, units, skeleton mapping and clip naming; retarget or bake if needed.
- Export shared-rig GLB animations, verify names in a local GLTF inspector, and load with `useGLTF`/`useAnimations`.
- Implement stable AnimationMixer control: one active exercise at a time, cancel previous clip cleanly, reset pose when switching.
- Record per-exercise phase markers as normalized progress fractions based on inspected clips.

### C. Scene state and validation
- `SceneState = { exerciseId, playing, speed, view, phase, isReady }`.
- Use a pure reducer for `SceneCommand` union. Check semantic validity of `seek_phase` against current exercise.
- Manage camera presets deterministically, with orbit controls for manual adjustment.
- Make `applyCommands` sequential: selecting exercise precedes seeking a phase; reject unsupported commands.
- Test reducer for invalid IDs, speed out of range, unavailable phases and reset behavior.

### D. GPT integration
- Initialize official `openai` SDK in a **server-only** route handler.
- Define one bounded `control_scene` tool or validated structured-output format.
- Provide to the model: exercise catalog, current scene state, allowed commands, reviewed cues and safety constraints.
- For tool calling, handle `function_call` objects and correlate `function_call_output` using the returned call IDs. Request the final assistant message after tool output; do not mistake proposed tool arguments for already-executed actions.
- Never have the model execute client commands server-side: validate, return serialized actions and let the browser reducer apply them once.
- Rate-limit and cap input lengths. Handle API/network failure with useful visible error; controls continue to work offline.

### E. Device test and deploy
- Deploy on an HTTPS preview (e.g. Vercel), set server environment variables in hosting dashboard.
- Open on iPhone 13 Safari, portrait and landscape; check mobile navigation, touch rotation and play/pause.
- Test background/foreground, weak Wi-Fi, iOS keyboard resizing and a long chat reply.
- Measure initial GLB bytes and app responsiveness; simplify materials and turn off shadows if needed.
- Add to Home Screen and verify routing/launch mode; treat microphone as optional and test browser support before claiming compatibility.

## GPT contract design

### Scene commands

```ts
type SceneCommand =
  | { type: 'select_exercise'; exerciseId: 'squat' | 'biceps_curl' }
  | { type: 'set_view'; view: 'front' | 'side' | 'three_quarter' }
  | { type: 'set_speed'; speed: 0.5 | 1 }
  | { type: 'seek_phase'; phase: 'start' | 'middle' | 'bottom' | 'top' }
  | { type: 'play' | 'pause' | 'reset' };
```

### Coaching policy
- Never generate frame-by-frame kinematic data.
- Never suggest a movement that isn't in the local reviewed catalog.
- Keep explanations short, accessible, and grounded in catalog cues.
- Explain uncertainty and scope if user requests individualized safety or medical assessments.
- Do not treat reconstructed body proportions as physical capability estimates.

### Test prompts

1. “Show a squat from the side.” → select squat, side view, play.
2. “Pause at the lowest point.” → select/sustain squat, seek bottom, pause.
3. “Play it slowly.” → 0.5 speed, play.
4. “Show me a biceps curl from the front.” → select curl, front, play.
5. “Explain what I should look for in a squat.” → catalog-backed text; scene optional.
6. “Show me a deadlift.” → clear unsupported message; no invalid command.
7. “Make the knees bend backwards.” → no unsafe animation-generation; reject.
8. “Rotate the camera and replay.” → camera preset or valid rotation action; reset/replay.

Collect command validity, execution success, response latency and API errors in local development logs; do not claim accuracy based solely on coherent language.

## Definition of done

- iPhone Safari loads viewer and exercises from a deployed HTTPS URL.
- Squat and biceps curl play without obvious rigging artifacts.
- Manual UI still works without OpenAI.
- GPT-6.1 Sol accepts a conversational request and changes viewer state using bounded commands.
- No secrets in frontend or Git; exercise licenses documented.
- Demo rehearsed twice; backup screen recording saved locally.

## Optional post-MVP: SAM 3D Body + MHR R&D spike (not in critical path)

**Success metric:** a consenting user's single-photo reconstruction has stable MHR identity and can be exported as a skinned, neutral-pose GLB compatible with one exercise clip.

1. Explore official MHR `web-viewer/` and low-LOD FBX assets on Mac (MHR project declares `osx-arm64` environment support).
2. Inspect rig formats, skeleton, neutral pose and conversion tools locally; use a generic MHR model before doing personal inference.
3. Request checkpoint access for SAM 3D Body and reproduce inference on compatible GPU (official setup uses Detectron2 and CUDA-first tooling).
4. Save inferred identity/pose outputs, document uncertainty and set privacy/deletion safeguards.
5. Verify export as rigged GLB and exercise retargeting separately; do not assume raw mesh OBJ has a rig.
6. Swap into frontend behind an `avatarProvider` interface **only when** retargeting is demonstrated.

## Known risks and mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Rig/clip incompatible | Blocks 3D demo | Choose same-rig assets; bake retargeted animations offline |
| iPhone 13 GPU lag | Bad live demo | Low-poly/LOD mesh, compressed assets, restrained lighting and DPR cap |
| Model produces invalid command | Unreliable controls | Strict schema validation, allowlist, reducer tests |
| Voice APIs differ across Safari versions | Voice feature breaks | Make voice optional, typed interaction primary |
| SAM 3D needs gated checkpoints/GPU | Blocks personalization | Keep experimental track separate |
| Unreviewed form cues | Misleading fitness advice | Reviewed exercise catalog, disclaimers and bounded claims |
| Asset licensing unclear | Publication risk | Asset manifest and replacement with permissively licensed alternatives |

## Sources and reference links

- https://developers.openai.com/api/docs/models/gpt-6.1-sol
- https://developers.openai.com/api/reference/typescript/resources/responses/methods/create
- https://nextjs.org/docs/app/getting-started/route-handlers
- https://threejs.org/docs/pages/AnimationMixer.html
- https://github.com/facebookresearch/MHR
- https://github.com/facebookresearch/sam-3d-body
- https://github.com/facebookresearch/sam-3d-body/blob/main/INSTALL.md
