import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Forma — AI 3D Fitness Coach",
    short_name: "Forma",
    description: "Interactive 3D exercise demonstrations with a conversational coach.",
    start_url: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#0e1013",
    theme_color: "#0e1013",
    icons: [
      { src: "/icon", sizes: "512x512", type: "image/png" },
      { src: "/apple-icon", sizes: "180x180", type: "image/png" },
    ],
  };
}
