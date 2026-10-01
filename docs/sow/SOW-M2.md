# SOW-M2 — Collect hardening, then models and the forecast job (local)

Two parts, done in order, one criteria file (`docs/tracking/criteria-m2.md`).
**Part A** (was SOW-M1.1) closes the data-loss gaps found in the M1 review. **Part B** is work units W5, W6, W7 of the build contract (`UrbanPulse_구현설계서.md` §4.0, §4.2, §5, §8): port the calendar-ratio model, prove the port, compute thresholds and activity profiles, and run `forecast` daily. Recommendations (W8) and tier B (W9, `ratio_v1b`) are M3. No cloud, no web work, no schema change.

## Inputs from the user

| Input | Notes |
|---|---|
| Local stack running, Docker Desktop up | `cd app; supabase status`. M1 data is in the database |
| Laptop stays on for the scheduler | Part A makes the task survive battery; sleep still stops it |

## Files you may touch

Create: `app/engine/config/place_codes.yaml`, `app/engine/jobs/{ingest_raw,forecast}.py`, `app/engine/{hourly,calendar_feats,levels,lively,ratio_model}.py`, `app/engine/train/{__init__,train_ratio,evaluate_ratio}.py`, `app/engine/train/research_holidays.txt`, `models/ratio_v1/{model.joblib,meta.json}`, `scripts/register_forecast_task.ps1` (ASCII), `app/engine/tests/**`, `docs/tracking/criteria-m2.md`.
Edit: `scripts/register_collect_task.ps1`, `app/engine/jobs/{collect,load_places,sync_holidays}.py`, `app/engine/parsers.py`, `app/engine/__main__.py` (wire `ingest_raw`, `forecast`; `tier_b evaluate archive` stay exit 2), `pyproject.toml` (add `engine.train` to `packages`), `app/engine/requirements.txt` (add `joblib` pinned to the installed version; nothing else), `docs/LLM_PROJECT_MAP.md`.
Read-only: `analysis/` (inputs: `analysis/data/place_oa/20*.parquet`, `analysis/data/place_oa/cover.csv`; reference: `analysis/scripts/eval_ratio_live.py`, `eval_days_ahead.py`, `exp_e3_e4_reco.py`, `exp_e3c_calm.py`), migrations, specs, `docs/sow/`, `AGENTS.md`, `app/web/`.

---

# Part A — Collect hardening

## What the M1 review observed (2026-10-01)

- The task ran 09:30, 10:00, 10:30, then missed five slots: `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries` were `True` (PowerShell defaults) and the laptop was on battery. The designer flipped both on the live task by hand; the script must set them.
- `collect` reads `places` from the database before fetching, so with Postgres down nothing is fetched and no raw snapshot exists. Raw snapshots are the one asset that cannot be re-created.
- Commerce category keys differ: the extracts use eight fixed zero-filled keys (`음식·음료, 유통, 패션·뷰티, 여가·오락, 생활서비스, 의료·건강, 교육, 숙박`); the live API sends `의료`; `collect` stores only categories present.
- `holidays` holds 2026-05-01 노동절 and 2026-07-17 제헌절, which the research holiday list does not. `sync_holidays` never reads the API's `isHoliday` field.
- `test_backfill` hung 148 s when the stack was down.

## Steps

### A-1 Task survives battery
`register_collect_task.ps1`: `-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable`, 10-minute limit. Re-running updates an existing task's settings.

### A-2 Raw first, database second
- `load_places` also writes `app/engine/config/place_codes.yaml` (the 121 POI codes in order, tracked). A second run leaves it byte-identical.
- `collect` takes codes from that file, fetches, and writes raw **before** any database call; then opens the ledger, reads `serve_state`, upserts.
- Database unreachable at that point → log `{"event": "fail", "reason": "database unavailable", "raw_dir": ...}`, exit 1, raw kept. No retry loop.
- A code in the file but not in `places`, or the reverse → exit 1 naming it.

