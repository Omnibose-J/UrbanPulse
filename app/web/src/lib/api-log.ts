export function logApiError(route: string, error: unknown) {
  const message = error instanceof Error ? error.message : "non-Error";
  console.error(`[api] ${route}`, message);
}
