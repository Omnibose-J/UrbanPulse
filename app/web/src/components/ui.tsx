"use client";

import { ChevronLeft, Clock, Map, Share2, SlidersHorizontal, Star, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { formatHourRange, formatLongDate, formatShortDate, formatShortWeekday, formatStoredWindows } from "@/lib/format";
import type { HourCell } from "@/lib/strip";
import { busiestRange, cellFill, cellSentence } from "@/lib/strip";
import { kindKey } from "@/lib/kind";
import type { Favorite, Purpose, Tolerance } from "@/lib/storage";

export function PlaceName({ name, nameEn }: { name: string; nameEn?: string | null }) {
  const locale = useLocale();
  if (locale === "en" && nameEn) return <span>{nameEn}</span>;
  return <span lang="ko">{name}</span>;
}

/** The place kind (Seoul's category) as a small chip next to the district; nothing when the row has no category. */
export function KindChip({ category }: { category: string | null | undefined }) {
  const t = useTranslations();
  const key = kindKey(category);
  if (!key) return null;
  return (
    <span data-kind className="inline-flex h-[18px] shrink-0 items-center whitespace-nowrap rounded-[var(--r-pill)] bg-bg-soft px-1.5 text-[11px] font-semibold text-text-2">
      {t(key)}
    </span>
  );
}

export function Phone({ children }: { children: React.ReactNode }) {
  return <div className="phone-shell px-4 pb-16">{children}</div>;
}

export function AppBar({
  backHref,
  backLabel,
  title,
  star,
  onStar,
  mapHref,
  onCond,
  onShare,
  children,
}: {
  backHref?: string;
  backLabel?: string;
  title?: string;
  star?: boolean;
  onStar?: () => void;
  mapHref?: string;
  onCond?: () => void;
  onShare?: () => void;
  children?: React.ReactNode;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const pathname = usePathname();
  const params = useSearchParams();
  const other = locale === "ko" ? "en" : "ko";
  const query = params.toString();
  const switched = pathname.replace(/^\/(ko|en)/, `/${other}`) + (query ? `?${query}` : "");
  return (
    <header className={`flex h-14 items-center gap-2 ${children ? "w-full" : "justify-between"}`}>
      <div className="flex items-center gap-1">
        {backHref ? (
          <>
            <Link prefetch={false} href={backHref} aria-label={backLabel ? undefined : t("nav.back")} className={`-ml-2.5 flex shrink-0 items-center gap-1 whitespace-nowrap text-[15px] font-semibold ${backLabel ? "h-11 pr-2" : "icon-hit"}`}>
              <ChevronLeft aria-hidden />
              {backLabel ? <span className="whitespace-nowrap">{backLabel}</span> : null}
            </Link>
            {title ? <h1 className="text-[17px] font-extrabold tracking-tight">{title}</h1> : null}
          </>
        ) : (
          <span className="flex items-center gap-2 font-extrabold tracking-tight">
            <span className="inline-block h-6 w-6 rounded-[6px] bg-ink" aria-hidden>
              <svg viewBox="0 0 24 24" className="h-6 w-6">
                <path d="M3 14h4l2-6 3 10 2-4h7" fill="none" stroke="var(--go-bright)" strokeWidth="2" />
              </svg>
            </span>
            {t("nav.logo")}
          </span>
        )}
      </div>
      {children ? <div className="min-w-0 flex-1">{children}</div> : null}
      <div className={`${children ? "ml-auto" : ""} flex items-center`}>
        {mapHref ? (
          <Link prefetch={false} href={mapHref} className="icon-hit flex items-center justify-center" aria-label={t("map.title")}>
            <Map />
          </Link>
        ) : null}
        {onCond ? (
          <button type="button" data-cond-button className="icon-hit flex items-center justify-center" onClick={onCond} aria-label={t("sheet.title")}>
            <SlidersHorizontal aria-hidden />
          </button>
        ) : null}
        {onShare ? (
          <button type="button" data-share className="icon-hit flex items-center justify-center" onClick={onShare} aria-label={t("share.action")}>
            <Share2 aria-hidden />
          </button>
        ) : null}
        {onStar ? (
          <button type="button" className="icon-hit" onClick={onStar} aria-pressed={star} aria-label={t("home.favorites")}>
            <Star fill={star ? "var(--star)" : "none"} color="var(--star)" />
          </button>
        ) : null}
        <a href={switched} data-lang className="label flex h-11 shrink-0 items-center px-2 font-bold" aria-label={t("nav.language")}>
          KO · EN
        </a>
      </div>
    </header>
  );
}

/** Share a screen: the system share sheet when the browser has one, otherwise the link goes to the clipboard and a
 * toast says so. A cancelled share sheet is not a failure; a failed copy is said as one. */
export function useShare() {
  const t = useTranslations();
  const [toast, setToast] = useState<string | null>(null);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 2200);
    return () => window.clearTimeout(timer);
  }, [toast]);
  const share = async (text: string, url: string) => {
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ text, url });
      } catch (error) {
        if ((error as Error).name !== "AbortError") setToast(t("share.failed"));
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setToast(t("share.copied"));
    } catch {
      setToast(t("share.failed"));
    }
  };
  const node = toast ? (
    <p role="status" data-toast className="label fixed bottom-6 left-1/2 z-30 -translate-x-1/2 whitespace-nowrap rounded-[var(--r-pill)] bg-ink px-4 py-2 text-on-ink">
      {toast}
    </p>
  ) : null;
  return { share, toast: node };
}

