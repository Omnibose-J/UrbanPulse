// Copies the MapLibre worker modules into public/, so they are served as static files.
// A route handler reading node_modules at request time works on a laptop but not in a traced serverless bundle.
import { copyFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const from = path.join("node_modules", "maplibre-gl", "dist");
const to = path.join("public", "vendor", "maplibre");
mkdirSync(to, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(path.join(from, file), path.join(to, file));
}
