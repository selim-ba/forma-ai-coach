# Forma — AI 3D Fitness Coach

> An iPhone-first, interactive 3D exercise demonstrator powered by GPT-6.1 Sol.

**Status:** MVP specification / not yet implemented  
**Target device:** iPhone 13 (Safari, Add to Home Screen)  
**Development device:** MacBook Pro M4 Pro  
**Budget:** 20 engineering hours  
**Stack:** Next.js (App Router), TypeScript, React Three Fiber, Three.js, Tailwind CSS, OpenAI Responses API

## What it does

Forma displays an animated human avatar performing curated exercise demonstrations. The user can ask a conversational coach to select an exercise, pause at a phase, change speed or camera angle, and explain movement cues. GPT-6.1 Sol translates user requests into **validated scene commands**. The app—not the LLM—owns the animation, transforms, and physical constraints.

**Demo script (60 seconds):**

1. Launch Forma from the iPhone Home Screen.
2. Say or type: “Show me a beginner squat from the side.”
3. The coach selects `squat`, switches to side view and starts the reference animation.
4. Say: “Slow it down and pause at the bottom.”
5. The avatar slows to 0.5× and seeks to the curated `bottom` marker.
6. Ask: “What should I pay attention to?” The coach gives concise educational cues from the reviewed exercise catalog.
7. Switch to `biceps_curl`, rotate and replay.

## MVP scope

### Must have
- [ ] Responsive mobile UI designed and tested at iPhone 13 viewport.
- [ ] Rigged generic humanoid GLB in a touch-friendly WebGL viewer.
- [ ] Two **reviewed, pre-authored** motion clips: squat and biceps curl.
- [ ] Drag-to-orbit and one-tap front/side camera presets.
- [ ] Play, pause, replay, 0.5× / 1× playback and phase markers.
- [ ] Server-side GPT-6.1 Sol API route with validated, allowlisted scene actions.
- [ ] Typed chat panel and visible event/action log for demos.
- [ ] Graceful fallback when API is unavailable; manual controls remain functional.
- [ ] Deploy over HTTPS; test on a physical iPhone 13.

### Nice to have (only when must-haves are stable)
- [ ] Voice input via Web Speech API *when supported* or an explicit record/upload transcription path.
- [ ] Spoken coaching via browser `speechSynthesis` or server-synthesized speech.
- [ ] Simple silhouette/body-shape presets (not presented as reconstruction).
- [ ] PWA manifest and installable Home Screen icon.

### Out of scope for the 20-hour MVP
- Accurate reconstruction of the user's body; SOMA; inference on the phone; arbitrary text-to-motion; automatic technique grading; injury diagnosis; authentication and social features; user photo storage.

## Architecture

```text
iPhone 13 Safari
  ├── Responsive Next.js frontend
  ├── React Three Fiber scene ── GLB skinned avatar + curated AnimationClips
  ├── Scene state machine ── validate & execute app commands
  └── Chat UI ── POST /api/coach
                       │
                       ▼
                 Next.js route handler (server-side)
                 ├── GPT-6.1 Sol Responses API
                 ├── Tool / JSON schema validation (Zod)
                 ├── Exercise catalog and coaching instructions
                 └── bounded scene-command response
                       │
                       ▼
                 Browser executes allowlisted scene commands

Later, independent branch:
iPhone photos ──> SAM 3D Body GPU inference ──> MHR identity/rig ──> export/retarget ──> skinned GLB
```

**Important:** `SAM 3D Body` is **not** a runtime requirement for the MVP. Only introduce it after generic avatar playback and GPT orchestration are tested. This avoids making the demo dependent on a CUDA-oriented research environment.

## Repository structure (to create)

```text
forma/
├── README.md
├── IMPLEMENTATION_PLAN.md
├── .env.example
├── .gitignore
├── package.json
├── next.config.ts
├── public/
│   ├── models/
│   │   └── humanoid.glb          # licensed, animated/rigged avatar
│   ├── motions/
│   │   ├── squat.glb             # compatible, reviewed animation
│   │   └── biceps-curl.glb
│   └── icons/
├── src/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   └── api/coach/route.ts
│   ├── components/
│   │   ├── viewer/AvatarCanvas.tsx
│   │   ├── viewer/AvatarModel.tsx
│   │   ├── viewer/CameraControls.tsx
│   │   ├── controls/PlaybackControls.tsx
│   │   ├── coach/CoachChat.tsx
│   │   ├── coach/MessageList.tsx
│   │   └── debug/ActionLog.tsx
│   ├── lib/
│   │   ├── exercises/catalog.ts
│   │   ├── exercises/schema.ts
│   │   ├── scene/commands.ts
│   │   ├── scene/reducer.ts
│   │   ├── openai/client.ts
│   │   ├── openai/tools.ts
│   │   └── openai/system-prompt.ts
│   ├── hooks/
│   │   └── useSceneController.ts
│   └── types/
│       ├── coach.ts
│       └── scene.ts
├── tests/
│   ├── scene-commands.test.ts
│   ├── exercise-catalog.test.ts
│   └── coach-route.test.ts
├── scripts/
│   └── validate-assets.mjs
└── research/
    └── sam3d-mhr/README.md       # optional independent research spike
```

