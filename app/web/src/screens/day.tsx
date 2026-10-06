"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { AltButton, AnswerCard, AppBar, ConditionField, ConditionSheet, DayStrip, HourSentence, Legend, Phone, StateBox, avoidTexts } from "@/components/ui";
import { formatLongDate, formatShortDate, formatShortWeekday, formatStoredWindows } from "@/lib/format";
import { reasonMessageIds } from "@/lib/reason";
import type { HourCell } from "@/lib/strip";
import { kstNow, stillAhead } from "@/lib/kst";
import { readConditions, readFavorites, toggleFavorite, writeConditions, type Purpose, type Tolerance } from "@/lib/storage";
import { useLoad } from "@/lib/use-load";

type Rec = {
  recommendation: {
    state: string;
    off_reason: string | null;
    windows: { hours: number[]; score: number; crowd?: number; act?: string | null; act_level?: string | null }[] | null;
    no_window: boolean | null;
    hours: HourCell[] | null;
    strip_mode: string | null;
  } | null;
  place: { id: string; tier: string; name: string; name_en: string | null; gu: string | null; serve_state: string };
  holiday: { name: string; name_en?: string | null; kind: string } | null;
  combos: { purpose: string; tolerance: string; state: string }[];
  alt_dates: { date: string; hours: number[]; score: number }[];
  alt_places: { place_id: string; hours: number[]; name: string; name_en: string | null }[];
};

