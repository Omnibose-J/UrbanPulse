"use client";

import { ChevronLeft, Clock, Map, SlidersHorizontal, Star, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { formatHourRange, formatLongDate, formatShortDate, formatShortWeekday, formatStoredWindows } from "@/lib/format";
import type { HourCell } from "@/lib/strip";
import { cellTone, toneColor } from "@/lib/strip";
import type { Favorite, Purpose, Tolerance } from "@/lib/storage";

export function PlaceName({ name, nameEn }: { name: string; nameEn?: string | null }) {
  const locale = useLocale();
  if (locale === "en" && nameEn) return <span>{nameEn}</span>;
  return <span lang="ko">{name}</span>;
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
}: {
  backHref?: string;
  backLabel?: string;
  title?: string;
  star?: boolean;
  onStar?: () => void;
  mapHref?: string;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const pathname = usePathname();
  const params = useSearchParams();
  const other = locale === "ko" ? "en" : "ko";
  const query = params.toString();
  const switched = pathname.replace(/^\/(ko|en)/, `/${other}`) + (query ? `?${query}` : "");
  return (
    <header className="flex h-14 items-center justify-between">
      <div className="flex items-center gap-1">
        {backHref ? (
          <>
            <a href={backHref} className={`-ml-2.5 flex shrink-0 items-center gap-1 whitespace-nowrap text-[15px] font-semibold ${backLabel ? "h-11 pr-2" : "icon-hit"}`}>
              <ChevronLeft aria-hidden />
              {backLabel ? <span className="whitespace-nowrap">{backLabel}</span> : null}
            </a>
            {title ? <span className="text-[17px] font-extrabold tracking-tight">{title}</span> : null}
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
      <div className="flex items-center">
        {mapHref ? (
          <a href={mapHref} className="icon-hit flex items-center justify-center" aria-label={t("map.title")}>
            <Map />
          </a>
        ) : null}
        {onStar ? (
          <button type="button" className="icon-hit" onClick={onStar} aria-pressed={star} aria-label={t("home.favorites")}>
            <Star fill={star ? "var(--star)" : "none"} color="var(--star)" />
          </button>
        ) : null}
        <a href={switched} className="label px-2 font-bold" aria-label={t("nav.language")}>
          KO · EN
        </a>
      </div>
    </header>
  );
}

export function StateBox({ kind, onRetry }: { kind: "preparing" | "error" | "skeleton"; onRetry?: () => void }) {
  const t = useTranslations();
  if (kind === "skeleton") {
    return <div data-state="skeleton" className="h-40 rounded-[20px] bg-ink" />;
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
      <span className="pointer-events-none absolute -right-10 -top-16 h-48 w-48 rounded-full" style={{ background: "radial-gradient(circle, rgb(70 224 160 / 22%), transparent 70%)" }} />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {dateLine ? <p className="label truncate font-semibold text-on-ink-3">{dateLine}</p> : null}
          <p className={`${nameClass} truncate`}>
            <PlaceName name={name} nameEn={nameEn} />
          </p>
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
      {extra ? <p className="label text-on-ink-3">{extra}</p> : null}
      {variant === "week" && href ? <p className="label font-semibold text-go-bright">{t("week.seeDay")} ›</p> : null}
    </div>
  );
  if (href) {
    return (
      <a href={href} className="block">
        {body}
      </a>
    );
  }
  return body;
}

export function MiniStrip({ hours, mode }: { hours: HourCell[]; mode: string | null }) {
  return (
    <div data-mini-strip className="flex h-[18px] w-full gap-px">
      {hours.map((cell) => (
        <span key={cell.h} className="h-full flex-1" style={{ background: toneColor(cellTone(cell, mode)) }} />
      ))}
    </div>
  );
}

export function Legend({ mode }: { mode: string | null }) {
  const t = useTranslations();
  const items = mode === "two_step" ? (["win", "1", "0"] as const) : (["win"] as const);
  const colors = { win: "var(--go)", "1": "var(--ok)", "0": "var(--bad)" };
  return (
    <p className="caption mt-2 flex gap-3 text-text-3">
      {items.map((key) => (
        <span key={key} className="inline-flex items-center gap-1">
          <i className="inline-block h-2 w-2" style={{ background: colors[key] }} />
          {t(`rate.${key}`)}
        </span>
      ))}
    </p>
  );
}

export function WeekList({
  days,
  locale,
  today,
  bestDate,
  hrefFor,
}: {
  days: { date: string; state: string; off_reason: string | null; windows: { hours: number[]; score: number }[] | null; hours: HourCell[] | null; strip_mode: string | null; holiday: { name: string; name_en?: string | null; kind: string } | null }[];
  locale: "ko" | "en";
  today: string;
  bestDate?: string | null;
  hrefFor: (date: string) => string;
}) {
  const t = useTranslations();
  const mark = marks(t);
  return (
    <section>
      <h2 className="section mb-2">{t("week.glance")}</h2>
      <ul>
        {days.map((day) => {
          const best = day.state !== "off" && day.windows && day.windows.length > 0;
          const time = best ? formatStoredWindows(day.windows, locale, mark.suffix)[0] : t("week.none");
          const holiday = day.holiday
            ? locale === "en"
              ? day.holiday.name_en || day.holiday.name
              : day.holiday.name
            : null;
          const recommended = Boolean(best) && day.date === bestDate;
          const lower = holiday ?? (recommended ? t("week.recommended") : formatShortDate(day.date));
          const lowerColor = holiday ? "var(--hol)" : recommended ? "var(--go-text)" : "var(--text-3)";
          return (
            <li key={day.date}>
              <a
                href={hrefFor(day.date)}
                className="row relative grid h-14 items-center gap-3"
                style={{ gridTemplateColumns: locale === "en" ? "56px minmax(0,1fr) 104px" : "56px minmax(0,1fr) 72px" }}
                data-row
              >
                {recommended ? <span className="absolute inset-y-0 -left-2 -right-2 rounded-[12px]" style={{ background: "var(--go-soft)" }} /> : null}
                <span className="relative caption">
                  <span className="block text-[15px] font-bold">{formatShortWeekday(day.date, mark.weekdays, t("time.today"), today)}</span>
                  <span className="block truncate text-[11px] font-medium" style={{ color: lowerColor }} lang={holiday && locale === "en" && !day.holiday?.name_en ? "ko" : undefined}>
                    {lower}
                  </span>
                </span>
                <span className="relative">
                  {day.state === "off" ? (
                    <span className="caption text-text-3">{day.off_reason === "myeongjeol" ? t("state.myeongjeolShort") : t("about.preparing")}</span>
                  ) : day.hours ? (
                    <MiniStrip hours={day.hours} mode={day.strip_mode} />
                  ) : null}
                </span>
                <span data-week-time className={`relative min-w-0 text-right whitespace-nowrap ${best ? "text-[15px] font-bold" : "caption text-text-3"}`}>
                  {day.off_reason === "myeongjeol" ? t("state.myeongjeolShort") : time}
                </span>
              </a>
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
  hidden,
  selected,
  onPick,
}: {
  hours: HourCell[];
  mode: string | null;
  hidden?: boolean;
  selected?: number | null;
  onPick: (cell: HourCell | null) => void;
}) {
  const t = useTranslations();
  const locale = useLocale() as "ko" | "en";
  const suffix = t("time.hour");
  if (hidden) return <p className="body">{t("state.foreignStrip")}</p>;
  return (
    <section>
      <h2 className="section mb-2">{t("day.byHour")}</h2>
      <div className="grid grid-cols-[repeat(15,minmax(0,1fr))] gap-[3px]" role="list">
        {hours.map((cell) => {
          const tone = cellTone(cell, mode);
          const verdict = cell.in_window ? t("reason.window") : cell.rating === 1 && mode === "two_step" ? t("reason.ok") : t("reason.avoid");
          const on = selected === cell.h;
          return (
            <button
              key={cell.h}
              type="button"
              data-cell
              data-tone={tone}
              className="h-12 rounded-[6px]"
              style={{ background: toneColor(tone), outline: on ? "2px solid var(--ink)" : undefined, outlineOffset: on ? "2px" : undefined }}
              aria-label={t("reason.cell", { hour: formatHourRange(cell.h, cell.h, locale, suffix), verdict, why: "" })}
              onClick={() => onPick(on ? null : cell)}
              aria-pressed={on}
            />
          );
        })}
      </div>
      <div className="mt-1.5 grid grid-cols-[repeat(15,minmax(0,1fr))] gap-[3px] text-[11px] text-text-3">
        {hours.map((cell, index) => (
          <span key={cell.h} data-axis-label={index % 3 === 0 ? "1" : undefined}>
            {index % 3 === 0 ? cell.h : ""}
          </span>
        ))}
      </div>
      <table className="sr-only">
        <tbody>
          {hours.map((cell) => (
            <tr key={cell.h}>
              <td>{cell.h}</td>
              <td>{cell.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
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
    <a href={href} data-press className="press body mt-2 flex items-center justify-between gap-3 rounded-[12px] px-4 font-semibold" style={{ background: "var(--go-soft)", color: "var(--go-text)" }}>
      <span data-field-label className="truncate">{label}</span>
      <span aria-hidden>›</span>
    </a>
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
  const [purposeNow, setPurposeNow] = useState(purpose);
  const [toleranceNow, setToleranceNow] = useState(tolerance);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const stateOf = (p: string, tol: string) => combos.find((row) => row.purpose === p && row.tolerance === tol)?.state ?? "off";
  const purposes: Purpose[] = ["sight", "food", "shop"];
  const tolerances: Tolerance[] = ["calm", "moderate", "busy_ok"];

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

  return (
    <div className="fixed inset-0 z-20 flex items-end" style={{ background: "var(--ink-48)" }} onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sheet-title"
        className="sheet-in w-full rounded-t-[24px] bg-bg p-4"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mx-auto mb-3 h-[5px] w-9 rounded-[var(--r-pill)] bg-line" />
        <div className="flex items-center justify-between">
          <h2 id="sheet-title" ref={title} tabIndex={-1} className="heading">
            {t("sheet.title")}
          </h2>
          <button type="button" className="icon-hit" onClick={onClose} aria-label={t("cond.change")}>
            <X />
          </button>
        </div>
        {tier === "A1" ? (
          <fieldset className="mt-4">
            <legend className="section">{t("sheet.purpose")}</legend>
            <div role="radiogroup" className="mt-2 flex h-12 items-center gap-1 rounded-[12px] bg-bg-soft p-1">
              {purposes.map((item) => (
                <button key={item} type="button" role="radio" aria-checked={purposeNow === item} className="h-10 flex-1 rounded-[10px] font-bold" style={{ background: purposeNow === item ? "var(--bg)" : "transparent" }} onClick={() => choosePurpose(item)}>
                  {t(`purpose.${item}`)}
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}
        <fieldset className="mt-4">
          <legend className="section">{t("sheet.crowd")}</legend>
          <div role="radiogroup" className="mt-2 flex h-12 items-center gap-1 rounded-[12px] bg-bg-soft p-1">
            {tolerances.map((item) => {
              const usedPurpose = tier === "A1" ? (purposeNow as string) : "none";
              const off = stateOf(usedPurpose, item) === "off";
              return (
                <button
                  key={item}
                  type="button"
                  role="radio"
                  aria-checked={toleranceNow === item}
                  aria-disabled={off}
                  className="h-10 flex-1 rounded-[10px] font-bold"
                  style={{ background: toleranceNow === item ? "var(--bg)" : "transparent", color: off ? "var(--text-3)" : "var(--ink)" }}
                  onClick={() => {
                    if (off) return;
                    setToleranceNow(item);
                  }}
                >
                  {off ? <Clock className="inline" size={14} /> : null}
                  {t(`tol.${item}`)}
                </button>
              );
            })}
          </div>
          <p className="label mt-2 text-text-2">
            {tolerances
              .filter((item) => stateOf(tier === "A1" ? (purposeNow as string) : "none", item) === "off")
              .map((item) => t("sheet.preparing", { purpose: t(`purpose.${purposeNow}`), tolerance: t(`tol.${item}`) }))
              .join(" ")}
          </p>
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
