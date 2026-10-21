import { networkInterfaces } from "node:os";
import type { NextConfig } from "next";

/**
 * In dev mode Next.js only serves its JS to localhost. Allow this Mac's own
 * LAN IPv4 addresses so a phone on the same Wi-Fi can load the app
 * (http://<mac-ip>:3000). Has no effect on production builds.
 */
const lanAddresses = Object.values(networkInterfaces())
  .flat()
  .filter((i): i is NonNullable<typeof i> => !!i && i.family === "IPv4" && !i.internal)
  .map((i) => i.address);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The dev-tools badge sits on top of the coach input at phone sizes.
  devIndicators: false,
  allowedDevOrigins: lanAddresses,
  async headers() {
    return [
      {
        // Let phones cache the avatar GLB between visits.
        source: "/models/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=86400, stale-while-revalidate=604800" }],
      },
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=(self)" },
        ],
      },
    ];
  },
};

export default nextConfig;
