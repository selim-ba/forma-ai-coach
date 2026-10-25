"use client";

import { Canvas } from "@react-three/fiber";
import { Environment, Lightformer, useGLTF, useProgress } from "@react-three/drei";
import { Component, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import * as THREE from "three";
import { resolveAvatar } from "@/lib/avatar/source";
import { EXERCISES } from "@/lib/exercises/catalog";
import { useSceneStore } from "@/lib/scene/store";
import { AvatarModel } from "./AvatarModel";
import { CameraControls } from "./CameraControls";
import { CueOverlay } from "./CueOverlay";

function radialTexture(stops: [number, string][]) {
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  for (const [at, color] of stops) g.addColorStop(at, color);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/**
 * Studio floor: a pool of light under the avatar that fades into the backdrop (no hard
 * edge), plus a soft radial contact shadow — textured quads, far cheaper than real
 * shadows on an iPhone.
 */
function Stage() {
  const pool = useMemo(
    () => radialTexture([[0, "rgba(58,63,72,1)"], [0.45, "rgba(36,40,46,0.85)"], [1, "rgba(20,22,26,0)"]]),
    [],
  );
  const shadow = useMemo(
    () => radialTexture([[0, "rgba(0,0,0,0.6)"], [0.5, "rgba(0,0,0,0.22)"], [1, "rgba(0,0,0,0)"]]),
    [],
  );
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position-y={0.001}>
        <planeGeometry args={[4.4, 4.4]} />
        <meshBasicMaterial map={pool} transparent depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.002, 0.04]} scale={[0.95, 1.2, 1]}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial map={shadow} transparent depthWrite={false} />
      </mesh>
    </group>
  );
}

/** Soft studio reflections for skin, fabric and weights: rendered once from light panels (no files). */
function StudioLight() {
  return (
    <>
      <Environment resolution={64} frames={1}>
        <Lightformer form="rect" intensity={2.2} position={[0, 4, 2]} rotation-x={Math.PI / 2.4} scale={[4, 2, 1]} />
        <Lightformer form="rect" intensity={1.2} color="#ffe6d4" position={[3, 1.5, 2]} rotation-y={-Math.PI / 3} scale={[1.2, 3, 1]} />
        <Lightformer form="rect" intensity={1.6} color="#b9d3ff" position={[-3, 2, -2.5]} rotation-y={Math.PI / 4} scale={[1, 3, 1]} />
      </Environment>
      <hemisphereLight args={["#f3efe8", "#24272d", 0.9]} />
      {/* key (warm, front right), rim (cool, behind left) to lift the silhouette off the backdrop */}
      <directionalLight position={[2.5, 4, 3.5]} intensity={2.0} color="#fff3e6" />
      <directionalLight position={[-2.8, 3.2, -3.4]} intensity={2.2} color="#b6ceff" />
      <directionalLight position={[-3, 1.5, 2]} intensity={0.35} />
    </>
  );
}

/** Loading state: real download progress, and a note when a demo or personal avatar has to wake the service. */
function Loading({ remote }: { remote?: boolean }) {
  const { progress } = useProgress();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setSlow(true), 6000);
    return () => window.clearTimeout(t);
  }, []);
  const pct = Math.round(progress);
  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-10" aria-live="polite">
      <div className="flex w-48 flex-col items-center gap-2.5 text-center">
        <p className="text-sm font-semibold text-ink">Loading avatar{pct > 0 ? ` ${pct}%` : ""}</p>
        <div className="h-1 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className={`h-full rounded-full bg-accent transition-[width] duration-300 ${pct === 0 ? "w-1/4 animate-pulse" : ""}`}
            style={pct > 0 ? { width: `${pct}%` } : undefined}
          />
        </div>
        {remote && slow && pct < 5 && (
          <p className="text-xs leading-snug text-ink-muted">Waking up the avatar service. The first load can take up to 30 seconds.</p>
        )}
      </div>
    </div>
  );
}

class ViewerErrorBoundary extends Component<
  { children: ReactNode; url: string; remote?: boolean; onRetry: () => void },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    useSceneStore.getState().setAvatarStatus({ status: "error", error: error.message });
  }
  render() {
    if (this.state.error && this.props.remote) {
      // Personal avatars are temporary: a missing file almost always means it expired or was deleted.
      return (
        <ViewerMessage
          title="This avatar isn't available anymore"
          body="Personal avatars are deleted after 24 hours, or when you delete them. You can make a new one from the generic body."
          action={{ label: "Use the generic body", onClick: () => window.location.assign("/") }}
        />
      );
    }
    if (this.state.error) {
      return (
        <ViewerMessage
          title="The 3D avatar couldn't load"
          body="Check your connection and try again. Playback buttons still work, and so does the coach."
          action={{
            label: "Retry",
            onClick: () => {
              useGLTF.clear(this.props.url);
              useSceneStore.getState().setAvatarStatus({ status: "loading" });
              this.setState({ error: null });
              this.props.onRetry();
            },
          }}
        />
      );
    }
    return this.props.children;
  }
}

function ViewerMessage({ title, body, action }: { title: string; body: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div role="alert" className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-surface/60 px-8 text-center backdrop-blur-sm">
      <p className="text-base font-semibold text-ink">{title}</p>
      <p className="text-sm text-ink-muted">{body}</p>
      {action && (
        <button type="button" onClick={action.onClick} className="btn-secondary mt-1">
          {action.label}
        </button>
      )}
    </div>
  );
}

function hasWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function AvatarCanvas() {
  const [attempt, setAttempt] = useState(0);
  const [webgl] = useState(() => hasWebGL());
  const [source] = useState(() => resolveAvatar(window.location.search));
  useEffect(() => {
    useSceneStore.getState().setAvatarSource(source);
  }, [source]);
  const status = useSceneStore((s) => s.avatar.status);
  const missing = useSceneStore((s) => s.avatar.missing);
  const exerciseId = useSceneStore((s) => s.scene.exerciseId);
  const unavailable = status === "ready" && (missing?.includes(exerciseId) ?? false);

  if (!webgl) {
    return (
      <ViewerMessage
        title="3D isn't available in this browser"
        body="WebGL is turned off or unsupported. The coach and controls still work, but the avatar can't be shown."
      />
    );
  }

  return (
    <ViewerErrorBoundary url={source.url} remote={source.remote} onRetry={() => setAttempt((a) => a + 1)}>
      <Canvas
        key={attempt}
        className="!absolute inset-0"
        dpr={[1, 2]}
        camera={{ fov: 30, near: 0.1, far: 50, position: [0, 1, 5] }}
        gl={{ antialias: true, powerPreference: "high-performance", alpha: true }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.05;
        }}
        aria-label="3D exercise demonstration. Drag to rotate."
        data-testid="avatar-canvas"
      >
        <StudioLight />
        <Stage />
        <Suspense fallback={null}>
          <AvatarModel url={source.url} />
          <CueOverlay />
        </Suspense>
        <CameraControls />
      </Canvas>
      {status === "error" && (
        <ViewerMessage
          title="The avatar file is incomplete"
          body={useSceneStore.getState().avatar.error ?? "An animation clip is missing."}
        />
      )}
      {unavailable && (
        <ViewerMessage
          title={`${EXERCISES[exerciseId].title} isn't animated for this avatar`}
          body="The wooden mannequin only has the squat and the curl. Pick another exercise, or open the app without ?avatar=mannequin to use the default body."
        />
      )}
      {status === "loading" && <Loading remote={source.remote} />}
    </ViewerErrorBoundary>
  );
}