export function StateBox({ kind, onRetry, text }: { kind: "preparing" | "error" | "skeleton" | "missing" | "comboOff" | "stale"; onRetry?: () => void; text?: string }) {
  const t = useTranslations();
  const locale = useLocale();
  if (kind === "skeleton") {
    return <div data-state="skeleton" className="h-40 rounded-[20px] bg-ink" />;
  }
  if (kind === "missing") {
    return (
      <div data-state="missing" className="rounded-[var(--r)] bg-bg-soft p-4">
        <p className="body">{t("state.notFoundPlace")}</p>
        <Link prefetch={false} href={`/${locale}`} className="press body mt-2 flex items-center font-semibold" style={{ color: "var(--go-text)" }}>
          {t("nav.home")}
        </Link>
      </div>
    );
  }
  if (kind === "comboOff" || kind === "stale") {
    return (
      <div data-state={kind} className="flex items-start gap-3 rounded-[var(--r)] bg-bg-soft p-4">
        <Clock aria-hidden />
        <p className="body">{kind === "comboOff" ? t("state.comboOff") : text}</p>
      </div>
    );
  }
  if (kind === "error") {
    return (
      <div data-state="error" className="rounded-[var(--r)] bg-bg-soft p-4">
        <p className="body" style={{ color: "var(--error-fg)" }}>
          {t("state.error")}
        </p>
        <button type="button" className="press body mt-2 font-semibold" onClick={onRetry}>
          {t("state.retry")}
        </button>
      </div>
    );
  }
  return (
    <div data-state="preparing" className="flex items-start gap-3 rounded-[var(--r)] bg-bg-soft p-4">
      <Clock aria-hidden />
      <p className="body">{t("state.preparing")}</p>
    </div>
  );
}

export function Badge({ kind }: { kind: "reference" | "holidayRef" | "experimental" }) {
  const t = useTranslations();
  const label = kind === "reference" ? t("badge.reference") : kind === "holidayRef" ? t("badge.holidayRef") : t("badge.experimental");
  return (
    <span data-badge className="label inline-flex h-6 shrink-0 items-center whitespace-nowrap rounded-[var(--r-pill)] px-2" style={{ background: "var(--on-ink-12)", color: "var(--on-ink)" }}>
      {label}
    </span>
  );
}

function marks(t: ReturnType<typeof useTranslations>) {
  return {
    month: t("time.month"),
    day: t("time.day"),
    weekdays: t.raw("time.weekdays") as string[],
    suffix: t("time.hour"),
  };
}

export function LevelDot({ level, onDark = false }: { level: number; onDark?: boolean }) {
  const colors = ["var(--go)", "var(--ok)", "var(--star)", "var(--hol)"];
  const background = onDark && level === 0 ? "var(--go-bright)" : colors[level] ?? "var(--bad-pin)";
  return <i data-status-dot className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background }} />;
}

