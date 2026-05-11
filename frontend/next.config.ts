import type { NextConfig } from "next";
import { existsSync, readFileSync } from "fs";
import { resolve } from "path";

// Load root .env — Next.js only searches its own directory by default
const rootEnv = resolve(__dirname, "../.env");
if (existsSync(rootEnv)) {
  for (const line of readFileSync(rootEnv, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (m && !(m[1] in process.env)) {
      process.env[m[1]] = m[2].replace(/^["'](.*)["']$/, "$1");
    }
  }
}

const nextConfig: NextConfig = {};

export default nextConfig;