export function DayScreen({ id, date, fromMap, hour }: { id: string; date: string; fromMap?: boolean; hour?: string }) {
  const t = useTranslations();
  const locale = useLocale() as "ko" | "en";
  const [cond, setCond] = useState({ purpose: "sight" as Purpose, tolerance: "moderate" as Tolerance });
  const [open, setOpen] = useState(false);
  const [star, setStar] = useState(false);
  const [ready, setReady] = useState(false);
  const [picked, setPicked] = useState<HourCell | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      const purpose = params.get("purpose");
      const tol = params.get("tol");
      const stored = readConditions();
      setCond({
        purpose: purpose === "food" || purpose === "shop" || purpose === "sight" ? purpose : stored.purpose,
        tolerance: tol === "calm" || tol === "moderate" || tol === "busy_ok" ? tol : stored.tolerance,
      });
      setStar(readFavorites().some((item) => item.id === id));
      setReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [id]);
  const loaded = useLoad<Rec>(ready ? `/api/places/${id}/recommend?date=${date}&tolerance=${cond.tolerance}&purpose=${cond.purpose}` : null);
  const place = loaded.data?.place;
  const clock = kstNow();
  const stored = loaded.data?.recommendation;
  // A window of today that has already ended is not a recommendation any more.
  const rec = stored && stored.windows ? { ...stored, windows: stillAhead(stored.windows, date === clock.date, clock.hour) } : stored;
  const suffix = t("time.hour");
  const marks = { month: t("time.month"), day: t("time.day"), weekdays: t.raw("time.weekdays") as string[] };
  const back = fromMap ? `/${locale}/map?date=${date}&hour=${hour ?? "9"}` : `/${locale}/p/${id}`;
  const comboOff = rec?.state === "off" && (rec.off_reason === "failed" || rec.off_reason === "unverified");
  const none = rec?.state !== "off" && Boolean(rec) && (rec?.windows ?? []).length === 0;
  const myeongjeol = rec?.off_reason === "myeongjeol";
  // No row at all for an in-range date is missing data, the same state as a row that says so.
  const preparing = place?.serve_state === "preparing" || rec?.off_reason === "preparing" || (Boolean(loaded.data) && !rec);
  const ranges = formatStoredWindows(rec?.windows, locale, suffix);
  const today = clock.date;
  const weekdays = t.raw("time.weekdays") as string[];
  const altDay = (iso: string) => formatShortWeekday(iso, weekdays, t("time.today"), today);
  const holiday = loaded.data?.holiday;
  const holidayName = holiday ? (locale === "en" ? holiday.name_en || holiday.name : holiday.name) : null;
  const dateLine = holidayName ? `${formatLongDate(date, locale, marks)} · ${holidayName}` : formatLongDate(date, locale, marks);
  const reason = place && rec?.windows?.[0] ? reasonMessageIds(place.tier, rec.windows[0]).map((id) => t(id)).join(" ") : undefined;
  const avoid = place && rec ? avoidTexts(rec.hours, place.tier, locale, t)?.line : undefined;
  const condLabel = place?.tier === "A1" ? `${t(`purpose.${cond.purpose}`)} · ${t(`tol.${cond.tolerance}`)}` : t(`tol.${cond.tolerance}`);
  return (
    <Phone>
      <AppBar
        backHref={back}
        backLabel={fromMap ? t("map.title") : t("week.back")}
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
      {place && preparing ? <StateBox kind="preparing" /> : null}
      {place && comboOff && !preparing ? <StateBox kind="comboOff" /> : null}
      {place && myeongjeol ? <AnswerCard variant="myeongjeol" name={place.name} nameEn={place.name_en} dateLine={dateLine} /> : null}
      {place && !preparing && !myeongjeol && none ? (
        <AnswerCard variant="none" name={place.name} nameEn={place.name_en} dateLine={dateLine} />
      ) : null}
      {place && !preparing && !myeongjeol && !none && ranges.length > 0 ? (
        <AnswerCard
          variant="day"
          name={place.name}
          nameEn={place.name_en}
          dateLine={dateLine}
          range={ranges[0]}
          reason={reason}
          avoid={avoid}
          badge={rec?.state === "reference" ? "reference" : holiday ? "holidayRef" : null}
          extra={ranges.length > 1 ? `${t("day.alsoRec")} ${ranges.slice(1).join(", ")}` : undefined}
        />
      ) : null}
      {place && none && !myeongjeol && !preparing
        ? (loaded.data?.alt_dates ?? []).slice(0, 1).map((alt) => (
            <AltButton key={alt.date} href={`/${locale}/p/${id}/${alt.date}`} label={t("alt.betterDay", { day: altDay(alt.date), date: formatShortDate(alt.date), time: formatStoredWindows([{ hours: alt.hours }], locale, suffix).join(", ") })} />
          ))
        : null}
      {place && place.tier === "A1" && none && !myeongjeol
        ? (loaded.data?.alt_places ?? []).slice(0, 1).map((alt) => (
            <AltButton key={alt.place_id} href={`/${locale}/p/${alt.place_id}/${date}`} label={t("alt.similar", { place: alt.name, time: formatStoredWindows([{ hours: alt.hours }], locale, suffix).join(", ") })} />
          ))
        : null}
      {place && !myeongjeol && place.serve_state !== "preparing" ? (
        <ConditionField label={condLabel} onClick={() => setOpen(true)} />
      ) : null}
      {rec?.hours && rec.state !== "off" ? (
        <div>
          <DayStrip hours={rec.hours} mode={rec.strip_mode} tier={place?.tier} purpose={cond.purpose} selected={picked?.h} nowHour={date === clock.date ? clock.hour : undefined} onPick={setPicked} />
          <Legend mode={rec.strip_mode} outside={rec.hours.some((cell) => cell.reason === "outside_hours")} />
          <p data-hour-sentence className="body mt-4 min-h-12 rounded-[12px] bg-bg-soft p-3">{picked ? <HourSentence mode={rec.strip_mode} hour={picked.h} cell={picked} locale={locale} tier={place?.tier} purpose={cond.purpose} hours={rec.hours} /> : t("day.tapHint")}</p>
        </div>
      ) : null}
      {myeongjeol ? <div className="hatch mt-4 h-12 rounded-[6px]" data-state="myeongjeol" /> : null}
      {place ? (
        <ConditionSheet
          open={open}
          tier={place.tier}
          purpose={cond.purpose}
          tolerance={cond.tolerance}
          combos={loaded.data?.combos ?? []}
          onClose={() => setOpen(false)}
          onApply={(next) => {
            writeConditions(next);
            setCond(next);
            setPicked(null);
            setOpen(false);
          }}
        />
      ) : null}
    </Phone>
  );
}
