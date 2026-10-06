"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  AnswerCard,
  avoidTexts,
  AppBar,
  ConditionField,
  ConditionSheet,
  Legend,
  Phone,
  StateBox,
  WeekList,
  useShare,
} from "@/components/ui";
import Link from "next/link";

import { bestDay, withTodayTrimmed } from "@/lib/best";
import { disablePush, enablePush, pushSupported, readPushOn, type PushOutcome } from "@/lib/push-client";
import { formatClock, formatShortWeekday, formatStoredWindows } from "@/lib/format";
import { kstNow } from "@/lib/kst";
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
  // The weekend reminder: hidden where the browser cannot push; its switch state is the browser's own record.
  const [push, setPush] = useState<{ supported: boolean; on: boolean; note: PushOutcome | "busy" | null }>({ supported: false, on: false, note: null });
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCond(readConditions());
      setStar(readFavorites().some((item) => item.id === id));
      setPush({ supported: pushSupported(), on: readPushOn(), note: null });
      setReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [id]);
  const togglePush = async () => {
    setPush((state) => ({ ...state, note: "busy" }));
    if (push.on) {
      const outcome = await disablePush();
      setPush((state) => ({ ...state, on: outcome === "off" ? false : state.on, note: outcome === "off" ? null : outcome }));
      return;
    }
    const key = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
    if (!key) throw new Error("missing env var: NEXT_PUBLIC_VAPID_PUBLIC_KEY");
    const outcome = await enablePush({ locale, placeIds: readFavorites().map((item) => item.id), tolerance: cond.tolerance, purpose: cond.purpose, vapidPublicKey: key });
    setPush((state) => ({ ...state, on: outcome === "on", note: outcome === "on" ? null : outcome }));
  };
  const purpose = cond.purpose;
  const loaded = useLoad<Body>(ready ? `/api/places/${id}/week?tolerance=${cond.tolerance}&purpose=${purpose}` : null);
  const place = loaded.data?.place;
  const clock = kstNow();
  const { share, toast } = useShare();
  // A window of today that has already ended is not a recommendation any more.
  const days = withTodayTrimmed(loaded.data?.days ?? [], clock.date, clock.hour);
  // Three different "nothing to show" states, each said as what it is.
  const placePreparing = place?.serve_state === "preparing";
  const allOff = days.every((day) => day.state === "off");
  const myeongjeolWeek = days.length > 0 && days.every((day) => day.off_reason === "myeongjeol");
  const dataPreparing = !placePreparing && (days.length === 0 || (allOff && days.every((day) => day.off_reason === "preparing")));
  const comboOff = !placePreparing && !dataPreparing && !myeongjeolWeek && allOff;
  const best = bestDay(days);
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
  const avoid = place && best ? avoidTexts(best.hours, place.tier, locale, t)?.line : undefined;
  const showList = Boolean(loaded.data) && !placePreparing && !dataPreparing;
  return (
    <Phone>
      {notice === "past" ? <p data-notice className="label py-2">{t("state.past")}</p> : null}
      {notice === "range" ? <p data-notice className="label py-2">{t("state.outOfRange")}</p> : null}
      <AppBar
        backHref={`/${locale}`}
        star={star}
        onShare={
          place
            ? () => {
                const name = locale === "en" && place.name_en ? place.name_en : place.name;
                const text = range && weekday ? t("share.textWeek", { place: name, day: weekday, time: range }) : t("share.textPlain", { place: name });
                void share(text, `${window.location.origin}/${locale}/p/${id}`);
              }
            : undefined
        }
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
          avoid={avoid}
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
      {place && showList ? (
        <Link prefetch={false} href={`/${locale}/search?compare=${id}`} data-press data-compare-link className="press body mt-2 flex items-center justify-between gap-3 rounded-[12px] bg-bg-soft px-4 font-semibold">
          <span data-field-label className="truncate">{t("compare.action")}</span>
          <span aria-hidden>›</span>
        </Link>
      ) : null}
      {place && showList && push.supported ? (
        <div className="mt-2 rounded-[12px] bg-bg-soft px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <span className="body font-semibold">{t("push.toggle")}</span>
            <button
              type="button"
              role="switch"
              aria-checked={push.on}
              data-push-toggle
              disabled={push.note === "busy" || (!push.on && !star)}
              className="label flex h-8 min-w-14 items-center justify-center rounded-[var(--r-pill)] px-3 font-bold disabled:opacity-50"
              style={{ background: push.on ? "var(--go)" : "var(--line)", color: push.on ? "var(--on-ink)" : "var(--text)" }}
              onClick={togglePush}
            >
              {push.on ? t("push.on") : t("push.off")}
            </button>
          </div>
          <p data-push-note className="caption mt-1 text-text-3">
            {push.note === "denied" ? t("push.denied") : push.note === "failed" || push.note === "unsupported" ? t("push.failed") : !push.on && !star ? t("push.needStar") : t("push.hint")}
          </p>
        </div>
      ) : null}
      {toast}
      {showList ? (
        <>
          <div className={now?.stale ? "opacity-50" : undefined}>
            <WeekList days={days} locale={locale} today={today} bestDate={best?.date} tier={place?.tier} nowHour={clock.hour} hrefFor={(date) => `/${locale}/p/${id}/${date}`} />
          </div>
          {comboOff ? null : (
            <Legend
              mode={days.find((day) => day.strip_mode)?.strip_mode ?? "windows_only"}
              busiest={days.some((day) => day.state !== "off" && avoidTexts(day.hours, place?.tier ?? "", locale, t) !== null)}
              outside={days.some((day) => day.hours?.some((cell) => cell.reason === "outside_hours"))}
            />
          )}
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
