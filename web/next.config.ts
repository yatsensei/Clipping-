import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root. Without it Turbopack walks up past the repository and finds
  // an unrelated package-lock.json in the user's home directory, then warns about it.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
