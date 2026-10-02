import fs from "node:fs";
import path from "node:path";

import { config as loadEnv } from "dotenv";
import type { NextConfig } from "next";

const envFile = path.resolve(process.cwd(), "../../.env");
if (fs.existsSync(envFile)) {
  loadEnv({ path: envFile, override: false });
}

const nextConfig: NextConfig = {
  // The service is not announced yet: no route may be indexed. Remove at launch (SOW-MC step 9).
  async headers() {
    return [{ source: "/:path*", headers: [{ key: "X-Robots-Tag", value: "noindex" }] }];
  },
  turbopack: {
    resolveAlias: {
      "next-intl/config": "./src/i18n/request.ts",
    },
  },
};

export default nextConfig;
