import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root. Without it Turbopack walks up past the repository and finds
  // an unrelated package-lock.json in the user's home directory, then warns about it.
  turbopack: {
    root: path.resolve(__dirname),
  },
  // The energy optimiser moved under /energy when the site grew other sections.
  async redirects() {
    return [
      { source: "/analysis", destination: "/energy/analysis", permanent: true },
    ];
  },
};

export default nextConfig;
