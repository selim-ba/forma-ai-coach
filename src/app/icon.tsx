import { ImageResponse } from "next/og";

export const size = { width: 512, height: 512 };
export const contentType = "image/png";

/**
 * App icon rendered at build time (no binary assets): a block in isometric view (a plyo
 * box, and plainly three-dimensional). Three tones of the app's accent with light edges,
 * on the app's surface colour.
 */
export function AppMark({ px }: { px: number }) {
  return (
    <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#0e1013" }}>
      <svg width={px * 0.7} height={px * 0.7} viewBox="0 0 32 32">
        <polygon points="16,5 27.5,11.5 16,18 4.5,11.5" fill="#ff9a6b" />
        <polygon points="4.5,11.5 16,18 16,29 4.5,22.5" fill="#ff6a2e" />
        <polygon points="16,18 27.5,11.5 27.5,22.5 16,29" fill="#b8410f" />
        <polyline points="4.5,11.5 16,18 27.5,11.5" fill="none" stroke="#ffd9c6" strokeWidth="0.6" strokeLinejoin="round" />
        <line x1="16" y1="18" x2="16" y2="29" stroke="#ffd9c6" strokeWidth="0.6" opacity="0.6" />
      </svg>
    </div>
  );
}

export default function Icon() {
  return new ImageResponse(<AppMark px={size.width} />, size);
}
