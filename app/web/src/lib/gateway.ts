/** The hosted database sits behind an edge gateway that can refuse a request outright (for example a search text
 * that looks like an attack) and answer with an HTML page instead of JSON. That is a rejection of the input, not an
 * outage, so the API says so with a 400 instead of a 500. */
export class GatewayRejected extends Error {
  constructor() {
    super("search text rejected by the gateway");
    this.name = "GatewayRejected";
  }
}

export function isGatewayRejection(message: string | null | undefined): boolean {
  if (!message) return false;
  const head = message.slice(0, 4000).toLowerCase();
  return (head.includes("<!doctype html") || head.includes("<html")) && head.includes("cloudflare");
}
