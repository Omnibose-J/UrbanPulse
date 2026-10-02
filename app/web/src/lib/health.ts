export function healthResponse(count: number | null, error: unknown) {
  if (error || count === null) {
    return { status: 500 as const, body: { error: "unavailable" as const } };
  }
  return { status: 200 as const, body: { db: "ok" as const, places: count } };
}
