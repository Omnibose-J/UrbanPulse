import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

const FILES = new Set(["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]);

export async function GET(_request: Request, context: { params: Promise<{ file: string }> }) {
  const { file } = await context.params;
  if (!FILES.has(file)) return new Response("not found", { status: 404 });
  const bytes = await readFile(path.join(process.cwd(), "node_modules", "maplibre-gl", "dist", file));
  return new Response(bytes, {
    headers: {
      "Content-Type": "text/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=86400",
    },
  });
}
