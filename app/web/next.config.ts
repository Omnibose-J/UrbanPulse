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
          // The service is not announced yet: no route may be indexed. Remove at launch (SOW-MC step 9).
          { key: "X-Robots-Tag", value: "noindex" },
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
