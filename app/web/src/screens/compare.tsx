"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AppBar, ConditionField, ConditionSheet, Legend, MiniStrip, Phone, PlaceName, StateBox } from "@/components/ui";
import { bestDay, withTodayTrimmed } from "@/lib/best";
import { formatShortDate, formatShortWeekday, formatStoredWindows } from "@/lib/format";
import { kstNow } from "@/lib/kst";
import type { HourCell } from "@/lib/strip";
import { readConditions, writeConditions, type Purpose, type Tolerance } from "@/lib/storage";
import { useLoad } from "@/lib/use-load";

type DayRow = {
  date: string;
  state: string;
  off_reason: string | null;
  windows: { hours: number[]; score: number }[] | null;
  hours: HourCell[] | null;
  strip_mode: string | null;
  holiday: { name: string; name_en?: string | null; kind: string } | null;
};

type Body = {
  place: { id: string; tier: string; name: string; name_en: string | null; gu: string | null; serve_state: string };
  days: DayRow[];
  combos: { purpose: string; tolerance: string; state: string }[];
};

/** ⑧ compare: two places' weeks side by side under one set of conditions. Each column is the week screen's data. */
export function CompareScreen({ a, b }: { a: string; b: string }) {
  const t = useTranslations();
  const locale = useLocale() as "ko" | "en";
  const [cond, setCond] = useState({ purpose: "sight" as Purpose, tolerance: "moderate" as Tolerance });
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCond(readConditions());
      setReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const query = `tolerance=${cond.tolerance}&purpose=${cond.purpose}`;
  const left = useLoad<Body>(ready ? `/api/places/${a}/week?${query}` : null);
  const right = useLoad<Body>(ready ? `/api/places/${b}/week?${query}` : null);
  const clock = kstNow();
  const sides = [left, right].map((side) => {
    const days = side.data ? withTodayTrimmed(side.data.days, clock.date, clock.hour) : [];
    return { ...side, days, best: bestDay(days) };
  });
  const weekdays = t.raw("time.weekdays") as string[];
  const suffix = t("time.hour");
  const dates = sides[0].days.length ? sides[0].days.map((day) => day.date) : sides[1].days.map((day) => day.date);
  const loading = sides.some((side) => side.loading);
  const missing = sides.some((side) => side.missing);
  const error = sides.some((side) => side.error);
  const both = sides.every((side) => side.data);
  // The condition sheet needs one place's combinations; an A1 side decides the purposes on offer.
  const sheetSide = sides.find((side) => side.data?.place.tier === "A1") ?? sides[0];
  return (
    <Phone>
      <AppBar backHref={`/${locale}/p/${a}`} title={t("compare.title")} />
      {error ? <StateBox kind="error" onRetry={() => sides.forEach((side) => side.retry())} /> : null}
      {missing ? <StateBox kind="missing" /> : null}
      {loading && !both ? <StateBox kind="skeleton" /> : null}
      {both ? (
        <>
          <div data-compare-heads className="mt-2 grid grid-cols-[44px_1fr_1fr] gap-3">
            <span />
            {sides.map((side, index) => {
              const place = side.data!.place;
              const best = side.best;
              return (
                <Link prefetch={false} key={place.id} href={`/${locale}/p/${place.id}`} data-compare-head={index === 0 ? "a" : "b"} className="min-w-0 rounded-[16px] bg-ink p-3 text-on-ink">
                  <span className="block truncate text-[15px] font-extrabold"><PlaceName name={place.name} nameEn={place.name_en} /></span>
                  <span className="label mt-1 block text-on-ink-3">{t("compare.best")}</span>
                  {best ? (
                    <span className="block text-[17px] font-extrabold text-go-bright" data-compare-best>
                      {formatShortWeekday(best.date, weekdays, t("time.today"), clock.date)} {formatStoredWindows(best.windows, locale, suffix)[0]}
                    </span>
                  ) : (
                    <span className="block text-[15px] font-bold text-on-ink-2" data-compare-best>{t("state.weekNone")}</span>
                  )}
                </Link>
              );
            })}
          </div>
          <ConditionField
            label={sheetSide.data!.place.tier === "A1" ? `${t(`purpose.${cond.purpose}`)} · ${t(`tol.${cond.tolerance}`)}` : t(`tol.${cond.tolerance}`)}
            onClick={() => setOpen(true)}
          />
          <section className="mt-6">
            <h2 className="section mb-2">{t("week.glance")}</h2>
            <ul>
              {dates.map((date) => (
                <li key={date} data-compare-row className="grid min-h-14 grid-cols-[44px_1fr_1fr] items-center gap-3 border-b border-line py-2">
                  <span className="caption">
                    <span className="block text-[15px] font-bold">{formatShortWeekday(date, weekdays, t("time.today"), clock.date)}</span>
                    <span className="block text-[11px] text-text-3">{formatShortDate(date)}</span>
                  </span>
                  {sides.map((side, index) => {
                    const day = side.days.find((row) => row.date === date);
                    if (!day) return <span key={index} />;
                    const pick = day.state !== "off" && day.windows && day.windows.length > 0;
                    const offLabel = day.off_reason === "myeongjeol" ? t("state.myeongjeolShort") : t("state.dayPreparing");
                    return (
                      <span key={index} className="min-w-0">
                        <span data-compare-time className={`block text-[13px] ${pick ? "truncate font-bold" : "caption text-text-3"}`}>
                          {day.state === "off" ? offLabel : pick ? formatStoredWindows(day.windows, locale, suffix)[0] : t("week.none")}
                        </span>
                        {day.state !== "off" && day.hours ? (
                          <span className="mt-1 block">
                            <MiniStrip hours={day.hours} mode={day.strip_mode} nowHour={date === clock.date ? clock.hour : undefined} />
                          </span>
                        ) : null}
                      </span>
                    );
                  })}
                </li>
              ))}
            </ul>
            <Legend mode={sides.flatMap((side) => side.days).find((day) => day.strip_mode)?.strip_mode ?? "windows_only"} />
          </section>
          <ConditionSheet
            open={open}
            tier={sheetSide.data!.place.tier}
            purpose={cond.purpose}
            tolerance={cond.tolerance}
            combos={sheetSide.data!.combos}
            onClose={() => setOpen(false)}
            onApply={(next) => {
              writeConditions(next);
              setCond(next);
              setOpen(false);
            }}
          />
        </>
      ) : null}
    </Phone>
  );
}
