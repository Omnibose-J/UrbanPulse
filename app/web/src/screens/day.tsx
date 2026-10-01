"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { AltButton, AnswerCard, AppBar, ConditionField, ConditionSheet, DayStrip, Legend, Phone, StateBox } from "@/components/ui";
import { formatLongDate, formatShortDate, formatStoredWindows } from "@/lib/format";
import type { HourCell } from "@/lib/strip";
import { readConditions, toggleFavorite, writeConditions, type Purpose, type Tolerance } from "@/lib/storage";
import { useLoad } from "@/lib/use-load";

type Rec = {
  recommendation: {
    state: string;
    off_reason: string | null;
    windows: { hours: number[]; score: number }[] | null;
    no_window: boolean | null;
    hours: HourCell[] | null;
    strip_mode: string | null;
  } | null;
  place: { id: string; tier: string; name: string; name_en: string | null; gu: string | null; serve_state: string };
  holiday: { name: string; kind: string } | null;
  combos: { purpose: string; tolerance: string; state: string }[];
  alt_dates: { date: string; hours: number[]; score: number }[];
  alt_places: { place_id: string; hours: number[]; name: string | null; name_en: string | null }[];
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
      setReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const loaded = useLoad<Rec>(ready ? `/api/places/${id}/recommend?date=${date}&tolerance=${cond.tolerance}&purpose=${cond.purpose}` : null);
  const place = loaded.data?.place;
  const rec = loaded.data?.recommendation;
  const suffix = t("time.hour");
  const marks = { month: t("time.month"), day: t("time.day"), weekdays: t.raw("time.weekdays") as string[] };
  const back = fromMap ? `/${locale}/map?date=${date}&hour=${hour ?? "9"}` : `/${locale}/p/${id}`;
  const none = rec?.no_window || rec?.state === "off";
  const myeongjeol = rec?.off_reason === "myeongjeol";
  const preparing = place?.serve_state === "preparing" || rec?.off_reason === "preparing";
  const ranges = formatStoredWindows(rec?.windows, locale, suffix);
  return (
    <Phone>
      <AppBar
        backHref={back}
        backLabel={fromMap ? t("map.title") : t("week.back")}
        star={star}
        onStar={() => {
          if (!place) return;
          const next = toggleFavorite({ id: place.id, name: place.name, nameEn: place.name_en, gu: place.gu });
          setStar(next.some((item) => item.id === place.id));
        }}
      />
      {loaded.error ? <StateBox kind="error" onRetry={loaded.retry} /> : null}
      {loaded.loading ? <StateBox kind="skeleton" /> : null}
      {place && preparing ? <StateBox kind="preparing" /> : null}
      {place && myeongjeol ? <AnswerCard variant="myeongjeol" name={place.name} nameEn={place.name_en} when={formatLongDate(date, locale, marks)} /> : null}
      {place && !preparing && !myeongjeol && none ? (
        <AnswerCard variant="none" name={place.name} nameEn={place.name_en} when={formatLongDate(date, locale, marks)} />
      ) : null}
      {place && !preparing && !myeongjeol && !none && ranges.length > 0 ? (
        <AnswerCard
          variant="day"
          name={place.name}
          nameEn={place.name_en}
          when={ranges[0]}
          badge={rec?.state === "reference" ? "reference" : loaded.data?.holiday ? "holidayRef" : null}
          extra={ranges.length > 1 ? `${t("day.alsoRec")} ${ranges.slice(1).join(", ")}` : undefined}
        />
      ) : null}
      {place && none && !myeongjeol && !preparing
        ? (loaded.data?.alt_dates ?? []).slice(0, 1).map((alt) => (
            <AltButton key={alt.date} href={`/${locale}/p/${id}/${alt.date}`} label={t("alt.betterDay", { day: formatShortDate(alt.date), date: formatShortDate(alt.date), time: formatStoredWindows([{ hours: alt.hours }], locale, suffix).join(", ") })} />
          ))
        : null}
      {place && place.tier === "A1" && none && !myeongjeol
        ? (loaded.data?.alt_places ?? []).slice(0, 1).map((alt) => (
            <AltButton key={alt.place_id} href={`/${locale}/p/${alt.place_id}/${date}`} label={t("alt.similar", { place: alt.name ?? alt.place_id, time: formatStoredWindows([{ hours: alt.hours }], locale, suffix).join(", ") })} />
          ))
        : null}
      {place && !myeongjeol ? (
        <ConditionField label={`${t(`purpose.${cond.purpose}`)} · ${t(`tol.${cond.tolerance}`)}`} onClick={() => setOpen(true)} />
      ) : null}
      {rec?.hours ? (
        <div className={false ? "opacity-50" : undefined}>
          <DayStrip hours={rec.hours} mode={rec.strip_mode} onPick={setPicked} />
          <Legend mode={rec.strip_mode} />
          <p className="body mt-4 min-h-12 rounded-[12px] bg-bg-soft p-3">{picked ? t("reason.cell", { hour: String(picked.h), verdict: picked.in_window ? t("reason.window") : t("reason.avoid"), why: t(`reason.${picked.reason === "too_busy" ? "tooBusy" : picked.reason === "closed" ? "closed" : picked.reason === "outside_hours" ? "outsideHours" : "ok"}`) }) : t("day.tapHint")}</p>
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
            setOpen(false);
          }}
        />
      ) : null}
    </Phone>
  );
}
