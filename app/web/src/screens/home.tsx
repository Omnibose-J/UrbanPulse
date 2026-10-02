"use client";

import { Search } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AppBar, LevelDot, MiniStrip, Phone, PlaceName, StateBox } from "@/components/ui";
import { formatClock, formatStoredWindows } from "@/lib/format";
import { kstNow } from "@/lib/kst";
import type { HourCell } from "@/lib/strip";
import { readConditions, readFavorites, type Favorite } from "@/lib/storage";
import { useLoad } from "@/lib/use-load";

type HomeBody = {
  as_of: string | null;
  stale: boolean;
  busy_top: { id: string; name: string; name_en: string | null; gu: string | null; level: number; window: { hours: number[] } | null }[];
  open_quiet: { id: string; name: string; name_en: string | null; gu: string | null; level: number; hours: HourCell[] | null; strip_mode: string | null; window: { hours: number[] } | null }[];
};

export function HomeScreen({ locale }: { locale: "ko" | "en" }) {
  const t = useTranslations();
  const [cond, setCond] = useState({ purpose: "sight", tolerance: "moderate" });
  const [favs, setFavs] = useState<Favorite[]>([]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCond(readConditions());
      setFavs(readFavorites());
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const loaded = useLoad<HomeBody>(`/api/home?tolerance=${cond.tolerance}&purpose=${cond.purpose}`);
  const suffix = t("time.hour");
  // Late data is said as late data. The lists are for fresh data only.
  const late = Boolean(loaded.data?.stale);
  const lateText = late && loaded.data?.as_of ? t("state.stale", { time: formatClock(loaded.data.as_of) }) : undefined;
  const busy = loaded.data && !late ? loaded.data.busy_top : [];
  const quiet = loaded.data && !late ? loaded.data.open_quiet : [];
  return (
    <Phone>
      <AppBar mapHref={`/${locale}/map`} />
      <div className="mt-3 flex flex-col gap-4">
        <h1 className="display">{t("home.title")}</h1>
        <p className="body text-text-2">{t("home.subtitle")}</p>
        <Link prefetch={false} href={`/${locale}/search`} data-press className="press body flex items-center gap-2.5 rounded-[12px] border border-line px-4 text-text-3">
          <Search size={16} aria-hidden />
          <span>{t("home.search")}</span>
        </Link>
      </div>
      <div className="mt-6 flex flex-col gap-6">
      <section data-busy>
        <h2 className="section mb-2">{t("home.busyTop")}</h2>
        {late ? <StateBox kind={lateText ? "stale" : "preparing"} text={lateText} /> : null}
        {loaded.error ? <StateBox kind="error" onRetry={loaded.retry} /> : null}
        {!loaded.data && !loaded.error ? (
          <div data-state="skeleton" className="flex flex-col gap-2">
            {[0, 1, 2].map((key) => (
              <div key={key} className="row rounded-[12px] bg-bg-soft" />
            ))}
          </div>
        ) : null}
        {loaded.data && !late && loaded.data.busy_top.length === 0 ? <p data-busy-empty className="body">{t("home.busyTopEmpty")}</p> : null}
        <ol>
          {busy.map((row, index) => {
            const range = row.window ? formatStoredWindows([row.window], locale, suffix)[0] : "";
            return (
            <li key={row.id}>
              <Link prefetch={false} href={`/${locale}/p/${row.id}`} data-row className="row flex items-center justify-between">
                <span className="flex items-center gap-3">
                  <span className="w-5 text-[20px] font-extrabold text-text-3">{index + 1}</span>
                  <span>
                    <span className="body block font-semibold"><PlaceName name={row.name} nameEn={row.name_en} /></span>
                    <span className="caption text-text-3" lang="ko">{row.gu}</span>
                  </span>
                </span>
                <span className="caption text-right">
                  <span className="flex items-center justify-end gap-1.5 text-text">
                    <LevelDot level={row.level} />
                    {t(`level.l${row.level}`)}
                  </span>
                  <span className="block">{range ? `${t("week.recommended")} ${range}` : t("home.noPickToday")}</span>
                </span>
              </Link>
            </li>
            );
          })}
        </ol>
      </section>
      <section data-quiet-section>
        <h2 className="section mb-2">{t("home.openQuiet")}</h2>
        {!loaded.data && !loaded.error ? (
          <div data-state="skeleton" className="flex gap-3">
            {[0, 1].map((key) => (
              <div key={key} className="h-32 w-[232px] shrink-0 rounded-[16px] bg-bg-soft" />
            ))}
          </div>
        ) : null}
        {loaded.data && !late && quiet.length === 0 ? <p data-quiet-empty className="body">{t("home.openQuietEmpty")}</p> : null}
        <div className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-3">
          {quiet.map((row) => {
            const range = row.window ? formatStoredWindows([row.window], locale, suffix)[0] : "";
            return (
            <Link prefetch={false} key={row.id} href={`/${locale}/p/${row.id}/${kstNow().date}`} data-quiet={row.level} className="flex w-[232px] shrink-0 snap-start flex-col gap-3 rounded-[16px] border border-line p-4">
              <span className="flex min-w-0 items-start justify-between gap-2">
                <span data-place-name className="min-w-0 truncate text-[17px] font-extrabold leading-snug"><PlaceName name={row.name} nameEn={row.name_en} /></span>
                <span data-place-status className="caption flex shrink-0 items-center gap-1.5 whitespace-nowrap font-semibold" style={{ color: "var(--go-text)" }}>
                  <LevelDot level={row.level} />
                  {t(`level.l${row.level}`)}
                </span>
              </span>
              <span className="caption -mt-2 text-text-3" lang="ko">{row.gu}</span>
              <span className="label text-text-2">
                {t("home.todayLabel")}
                <b className="ml-1 text-[20px] font-extrabold text-text">{range || t("week.none")}</b>
              </span>
              {row.hours ? <MiniStrip hours={row.hours} mode={row.strip_mode} /> : null}
            </Link>
            );
          })}
        </div>
      </section>
      {favs.length ? (
        <section>
          <h2 className="section mb-2">{t("home.favorites")}</h2>
          <ul>
            {favs.map((row) => (
              <li key={row.id}>
                <Link prefetch={false} href={`/${locale}/p/${row.id}`} data-row className="row flex items-center">
                  <PlaceName name={row.name} nameEn={row.nameEn} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      </div>
    </Phone>
  );
}
