import path from "node:path";

import { config as loadEnv } from "dotenv";
import type { NextConfig } from "next";

// One secrets file for the whole repo: <repo root>/.env (gitignored). Values already in the process win.
// In the cloud (SOW-MC) the host injects the same names, and this call finds no file and does nothing.
loadEnv({ path: path.resolve(process.cwd(), "../../.env"), override: false });

const nextConfig: NextConfig = {};

export default nextConfig;
