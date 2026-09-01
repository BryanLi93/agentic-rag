import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep Turbopack resolution scoped to the web workspace in this monorepo.
  turbopack: { root: __dirname },
};

export default nextConfig;