### A-3 `ingest_raw`
`python -m engine ingest_raw [--date YYYY-MM-DD]` (default today KST): parse every `.json.gz` under that day's run folders with `parse_citydata` and upsert with the statements `collect` uses (shared, not copied). Idempotent. `job_runs.detail = {"folders","files","live","commerce"}`.

### A-4 Commerce categories
`parsers.COMMERCE_CATEGORIES` = the eight names. `cat_counts` always has exactly these keys, zero-filled; alias `의료` → `의료·건강`. Any other name: add its count under `기타` (a ninth key only when it occurs) and list the raw names in `detail.unknown_categories`. Requested behaviour, not a silent fallback: an unexpected label must not stop collection and must be visible. Then `ingest_raw --date 2026-10-01` (and every later date collected before this fix) to normalize stored rows.

### A-5 Holidays are days off
`sync_holidays` keeps a row only when the API item's `isHoliday` is `Y`, and deletes rows in 2023–2027 that the API no longer returns as `Y`. Report what the API says for 2026-05-01 and 2026-07-17.

### A-6 Database tests fail fast
Tests that need Postgres connect with `connect_timeout=5` and fail with `local database not reachable (cd app; supabase start)`. Never skip.

---

# Part B — Models and forecast

## Definitions (use exactly these; each differs from, or pins down, the research code)

- **Hourly live value** `live(place, h)`: mean of `(pop_min + pop_max) / 2` over `live_obs` rows with `ts` in `[h, h + 1h)` KST. **Hourly level**: `level` of the latest row in that hour. One implementation in `app/engine/hourly.py`, used by training evaluation, thresholds, forecast, and the M5 evaluator.
  - The research code used `ppltn_time.dt.round("h")`, which is round-half-even: `10:30 → 10:00`, `11:30 → 12:00`. Odd hours were empty and even hours averaged two stamps; that is the "one-hour holes" the backtests interpolated. The engine floors. `evaluate_ratio --grid research` reproduces the old grid only to prove the port (B-3).
- **Hourly commerce value** per purpose: mean over `commerce_obs` rows in the hour of `all = pay_cnt`, `food = cat_counts['음식·음료']`, `shop = cat_counts['유통'] + cat_counts['패션·뷰티']`.
- **Day type** of a date from `holidays`: `myeongjeol` if `kind in ('seol','chuseok')`; `holiday` if any other row; else `weekend` (Sat/Sun) or `weekday`.
- **Calendar features** for an hourly timestamp (`app/engine/calendar_feats.py`, port of `calendar()` in `eval_ratio_live.py`): `hour`, `dow` (Mon=0), `month`, `hol` (date in holiday set), `hol_wkend` (`hol` and Sat/Sun), `big` (0; 1 if the date is within −3…+6 days of the first day of a 설 block; 2 for a 추석 block), `to_hol` and `from_hol` (days to the next / since the previous holiday, clipped to [0, 8]). The holiday set and block starts are arguments, so the same function serves both holiday sources below. A block's first day = the earliest of consecutive `seol` (or `chuseok`) dates.
- **Baseline** for target hour `T` at horizon `d` days (0–7): mean of `live(place, T − 7k days)` for `k = kmin … kmin + 2`, `kmin = 1` if `d < 7` else `2`, over the values that exist. Fewer than 2 of the 3 → not ready.

## Steps

