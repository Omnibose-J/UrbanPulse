"use client";

import { Search } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AppBar, KindChip, LevelDot, Phone, PlaceName, StateBox } from "@/components/ui";
import { useLoad } from "@/lib/use-load";

type Place = { id: string; tier: string; name: string; name_en: string | null; gu: string | null; category: string | null; serve_state: string; level: number | null };

export function SearchScreen() {
  const t = useTranslations();
  const locale = useLocale();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(q.trim()), 200);
    return () => window.clearTimeout(timer);
  }, [q]);
  const loaded = useLoad<{ places: Place[] }>(`/api/places?q=${encodeURIComponent(debounced)}`);
  return (
    <Phone>
      <AppBar backHref={`/${locale}`}>
        <label data-search className="flex h-11 items-center gap-2 rounded-[12px] bg-bg-soft px-3">
          <Search size={16} aria-hidden data-search-icon />
          <input
            autoFocus
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={t("home.search")}
            className="body min-w-0 flex-1 bg-transparent outline-none"
            aria-label={t("home.search")}
          />
        </label>
      </AppBar>
      {loaded.error ? <StateBox kind="error" onRetry={loaded.retry} /> : null}
      {loaded.loading ? <StateBox kind="skeleton" /> : null}
      {!q && loaded.data ? <h2 className="section mb-2 mt-4">{t("home.popular")}</h2> : null}
      {q && loaded.data && loaded.data.places.length === 0 ? <p className="body mt-4">{t("search.empty")}</p> : null}
      <ul>
        {(loaded.data?.places ?? []).map((place) => (
          <li key={place.id}>
            <Link prefetch={false} href={`/${locale}/p/${place.id}`} data-row className="row flex items-center justify-between">
              <span>
                <span className="body block font-semibold"><PlaceName name={place.name} nameEn={place.name_en} /></span>
                <span className="caption flex items-center gap-1.5 text-text-3">
                  <span lang="ko">{place.gu}</span>
                  <KindChip category={place.category} />
                </span>
              </span>
              {place.tier === "B" ? <span className="label">{t("badge.experimental")}</span> : place.level === null ? null : (
                <span data-search-status className="caption flex shrink-0 items-center gap-1.5 whitespace-nowrap font-semibold">
                  <LevelDot level={place.level} />
                  {t(`level.l${place.level}`)}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </Phone>
  );
}
