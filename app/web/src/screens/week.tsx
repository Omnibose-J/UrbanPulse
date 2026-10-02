"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  AnswerCard,
  AppBar,
  ConditionField,
  ConditionSheet,
  Legend,
  Phone,
  StateBox,
  WeekList,
} from "@/components/ui";
import { formatClock, formatShortWeekday, formatStoredWindows } from "@/lib/format";
import { kstNow, stillAhead } from "@/lib/kst";
import { reasonMessageIds } from "@/lib/reason";
import type { HourCell } from "@/lib/strip";
import { readConditions, readFavorites, toggleFavorite, writeConditions, type Purpose, type Tolerance } from "@/lib/storage";
import { useLoad } from "@/lib/use-load";

type DayRow = {
  date: string;
  state: string;
  off_reason: string | null;
  windows: { hours: number[]; score: number; crowd?: number; act?: string | null; act_level?: string | null }[] | null;
  no_window: boolean | null;
  hours: HourCell[] | null;
  strip_mode: string | null;
  holiday: { name: string; name_en?: string | null; kind: string } | null;
};

type Body = {
  place: { id: string; tier: string; name: string; name_en: string | null; gu: string | null; serve_state: string; foreign_heavy: boolean };
  now: { level: number | null; stale: boolean; ts: string } | null;
  days: DayRow[];
  combos: { purpose: string; tolerance: string; state: string }[];
};

export function WeekScreen({ id, notice }: { id: string; notice?: string }) {
  const t = useTranslations();
  const locale = useLocale() as "ko" | "en";
  const [cond, setCond] = useState({ purpose: "sight" as Purpose, tolerance: "moderate" as Tolerance });
  const [open, setOpen] = useState(false);
  const [star, setStar] = useState(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCond(readConditions());
      setStar(readFavorites().some((item) => item.id === id));
      setReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [id]);
  const purpose = cond.purpose;
  const loaded = useLoad<Body>(ready ? `/api/places/${id}/week?tolerance=${cond.tolerance}&purpose=${purpose}` : null);
  const place = loaded.data?.place;
  const clock = kstNow();
  // A window of today that has already ended is not a recommendation any more.
  const days = (loaded.data?.days ?? []).map((day) =>
    day.date === clock.date && day.windows ? { ...day, windows: stillAhead(day.windows, true, clock.hour) } : day,
  );
  // Three different "nothing to show" states, each said as what it is.
  const placePreparing = place?.serve_state === "preparing";
  const allOff = days.every((day) => day.state === "off");
  const myeongjeolWeek = days.length > 0 && days.every((day) => day.off_reason === "myeongjeol");
  const dataPreparing = !placePreparing && (days.length === 0 || (allOff && days.every((day) => day.off_reason === "preparing")));
  const comboOff = !placePreparing && !dataPreparing && !myeongjeolWeek && allOff;
  const ranked = days.filter((day) => day.windows && day.windows.length > 0 && day.state !== "off");
  ranked.sort((a, b) => (b.windows![0].score - a.windows![0].score) || a.date.localeCompare(b.date));
  const best = ranked[0];
  const suffix = t("time.hour");
  const weekdays = t.raw("time.weekdays") as string[];
  const today = clock.date;
  const now = loaded.data?.now;
  const nowText = place?.tier === "B"
    ? t("state.tierb")
    : now && !now.stale && now.level !== null
      ? `${t(`now.l${now.level}`)} · ${t("now.asOf", { time: formatClock(now.ts) })}`
      : null;
  const range = best ? formatStoredWindows(best.windows, locale, suffix)[0] : undefined;
  const weekday = best ? formatShortWeekday(best.date, weekdays, t("time.today"), today) : undefined;
  const reason = place && best ? reasonMessageIds(place.tier, best.windows?.[0]).map((key) => t(key)).join(" ") : undefined;
  const showList = Boolean(loaded.data) && !placePreparing && !dataPreparing;
  return (
    <Phone>
      {notice === "past" ? <p data-notice className="label py-2">{t("state.past")}</p> : null}
      {notice === "range" ? <p data-notice className="label py-2">{t("state.outOfRange")}</p> : null}
      <AppBar
        backHref={`/${locale}`}
        star={star}
        onStar={
          place
            ? () => {
                const next = toggleFavorite({ id: place.id, name: place.name, nameEn: place.name_en, gu: place.gu });
                setStar(next.some((item) => item.id === place.id));
              }
            : undefined
        }
      />
      {loaded.error ? <StateBox kind="error" onRetry={loaded.retry} /> : null}
      {loaded.missing ? <StateBox kind="missing" /> : null}
      {loaded.loading ? <StateBox kind="skeleton" /> : null}
      {place && (placePreparing || dataPreparing) ? <StateBox kind="preparing" /> : null}
      {place && comboOff ? <StateBox kind="comboOff" /> : null}
      {place && showList && !comboOff && best ? (
        <AnswerCard
          variant="week"
          name={place.name}
          nameEn={place.name_en}
          weekday={weekday}
          range={range}
          reason={reason}
          href={`/${locale}/p/${id}/${best.date}`}
          nowText={nowText}
          nowLevel={place.tier === "B" || !now || now.stale ? null : now.level}
          staleText={now?.stale ? t("state.stale", { time: formatClock(now.ts) }) : null}
          badge={place.tier === "B" ? "experimental" : best.state === "reference" ? "reference" : null}
        />
      ) : null}
      {place && showList && !comboOff && !best ? <AnswerCard variant="none" name={place.name} nameEn={place.name_en} /> : null}
      {place && showList && !myeongjeolWeek ? (
        <ConditionField
          label={place.tier === "A1" ? `${t(`purpose.${purpose}`)} · ${t(`tol.${cond.tolerance}`)}` : t(`tol.${cond.tolerance}`)}
          onClick={() => setOpen(true)}
        />
      ) : null}
      {showList ? (
        <>
          <div className={now?.stale ? "opacity-50" : undefined}>
            <WeekList days={days} locale={locale} today={today} bestDate={best?.date} hrefFor={(date) => `/${locale}/p/${id}/${date}`} />
          </div>
          {comboOff ? null : <Legend mode={days.find((day) => day.strip_mode)?.strip_mode ?? "windows_only"} />}
        </>
      ) : null}
      {place ? (
        <ConditionSheet
          open={open}
          tier={place.tier}
          purpose={purpose}
          tolerance={cond.tolerance}
          combos={loaded.data?.combos ?? []}
          onClose={() => setOpen(false)}
          onApply={(next) => {
            writeConditions(next);
            setCond(next);
            setOpen(false);
          }}
        />
      ) : null}
    </Phone>
  );
}