### B-1 Train `ratio_v1` — `python -m engine.train.train_ratio --holidays {research|table} --out <dir>`
Port of `train()` in `eval_ratio_live.py`. Keep every number:
- Data: `analysis/data/place_oa/20*.parquet` (`poi, dt, est_oa`), places with `cover.csv >= 0.8`, pivoted to an hourly frame `asfreq("h")`.
- For each horizon `h` in 0…7: `prof` = nan-mean of the frame shifted 7·24·k hours for `k = kmin … kmin+2` (first `7·24·k` rows NaN); target `y = log(X / prof)`; drop non-finite; keep rows with `t >= 21·24`.
- Concatenate horizons, `sample(n=3_000_000, random_state=0)`.
- Features in this order: `hour, dow, month, hol, hol_wkend, big, to_hol, from_hol, poi_i, h` (`poi_i` = column position of the place in the pivot).
- `HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, max_leaf_nodes=63, random_state=0)`.
- `--holidays research`: the frozen list in `app/engine/train/research_holidays.txt`, which you create by copying the `HOLIDAYS` dates and the `BIG` block starts from `analysis/scripts/eval_days_ahead.py` verbatim. `--holidays table`: the `holidays` table (after A-5).
- Output: `model.joblib` and `meta.json` (`place_index`, `features`, `horizons_trained`, `holidays_source`, `trained_range`, `n_rows`, `sklearn_version`, `git_commit`, `created_at`).

### B-2 Model loader — `app/engine/ratio_model.py`
`load(dir)` → object with `ratio(place_id, timestamps, horizon_d) -> array | None` (None when the place is not in `place_index`). Refuses to load when the installed scikit-learn version differs from `meta.sklearn_version` (exit 1 naming both).

### B-3 Prove the port, then gate — `python -m engine.train.evaluate_ratio --model <dir> --grid {research|floor}`
Serve-form evaluation on live targets 2026-08-01 … 2026-09-29 read from `live_obs` (port of `live_eval()` with `require=("live","prof","last")`, no gap filling): per horizon 0…7, WAPE (`sum|pred − live| / sum live`) of the model and of the baseline, on the five holidays 2026-08-15, 08-17, 09-24, 09-25, 09-26 and on all other days, restricted to places in `place_index`.
1. **Equivalence run**: model trained with `--holidays research`, evaluated with `--grid research` (round-half-even hour, first observation per hour). Research values to reproduce (서비스정의서 부록 실험 7): holiday WAPE at horizon 3, baseline 21.6 % and model 17.4 %; at horizon 7, baseline 21.6 % and model 18.2 %; normal days about 6.1 % → 6.0 %. Tolerance ±0.5 %p on each of the four holiday figures. Outside tolerance → record B1 as FAIL with the measured table; do not adjust anything; continue with the served run (its gate judges the shipped model on its own).
2. **Served run**: model trained with `--holidays table` into `models/ratio_v1/`, evaluated with `--grid floor`. Report the same table. This is the model that ships.
3. **Registration gate** (build contract §5, pre-registered) on the served run, per horizon: holiday WAPE at least 10 % lower than baseline (relative), and normal-day WAPE no more than 0.3 %p worse. Passing horizons go to `model_registry.horizons`; `metrics` = the full table of both runs; `artifact_uri = "models/ratio_v1"`; `active = true` if at least one horizon passes. No horizon passes → `active = false`, report it, and continue: `forecast` then uses the baseline for every horizon.
The equivalence model is not committed (write it under `data/`); only the served model is.

### B-4 Level thresholds — `app/engine/levels.py`
Port of `thresholds()` in `exp_e3_e4_reco.py`, on raw `live_obs` rows of the last 90 days before today (KST): `t_k` = lowest `(pop_min+pop_max)/2` among rows with `level >= k`, `k = 1,2,3`; `Infinity` when no such row. `based_on_days` = distinct dates in the window. `level_of(pop, t1, t2, t3)` = number of thresholds `<= pop`. A place is **threshold-ready** when at least three of the four levels occur in the window.

### B-5 Activity profile — `app/engine/lively.py` (A1 only)
Port of the profile in `exp_e3c_calm.py`: per purpose, `p90` = 0.9 quantile of the hourly commerce value over the last 56 days before today, day types other than `weekday`, hours 9–23. `a(day_type, hour)` = mean over all history before today of `value / p90` for that day type and hour; `n_days` = distinct dates behind it. Store hours 0–23. `p90` missing or zero → that purpose's `a_*` is null. Fewer than 4 dates for a day type (1 for `myeongjeol`) → null.