export function AnswerCard({
  variant,
  name,
  nameEn,
  dateLine,
  weekday,
  range,
  reason,
  avoid,
  href,
  badge,
  extra,
  staleText,
  nowText,
  nowLevel,
}: {
  variant: "week" | "day" | "none" | "myeongjeol";
  name: string;
  nameEn?: string | null;
  dateLine?: string;
  weekday?: string;
  range?: string;
  reason?: string;
  /** "가장 붐빌 때 13~15시 · 붐빔": the busiest run of the day and its forecast level. */
  avoid?: string;
  href?: string;
  badge?: "reference" | "holidayRef" | "experimental" | null;
  extra?: string;
  staleText?: string | null;
  nowText?: string | null;
  nowLevel?: number | null;
}) {
  const t = useTranslations();
  const weekNone = variant === "none" && !dateLine;
  const nameClass = variant === "week" || weekNone ? "title" : "label text-on-ink-2";
  const body = (
    <div data-answer-card className="relative flex flex-col gap-4 overflow-hidden rounded-[20px] bg-ink p-5 text-on-ink">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {dateLine ? <p className="label truncate font-semibold text-on-ink-3">{dateLine}</p> : null}
          <h1 className={`${nameClass} truncate`}>
            <PlaceName name={name} nameEn={nameEn} />
          </h1>
          {variant === "week" && (staleText || nowText) ? (
            <p className="label mt-1 flex items-center gap-1.5 text-on-ink-2">
              {staleText || nowLevel === null || nowLevel === undefined ? null : <LevelDot level={nowLevel} onDark />}
              {staleText ?? nowText}
            </p>
          ) : null}
        </div>
        {badge ? <Badge kind={badge} /> : null}
      </div>
      {variant === "week" && range ? <hr className="h-px border-0" style={{ background: "var(--on-ink-12)" }} /> : null}
      {variant === "week" && range ? (
        <div className="flex flex-col gap-1">
          <p className="label font-semibold text-on-ink-3">{t("week.bestWhen")}</p>
          {weekday ? <p className="text-[20px] font-bold leading-6 text-on-ink">{weekday}</p> : null}
          <p className="answer-time text-go-bright" data-range>
            {range}
          </p>
        </div>
      ) : null}
      {variant === "day" && range ? (
        <div className="flex flex-col items-start gap-2">
          <p className="answer-time text-go-bright" data-range>
            {range}
          </p>
          <span className="label inline-flex h-7 items-center rounded-[var(--r-pill)] bg-go-bright px-3 font-bold text-ink">{t("day.goodToGo")}</span>
        </div>
      ) : null}
      {variant === "myeongjeol" ? <p className="body text-on-ink-2">{t("state.myeongjeol")}</p> : null}
      {variant === "none" ? (
        <>
          <p className="text-[22px] font-extrabold leading-[30px]">{weekNone ? t("state.weekNone") : t("day.noPick")}</p>
          <p className="body text-on-ink-2">{weekNone ? t("state.weekNoneHint") : t("day.tryThis")}</p>
        </>
      ) : null}
      {reason ? <p className="body text-on-ink-2">{reason}</p> : null}
      {avoid ? <p data-avoid className="label text-on-ink-3">{avoid}</p> : null}
      {extra ? <p className="label text-on-ink-3">{extra}</p> : null}
      {variant === "week" && href ? <p className="label font-semibold text-go-bright">{t("week.seeDay")} ›</p> : null}
    </div>
  );
  if (href) {
    return (
      <Link prefetch={false} href={href} className="block">
        {body}
      </Link>
    );
  }
  return body;
}

/** The busiest hours of a day as copy: `line` for the answer card ("가장 붐빌 때 13~15시 · 붐빔"); the week list shows
 * the level dot plus `range` and carries `line` as its accessible name. Null when no open hour reaches "a bit busy".
 * Tier B has no level forecast, only "busier than usual". */
