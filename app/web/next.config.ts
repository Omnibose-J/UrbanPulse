import fs from "node:fs";
import path from "node:path";

import { config as loadEnv } from "dotenv";
import type { NextConfig } from "next";

const envFile = path.resolve(process.cwd(), "../../.env");
if (fs.existsSync(envFile)) {
  loadEnv({ path: envFile, override: false });
}

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
  turbopack: {
    resolveAlias: {
      "next-intl/config": "./src/i18n/request.ts",
    },
  },
};

export default nextConfig;