### B-6 `forecast` job — `python -m engine forecast` (daily 05:00 KST)
Order inside one `job_runs` row:
1. **Refresh places** (A1/A2 only; `experimental` rows untouched): `tier = 'A1'` when the place has a `commerce_obs` row in the last 28 days, else `'A2'`. `serve_state = 'off'` when it has no `live_obs` row in the last 7 days; `'on'` when it is in `place_index`, is threshold-ready, and has live rows on at least 14 distinct dates; otherwise `'preparing'`. Put every transition in `detail.transitions` (`{"POI122": ["off","preparing"], …}`).
2. Recompute `level_thresholds` and `lively_profile`.
3. For every A1/A2 place not `off`, every hour of today … today+7 (KST), upsert `forecast_hourly`:
   - `horizon_d` = target date − today. Baseline as defined; not ready → `ready=false`, `pop/level` null, `source='profile'`.
   - Place in `place_index` and `horizon_d` in the registry's passing horizons → `pop = baseline × exp(ratio)`, `source='model'`; otherwise `pop = baseline`, `source='profile'`. Baseline-only is a registered setting, not a fallback: the gate decides it.
   - `level = level_of(pop, …)` when threshold-ready, else `ready=false`.
   - `a_all, a_food, a_shop` from `lively_profile` for the target's day type (A1; null for A2).
   - `issued_ts` = job start. `stale = true` when the place's newest `live_obs` is older than 90 minutes.
   - Then overlay (step 5).
4. Insert `forecast_log` for `horizon_d` in (1, 3, 7), hours 9–23: `pred` (as served), `baseline`, `model_version`. `on conflict do nothing`; never update (invariant 4).
5. **Overlay**, also called by `collect` after its upsert for the places it just stored: hours of today that have a `live_obs` row → `source='live'`, `pop` = hourly live value, `level` = hourly level, `ready=true`; future hours with a `city_fcst` row → `source='seoul'`, `pop = (pop_min+pop_max)/2`, `level` as given, `ready=true`. Overlay never touches hours beyond the last `city_fcst` target.
6. Delete `forecast_hourly` rows with `target_ts` before today 00:00 KST.
`scripts/register_forecast_task.ps1`: task `UrbanPulse forecast`, daily 05:00, same battery and limit settings as collect (limit 20 minutes), log to `data/logs/forecast.log`.

### B-7 Tests
- `test_hourly.py`: `10:30` and `11:30` stamps land in hours 10 and 11 (floor); the research grid helper puts them in 10 and 12.
- `test_calendar_feats.py`: for the research holiday list, `big`, `to_hol`, `from_hol`, `hol_wkend` on 2026-09-21 … 09-30 and 2026-08-15, 08-17 equal values computed by hand in the test.
- `test_levels.py`: thresholds from a hand-built window; missing level → infinity; `level_of` is monotone in `pop` (invariant 3) under random thresholds.
- `test_lively.py`: p90 and profile from a 10-day hand-built commerce table; zero p90 → null.
- `test_forecast_baseline.py` (invariant 1): for issue date D and every horizon, the baseline reads no `live_obs` row with `ts >= D 00:00`; horizon 7 reads only weeks 2–4; two of three weeks present → ready, one → not ready.
- `test_forecast_sources.py`: with a fake model and registry passing horizons {0…6}: horizon 3 row is `model`, horizon 7 row is `profile` and equals the baseline; a place outside `place_index` is `profile`; overlay turns a past hour into `live` and a `city_fcst` hour into `seoul`; A2 rows have null `a_*` (invariant 6).
- `test_refresh_places.py`: the transition rules above on a hand-built set (off → preparing, preparing → on, on → off, experimental untouched, A2 → A1 when commerce appears).
- `test_ratio_model.py`: version mismatch refuses to load; unknown place → None.
- Part A: `test_collect_run.py` gains "database down → raw written, exit 1"; `test_ingest_raw.py` idempotence; `test_parsers.py` eight keys, alias, `기타`; `test_holidays.py` drops `isHoliday = N`.

