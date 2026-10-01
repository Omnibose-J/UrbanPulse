"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { AttributionControl, LngLatBounds, Map, Marker, setWorkerUrl } from "maplibre-gl";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { AppBar } from "@/components/ui";
import { formatShortDate, formatShortWeekday, formatStoredWindows, kstParts } from "@/lib/format";
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

type Holiday = { date: string; name: string; name_en: string | null };

function placeTone(place: Pin, clock: number) {
  const cell = place.hours?.find((item) => item.h === clock);
  return cell ? cellTone(cell, place.strip_mode) : "bad";
}

export function MapScreen({ date, hour }: { date?: string; hour?: string }) {
  const t = useTranslations();
  const locale = useLocale() as "ko" | "en";
  const today = kstNow().date;
  const [day, setDay] = useState(date || today);
  const [clock, setClock] = useState(Number(hour || kstNow().hour));
  const [stations, setStations] = useState(false);
  const [cond, setCond] = useState({ purpose: "sight" as Purpose, tolerance: "moderate" as Tolerance });
  const [places, setPlaces] = useState<Pin[]>([]);
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [styleFailed, setStyleFailed] = useState(false);
  const [mounted, setMounted] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const fitted = useRef("");
  const boundsRef = useRef<LngLatBounds | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCond(readConditions());
      setStations(readStations());
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    let cancel = false;
    fetch(`/api/map?date=${day}&tolerance=${cond.tolerance}&purpose=${cond.purpose}&stations=${stations ? 1 : 0}`)
      .then((response) => response.json())
      .then((body: { places: Pin[]; holidays?: Holiday[] }) => {
        if (cancel) return;
        setPlaces(body.places ?? []);
        setHolidays(body.holidays ?? []);
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
    setWorkerUrl(new URL("/vendor/maplibre/maplibre-gl-worker.mjs", window.location.origin).href);
    const map = new Map({
      container: node,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [126.978, 37.566],
      zoom: 11,
      attributionControl: false,
    });
    map.addControl(new AttributionControl({ compact: true }), "top-right");
    mapRef.current = map;
    setMounted(true);
    const onLoad = () => {
      const bounds = boundsRef.current;
      if (bounds && !bounds.isEmpty()) {
        map.fitBounds(bounds, { padding: { top: 64, bottom: 210, left: 48, right: 48 }, maxZoom: 12, duration: 0 });
      }
    };
    const onError = (event: { error: { message: string } }) => {
      const message = event.error.message ?? "";
      if (!map.loaded() && /Worker failed to load|Failed to load style/i.test(message)) setStyleFailed(true);
    };
    map.on("load", onLoad);
    map.on("error", onError);
    return () => {
      setMounted(false);
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, [styleFailed]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mounted || styleFailed) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    const bounds = new LngLatBounds();
    const active = selected ?? places[0]?.id;
    for (const place of places) {
      if (place.lon == null || place.lat == null) continue;
      const tone = placeTone(place, clock);
      const on = place.id === active;
      const wrap = document.createElement("div");
      wrap.style.display = "flex";
      wrap.style.flexDirection = "column";
      wrap.style.alignItems = "center";
      wrap.style.gap = "4px";
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.pin = "";
      button.dataset.tone = tone;
      button.setAttribute("aria-label", place.name);
      const size = on ? 38 : 28;
      button.style.width = `${size}px`;
      button.style.height = `${size}px`;
      button.style.borderRadius = "999px";
      button.style.border = "3px solid var(--on-ink)";
      button.style.background = toneColor(tone, true);
      button.style.boxShadow = on ? "0 0 0 3px var(--ink)" : "0 2px 6px rgb(15 24 34 / 28%)";
      button.style.padding = "0";
      button.addEventListener("click", () => setSelected(place.id));
      const label = document.createElement("span");
      label.dataset.pinLabel = "1";
      label.dataset.selected = on ? "1" : "0";
      label.textContent = place.name;
      label.lang = "ko";
      label.style.fontSize = "11px";
      label.style.fontWeight = "700";
      label.style.background = "rgb(255 255 255 / 92%)";
      label.style.borderRadius = "6px";
      label.style.padding = "2px 6px";
      label.style.whiteSpace = "nowrap";
      label.style.display = on || map.getZoom() >= 13 ? "block" : "none";
      wrap.append(button, label);
      const marker = new Marker({ element: wrap, anchor: "center" }).setLngLat([place.lon, place.lat]).addTo(map);
      markersRef.current.push(marker);
      bounds.extend([place.lon, place.lat]);
    }
    boundsRef.current = bounds;
    const key = places.map((place) => `${place.id}:${place.lon}:${place.lat}`).join(",");
    if (map.loaded() && key && key !== fitted.current && !bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: { top: 64, bottom: 210, left: 48, right: 48 }, maxZoom: 12, duration: 0 });
      fitted.current = key;
    }
    const onZoom = () => {
      const showAll = map.getZoom() >= 13;
      map.getContainer().querySelectorAll<HTMLElement>("[data-pin-label]").forEach((node) => {
        node.style.display = showAll || node.dataset.selected === "1" ? "block" : "none";
      });
    };
    map.on("zoom", onZoom);
    return () => {
      map.off("zoom", onZoom);
    };
  }, [places, clock, selected, mounted, styleFailed]);

  const current = places.find((place) => place.id === selected) ?? places[0];
  const days = Array.from({ length: 8 }, (_, index) => addDays(today, index));
  const weekdays = t.raw("time.weekdays") as string[];
  const suffix = t("time.hour");
  const coords = places.filter((place) => place.lon != null && place.lat != null);
  const minLon = Math.min(...coords.map((place) => place.lon ?? 0));
  const maxLon = Math.max(...coords.map((place) => place.lon ?? 0));
  const minLat = Math.min(...coords.map((place) => place.lat ?? 0));
  const maxLat = Math.max(...coords.map((place) => place.lat ?? 0));
  const spanLon = Math.max(maxLon - minLon, 0.05);
  const spanLat = Math.max(maxLat - minLat, 0.05);
  const tone = current ? placeTone(current, clock) : "bad";
  const verdict = tone === "go" ? t("reason.window") : tone === "ok" ? t("reason.ok") : t("reason.avoid");
  const pick = current ? formatStoredWindows(current.windows, locale, suffix)[0] : "";
  const dateLabel = day === today ? t("time.today") : formatShortDate(day);
  const card = current ? (
    <a
      data-map-card
      href={`/${locale}/p/${current.id}/${day}?from=map&hour=${clock}`}
      className="absolute bottom-16 left-4 right-4 z-10 flex flex-col gap-3 rounded-[16px] bg-bg p-4 shadow-[0_8px_24px_rgb(15_24_34/18%)] min-[1024px]:hidden"
    >
      <span className="text-[18px] font-extrabold" lang="ko">{current.name}</span>
      <span className="text-[14px] text-text-2">
        <b className="text-text">{t("map.hourLine", { hour: String(clock), verdict })}</b>
      </span>
      <span className="text-[14px] text-text-2">
        {pick ? t("map.dayPick", { date: dateLabel, time: pick }) : day === today ? t("home.noPickToday") : `${dateLabel} ${t("week.none")}`}
      </span>
      <span data-map-action className="press flex items-center justify-between rounded-[12px] px-4 font-semibold" style={{ background: "var(--go-soft)", color: "var(--go-text)" }}>
        {t("map.seePlace")} ›
      </span>
    </a>
  ) : null;

  return (
    <div className="flex min-h-screen flex-col min-[1024px]:grid min-[1024px]:grid-cols-[1fr_400px]">
      <div className="flex min-h-screen flex-col">
        <div className="px-4">
          <AppBar backHref={`/${locale}`} title={t("map.title")} />
          <div className="flex gap-1.5 overflow-x-auto pb-2">
            {days.map((item) => {
              const holiday = holidays.find((row) => row.date === item);
              const holidayName = holiday ? (locale === "en" ? holiday.name_en || holiday.name : holiday.name) : null;
              const label = item === today ? t("time.today") : `${formatShortWeekday(item, weekdays, t("time.today"), today)} ${kstParts(item).day}`;
              const on = item === day;
              return (
                <button
                  key={item}
                  type="button"
                  className="flex h-10 shrink-0 flex-col items-center justify-center rounded-[12px] px-3 text-[14px] font-semibold leading-none"
                  style={{ background: on ? "var(--ink)" : "var(--bg-soft)", color: on ? "var(--on-ink)" : "var(--text-2)" }}
                  onClick={() => setDay(item)}
                >
                  {label}
                  {holidayName ? <small className="text-[10px] font-semibold" style={{ color: "var(--hol)" }} lang={locale === "en" && !holiday?.name_en ? "ko" : undefined}>{holidayName}</small> : null}
                </button>
              );
            })}
          </div>
          <label className="flex h-12 items-center gap-3">
            <span className="w-[52px] text-[20px] font-extrabold">{t("map.hourNow", { hour: String(Math.min(23, Math.max(9, clock))) })}</span>
            <input data-hour className="min-w-0 flex-1" type="range" min={9} max={23} value={Math.min(23, Math.max(9, clock))} onChange={(event) => setClock(Number(event.target.value))} />
          </label>
        </div>
        <div ref={box} data-map className="relative min-h-[420px] flex-1" style={{ height: "calc(100dvh - 220px)", background: "var(--map-land)" }}>
          <div className="absolute left-4 top-3 z-10 flex items-center gap-2 rounded-[var(--r-pill)] bg-bg px-3 py-1.5 text-[11px] font-semibold text-text-2 shadow-[var(--shadow-card)]">
            {(["win", "1", "0"] as const).map((key) => (
              <span key={key} className="inline-flex items-center gap-1">
                <i className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: key === "win" ? "var(--go)" : key === "1" ? "var(--ok)" : "var(--bad-pin)" }} />
                {t(`rate.${key}`)}
              </span>
            ))}
            <label className="inline-flex items-center gap-1 border-l border-line pl-2">
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
          {styleFailed
            ? places.map((place) => {
                if (place.lon == null || place.lat == null) return null;
                const pinTone = placeTone(place, clock);
                const left = 12 + ((place.lon - minLon) / spanLon) * 76;
                const top = 8 + ((maxLat - place.lat) / spanLat) * 58;
                return (
                  <button
                    key={place.id}
                    type="button"
                    data-pin
                    data-tone={pinTone}
                    className="absolute h-7 w-7 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px]"
                    style={{ background: toneColor(pinTone, true), borderColor: "var(--on-ink)", left: `${left}%`, top: `${top}%` }}
                    onClick={() => setSelected(place.id)}
                  />
                );
              })
            : null}
          {card}
        </div>
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
