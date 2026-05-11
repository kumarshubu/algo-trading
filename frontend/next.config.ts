import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // All external API calls go through backend - no direct key exposure
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
