"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { AttributionControl, LngLatBounds, Map as MapLibre, Marker, setWorkerUrl } from "maplibre-gl";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";

import { AppBar, ConditionSheet, HourSentence, PlaceName, StateBox } from "@/components/ui";
import { useLoad } from "@/lib/use-load";
import { formatShortDate, formatShortWeekday, formatStoredWindows, kstParts } from "@/lib/format";
import { addDays, initialHour, kstNow } from "@/lib/kst";
import { cellTone, toneColor, type HourCell } from "@/lib/strip";
import { readConditions, readStations, writeConditions, writeStations, type Purpose, type Tolerance } from "@/lib/storage";

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
type Drawn = Pin & { lat: number; lon: number; hours: HourCell[] };
type Holiday = { date: string; name: string; name_en: string | null };
type FlagRow = { tier: string; purpose: string; tolerance: string; state: string };

const FIT = { padding: { top: 64, bottom: 210, left: 48, right: 48 }, maxZoom: 12, duration: 0 };
const TONE_ORDER = { go: 0, ok: 1, bad: 2 } as const;

function toneAt(place: Drawn, clock: number) {
  const cell = place.hours.find((item) => item.h === clock);
  if (!cell) throw new Error(`no cell for hour ${clock}`);
  return cellTone(cell, place.strip_mode);
}

function pinSize(selected: boolean, zoom: number) {
  return selected ? 38 : zoom >= 12 ? 28 : 18;
}

