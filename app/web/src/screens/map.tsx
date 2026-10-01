"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { AppBar } from "@/components/ui";
import { formatStoredWindows } from "@/lib/format";
import { addDays, kstNow } from "@/lib/kst";
import { cellTone, toneColor, type HourCell } from "@/lib/strip";
import { readConditions, readStations, writeStations, type Purpose, type Tolerance } from "@/lib/storage";

type Pin = {
  id: string;
  tier: string;
  name: string;
  name_en: string | null;
  lat: number | null;
  lon: number | null;
  state: string;
  windows: { hours: number[] }[] | null;
  hours: HourCell[] | null;
  strip_mode: string | null;
};

export function MapScreen({ date, hour }: { date?: string; hour?: string }) {
  const t = useTranslations();
  const locale = useLocale();
  const today = kstNow().date;
  const [day, setDay] = useState(date || today);
  const [clock, setClock] = useState(Number(hour || kstNow().hour));
  const [stations, setStations] = useState(false);
  const [cond, setCond] = useState({ purpose: "sight" as Purpose, tolerance: "moderate" as Tolerance });
  const [places, setPlaces] = useState<Pin[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [styleFailed, setStyleFailed] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCond(readConditions());
      setStations(readStations());
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    let cancel = false;
    const purpose = cond.purpose;
    fetch(`/api/map?date=${day}&tolerance=${cond.tolerance}&purpose=${purpose}&stations=${stations ? 1 : 0}`)
      .then((response) => response.json())
      .then((body: { places: Pin[] }) => {
        if (cancel) return;
        setPlaces(body.places ?? []);
        setSelected((current) => current ?? body.places?.[0]?.id ?? null);
      })
      .catch(() => {
        if (!cancel) setPlaces([]);
      });
    return () => {
      cancel = true;
    };
  }, [day, cond.purpose, cond.tolerance, stations]);

  useEffect(() => {
    const node = box.current;
    if (!node || styleFailed) return;
    let map: { remove: () => void } | null = null;
    let dead = false;
    import("maplibre-gl").then((mod) => {
      if (dead) return;
      const next = new mod.Map({
        container: node,
        style: "https://tiles.openfreemap.org/styles/positron",
        center: [126.978, 37.566],
        zoom: 11,
      });
      next.on("error", () => setStyleFailed(true));
      map = next;
    }).catch(() => setStyleFailed(true));
    return () => {
      dead = true;
      map?.remove();
    };
  }, [styleFailed]);

  const current = places.find((place) => place.id === selected) ?? places[0];
  const days = Array.from({ length: 8 }, (_, index) => addDays(today, index));
  return (
    <div className="flex min-h-screen flex-col min-[1024px]:grid min-[1024px]:grid-cols-[1fr_400px]">
      <div className="flex min-h-screen flex-col">
        <div className="px-4">
          <AppBar backHref={`/${locale}`} />
          <h1 className="section">{t("map.title")}</h1>
          <div className="mt-2 flex gap-2 overflow-x-auto">
            {days.map((item) => (
              <button key={item} type="button" className="h-10 shrink-0 rounded-[12px] px-3" style={{ background: item === day ? "var(--ink)" : "var(--bg-soft)", color: item === day ? "var(--on-ink)" : "var(--text)" }} onClick={() => setDay(item)}>
                {item.slice(5)}
              </button>
            ))}
          </div>
          <label className="press flex items-center justify-between">
            <span className="text-[20px] font-extrabold">{t("map.hourNow", { hour: String(clock) })}</span>
            <input data-hour type="range" min={9} max={23} value={Math.min(23, Math.max(9, clock))} onChange={(event) => setClock(Number(event.target.value))} />
          </label>
          <label className="caption flex items-center gap-2 text-text-3">
            <input
              type="checkbox"
              checked={stations}
              onChange={(event) => {
                writeStations(event.target.checked);
                setStations(event.target.checked);
              }}
            />
            {t("map.includeStations")}
          </label>
        </div>
        <div ref={box} data-map className="relative min-h-[420px] flex-1" style={{ background: "var(--map-land)" }}>
          {places.map((place) => {
            const cell = place.hours?.find((item) => item.h === clock);
            const tone = cell ? cellTone(cell, place.strip_mode) : "bad";
            return (
              <button
                key={place.id}
                type="button"
                data-pin
                data-tone={tone}
                className="absolute h-7 w-7 rounded-full border-[3px] border-white"
                style={{ background: toneColor(tone, true), left: `${((place.lon ?? 127) - 126.7) * 40}%`, top: `${(37.8 - (place.lat ?? 37.5)) * 40}%` }}
                onClick={() => setSelected(place.id)}
              />
            );
          })}
        </div>
        {current ? (
          <a data-map-card href={`/${locale}/p/${current.id}/${day}?from=map&hour=${clock}`} className="m-4 block rounded-[16px] border border-line p-4">
            <span className="body font-extrabold" lang="ko">{current.name}</span>
            <span className="caption mt-1 block">
              {formatStoredWindows(current.windows, locale === "en" ? "en" : "ko", t("time.hour")).join(", ")}
            </span>
            <span className="caption mt-1 block">{t("map.seePlace")}</span>
          </a>
        ) : null}
      </div>
      <aside className="hidden min-[1024px]:block">
        <ul>
          {places.map((place) => (
            <li key={place.id}>
              <button type="button" className="row w-full text-left" onClick={() => setSelected(place.id)}>
                <span lang="ko">{place.name}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
