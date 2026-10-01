export function kstNow(now = new Date()): { date: string; hour: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  let hour = Number(get("hour"));
  if (hour === 24) hour = 0;
  return { date: `${get("year")}-${get("month")}-${get("day")}`, hour };
}

export function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const utc = new Date(Date.UTC(year, month - 1, day + days));
  return utc.toISOString().slice(0, 10);
}

export function kstHour(iso: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  let hour = Number(parts.find((part) => part.type === "hour")?.value ?? "0");
  if (hour === 24) hour = 0;
  return hour;
}

export function hourBounds(date: string, hour: number): [string, string] {
  const start = `${date}T${String(hour).padStart(2, "0")}:00:00+09:00`;
  const end =
    hour < 23
      ? `${date}T${String(hour + 1).padStart(2, "0")}:00:00+09:00`
      : `${addDays(date, 1)}T00:00:00+09:00`;
  return [start, end];
}

export function dayBounds(date: string): [string, string] {
  return [`${date}T00:00:00+09:00`, `${addDays(date, 1)}T00:00:00+09:00`];
}