export function MapScreen({ date, hour }: { date?: string; hour?: string }) {
  const t = useTranslations();
  const locale = useLocale() as "ko" | "en";
  const today = kstNow().date;
  const days = useMemo(() => Array.from({ length: 8 }, (_, index) => addDays(today, index)), [today]);
  const [day, setDay] = useState(date && days.includes(date) ? date : today);
  const [clock, setClock] = useState(() => initialHour(hour, kstNow().hour));
  const [stations, setStations] = useState(false);
  const [cond, setCond] = useState({ purpose: "sight" as Purpose, tolerance: "moderate" as Tolerance });
  const [selected, setSelected] = useState<string | null>(null);
  const [mapError, setMapError] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [sheet, setSheet] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const markers = useRef(new Map<string, { marker: Marker; button: HTMLButtonElement; label: HTMLSpanElement }>());
  const fitted = useRef("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCond(readConditions());
      setStations(readStations());
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  // The address always says which day and hour are shown, so a reload or a shared link shows the same map.
  useEffect(() => {
    window.history.replaceState(null, "", `/${locale}/map?date=${day}&hour=${clock}`);
  }, [day, clock, locale]);

  const loaded = useLoad<{ places: Pin[]; holidays: Holiday[] }>(
    `/api/map?date=${day}&tolerance=${cond.tolerance}&purpose=${cond.purpose}&stations=${stations ? 1 : 0}`,
  );
  const flags = useLoad<{ rows: FlagRow[] }>("/api/flags");
  // A switched-off combination is not a verdict about the place, so it gets no pin.
  const places = useMemo(
    () => (loaded.data ? loaded.data.places.filter((place): place is Drawn => place.state !== "off" && place.hours !== null && place.lat !== null && place.lon !== null) : []),
    [loaded.data],
  );
  const holidays = loaded.data ? loaded.data.holidays : [];
  const ordered = useMemo(
    () => [...places].sort((x, y) => TONE_ORDER[toneAt(x, clock)] - TONE_ORDER[toneAt(y, clock)] || x.name.localeCompare(y.name, "ko")),
    [places, clock],
  );
  const current = places.find((place) => place.id === selected) ?? ordered[0];
  const activeId = current?.id;
  const nameOf = (place: Pin) => (locale === "en" && place.name_en ? place.name_en : place.name);

  useEffect(() => {
    const node = box.current;
    if (!node || mapError) return;
    setWorkerUrl(new URL("/vendor/maplibre/maplibre-gl-worker.mjs", window.location.origin).href);
    const map = new MapLibre({
      container: node,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [126.978, 37.566],
      zoom: 11,
      attributionControl: false,
    });
    map.addControl(new AttributionControl({ compact: true }), "top-right");
    mapRef.current = map;
    setMounted(true);
    const drawn = markers.current;
    // A tile that fails to load is not fatal. A style or worker failure before the first render is.
    const onError = (event: { sourceId?: string; tile?: unknown }) => {
      if (event.sourceId || event.tile || map.loaded()) return;
      setMapError(true);
    };
    const onZoom = () => {
      const zoom = map.getZoom();
      for (const { button, label } of drawn.values()) {
        const on = button.dataset.selected === "1";
        const size = pinSize(on, zoom);
        button.dataset.pinSize = String(size);
        button.style.width = `${size}px`;
        button.style.height = `${size}px`;
        label.style.display = on || zoom >= 13 ? "block" : "none";
      }
    };
    map.once("load", () => node.setAttribute("data-map-ready", "1"));
    map.on("error", onError as never);
    map.on("zoom", onZoom);
    return () => {
      setMounted(false);
      node.removeAttribute("data-map-ready");
      for (const { marker } of drawn.values()) marker.remove();
      drawn.clear();
      map.remove();
      mapRef.current = null;
    };
  }, [mapError]);

  // Markers are created when the set of places changes, not on every slider step.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mounted || mapError) return;
    const drawn = markers.current;
    for (const { marker } of drawn.values()) marker.remove();
    drawn.clear();
    const bounds = new LngLatBounds();
    for (const place of places) {
      const wrap = document.createElement("div");
      wrap.style.display = "flex";
      wrap.style.flexDirection = "column";
      wrap.style.alignItems = "center";
      wrap.style.gap = "4px";
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.pin = place.id;
      button.style.borderRadius = "999px";
      button.style.border = "3px solid var(--on-ink)";
      button.style.padding = "0";
      button.addEventListener("click", () => setSelected(place.id));
      const label = document.createElement("span");
      label.dataset.pinLabel = "1";
      const shown = locale === "en" && place.name_en ? place.name_en : place.name;
      label.textContent = place.tier === "B" ? t("map.station", { name: shown }) : shown;
      button.setAttribute("aria-label", label.textContent);
      if (shown === place.name) label.lang = "ko";
      label.style.fontSize = "11px";
      label.style.fontWeight = "700";
      label.style.background = "rgb(255 255 255 / 92%)";
      label.style.borderRadius = "6px";
      label.style.padding = "2px 6px";
      label.style.whiteSpace = "nowrap";
      wrap.append(button, label);
      const marker = new Marker({ element: wrap, anchor: "center" }).setLngLat([place.lon, place.lat]).addTo(map);
      drawn.set(place.id, { marker, button, label });
      bounds.extend([place.lon, place.lat]);
    }
    // The camera is set once per set of places, and does not wait for the style, so a later load cannot undo a zoom.
    const key = places.map((place) => place.id).join(",");
    if (key && key !== fitted.current) {
      map.fitBounds(bounds, FIT);
      fitted.current = key;
    }
  }, [places, mounted, mapError, locale, t]);

  // Hour and selection only recolour and resize what is already drawn.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mounted || mapError) return;
    const zoom = map.getZoom();
    for (const place of places) {
      const entry = markers.current.get(place.id);
      if (!entry) continue;
      const on = place.id === activeId;
      const tone = toneAt(place, clock);
      const size = pinSize(on, zoom);
      entry.button.dataset.selected = on ? "1" : "0";
      entry.button.dataset.tone = tone;
      entry.button.dataset.pinSize = String(size);
      entry.button.style.width = `${size}px`;
      entry.button.style.height = `${size}px`;
      entry.button.style.background = toneColor(tone, true);
      entry.button.style.boxShadow = on ? "0 0 0 3px var(--ink)" : "0 2px 6px rgb(15 24 34 / 28%)";
      entry.label.style.display = on || zoom >= 13 ? "block" : "none";
    }
  }, [places, clock, activeId, mounted, mapError]);

  const weekdays = t.raw("time.weekdays") as string[];
  const suffix = t("time.hour");
  const clockCell = current ? current.hours.find((cell) => cell.h === clock) : undefined;
  const dateLabel = day === today ? t("time.today") : formatShortDate(day);
  const pickLine = (place: Drawn) => {
    const first = formatStoredWindows(place.windows, locale, suffix)[0];
    if (first) return t("map.dayPick", { date: dateLabel, time: first });
    return day === today ? t("home.noPickToday") : `${dateLabel} ${t("week.none")}`;
  };
  const detailHref = (place: Pin) => `/${locale}/p/${place.id}/${day}?from=map&hour=${clock}`;
  // The sheet on the map is not about one place: an A1 option is ready when any A1 place serves it today.
  const combos = flags.data
    ? flags.data.rows.filter((row) => row.tier === "A1" && row.state !== "off").map((row) => ({ purpose: row.purpose, tolerance: row.tolerance, state: "on" }))
    : [];
  const failed = loaded.error || mapError;
  const card = current && clockCell ? (
    <a
      data-map-card
      href={detailHref(current)}
      className="absolute bottom-16 left-4 right-4 z-10 flex flex-col gap-3 rounded-[16px] bg-bg p-4 shadow-[0_8px_24px_rgb(15_24_34/18%)] min-[1024px]:hidden"
    >
      <span className="text-[18px] font-extrabold"><PlaceName name={current.name} nameEn={current.name_en} /></span>
      <span className="text-[14px] text-text-2">
        <b className="text-text" data-hour-sentence>
          <HourSentence mode={current.strip_mode} hour={clock} cell={clockCell} locale={locale} tier={current.tier} purpose={cond.purpose} />
        </b>
      </span>
      <span className="text-[14px] text-text-2">{pickLine(current)}</span>
      <span data-map-action className="press flex items-center justify-between rounded-[12px] px-4 font-semibold" style={{ background: "var(--go-soft)", color: "var(--go-text)" }}>
        {t("map.seePlace")} ›
      </span>
    </a>
  ) : null;

  return (
    <div className="flex min-h-screen flex-col min-[1024px]:grid min-[1024px]:grid-cols-[1fr_400px]">
      <div className="flex min-h-screen flex-col">
        <div className="px-4">
          <AppBar backHref={`/${locale}`} title={t("map.title")} onCond={flags.data ? () => setSheet(true) : undefined} />
          <div className="flex gap-1.5 overflow-x-auto pb-2">
            {days.map((item) => {
              const holiday = holidays.find((row) => row.date === item);
              const holidayName = holiday ? (locale === "en" && holiday.name_en ? holiday.name_en : holiday.name) : null;
              const label = item === today ? t("time.today") : `${formatShortWeekday(item, weekdays, t("time.today"), today)} ${kstParts(item).day}`;
              const on = item === day;
              return (
                <button
                  key={item}
                  type="button"
                  data-day={item}
                  aria-pressed={on}
                  className="flex h-10 shrink-0 flex-col items-center justify-center rounded-[12px] px-3 text-[14px] font-semibold leading-none"
                  style={{ background: on ? "var(--ink)" : "var(--bg-soft)", color: on ? "var(--on-ink)" : "var(--text-2)" }}
                  onClick={() => setDay(item)}
                >
                  {label}
                  {holidayName ? <small className="text-[10px] font-semibold" style={{ color: "var(--hol)" }} lang={holidayName === holiday?.name && locale === "en" ? "ko" : undefined}>{holidayName}</small> : null}
                </button>
              );
            })}
          </div>
          <label className="flex h-12 items-center gap-3">
            <span className="w-[52px] text-[20px] font-extrabold">{t("map.hourNow", { hour: String(clock) })}</span>
            <input data-hour className="min-w-0 flex-1" type="range" min={9} max={23} value={clock} onChange={(event) => setClock(Number(event.target.value))} />
          </label>
        </div>
        {failed ? (
          <StateBox kind="error" onRetry={() => { setMapError(false); loaded.retry(); }} />
        ) : null}
        <div ref={box} data-map className="relative min-h-[420px] flex-1" style={{ height: "calc(100dvh - 220px)", background: "var(--map-land)", display: failed ? "none" : undefined }}>
          <div className="absolute left-4 top-3 z-10 flex items-center gap-2 rounded-[var(--r-pill)] bg-bg px-3 py-1.5 text-[11px] font-semibold text-text-2 shadow-[var(--shadow-card)]">
            {(current?.strip_mode === "two_step" ? (["win", "1", "0"] as const) : (["win"] as const)).map((key) => (
              <span key={key} data-legend className="inline-flex items-center gap-1">
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
          {failed ? null : card}
        </div>
      </div>
      <aside data-map-list className="hidden max-h-screen overflow-y-auto border-l border-line px-4 min-[1024px]:block">
        <ul>
          {ordered.map((place) => (
            <li key={place.id} className="row flex items-center justify-between gap-3" data-list-row={place.id} data-tone={toneAt(place, clock)}>
              <button
                type="button"
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                aria-pressed={place.id === activeId}
                onClick={() => {
                  setSelected(place.id);
                  mapRef.current?.flyTo({ center: [place.lon, place.lat], zoom: Math.max(mapRef.current.getZoom(), 13) });
                }}
              >
                <i className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: toneColor(toneAt(place, clock), true) }} />
                <span className="min-w-0">
                  <span className="body block truncate font-semibold">
                    {place.tier === "B" ? t("map.station", { name: nameOf(place) }) : <PlaceName name={place.name} nameEn={place.name_en} />}
                  </span>
                  <span className="caption block text-text-3">{pickLine(place)}</span>
                </span>
              </button>
              <a href={detailHref(place)} className="caption shrink-0 font-semibold" style={{ color: "var(--go-text)" }}>
                {t("map.seePlace")} ›
              </a>
            </li>
          ))}
        </ul>
      </aside>
      <ConditionSheet
        open={sheet}
        tier="A1"
        purpose={cond.purpose}
        tolerance={cond.tolerance}
        combos={combos}
        onClose={() => setSheet(false)}
        onApply={(next) => {
          writeConditions(next);
          setCond(next);
          setSheet(false);
        }}
      />
    </div>
  );
}
