"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { AppBar, Phone, PlaceName, StateBox } from "@/components/ui";
import { formatStoredWindows } from "@/lib/format";
import { kstNow } from "@/lib/kst";
import { readConditions, readFavorites, type Favorite } from "@/lib/storage";
import { useLoad } from "@/lib/use-load";

type HomeBody = {
  as_of: string | null;
  stale: boolean;
  busy_top: { id: string; name: string; name_en: string | null; gu: string | null; level: number; window: { hours: number[] } | null }[];
  open_quiet: { id: string; name: string; name_en: string | null; gu: string | null; level: number; hours: { h: number; rating: number; in_window: boolean }[] | null; strip_mode: string | null; window: { hours: number[] } | null }[];
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
  return (
    <Phone>
      <AppBar mapHref={`/${locale}/map`} />
      <h1 className="display">{t("home.title")}</h1>
      <p className="body text-text-2">{t("home.subtitle")}</p>
      <a href={`/${locale}/search`} data-press className="press body mt-4 flex items-center rounded-[12px] border border-line shadow-[var(--shadow-card)]">
        {t("home.search")}
      </a>
      <section className="mt-6">
        <h2 className="section mb-2">
          {t("home.busyTop")}
          {loaded.data?.stale ? <span className="caption ml-2" style={{ color: "var(--stale-fg)" }}>{t("now.asOf", { time: "" })}</span> : null}
        </h2>
        {loaded.error ? <StateBox kind="error" onRetry={loaded.retry} /> : null}
        {loaded.loading ? <StateBox kind="skeleton" /> : null}
        <ol>
          {(loaded.data?.busy_top ?? []).map((row, index) => (
            <li key={row.id}>
              <a href={`/${locale}/p/${row.id}`} data-row className="row flex items-center justify-between">
                <span className="flex items-center gap-3">
                  <span className="text-[20px] font-extrabold text-text-3">{index + 1}</span>
                  <span>
                    <span className="body block font-semibold"><PlaceName name={row.name} nameEn={row.name_en} /></span>
                    <span className="caption text-text-3" lang="ko">{row.gu}</span>
                  </span>
                </span>
                <span className="caption text-right">
                  <span className="block">{t(`level.l${row.level}`)}</span>
                  <span className="block">{row.window ? formatStoredWindows([row.window], locale, suffix).join(", ") : t("home.noPickToday")}</span>
                </span>
              </a>
            </li>
          ))}
        </ol>
      </section>
      <section className="mt-6">
        <h2 className="section mb-2">{t("home.openQuiet")}</h2>
        {(loaded.data?.open_quiet.length ?? 0) === 0 && loaded.data ? <p className="body">{t("home.openQuietEmpty")}</p> : null}
        <div className="flex gap-4 overflow-x-auto">
          {(loaded.data?.open_quiet ?? []).map((row) => (
            <a key={row.id} href={`/${locale}/p/${row.id}/${kstNow().date}`} data-quiet={row.level} className="w-[232px] shrink-0 rounded-[16px] border border-line p-3 shadow-[var(--shadow-card)]">
              <span className="body block font-extrabold"><PlaceName name={row.name} nameEn={row.name_en} /></span>
              <span className="caption text-text-3" lang="ko">{row.gu}</span>
              <span className="caption mt-2 block">{row.window ? formatStoredWindows([row.window], locale, suffix).join(", ") : t("home.noPickToday")}</span>
            </a>
          ))}
        </div>
      </section>
      {favs.length ? (
        <section className="mt-6">
          <h2 className="section mb-2">{t("home.favorites")}</h2>
          <ul>
            {favs.map((row) => (
              <li key={row.id}>
                <a href={`/${locale}/p/${row.id}`} data-row className="row flex items-center">
                  <PlaceName name={row.name} nameEn={row.nameEn} />
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </Phone>
  );
}
