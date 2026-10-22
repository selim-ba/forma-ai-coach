"use client";

import { Canvas } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import { Component, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import * as THREE from "three";
import { resolveAvatar } from "@/lib/avatar/source";
import { EXERCISES } from "@/lib/exercises/catalog";
import { useSceneStore } from "@/lib/scene/store";
import { AvatarModel } from "./AvatarModel";
import { CameraControls } from "./CameraControls";

/** Soft radial "contact shadow" — a single textured quad, far cheaper than real shadows on iPhone. */
function FloorShadow() {
  const texture = useMemo(() => {
    const size = 128;
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = size;
    const ctx = canvas.getContext("2d")!;
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, "rgba(0,0,0,0.55)");
    g.addColorStop(0.55, "rgba(0,0,0,0.18)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    const t = new THREE.CanvasTexture(canvas);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, []);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position-y={0.001}>
        <circleGeometry args={[1.6, 64]} />
        <meshStandardMaterial color="#1a1d22" roughness={1} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.002, 0.05]} scale={[0.9, 1.15, 1]}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial map={texture} transparent depthWrite={false} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position-y={0.003}>
        <ringGeometry args={[1.58, 1.6, 96]} />
        <meshBasicMaterial color="#3a3f47" />
      </mesh>
    </group>
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
        <hemisphereLight args={["#f3efe8", "#2a2d33", 1.6]} />
        <directionalLight position={[2.5, 4, 3.5]} intensity={2.2} />
        <directionalLight position={[-3, 2.5, -2]} intensity={0.9} color="#ffd9c4" />
        <FloorShadow />
        <Suspense fallback={null}>
          <AvatarModel url={source.url} />
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
      {status === "loading" && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center" aria-live="polite">
          <div className="flex flex-col items-center gap-3">
            <div className="h-28 w-12 animate-pulse rounded-full bg-white/10" />
            <p className="text-xs uppercase tracking-[0.2em] text-ink-muted">Loading avatar…</p>
          </div>
        </div>
      )}
    </ViewerErrorBoundary>
  );
}
