export type Locale = "ko" | "en";

const EN_HOUR = (hour: number) => {
  const period = hour < 12 ? "AM" : "PM";
  const face = hour % 12 === 0 ? 12 : hour % 12;
  return { face, period };
};

export function formatHour(hour: number, locale: Locale, suffix: string): string {
  if (locale === "en") {
    const { face, period } = EN_HOUR(hour);
    return `${face} ${period}`;
  }
  return `${hour}${suffix}`;
}

export function formatHourRange(start: number, end: number, locale: Locale, suffix: string): string {
  if (start === end) return formatHour(start, locale, suffix);
  if (locale === "en") {
    const a = EN_HOUR(start);
    const b = EN_HOUR(end);
    if (a.period === b.period) return `${a.face} to ${b.face} ${b.period}`;
    return `${a.face} ${a.period} to ${b.face} ${b.period}`;
  }
  return `${start}~${end}${suffix}`;
}

export function formatWindow(hours: number[] | undefined, locale: Locale, suffix: string): string {
  if (!hours || hours.length === 0) return "";
  return formatHourRange(hours[0], hours[hours.length - 1], locale, suffix);
}

/** Stored windows are single hours. Adjacent hours become one range; a lone hour spans the next hour. */
export function formatStoredWindows(
  windows: { hours: number[] }[] | null | undefined,
  locale: Locale,
  suffix: string,
): string[] {
  const firstPick = new Map<number, number>();
  (windows ?? []).forEach((window, index) => {
    for (const hour of window.hours) {
      if (!firstPick.has(hour)) firstPick.set(hour, index);
    }
  });
  const groups: { start: number; end: number; pick: number }[] = [];
  for (const hour of [...firstPick.keys()].sort((a, b) => a - b)) {
    const previous = groups[groups.length - 1];
    if (previous && hour === previous.end) {
      previous.end = hour + 1;
      continue;
    }
    groups.push({ start: hour, end: hour + 1, pick: firstPick.get(hour) ?? 0 });
  }
  groups.sort((a, b) => a.pick - b.pick || a.start - b.start);
  return groups.map((group) => formatHourRange(group.start, group.end, locale, suffix));
}

export function kstParts(isoDate: string): { year: number; month: number; day: number; weekday: number } {
  const [year, month, day] = isoDate.split("-").map(Number);
  const utc = Date.UTC(year, month - 1, day, 0, 0, 0);
  const weekday = new Date(utc).getUTCDay();
  return { year, month, day, weekday };
}

export function formatLongDate(
  isoDate: string,
  locale: Locale,
  marks: { month: string; day: string; weekdays: string[] },
): string {
  const parts = kstParts(isoDate);
  const week = marks.weekdays[parts.weekday];
  if (locale === "en") {
    const monthName = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][parts.month - 1];
    return `${week}, ${monthName} ${parts.day}`;
  }
  return `${parts.month}${marks.month} ${parts.day}${marks.day} (${week})`;
}

export function formatShortWeekday(isoDate: string, weekdays: string[], todayLabel: string, today: string): string {
  if (isoDate === today) return todayLabel;
  return weekdays[kstParts(isoDate).weekday];
}

export function formatShortDate(isoDate: string): string {
  const parts = kstParts(isoDate);
  return `${parts.month}/${parts.day}`;
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  const text = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
  return text;
}
