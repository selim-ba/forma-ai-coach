import { ImageResponse } from "next/og";

export const size = { width: 512, height: 512 };
export const contentType = "image/png";

/** App icon rendered at build time — no binary assets to source or license. */
export function FormaMark({ px }: { px: number }) {
  const u = px / 32;
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#0e1013",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: u * 1.2 }}>
        <div style={{ width: u * 6, height: u * 6, borderRadius: u * 3, background: "#e9e3d8" }} />
        <div style={{ width: u * 12, height: u * 7, borderRadius: u * 3, background: "#e9e3d8" }} />
        <div style={{ display: "flex", gap: u * 2 }}>
          <div style={{ width: u * 3.6, height: u * 8, borderRadius: u * 1.8, background: "#ff7a45" }} />
          <div style={{ width: u * 3.6, height: u * 8, borderRadius: u * 1.8, background: "#ff7a45" }} />
        </div>
      </div>
    </div>
  );
}

export default function Icon() {
  return new ImageResponse(<FormaMark px={size.width} />, size);
}
