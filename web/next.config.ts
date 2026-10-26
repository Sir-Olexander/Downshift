import type { NextConfig } from "next";

// The browser talks to the Downshift API through /api/* so no CORS setup is needed.
const API_URL = process.env.API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
