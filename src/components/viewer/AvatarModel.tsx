"use client";

import { useAnimations, useGLTF } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useRef } from "react";
import * as THREE from "three";
import { EXERCISES } from "@/lib/exercises/catalog";
import { playhead, useSceneStore } from "@/lib/scene/store";
import type { Prop } from "@/lib/exercises/schema";
import type { ExerciseId, SceneState } from "@/types/scene";

/** Prop → mesh name in the avatar GLBs (research/avatar-pipeline/build_avatar.py). */
const PROP_MESHES: Record<Prop, string> = {
  dumbbells: "Dumbbells",
  kettlebell_goblet: "KettlebellGoblet",
  kettlebell_swing: "KettlebellSwing",
};

type Actions = Record<string, THREE.AnimationAction | null>;
type Applied = { exerciseId: ExerciseId | null; seekNonce: number };
type MirroredState = Pick<SceneState, "exerciseId" | "speed" | "seek" | "playing">;

/**
 * Imperatively mirror scene state onto the AnimationMixer, in a fixed order:
 * exercise → speed → seek → play/pause. Three.js animation objects are mutable
 * by design, so this lives outside the component (React's immutability lint
 * rule rightly forbids mutating hook return values inside render scope).
 */
function syncMixer(actions: Actions, mixer: THREE.AnimationMixer, model: THREE.Object3D, state: MirroredState, applied: Applied) {
  const exercise = EXERCISES[state.exerciseId];
  const action = actions[exercise.clipName];
  if (!action) {
    // This avatar has no clip for the exercise (the viewer shows a message): stop the old one.
    for (const other of Object.values(actions)) other?.stop();
    for (const meshName of Object.values(PROP_MESHES)) {
      const mesh = model.getObjectByName(meshName);
      if (mesh) mesh.visible = false;
    }
    applied.exerciseId = null;
    return;
  }

  // Re-activate if the action was stopped/uncached behind our back (e.g. React StrictMode's
  // dev-only unmount/remount runs drei's cleanup, which uncaches every action).
  const deactivated = applied.exerciseId === state.exerciseId && !action.isScheduled();
  if (deactivated) applied.seekNonce = -1; // re-apply the latest seek after reactivation

  if (applied.exerciseId !== state.exerciseId || deactivated) {
    for (const other of Object.values(actions)) {
      if (other && other !== action) other.stop();
    }
    action.reset();
    action.setLoop(THREE.LoopRepeat, Infinity);
    action.clampWhenFinished = false;
    action.play();
    applied.exerciseId = state.exerciseId;
    for (const [prop, meshName] of Object.entries(PROP_MESHES) as [Prop, string][]) {
      const mesh = model.getObjectByName(meshName);
      if (mesh) mesh.visible = exercise.props.includes(prop);
    }
  }

  action.timeScale = state.speed;

  if (state.seek && state.seek.nonce !== applied.seekNonce) {
    action.time = state.seek.progress * action.getClip().duration;
    applied.seekNonce = state.seek.nonce;
  }

  action.paused = !state.playing;
  // Evaluate the current time immediately so a paused seek or a clip switch
  // never shows a frame in the bind pose.
  mixer.update(0);
}

/** The loaded avatar's root object, for overlays that follow its bones (CueOverlay). */
export const avatarRig: { current: THREE.Object3D | null } = { current: null };

function disableFrustumCulling(model: THREE.Object3D) {
  model.traverse((obj) => {
    if ((obj as THREE.Mesh).isMesh) obj.frustumCulled = false; // skinned bounds are bind-pose only
  });
}

/**
 * Loads the rigged avatar GLB and drives its AnimationMixer from scene state.
 * Exactly one AnimationAction is active at a time. Scene state is the source
 * of truth; this component only mirrors it imperatively.
 */
export function AvatarModel({ url }: { url: string }) {
  const group = useRef<THREE.Group>(null);
  const { scene: model, animations } = useGLTF(url);
  const { actions, mixer } = useAnimations(animations, group);
  const scene = useSceneStore((s) => s.scene);
  const setAvatarStatus = useSceneStore((s) => s.setAvatarStatus);

  const applied = useRef<Applied>({ exerciseId: null, seekNonce: -1 });

  // One-time mesh setup, and expose the rig to overlays.
  useLayoutEffect(() => {
    disableFrustumCulling(model);
    avatarRig.current = model;
    return () => {
      if (avatarRig.current === model) avatarRig.current = null;
    };
  }, [model]);

  // Check which catalog clips this avatar has. Older avatars (the wooden mannequin) only
  // have some exercises: those are marked unavailable instead of failing the whole viewer.
  useEffect(() => {
    const missing = Object.values(EXERCISES).filter((e) => !actions[e.clipName]);
    if (missing.length === Object.keys(EXERCISES).length) {
      setAvatarStatus({ status: "error", error: "This avatar file has none of the exercise animations." });
    } else {
      setAvatarStatus({ status: "ready", missing: missing.map((e) => e.id) });
    }
  }, [actions, setAvatarStatus]);

  const { exerciseId, speed, seek, playing } = scene;
  useEffect(() => {
    syncMixer(actions, mixer, model, { exerciseId, speed, seek, playing }, applied.current);
  }, [exerciseId, speed, seek, playing, actions, mixer, model]);

  // Dev-only inspection handle for debugging avatars in the browser console.
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __forma?: unknown }).__forma = { actions, mixer, model, applied };
    }
  }, [actions, mixer, model]);

  useFrame(() => {
    const action = actions[EXERCISES[scene.exerciseId].clipName];
    if (!action) return;
    const duration = action.getClip().duration;
    playhead.duration = duration;
    playhead.progress = duration > 0 ? (action.time % duration) / duration : 0;
  });

  return (
    <group ref={group} dispose={null}>
      <primitive object={model} />
    </group>
  );
}