## Acceptance (`docs/tracking/criteria-m2.md`, rows created before A-1)

| # | Criterion | Command |
|---|---|---|
| A1 | Task survives battery | run the script; `(Get-ScheduledTask 'UrbanPulse collect').Settings | Select DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable` → `False, False, True`; one task |
| A2 | Raw written with the database down | `cd app; supabase stop`; `python -m engine collect` → exit 1, log `database unavailable`; run folder has ≥ 100 `.json.gz` |
| A3 | Raw ingested afterwards | `supabase start`; `python -m engine ingest_raw` → exit 0; that run's `live_obs` rows ≥ 100; a second run changes 0 rows |
| A4 | Categories normalized | `select count(*) from commerce_obs where (select count(*) from jsonb_object_keys(cat_counts)) not in (8, 9)` → 0; `select count(*) from commerce_obs where cat_counts ? '의료'` → 0 |
| A5 | Holidays are days off | `python -m engine sync_holidays` → exit 0; paste `select date, name from holidays where date in ('2026-05-01','2026-07-17')` and the API's `isHoliday` for both |
| A6 | Place codes file stable | second `load_places` → `git diff --stat app/engine/config/place_codes.yaml` empty; 121 codes |
| B1 | Port reproduces the research figures | equivalence run → paste the per-horizon table; holiday WAPE within ±0.5 %p of baseline 21.6 / model 17.4 at horizon 3 and baseline 21.6 / model 18.2 at horizon 7 |
| B2 | Served model evaluated and registered | served run table pasted; `select name, version, horizons, active from model_registry` → one active `ratio_v1` row whose `horizons` are exactly the horizons that pass the gate in the pasted table |
| B3 | Forecast rows | `python -m engine forecast` → exit 0; `select source, ready, count(*) from forecast_hourly group by 1,2 order by 1,2` pasted; every place not `off` has 8 × 24 rows; no row with `ready` and null `level` |
| B4 | Places refreshed from live data | `select tier, serve_state, count(*) from places group by 1,2 order by 1,2` and `detail.transitions` pasted. Do not steer these counts; report them |
| B5 | Log is append-only | run `forecast` twice the same day → `forecast_log` row count unchanged after the second run; rows exist only for `horizon_d in (1,3,7)` and hours 9–23 |
| B6 | Overlay via collect | after `python -m engine collect`: the current hour's `forecast_hourly` rows have `source='live'` for places with a fresh observation; the next hours covered by `city_fcst` have `source='seoul'` |
| B7 | Forecast scheduled | `Get-ScheduledTask 'UrbanPulse forecast'` → daily 05:00, battery settings as A1 |
| B8 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0 (stack up); stack stopped → database tests fail in under 30 s total naming `supabase start`; `ruff check app/engine` → exit 0 |
| B9 | No key, model tracked | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match; `git ls-files models/ratio_v1` lists `model.joblib` and `meta.json`; `model.joblib` under 50 MB |

## Open facts to report

- Category names that landed in `기타`; slots missing from `job_runs` on 2026-10-01.
- 2026-05-01 and 2026-07-17: the API's `isHoliday` values. If either is `Y`, the research list missed a real holiday; say so (the designer decides whether the research figures need a note).
- The equivalence table and the served table side by side, and how far the floor grid moves the holiday and normal WAPE.
- The `on / preparing / off` counts and which places are `preparing` only because they are not in `place_index` (expected to include POI090, POI100 and POI122–131).
- Training time, `model.joblib` size, forecast job duration.
- Anything in `calendar()` or `train()` whose behaviour you had to infer rather than read.