Files describing future implementation are design targets; this README does not claim the source tree currently exists.

## Installation (after source is implemented)

### Prerequisites
- Node.js current supported LTS, npm, Git.
- An OpenAI API key with access to `gpt-6.1-sol`.
- Blender (optional, for rigging/retargeting).
- iPhone 13 with Safari and access to deployed HTTPS app.

```bash
npx create-next-app@latest forma --typescript --tailwind --eslint --app --src-dir --import-alias '@/*'
cd forma
npm install three @react-three/fiber @react-three/drei openai zod zustand lucide-react
npm install -D @types/three vitest @testing-library/react @testing-library/jest-dom
```

Install versions compatible with the generated React/Next.js versions and commit the lockfile; do not use floating versions for deployment.

Create `.env.local`:

```dotenv
OPENAI_API_KEY=replace_me
OPENAI_MODEL=gpt-6.1-sol
```

Never prefix secrets with `NEXT_PUBLIC_` and never commit `.env.local`.

```bash
npm run dev
```

Open `http://localhost:3000` on the MacBook. For iPhone testing use a deployed HTTPS preview (recommended). If testing over LAN, mobile-browser secure-context restrictions may affect microphone and camera features; plain HTTP on a LAN address is not equivalent to HTTPS.

## Assets and rigging rules

1. Source a rigged humanoid with an explicit license permitting intended demo distribution. Keep credits in `ASSETS.md` and don't commit assets whose terms forbid redistribution.
2. Source two **correct exercise animations**. Do not assume a motion from a generic library is biomechanically appropriate.
3. Prefer a single GLB with a shared skeleton and embedded clips, if available. If files have different rigs, retarget offline in Blender and export compatible GLBs.
4. Record coordinate system, scale, bind pose, skeleton hierarchy, GLB size and clip duration.
5. Keep the initial download light: target approximately 5–10 MB total assets as a **performance target**, not a verified benchmark.
6. Validate that the avatar stays on-screen, feet remain near the floor and limbs do not severely penetrate the torso during curated motions.

Three.js `AnimationMixer`/`AnimationAction` controls playback. Phase markers must be **authored per exercise**; they cannot safely be inferred from arbitrary clip timestamps. Keep the app animation state independent of model output.

## Exercise catalog

The catalog is the authority for valid exercise IDs and coaching content. Example schema:

```ts
type ExerciseId = "squat" | "biceps_curl";
type View = "front" | "side" | "three_quarter";
type Phase = "start" | "middle" | "bottom" | "top";

type Exercise = {
  id: ExerciseId;
  title: string;
  animationUrl: string;
  availablePhases: Partial<Record<Phase, number>>; // normalized 0..1
  availableViews: View[];
  reviewedCues: string[];
  limitations: string[];
};
```

