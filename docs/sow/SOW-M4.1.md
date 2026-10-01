# SOW-M4.1 — Screens match the design; today's picks are still ahead (local)

The M4 review opened the live screens at 390 × 844 on 2026-10-01 21:00 KST. The tests passed, but the screens do not yet look or read like `design/UrbanPulse_시안_v6.html` and `UrbanPulse_디자인명세서.md`, and two data rules produce answers a visitor cannot use. This SOW fixes those. Run it before SOW-MB.

## Files you may touch

`app/web/**` (not its `AGENTS.md`, `CLAUDE.md`, `README.md`), `app/engine/reco.py`, `app/engine/jobs/{forecast,collect}.py`, `app/engine/tests/**`, `docs/tracking/criteria-m4.1.md`, `docs/tracking/criteria-m5.md` (row A7 only), `docs/LLM_PROJECT_MAP.md`.
Read-only: specs, `design/`, `docs/sow/`, migrations, `analysis/`.

## What the review saw (each line is a defect to fix)

**Data rules**
1. At 21:00 the week screen's best time was "10월 1일 (목) 9~10시, 18~20시": hours already over. Home cards showed "19~20시" the same way.
2. In the first minutes of every hour the home "지금 가장 붐비는 곳" list is empty, because the current hour's `forecast_hourly` row is still `source = 'seoul'` until the next collect. The live smoke test fails in that window.

**① Home** — search field has no inner padding, icon or shadow (§5.8); TOP 5 shows a bare heading when empty; place cards lack the "● 한산해요" status, the "오늘 추천" label and the mini strip (§5.7); section spacing is not 24 / 8.

**③ Week** — the answer card shows a date and every merged window in `answer-time` size. It must show, top to bottom (§5.2): place name (`title`), the now line (dot + sentence + "14:30 기준"), divider, "이번 주 가장 좋은 때", **weekday + first range only** (`answer-time`), one reason sentence (§9.3), "이날 자세히 보기 ›". Week rows: the right column shows only the first range (72 px, right-aligned, one line); the best day's date cell says "추천" on `--go-soft` (present) but the row must not grow taller than the others; holiday names on `/en` are Korean (use `holidays.name_en`); the legend is hidden behind the dev badge on short pages (add bottom padding 24). A2 places show no condition field; they must (tolerance only).

**⑤ Day** — the answer card lacks the date line, the place name, the reason sentence and "이 시간도 추천해요 …" for the other ranges (§5.2). The back label "이번 주" wraps to two lines. The strip has no hour axis (9, 12, 15, 18, 21) (§5.5).

**⑦ Map** — every pin is stacked in the top-left corner on an empty background and the dev overlay reports an error: the map is not rendering and pins are not placed by coordinates. Date chips read "10-01" instead of weekday + date with "오늘" (§5.11). The slider uses the browser's blue. The bottom card lacks the hour sentence ("21시는 가도 괜찮아요."), the day's pick line and the "이 장소 자세히 보기 ›" button, and is partly off-screen.

**English** — "Thu, Oct 1 1 to 2 PM, 3 to 5 PM" overflows the answer card; after the fix above the card shows `Thu` + `1 to 2 PM` on separate lines.

## Steps

### 1 Today's windows come from the hours still ahead (engine)
`reco.build_row` gains `now_hour` (KST hour at build time; `None` for future dates). For today, window candidates are the `rating = 1` cells with `h >= now_hour`. Cells of earlier hours keep their rating and reason and are never `in_window`. No candidate left → `no_window = true` (alternatives then point to later dates). `forecast` and the collect-time refresh both pass it. `recommendation_log` is unaffected (it logs `today + 3`). Tests: at `now_hour = 21` a day whose only fit hours are 9 and 18 has `no_window`; at `now_hour = 18` hour 18 is still a candidate; invariants 8–10 hold.

