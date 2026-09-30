# SOW-M1 — Places, holidays, backfill, collect (local)

Work units W2, W4, W3a, W3 of the build contract (`UrbanPulse_구현설계서.md` §2, §4.0, §4.1, §8). Everything runs on the laptop against the local Supabase stack from M0. No cloud. When M1 is done the database holds every A1/A2 place, the 2023–2027 holidays, the 2026-05-11→ history, and `collect` adds a fresh snapshot every 30 minutes.

## Goal

1. `places` holds the 121 Seoul places with tier, geometry, centroid, category, gu, `foreign_heavy`, palace `open_hours`, `serve_state`.
2. `holidays` holds 2023-01-01 … 2027-12-31 from the KASI API with `kind` and English names.
3. `backfill` loads the research extracts (`analysis/data/*.csv`) into `live_obs` and `commerce_obs`, idempotently.
4. `collect` calls the Seoul citydata API for all 121 places, stores raw snapshots under `RAW_DIR`, upserts `live_obs`, `commerce_obs`, `city_fcst`, and is registered with Windows Task Scheduler every 30 minutes.

## Inputs from the user (record which were provided, never the values)

| Input | Notes |
|---|---|
| Local stack running | `cd app; supabase start` (ports 553xx). `.env` already holds `DATABASE_URL`, `SEOUL_API_KEY`, `KASI_API_KEY` |
| `DATA_GO_KR_KEY` approval for 서울시 실시간 인구데이터(영문) API (data.go.kr 15146171) | Optional. If the user has not applied, `name_en` stays null and you record it in Open facts; do not invent English names |
| Geopandas available | `pip install geopandas pyogrio` into the same interpreter (research-side dependency, used only by the one-off `load_places` step; do **not** add it to `app/engine/requirements.txt`) |

## Files you may touch

Create: `app/engine/jobs/{backfill,collect,load_places,sync_holidays}.py`, `app/engine/{seoul_api,parsers,raw_store}.py`, `app/engine/config/{open_hours.yaml,holiday_names_en.yaml,foreign_heavy.yaml}`, `app/engine/tests/**` (new test files and fixtures), `scripts/register_collect_task.ps1` (ASCII only), `docs/tracking/criteria-m1.md`.
Edit: `app/engine/__main__.py` (wire the four jobs; `forecast tier_b evaluate archive` stay exit 2), `app/engine/requirements.txt` (only if a runtime package is truly needed; justify in the report), `docs/LLM_PROJECT_MAP.md` (add the new files and the scheduler command), `.env.example` (only if a new variable is added).
Read-only: everything under `analysis/`, the specs, `docs/sow/`, `AGENTS.md`, migrations (a schema change needs a new SOW).

## Facts you build on (verified 2026-10-01)