For each motion, author `availablePhases` based on that actual clip (example: a squat's `bottom` phase). A biceps curl may have `top` but no meaningful `bottom` marker. Avoid generating numeric form thresholds or individualized corrections from GPT alone.

## GPT-6.1 Sol: coach and scene-control interface

The model interprets intent; the app executes deterministic actions. Use the **Responses API**, which supports GPT-6.1 Sol tool calling. Keep the provider SDK in a server-only module.

Recommended validated command union:

```ts
type SceneCommand =
  | { type: "select_exercise"; exerciseId: "squat" | "biceps_curl" }
  | { type: "play" }
  | { type: "pause" }
  | { type: "set_speed"; speed: 0.5 | 1 }
  | { type: "set_view"; view: "front" | "side" | "three_quarter" }
  | { type: "seek_phase"; phase: "start" | "middle" | "bottom" | "top" }
  | { type: "reset" };
```

Expose a model function `control_scene` with one or more such commands as strictly structured arguments. Validate against Zod on the server and **again** in the client reducer; reject commands not supported by the selected exercise. Limit command count, token output and chat length. Accept a final assistant explanation alongside the validated commands. The frontend must not execute arbitrary code from the model.

Example intent/result:

**User:** “Show squats from the side, slowly, and stop at the bottom.”

```json
{
  "commands": [
    { "type": "select_exercise", "exerciseId": "squat" },
    { "type": "set_view", "view": "side" },
    { "type": "set_speed", "speed": 0.5 },
    { "type": "seek_phase", "phase": "bottom" },
    { "type": "pause" }
  ],
  "message": "Here is the bottom position from the side. Watch your balance and maintain a comfortable range of motion."
}
```

The JSON above illustrates the **internal app-facing result** after tool handling/validation; it is not a claim that Responses API emits this exact envelope automatically. Implement the actual `function_call`/`function_call_output` loop according to current official API documentation, or use a validated structured-output response for this simple MVP. When using tools, verify call IDs, execute only allowlisted commands, provide tool results and obtain the final natural-language answer.

### System behavior requirements
- Use exercise catalog facts and pre-reviewed cues; don't invent muscle activation percentages or diagnose injury.
- Clarify unsupported exercise requests and offer the two supported demos.
- Treat scene commands as untrusted until validated.
- Never promise that an avatar's animation is a precise personalized biomechanical simulation.
- Refuse requests for dangerous movement modifications and recommend appropriate professional advice for pain/injury concerns.
- Prefer short, mobile-friendly replies (one to three sentences).

### API request/response contract (your own endpoint)

`POST /api/coach`

```json
{
  "message": "Show me a squat from the side",
  "scene": { "exerciseId": "biceps_curl", "playing": false, "speed": 1, "view": "front" }
}
```

Example HTTP 200 body:

```json
{
  "message": "Switching to a side-view squat demonstration.",
  "commands": [
    { "type": "select_exercise", "exerciseId": "squat" },
    { "type": "set_view", "view": "side" },
    { "type": "play" }
  ]
}
```

Add input size limits and basic rate limiting before any public deployment. Do not expose raw system prompts, API keys or provider errors to the browser. Keep conversation history bounded and avoid submitting personal photos to GPT as part of this MVP.

## iPhone 13 verification checklist

- [ ] Open the HTTPS deployment in Safari (not only Mac responsive preview).
- [ ] Check portrait layout (~390 CSS px width, subject to device/browser settings) and landscape orientation.
- [ ] Rotate avatar with touch; swipe gestures do not inadvertently scroll the entire page.
- [ ] GLB finishes loading over mobile data; errors show a usable fallback.
- [ ] Exercise playback operates at a usable frame rate; inspect FPS if possible rather than promising 60 FPS.
- [ ] Test play, pause, replay, 0.5×, camera and phase controls.
- [ ] Confirm chatbot command is executed exactly once with visible feedback.
- [ ] Test lost network connection, API timeout, model invalid response and device sleep/resume.
- [ ] Test Home Screen installation: Safari Share > Add to Home Screen (wording varies by iOS).
- [ ] If voice is implemented, check mic permissions, HTTPS, Safari compatibility and fallback to typing.
- [ ] Ensure touch targets are >=44×44 CSS px where practical and text/input focus works with the iOS keyboard.
- [ ] Disable costly lighting/shadows/postprocessing if thermal throttling or rendering lag occurs.

## Definition of done

A developer unfamiliar with the repo can install it, run `npm run dev`, and reproduce the two-exercise demo. The app is accessible on a real iPhone 13 via HTTPS, and a GPT-6.1 request reliably changes the exercise, view, speed and playback state. It must still function as a manual 3D viewer when OpenAI is inaccessible. The animation assets must have documented licensing and must not be represented as personalized anatomical truth.

## SAM 3D Body / MHR: subsequent research track

After the core demo, run an **independent** experiment:

1. Request access to official checkpoints at `facebook/sam-3d-body-dinov3` (or ViT-H) on Hugging Face.
2. On a suitable GPU environment, reproduce official inference on a consenting subject's image.
3. Inspect the MHR identity coefficients, pose and mesh/rig outputs.
4. Try a neutral pose, lower-detail MHR asset and skinned GLB export.
5. Verify MHR skeleton compatibility with the reference exercise clips; retarget offline if required.
6. Compare identity consistency across photos and don't claim anatomical measurement precision.
7. Replace the generic avatar **only after** the resulting personalized GLB animates successfully in the existing viewer.

MHR's own repository includes a web viewer, FBX/LOD assets and SMPL conversion tooling; this **does not guarantee** a frictionless export/retargeting path to your particular Next.js scene. Keep Python/CUDA tooling outside the Node app and don't require it for startup.

## Privacy and safety

Current MVP processes typed instructions and renders a generic avatar; it does not collect user body photos. If photo reconstruction is added, obtain explicit consent, offer deletion, minimize retention and avoid committing photos or reconstructed personal meshes to Git. Show a clear notice: “Visual exercise education only; not medical or injury-prevention advice.” Feedback from camera/video will require validation before claims about joint angles, movement quality or safety.

## Sources

- GPT-6.1 Sol model: https://developers.openai.com/api/docs/models/gpt-6.1-sol
- Responses API: https://developers.openai.com/api/reference/typescript/resources/responses/methods/create
- OpenAI JS SDK: https://developers.openai.com/api/docs/libraries
- Next.js App Router: https://nextjs.org/docs/app
- Three.js AnimationMixer: https://threejs.org/docs/pages/AnimationMixer.html
- SAM 3D Body: https://github.com/facebookresearch/sam-3d-body
- Official SAM 3D Body setup: https://github.com/facebookresearch/sam-3d-body/blob/main/INSTALL.md
- MHR: https://github.com/facebookresearch/MHR
- MHR SMPL conversion: https://github.com/facebookresearch/MHR/tree/main/tools/mhr_smpl_conversion
- Adobe Mixamo: https://www.mixamo.com/

**No assets, exercise animations, model checkpoints or API credentials are bundled with this spec.**