### 2 "Now" is the latest measured hour (API)
In `/api/home` and the `now` object of `/api/places/[id]/week`: use, per place, the latest `forecast_hourly` row of today with `source = 'live'`; ignore it when it is more than one hour before the current hour (then the place has no "now" and is left out of both home lists). `stale` and `as_of` are unchanged. The live smoke test must pass at any minute of the hour.

### 3 Rebuild the five screens against the mockup
Open `design/UrbanPulse_시안_v6.html` beside each screen and fix every defect listed above. Structure, order, sizes and copy come from the design spec (§4, §5, §6, §9); the mockup settles what the spec does not say. Keep tokens only, messages only.
- Answer card time: weekday (or date on ⑤) on its own line above the range; one range only on ③; ⑤ lists the other ranges under `day.alsoRec`.
- Reason sentence from the first window's `crowd`, `act`, `act_level` (§9.3).
- Map: find and fix the rendering error first (report the console message and the cause). The container needs an explicit height and `maplibre-gl/dist/maplibre-gl.css`. Pins are MapLibre markers at `[lon, lat]`; initial view fits all pins. If the OpenFreeMap style cannot load, draw the pins over a plain `--map-land` background at correct positions and report it.
- Style the range input with tokens (`--ink` thumb, `--line` track).

### 4 Visual acceptance by screenshot
Add `e2e/visual.spec.ts`: at 390 × 844, live data, `ko` and `en`, save full-page screenshots of ①, ③ (one A1, one A2), ⑤ (a day with a window, a day without), ⑦ to `e2e/screenshots/live/`. Assertions per screen, measured from the DOM (not pixel diffs):
- ③: the answer card contains the place name, exactly one time range, and a reason sentence; its bottom edge is above 844; every week row is the same height; the right column text fits one line.
- ⑤: the answer card contains the date, the place name and a reason sentence; the strip has five axis labels; the back label is one line.
- ⑦: at least 20 pins; the bounding box of pin centres is wider than 150 px and taller than 150 px; a `canvas` with non-zero size exists or the plain-background mode is reported; the card's button is inside the viewport.
- ①: the search field's text starts at x ≥ 28; each place card contains a status dot and a 15-cell strip; with an empty TOP 5 the section shows the empty sentence (add key `home.busyTopEmpty`: "지금은 붐비는 곳이 없어요" / "Nothing is busy right now").
- No page logs a console error.
- No recommended range shown for today starts before the current KST hour.

### 5 Admin token (closes M5 row A7)
`ADMIN_TOKEN` is now set in `.env` (the designer generated it; never print it). Restart `npm run dev`, rerun the A7 command, fill the row.

## Acceptance (`docs/tracking/criteria-m4.1.md`, rows created before step 1)

| # | Criterion | Command |
|---|---|---|
| A1 | Today's picks are ahead | `python -m engine collect` → exit 0 or warn; `select count(*) from recommendations r cross join lateral jsonb_array_elements(r.windows) w where r.date = (now() at time zone 'Asia/Seoul')::date and r.state <> 'off' and (w->'hours'->>0)::int < extract(hour from now() at time zone 'Asia/Seoul')` → 0 |
| A2 | Home has a "now" at any minute | within the first 10 minutes of an hour: `/api/home` → `busy_top` has 5 rows (paste the time and the five levels) |
| A3 | Engine tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 |
| A4 | Web checks | `cd app/web; npm run lint; npm run build; npx playwright test` → exit 0 (paste the passed count) |
| A5 | Visual assertions | `npx playwright test e2e/visual.spec.ts` → exit 0; list the screenshot files written |
| A6 | Map renders | paste the console message that was the cause and the fix; pin bounding box size from the test |
| A7 | Admin guarded and reachable | M5 row A7 filled: no token 404, token 200 |
| A8 | No literal copy, no hex, no key | the three `git grep` commands of SOW-M4 rows A5, A6 and SOW-M3 row A10 → no match |

## Open facts to report

- The map error and its cause.
- Every place where the mockup and the spec disagreed and which one you followed.
- New message keys with both texts.