- Place polygons: `analysis/data/poi/서울시 주요 121장소 영역/서울시 주요 121장소 영역.shp` (attributes include the POI code `AREA_CD` and name `AREA_NM`; check the layer's CRS with geopandas and convert to EPSG:4326 for `lat`/`lon`/`geom`, EPSG:5179 only if you need metres).
- Place category for the 111 live places: `analysis/data/fill_gap_by_place.csv` columns `poi, AREA_NM, CATEGORY` (utf-8-sig).
- Research extracts (hourly, KST, utf-8):
  - `analysis/data/obs_hist.csv` (2026-05-12→), `obs_hist_aug.csv` (Aug 1–19), `obs.csv` (Aug 30→): `snap_time` (YYYYMMDDHHMM), `poi`, `name`, `ppltn_time` (`YYYY-MM-DD HH:MM`), `pmin`, `pmax`, `lvl` (여유/보통/약간 붐빔/붐빔), `temp`, `precip`, `precpt_type`, `n_event`.
  - `analysis/data/cmrcl.csv` (weekends/holidays) and `cmrcl_rest.csv` (weekdays + Aug 1–19): `snap_time`, `poi`, `cmrcl_time` (`YYYYMMDD HHMM`), `lvl` (한산한/보통/분주한/바쁜), `pay_cnt`, `amt_min`, `cat_음식·음료`, `cat_유통`, `cat_패션·뷰티`, `cat_여가·오락`, `cat_생활서비스`, `cat_의료·건강`, `cat_교육`, `cat_숙박`.
  - 111 distinct `poi` in obs, 81 in cmrcl. These extracts are what produced every number in the specs; load them as they are.
- Live API shape (`analysis/scripts/collect_rtd.py`, `collect_cmrcl.py`): `CITYDATA.AREA_CD`, `AREA_NM`; `LIVE_PPLTN_STTS.LIVE_PPLTN_STTS` (a dict, or a one-element list) with `PPLTN_TIME`, `AREA_PPLTN_MIN`, `AREA_PPLTN_MAX`, `AREA_CONGEST_LVL`, age shares `PPLTN_RATE_0 … PPLTN_RATE_70`, `MALE_PPLTN_RATE`, and `FCST_PPLTN.FCST_PPLTN[]` with `FCST_TIME`, `FCST_PPLTN_MIN`, `FCST_PPLTN_MAX`, `FCST_CONGEST_LVL`; `LIVE_CMRCL_STTS` with `CMRCL_TIME`, `AREA_CMRCL_LVL`, `AREA_SH_PAYMENT_CNT`, `CMRCL_RSB.CMRCL_RSB` (a list, or a single dict when one category) of `RSB_LRG_CTGR`, `RSB_SH_PAYMENT_CNT`. Confirm field names against the first live response and record any difference in Open facts.
- Level words → `level`: live 여유 0 / 보통 1 / 약간 붐빔 2 / 붐빔 3; commerce 한산한 0 / 보통 1 / 분주한 2 / 바쁜 3. Any other word → fail loud (raise, do not map to null).
- Foreign-heavy places (build contract §4.4, 11 places): every place whose `AREA_NM` contains one of 명동, 동대문, 이태원, 홍대, 인사동, 남대문. Put the six substrings in `app/engine/config/foreign_heavy.yaml`; the count must come out 11.
- Station master for later tier B work: `analysis/data/subway/stations.csv` (`BLDN_NM`, `LAT`, `LOT`). Not used in M1.

## Steps

### M1-1 `load_places` (W2), one-off job `python -m engine load_places`
- Read the shapefile; for each of the 121 features upsert `places`: `id` = `AREA_CD`, `poi_code` = `AREA_CD`, `name` = `AREA_NM`, `geom` = polygon as GeoJSON (EPSG:4326), `lat`/`lon` = centroid, `category` from `fill_gap_by_place.csv` when present, `gu` from the polygon's centroid against `analysis/data/poi/dong.geojson` (its 시군구 attribute; record the attribute name you used).
- Tier: `A1` if the POI appears in `cmrcl.csv` or `cmrcl_rest.csv` (81), else `A2`.
- `serve_state`: `preparing` for every place with live rows in the obs extracts (111); `off` for the 10 that never appear (they never returned data). M2 flips `preparing` → `on` once a model index exists (build contract §0).
- `foreign_heavy` from `foreign_heavy.yaml`.
- `open_hours` for A2 places whose `CATEGORY` is 고궁·문화유산: from `app/engine/config/open_hours.yaml`, shape `{ "<POI>": { "hours": {"mon": null, "tue": "09:00-18:00", ...}, "source": "<url>", "checked": "<date>" } }` (null = closed that weekday). Fill it from the 궁능유적본부 official pages and record the URLs and the date in the report; do not guess.
- `name_en`: from the English API if the key is approved, matched by `AREA_CD`; otherwise null.
- Re-running must not duplicate rows or change `updated_at` when nothing changed (compare before write).

### M1-2 `sync_holidays` (W4), job `python -m engine sync_holidays`
- Call `getRestDeInfo` for every month 2023-01 … 2027-12 (60 calls, 0.2 s apart). Upsert `holidays` by `date`.
- `kind`: `substitute` if `dateName` contains 대체; `seol` if it contains 설날; `chuseok` if it contains 추석; else `holiday`. This makes the three days of each 설·추석 range `seol`/`chuseok` (the API lists all three under the same name).
- `name_en` from `app/engine/config/holiday_names_en.yaml`, which you create with exactly this content and extend only if the API returns a name not listed (report it): 신정 New Year's Day · 설날 Seollal · 삼일절 Independence Movement Day · 어린이날 Children's Day · 부처님오신날 Buddha's Birthday · 현충일 Memorial Day · 광복절 Liberation Day · 추석 Chuseok · 개천절 National Foundation Day · 한글날 Hangul Day · 기독탄신일 Christmas Day · 대체공휴일 Substitute holiday · 임시공휴일 Temporary public holiday · 제21대 대통령선거일 Presidential election day · 국회의원선거일 National Assembly election day · 지방선거일 Local election day.
- Keys travel only in URLs; wrap httpx errors as in `healthcheck`.

### M1-3 `backfill` (W3a), one-off job `python -m engine backfill`
- Parsers live in `app/engine/parsers.py` and are shared with `collect`: `parse_live_level(word)`, `parse_commerce_level(word)`, `kst(ts_str, fmt)` → timezone-aware `Asia/Seoul` timestamps.
- `live_obs`: for each obs CSV row → `place_id=poi`, `ts=ppltn_time` (KST), `pop_min=pmin`, `pop_max=pmax`, `level`, `age_rates=null`, `male_rate=null` (the extracts have no rates). Several snapshots share one `ppltn_time`; keep the row with the latest `snap_time`. Upsert on (`place_id`,`ts`).
- `commerce_obs`: for each cmrcl CSV row → `ts=cmrcl_time`, `level`, `pay_cnt`, `cat_counts` = the eight `cat_*` columns as a JSON object keyed by category name (without the `cat_` prefix). Same dedupe and upsert.
- Skip rows whose `poi` is not in `places` and count them (report the count; expected 0).
- Load in batches with `psycopg` `executemany`/`COPY`, one transaction per file. Log rows read / written / skipped per file.
- Print the final counts: `select count(*) from live_obs`, `commerce_obs`, `min(ts)`, `max(ts)`. Run twice; the second run changes nothing.

### M1-4 `collect` (W3), job `python -m engine collect`
- `seoul_api.fetch(place_code, client)` → parsed JSON; timeout 20 s; up to 3 attempts with 1 s, 2 s backoff; HTTP ≠ 200 or missing `CITYDATA` counts as a failure for that place. Never log the URL.
- Run for all 121 `places` rows (including `serve_state = off`, to notice a recovery), 10 in flight (`httpx.Client` + `concurrent.futures.ThreadPoolExecutor`).
- `raw_store.write(run_ts, place_code, body)` → `RAW_DIR/YYYY/MM/DD/HHMM/<POI>.json.gz` (KST, minute rounded down to the run's start). Written before parsing; never modified afterwards (invariant 4). `RAW_DIR` defaults to `data/raw` when unset.
- Parse and upsert: `live_obs` (`ts=PPLTN_TIME`, `age_rates` = the `PPLTN_RATE_*` shares as a JSON object, `male_rate`), `commerce_obs` (`ts=CMRCL_TIME`, categories summed into `cat_counts` by `RSB_LRG_CTGR`; handle both list and single-dict `CMRCL_RSB`), `city_fcst` (`target_ts=FCST_TIME`, `issued_ts=PPLTN_TIME`; upsert on (`place_id`,`target_ts`) so only the latest issue is kept). A place with no `LIVE_PPLTN_STTS` contributes nothing and counts as "no data" (not a failure) when the HTTP call succeeded.
- One `job_runs` row per run with `detail = {"called": 121, "ok": n, "no_data": n, "failed": n, "raw_dir": "<relative path>"}`. More than 20 failures among the 111 `serve_state <> 'off'` places → status `fail`, exit 1. Otherwise `ok`; `warn` if 1–20 failed.
- The build contract's step "overwrite today's `forecast_hourly` from the 12-hour forecast" waits for M2 (`forecast_hourly` rows need the M2 thresholds); note this in the report.
- `scripts/register_collect_task.ps1` (ASCII only, PowerShell 5.1): registers a Task Scheduler task `UrbanPulse collect` that runs `python -m engine collect` in the repo root every 30 minutes starting at the next :00/:30, appending stdout/stderr to `data/logs/collect.log`, with a 10-minute execution limit; `-Unregister` switch removes it. Running it twice must not create two tasks.

### M1-5 Tests (`app/engine/tests/`)
Fixtures are frozen real payloads: save one real citydata response for a place with commerce data and one for a park (no `LIVE_CMRCL_STTS`) under `tests/fixtures/` after redacting nothing (the response contains no key). Also a CSV fixture of 20 real rows from each extract.
- `test_parsers.py`: every level word maps as listed; an unknown word raises; `kst("2026-08-29 23:30", ...)` is 2026-08-29T23:30+09:00; `cmrcl_time` `20260515 2300` parses.
- `test_collect_parse.py`: the fixture responses produce the expected `live_obs`/`commerce_obs`/`city_fcst` rows (counts, `ts`, level, category sums); the single-dict `CMRCL_RSB` shape is covered by a hand-edited copy of the fixture.
- `test_collect_run.py`: with mocked HTTP (MockTransport) for 121 places where 25 return 500 → exit 1 and `detail.failed == 25`; where 5 return 500 → exit 0 and status `warn`; raw files exist for every successful place and none for failures; the key appears nowhere in stdout/stderr/detail.
- `test_backfill.py`: loading the CSV fixture twice into a temporary schema (or a transaction rolled back) yields the same counts; duplicate `ppltn_time` keeps the latest `snap_time`.
- `test_holidays.py`: kind mapping for the 2026 rows (설날 ×3 → seol, 추석 ×3 → chuseok, 대체공휴일 → substitute); every returned name has an English entry.

## Acceptance (`docs/tracking/criteria-m1.md`, rows created before M1-1)

| # | Criterion | Command |
|---|---|---|
| A1 | Places loaded with the expected split | `python -m engine load_places` → exit 0; `select tier, serve_state, count(*) from places group by 1,2 order by 1,2` → `A1 preparing 81`, `A2 preparing 30`, `A2 off 10`; `select count(*) from places where foreign_heavy` → 11; every row has `lat`, `lon`, `geom`; palaces have `open_hours` |
| A2 | Holidays 2023–2027 | `python -m engine sync_holidays` → exit 0; `select count(*) from holidays where date between '2023-01-01' and '2027-12-31'` (paste); `select date, kind from holidays where date between '2026-09-24' and '2026-09-26'` → three `chuseok` rows; `select count(*) from holidays where name_en is null` → 0 |
| A3 | Backfill idempotent | `python -m engine backfill` twice → both exit 0; counts of `live_obs` and `commerce_obs` identical after the second run (paste both); `min(ts)` ≤ 2026-05-12, `max(ts)` ≥ 2026-09-29 |
| A4 | Collect writes a snapshot | `python -m engine collect` → exit 0 or `warn`; latest `job_runs` row has `called: 121`, `ok ≥ 100`; `select count(*) from live_obs where ts >= now() - interval '2 hours'` ≥ 100; the run's `RAW_DIR/.../HHMM/` folder has one `.json.gz` per successful place |
| A5 | Scheduler registered once | `powershell -File scripts/register_collect_task.ps1` twice → `schtasks /Query /TN "UrbanPulse collect"` lists exactly one task with a 30-minute trigger; after ≥ 1 hour, `select job, status, started_at from job_runs where job='collect' order by id desc limit 3` shows runs 30 minutes apart |
| A6 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 |
| A7 | No key anywhere | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match; the Seoul key value does not appear in `data/logs/collect.log` or in any `job_runs.detail` (script prints `matched`/`no match`) |
| A8 | Raw never rewritten | run `collect` twice within the same minute is impossible by design (folder per run start); instead: `python -m engine collect` then `Get-ChildItem -Recurse data/raw | Measure-Object` count equals the `ok` count of that run; a second run adds a new folder and leaves the first untouched (`LastWriteTime` unchanged) |

## Open facts to report

- The exact CRS of the shapefile and the 시군구 attribute name used for `gu`.
- Places whose polygon centroid falls outside every dong polygon (should be none).
- Whether the English-name API key was available; if not, how many `name_en` are null (expected 121).
- Any live field name that differs from the list above; the share of the 111 places returning `LIVE_CMRCL_STTS` on the first run (spec expects 81).
- First-day collect statistics after the task has run overnight: runs, failures, average duration (from `job_runs`).
- Anything in `holiday_names_en.yaml` you had to add.