export function avoidTexts(
  hours: HourCell[] | null | undefined,
  tier: string,
  locale: "ko" | "en",
  t: (key: string, values?: Record<string, string>) => string,
): { line: string; range: string; crowd: number } | null {
  const busiest = busiestRange(hours);
  if (!busiest) return null;
  const crowd = Math.min(Math.max(busiest.crowd, 0), 3);
  const range = formatHourRange(busiest.start, busiest.end, locale, t("time.hour"));
  const state = tier === "B" ? t("avoid.b") : t(`level.l${crowd}`);
  return { line: t("avoid.line", { label: t("avoid.busiest"), range, state }), range, crowd };
}

/** `nowHour` is passed for today only: hours before it are dimmed, the current hour carries a ring. */
export function MiniStrip({ hours, mode, nowHour }: { hours: HourCell[]; mode: string | null; nowHour?: number }) {
  return (
    <div data-mini-strip className="flex h-[18px] w-full gap-px">
      {hours.map((cell) => (
        <span
          key={cell.h}
          className="h-full flex-1"
          style={cellStyle(cellFill(cell, mode), cell.h, nowHour)}
          data-past={nowHour !== undefined && cell.h < nowHour ? "1" : undefined}
          data-now={cell.h === nowHour ? "1" : undefined}
        />
      ))}
    </div>
  );
}

function cellStyle(fill: ReturnType<typeof cellFill>, hour: number, nowHour: number | undefined): React.CSSProperties {
  const past = nowHour !== undefined && hour < nowHour;
  const rings = [fill.hollow ? "inset 0 0 0 1px var(--line)" : null, hour === nowHour ? "inset 0 0 0 2px var(--ink)" : null].filter(Boolean);
  return { background: fill.color, opacity: past ? 0.35 : undefined, boxShadow: rings.length ? rings.join(", ") : undefined };
}

/** `two_step`: the three verdict colours. `windows_only`: the pick colour, the four crowd shades (quiet to busy),
 * the hollow closed-hours cell when `outside` is set, and the busiest dot when `busiest` is set (week list). */
export function Legend({ mode, busiest, outside }: { mode: string | null; busiest?: boolean; outside?: boolean }) {
  const t = useTranslations();
  if (mode === "two_step") {
    const items = ["win", "1", "0"] as const;
    const colors = { win: "var(--go)", "1": "var(--ok)", "0": "var(--bad)" };
    return (
      <p data-legend-row className="caption mt-2 flex flex-wrap gap-x-3 gap-y-1 text-text-3">
        {items.map((key) => (
          <span key={key} data-legend-item className="inline-flex items-center gap-1">
            <i className="inline-block h-2 w-2" style={{ background: colors[key] }} />
            {t(`rate.${key}`)}
          </span>
        ))}
      </p>
    );
  }
  return (
    <p data-legend-row className="caption mt-2 flex flex-wrap gap-x-3 gap-y-1 text-text-3">
      <span data-legend-item className="inline-flex items-center gap-1">
        <i className="inline-block h-2 w-2" style={{ background: "var(--go)" }} />
        {t("rate.win")}
      </span>
      <span data-legend-item data-legend-crowd className="inline-flex items-center gap-1">
        {t("legend.crowd")}
        <span className="inline-flex items-center gap-0.5">
          <span>{t("legend.low")}</span>
          {[0, 1, 2, 3].map((level) => (
            <i key={level} className="inline-block h-2 w-2" style={{ background: `var(--crowd-${level})` }} />
          ))}
          <span>{t("legend.high")}</span>
        </span>
      </span>
      {outside ? (
        <span data-legend-item className="inline-flex items-center gap-1">
          <i className="inline-block h-2 w-2" style={{ background: "var(--bg)", boxShadow: "inset 0 0 0 1px var(--line)" }} />
          {t("legend.outside")}
        </span>
      ) : null}
      {busiest ? (
        <span data-legend-item data-legend-busiest className="inline-flex items-center gap-1">
          <LevelDot level={3} />
          {t("legend.busiest")}
        </span>
      ) : null}
    </p>
  );
}

