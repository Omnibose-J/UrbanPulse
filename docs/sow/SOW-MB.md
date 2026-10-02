# SOW-MB — Tier B station areas, experimental (local)

Work unit W9 (`docs/specs/UrbanPulse_구현설계서.md` §4.3), cut to what the frozen research files support. Station areas outside the 121 places get a usual-flow profile and recommendations, reachable by search and by the map toggle only. **Run this last**; nothing else depends on it.

Deferred, not in this SOW: the holiday adjustment with `ratio_v1b`, `ratio_v1b` for A1/A2 places outside `place_index` (they stay `preparing`), monthly refresh from the ridership API. On holiday dates tier B rows are off.

## Depends on

SOW-M3 (recommendation builder, flags), SOW-M4 (tier B UI already built on mocked data).

## Files you may touch

Create: `app/engine/jobs/tier_b.py`, `app/engine/tierb/{__init__,stations,flows,profile}.py`, `app/engine/tests/**`, `docs/tracking/criteria-mb.md`.
Edit: `app/engine/__main__.py` (wire `tier_b [--check]`), `app/engine/jobs/forecast.py`, `app/engine/reco.py` and `app/engine/flags.py` (group `b`), `app/engine/config/feature_flags.yaml` (three lines below), `pyproject.toml` (`engine.tierb` package), `docs/LLM_PROJECT_MAP.md`.
Read-only inputs (never rewrite): `analysis/data/subway/{stations.csv, day_153.csv, day_154.csv, day_155.csv, hourly_month_2026.csv}`, `analysis/data/lp_oa/{oa_202605.zip, oa_202606.zip}`, `analysis/data/poi/oa2016.geojson`, the 121-place shapefile and `dong.geojson` that `load_places` reads. Reference code: `analysis/scripts/exp_e1_tier_b.py`, `eval_station_fill.py` (`norm`), `eval_fill_gap_oa.py` (`read_oa`), `rejudge.py` (`e1()`).
`geopandas` is needed by this job only, like `load_places`; do not add it to `app/engine/requirements.txt`.

## Steps

### 1 Port the flows — `app/engine/tierb/flows.py`
Port number for number from `exp_e1_tier_b.py`: `norm`, `buffers` (250 m circles in EPSG:5179, dissolved per station name), `oa_flow` (area-weighted 집계구 population, months 202605 and 202606), `st_flow` (daily totals from the three `day_*.csv` × monthly hourly share of 202605–202606, share smoothed as mean of bins H−1 and H), `weekly` (holidays excluded, day type `wk`/`sat`/`sun` × hour mean), `dtype_of`. Holidays for the exclusion come from the `holidays` table.

### 2 Prove the port — `python -m engine tier_b --check`
Reproduce `e1()` of `rejudge.py` on the 44 station-named live places with the selection threshold 0.0, live truth 2026-08-01…09-29 on the research grid (the `--grid research` helper of SOW-M2). Research values (`analysis/data/rejudge.csv`): median weekly-profile correlation 0.84, share with r < 0.3 6.67 %, three-level agreement 62.28 %. Tolerance ±0.02, ±3 %p, ±2 %p. Writes nothing to the database. Outside tolerance → record the row as FAIL, do not adjust, and still complete steps 3–6 (tier B stays `experimental`; the designer decides).

### 3 Stations as places — `app/engine/tierb/stations.py`
- One place per normalised station name in `stations.csv` (coordinates = mean of its rows; `station_codes` = its `BLDN_ID`s).
- Drop a station when at least half of its dissolved 250 m area lies inside the union of the 121 place polygons.
- `id = 'STN' + zero-padded 3-digit index` in normalised-name order; `name` = the station name ending in `역`; `name_en` null (the file has no English name; report it); `tier = 'B'`; `serve_state = 'experimental'`; `category = '역세권'`; `gu` by the same dong lookup as `load_places`; `lat`, `lon`; `geom` = the circle as GeoJSON in EPSG:4326.
- Upsert; a second run changes 0 rows. A1/A2 rows are never touched.

