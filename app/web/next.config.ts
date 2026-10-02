import fs from "node:fs";
import path from "node:path";

import { config as loadEnv } from "dotenv";
import type { NextConfig } from "next";

const envFile = path.resolve(process.cwd(), "../../.env");
if (fs.existsSync(envFile)) {
  loadEnv({ path: envFile, override: false });
}

const nextConfig: NextConfig = {
  turbopack: {
    resolveAlias: {
      "next-intl/config": "./src/i18n/request.ts",
    },
  },
};

export default nextConfig;