export function WeekList({
  days,
  locale,
  today,
  bestDate,
  tier,
  nowHour,
  hrefFor,
}: {
  days: { date: string; state: string; off_reason: string | null; windows: { hours: number[]; score: number }[] | null; hours: HourCell[] | null; strip_mode: string | null; holiday: { name: string; name_en?: string | null; kind: string } | null }[];
  locale: "ko" | "en";
  today: string;
  bestDate?: string | null;
  tier?: string;
  /** The current KST hour: today's row dims the hours before it and rings the current one. */
  nowHour?: number;
  hrefFor: (date: string) => string;
}) {
  const t = useTranslations();
  const mark = marks(t);
  const columns = locale === "en" ? "56px minmax(0,1fr) 104px" : "56px minmax(0,1fr) 72px";
  return (
    <section className="mt-6">
      <h2 className="section mb-2">{t("week.glance")}</h2>
      <div className="grid gap-3" style={{ gridTemplateColumns: columns }} aria-hidden>
        <span />
        <span data-week-axis className="relative block h-4 text-[11px] leading-4 text-text-3">
          {[9, 12, 15, 18, 21].map((hour) => (
            <span key={hour} className="absolute" style={{ left: `${((hour - 9) / 15) * 100}%` }}>
              {hour}
            </span>
          ))}
        </span>
        <span />
      </div>
      <ul>
        {days.map((day) => {
          const best = day.state !== "off" && day.windows && day.windows.length > 0;
          // A day the engine could not forecast says why, in the strip's place; no date is promised.
          const offLabel = day.off_reason === "myeongjeol" ? t("state.myeongjeolShort") : t("state.dayPreparing");
          const time = day.state === "off" ? "" : best ? formatStoredWindows(day.windows, locale, mark.suffix)[0] : t("week.none");
          const holiday = day.holiday
            ? locale === "en"
              ? day.holiday.name_en || day.holiday.name
              : day.holiday.name
            : null;
          const recommended = Boolean(best) && day.date === bestDate;
          const avoid = day.state === "off" ? null : avoidTexts(day.hours, tier ?? "", locale, t);
          // The date is always there; a holiday name or "추천" is a third line under it.
          const third = holiday ?? (recommended ? t("week.recommended") : null);
          const thirdColor = holiday ? "var(--hol)" : "var(--go-text)";
          return (
            <li key={day.date}>
              <Link prefetch={false}
                href={hrefFor(day.date)}
                className="row relative grid h-14 items-center gap-3"
                style={{ gridTemplateColumns: columns }}
                data-row
              >
                {recommended ? <span className="absolute inset-y-0 -left-2 -right-2 rounded-[12px]" style={{ background: "var(--go-soft)" }} /> : null}
                <span className="relative caption">
                  <span className="block text-[15px] font-bold">{formatShortWeekday(day.date, mark.weekdays, t("time.today"), today)}</span>
                  <span className="block text-[11px] font-medium leading-[14px] text-text-3">{formatShortDate(day.date)}</span>
                  {third ? (
                    <span
                      data-week-third
                      className="block truncate text-[11px] font-medium leading-[14px]"
                      style={{ color: thirdColor }}
                      title={third}
                      lang={holiday && locale === "en" && !day.holiday?.name_en ? "ko" : undefined}
                    >
                      {third}
                    </span>
                  ) : null}
                </span>
                <span className="relative">
                  {day.state === "off" ? (
                    <span className="caption text-text-3">{offLabel}</span>
                  ) : day.hours ? (
                    <MiniStrip hours={day.hours} mode={day.strip_mode} nowHour={day.date === today ? nowHour : undefined} />
                  ) : null}
                </span>
                <span className="relative min-w-0 text-right">
                  <span data-week-time className={`block whitespace-nowrap ${best ? `${locale === "en" ? "text-[14px]" : "text-[15px]"} font-bold` : "caption text-text-3"}`}>
                    {time}
                  </span>
                  {avoid ? (
                    <span data-week-avoid aria-label={avoid.line} title={avoid.line} className="flex items-center justify-end gap-1 whitespace-nowrap text-[11px] font-medium leading-4 text-text-3">
                      <LevelDot level={avoid.crowd} />
                      <span aria-hidden>{avoid.range}</span>
                    </span>
                  ) : null}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function DayStrip({
  hours,
  mode,
  tier,
  purpose,
  hidden,
  selected,
  nowHour,
  onPick,
}: {
  hours: HourCell[];
  mode: string | null;
  tier?: string;
  purpose?: string;
  hidden?: boolean;
  selected?: number | null;
  /** The current KST hour, for today only. */
  nowHour?: number;
  onPick: (cell: HourCell | null) => void;
}) {
  const t = useTranslations();
  const locale = useLocale() as "ko" | "en";
  const say = useCellText();
  if (hidden) return <p className="body">{t("state.foreignStrip")}</p>;
  const labels = hours.map((cell) => say({ mode, hour: cell.h, cell, locale, tier, purpose, hours }));
  return (
    <section className="mt-6">
      <h2 className="section mb-2">{t("day.byHour")}</h2>
      <div className="grid grid-cols-[repeat(15,minmax(0,1fr))] gap-[3px]" role="list">
        {hours.map((cell, index) => {
          const fill = cellFill(cell, mode);
          const label = labels[index];
          const on = selected === cell.h;
          const past = nowHour !== undefined && cell.h < nowHour;
          return (
            <button
              key={cell.h}
              type="button"
              data-cell
              data-hour={cell.h}
              data-tone={fill.tone}
              data-crowd={fill.crowd ?? undefined}
              data-past={past ? "1" : undefined}
              data-now={cell.h === nowHour ? "1" : undefined}
              className="h-12 rounded-[6px]"
              style={{ ...cellStyle(fill, cell.h, nowHour), outline: on ? "2px solid var(--ink)" : undefined, outlineOffset: on ? "2px" : undefined }}
              aria-label={label}
              onClick={() => onPick(on ? null : cell)}
              aria-pressed={on}
            />
          );
        })}
      </div>
      <div className="mt-1.5 grid grid-cols-[repeat(15,minmax(0,1fr))] gap-[3px] text-[11px] text-text-3">
        {hours.map((cell, index) => (
          <span
            key={cell.h}
            data-axis-label={index % 3 === 0 ? "1" : undefined}
            data-axis-now={cell.h === nowHour ? "1" : undefined}
            className={cell.h === nowHour ? "font-bold text-text" : undefined}
          >
            {cell.h === nowHour ? t("legend.now") : index % 3 === 0 ? cell.h : ""}
          </span>
        ))}
      </div>
      <ul className="sr-only">
        {labels.map((label, index) => (
          <li key={hours[index].h}>{label}</li>
        ))}
      </ul>
    </section>
  );
}

type CellTextInput = {
  mode: string | null;
  hour: number;
  cell: HourCell;
  locale: "ko" | "en";
  tier?: string;
  purpose?: string;
  /** Every cell of the day, so a not-picked hour can name the next pick. */
  hours?: HourCell[] | null;
};

/** The one place a cell becomes a sentence: the strip, its screen-reader list and the map card all use it. */
export function useCellText() {
  const t = useTranslations();
  return ({ mode, hour, cell, locale, tier, purpose, hours }: CellTextInput): string => {
    const sentence = cellSentence({
      mode,
      inWindow: cell.in_window,
      rating: cell.rating,
      reason: cell.reason,
      hour,
      locale,
      tier,
      purpose,
      crowd: cell.crowd,
      act: cell.act,
      hours,
    });
    if (sentence.kind === "notPick") {
      // "운영 시간이 아니에요." already ends its clause; the template adds the full stop for a crowd sentence.
      const why = sentence.whys.map((id) => t(id)).join(" ").replace(/\.$/, "");
      const head = t("reason.notPickWhy", { hour: sentence.hour, why });
      if (!sentence.next) return head;
      const time = formatHourRange(sentence.next.start, sentence.next.end, locale, t("time.hour"));
      return `${head} ${t(sentence.next.kind === "from" ? "reason.pickFrom" : "reason.pickWas", { time })}`;
    }
    return t("reason.cell", {
      hour: sentence.hour,
      verdict: t(`reason.${sentence.verdict}`),
      why: sentence.whys.map((id) => t(id)).join(" "),
    });
  };
}

export function HourSentence(props: CellTextInput) {
  const say = useCellText();
  return say(props);
}

export function ConditionField({ label, onClick }: { label: string; onClick: () => void }) {
  const t = useTranslations();
  return (
    <button type="button" data-press className="press fade mt-4 flex w-full items-center justify-between gap-3 rounded-[12px] bg-bg-soft px-4" onClick={onClick}>
      <span className="body flex min-w-0 items-center gap-2 font-semibold">
        <SlidersHorizontal size={16} aria-hidden />
        <span data-field-label className="truncate">{label}</span>
      </span>
      <span className="body font-semibold" style={{ color: "var(--go-text)" }}>
        {t("cond.change")}
      </span>
    </button>
  );
}

export function AltButton({ href, label }: { href: string; label: string }) {
  return (
    <Link prefetch={false} href={href} data-press className="press body mt-2 flex items-center justify-between gap-3 rounded-[12px] px-4 font-semibold" style={{ background: "var(--go-soft)", color: "var(--go-text)" }}>
      <span data-field-label className="truncate">{label}</span>
      <span aria-hidden>›</span>
    </Link>
  );
}

export function ConditionSheet({
  open,
  tier,
  purpose,
  tolerance,
  combos,
  onClose,
  onApply,
}: {
  open: boolean;
  tier: string;
  purpose: Purpose;
  tolerance: Tolerance;
  combos: { purpose: string; tolerance: string; state: string }[];
  onClose: () => void;
  onApply: (next: { purpose: Purpose; tolerance: Tolerance }, note: string | null) => void;
}) {
  const t = useTranslations();
  const title = useRef<HTMLHeadingElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const [purposeNow, setPurposeNow] = useState(purpose);
  const [toleranceNow, setToleranceNow] = useState(tolerance);
  const [note, setNote] = useState<string | null>(null);

  // Focus moves into the sheet when it opens and back to what opened it when it closes; Tab stays inside.
  // The opener is captured once per opening: `onClose` is a fresh function on every render of the parent, so the
  // effect must not re-run (and re-capture the sheet's own title as the opener) each time it changes.
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    title.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialog.current) return;
      const items = [...dialog.current.querySelectorAll<HTMLElement>("button")];
      const first = items[0];
      const last = items[items.length - 1];
      const inside = dialog.current.contains(document.activeElement);
      if (event.shiftKey && (!inside || document.activeElement === first || document.activeElement === title.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (!inside || document.activeElement === last)) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener?.focus();
    };
  }, [open]);

  if (!open) return null;
  // Invariant 7: a combination the API did not list is off.
  const stateOf = (p: string, tol: string) => combos.find((row) => row.purpose === p && row.tolerance === tol)?.state ?? "off";
  const purposes: Purpose[] = ["sight", "food", "shop"];
  const tolerances: Tolerance[] = ["calm", "moderate", "busy_ok"];
  const usedPurpose = tier === "A1" ? (purposeNow as string) : "none";
  const offNow = tolerances.filter((item) => stateOf(usedPurpose, item) === "off");

  function choosePurpose(next: Purpose) {
    let tol = toleranceNow as Tolerance;
    let moved: string | null = null;
    if (stateOf(next, tol) === "off") {
      tol = stateOf(next, "moderate") === "off" ? "busy_ok" : "moderate";
      moved = t("sheet.moved", { tolerance: t(`tol.${tol}`) });
    }
    setPurposeNow(next);
    setToleranceNow(tol);
    setNote(moved);
  }

  // Arrow keys move the choice within a group, skipping options that are not ready.
  function onArrow<T extends string>(event: React.KeyboardEvent, items: T[], current: T, usable: (item: T) => boolean, choose: (item: T) => void) {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const start = items.indexOf(current);
    for (let moved = 1; moved <= items.length; moved += 1) {
      const next = items[(start + step * moved + items.length * moved) % items.length];
      if (usable(next)) {
        choose(next);
        const group = event.currentTarget as HTMLElement;
        window.setTimeout(() => group.querySelector<HTMLElement>('[aria-checked="true"]')?.focus(), 0);
        return;
      }
    }
  }

  return (
    <div className="fixed inset-0 z-20 flex items-end" style={{ background: "var(--ink-48)" }} onClick={onClose}>
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sheet-title"
        className="sheet-in w-full rounded-t-[24px] bg-bg p-4"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mx-auto mb-3 h-[5px] w-9 rounded-[var(--r-pill)] bg-line" />
        <div className="flex items-center justify-between">
          <h2 id="sheet-title" ref={title} tabIndex={-1} className="heading outline-none">
            {t("sheet.title")}
          </h2>
          <button type="button" className="icon-hit" onClick={onClose} aria-label={t("sheet.close")}>
            <X aria-hidden />
          </button>
        </div>
        {tier === "A1" ? (
          <fieldset className="mt-4">
            <legend className="section">{t("sheet.purpose")}</legend>
            <div
              role="radiogroup"
              aria-label={t("sheet.purpose")}
              className="mt-2 flex h-12 items-center gap-1 rounded-[12px] bg-bg-soft p-1"
              onKeyDown={(event) => onArrow(event, purposes, purposeNow, () => true, choosePurpose)}
            >
              {purposes.map((item) => (
                <button
                  key={item}
                  type="button"
                  role="radio"
                  aria-checked={purposeNow === item}
                  tabIndex={purposeNow === item ? 0 : -1}
                  className="h-10 flex-1 rounded-[10px] font-bold"
                  style={{ background: purposeNow === item ? "var(--bg)" : "transparent" }}
                  onClick={() => choosePurpose(item)}
                >
                  {t(`purpose.${item}`)}
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}
        <fieldset className="mt-4">
          <legend className="section">{t("sheet.crowd")}</legend>
          <div
            role="radiogroup"
            aria-label={t("sheet.crowd")}
            className="mt-2 flex h-12 items-center gap-1 rounded-[12px] bg-bg-soft p-1"
            onKeyDown={(event) => onArrow(event, tolerances, toleranceNow, (item) => stateOf(usedPurpose, item) !== "off", setToleranceNow)}
          >
            {tolerances.map((item) => {
              const off = stateOf(usedPurpose, item) === "off";
              return (
                <button
                  key={item}
                  type="button"
                  role="radio"
                  aria-checked={toleranceNow === item}
                  aria-disabled={off}
                  aria-describedby={off ? "sheet-not-ready" : undefined}
                  tabIndex={toleranceNow === item ? 0 : -1}
                  className="h-10 flex-1 rounded-[10px] font-bold"
                  style={{ background: toleranceNow === item ? "var(--bg)" : "transparent", color: off ? "var(--text-3)" : "var(--ink)" }}
                  onClick={() => {
                    if (off) return;
                    setToleranceNow(item);
                  }}
                >
                  {off ? <Clock className="inline" size={14} aria-hidden /> : null}
                  {t(`tol.${item}`)}
                </button>
              );
            })}
          </div>
          {offNow.length ? (
            <p id="sheet-not-ready" className="label mt-2 text-text-2">
              {offNow
                .map((item) =>
                  tier === "A1"
                    ? t("sheet.preparing", { purpose: t(`purpose.${purposeNow}`), tolerance: t(`tol.${item}`) })
                    : t("sheet.preparingPlain", { tolerance: t(`tol.${item}`) }),
                )
                .join(" ")}
            </p>
          ) : null}
          {note ? <p className="label mt-1">{note}</p> : null}
        </fieldset>
        <button
          type="button"
          data-press
          className="press body mt-4 w-full rounded-[12px] bg-ink font-semibold text-on-ink"
          onClick={() => onApply({ purpose: purposeNow as Purpose, tolerance: toleranceNow as Tolerance }, note)}
        >
          {t("sheet.apply")}
        </button>
      </div>
    </div>
  );
}

export function useDateMarks() {
  const t = useTranslations();
  const locale = useLocale() as "ko" | "en";
  return { locale, ...marks(t), long: (iso: string) => formatLongDate(iso, locale, marks(t)) };
}

export type { Favorite };