### 4 Profile — `app/engine/tierb/profile.py`, job `python -m engine tier_b`
For every tier B place: 집계구 flow and ridership flow as in step 1; correlation of the two weekly vectors; use the ridership flow when the correlation is below 0.0, else the 집계구 flow (no ridership → 집계구). `rel` = chosen weekly value ÷ its 0.9 quantile over hours 9…23. Replace `tier_b_profile` (`day_type` `weekday`/`sat`/`sun`, hours 0…23) in one transaction. A station with no 집계구 overlap gets no profile and is reported. `job_runs.detail` = `{"places", "profiles", "used_ridership", "no_profile"}`.

### 5 Forecast and recommendations for tier B — `forecast` job
- `forecast_hourly` for B places with a profile, today…today+7: `rel` from the profile for the date's weekday / Saturday / Sunday, `level` = 0 when `rel < 0.5`, 1 when `< 0.9`, else 2; `pop` null; `source = 'profile'`; `ready = true`; `stale = false`; `a_*` null. No overlay, no `forecast_log`.
- Flag file, group `b`: `{group: b, purpose: none, tolerance: calm|moderate|busy_ok, state: on, strip: windows_only}` (three lines).
- `reco.build_row` for group `b`: purpose `none`; open hours 9…22 (hour 23 → `outside_hours`); activity 1; `act` null; `crowd` 0…2; same scores, cells, windows. Any date in `holidays` → `off`, `off_reason = 'unverified'` (the holiday adjustment is not built). No `alt_places`. No `recommendation_log` rows (no live truth to score).
- B places without a profile get no `forecast_hourly` and no `recommendations` rows.

### 6 Tests
- `test_tierb_flows.py`: `norm`; share smoothing on a hand-built 24-bin vector; `weekly` drops holiday dates; selection rule at −0.01 / 0.0 / 0.01.
- `test_tierb_stations.py`: overlap ≥ 50 % dropped, 49 % kept (synthetic polygons); stable ids; second upsert changes nothing.
- `test_tierb_levels.py`: `rel` 0.49 / 0.5 / 0.89 / 0.9 → 0 / 1 / 1 / 2.
- `test_reco_b.py`: hour 23 `outside_hours`; `act` null (invariant 6); holiday → off `unverified`; `moderate` never `too_busy` (levels stop at 2).

## Acceptance (`docs/tracking/criteria-mb.md`, rows created before step 1)

| # | Criterion | Command |
|---|---|---|
| A1 | Port reproduces E1 | `python -m engine tier_b --check` → the three figures pasted next to 0.84 / 6.67 % / 62.28 % with PASS or FAIL per tolerance |
| A2 | Stations loaded | `python -m engine tier_b` → exit 0; `select count(*) from places where tier = 'B'` pasted with the dropped-by-overlap count; `select tier, serve_state, count(*) from places where tier <> 'B' group by 1,2` identical before and after |
| A3 | Profiles | `select count(distinct place_id), count(*) from tier_b_profile` → rows = places × 3 × 24; `detail` pasted |
| A4 | B rows | `python -m engine forecast` → exit 0; `select state, off_reason, count(*) from recommendations r join places p on p.id = r.place_id where p.tier = 'B' group by 1,2`; no B cell with non-null `act`; no B cell with `crowd = 3` |
| A5 | Reachable by search and toggle only | with `npm run dev`: `/api/places?q=` (empty) has no tier B row; `/api/places?q=<a station name>` has one; `/api/map?...&stations=0` has none; `&stations=1` has some; `/api/home` has none |
| A6 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 |
| A7 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match |

## Open facts to report

- Station count, dropped count, stations without a profile, how many use the ridership flow.
- The `--check` table and, if it failed, which figure and by how much.
- Duration of `tier_b` and the added duration of `forecast`.
- That `name_en` is null for every station (English UI shows the Korean name with `lang="ko"`).
