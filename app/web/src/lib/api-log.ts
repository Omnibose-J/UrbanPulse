const SECRET = /eyJ|sb_secret_|postgres:\/\//i;

export function driverMessage(error: { message?: string } | null | undefined): string {
  const message = error?.message ?? "";
  if (!message || SECRET.test(message)) return "unavailable";
  return message;
}

export function logApiError(route: string, error: unknown) {
  const message = error instanceof Error ? error.message : "non-Error";
  console.error(`[api] ${route}`, SECRET.test(message) ? "unavailable" : message);
}
