# criteria-m2 — Collect hardening, then models and forecast

Written 2026-10-01 before implementation. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Task survives battery | run the script; `(Get-ScheduledTask 'UrbanPulse collect').Settings | Select DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable` → `False, False, True`; one task | 0 | `DisallowStartIfOnBatteries False`, `StopIfGoingOnBatteries False`, `StartWhenAvailable True`; task count 1; next run 2026-10-01 14:00 |
| A2 | Raw written with the database down | `cd app; supabase stop`; `python -m engine collect` → exit 1, log `database unavailable`; run folder has ≥ 100 `.json.gz` | 1 | log `reason=database unavailable`, `raw_dir=data/raw/2026/10/01/1347`; that folder has 121 `.json.gz`; `supabase start` exit 0 afterwards |
| A3 | Raw ingested afterwards | `supabase start`; `python -m engine ingest_raw` → exit 0; that run's `live_obs` rows ≥ 100; a second run changes 0 rows | 0 / 0 | first `live` 847, `commerce` 574, `affected` 1573; second `affected` 0 with the same 847 live rows |
| A4 | Categories normalized | `select count(*) from commerce_obs where (select count(*) from jsonb_object_keys(cat_counts)) not in (8, 9)` → 0; `select count(*) from commerce_obs where cat_counts ? '의료'` → 0 | 0 | both counts 0; `기타` count 0; ingest `unknown_categories` [] |
| A5 | Holidays are days off | `python -m engine sync_holidays` → exit 0; paste `select date, name from holidays where date in ('2026-05-01','2026-07-17')` and the API's `isHoliday` for both | 0 | API `isHoliday=Y` for both: 2026-05-01 노동절, 2026-07-17 제헌절; both rows remain (`deleted` 0). The research list missed two real days off |
| A6 | Place codes file stable | second `load_places` → `git diff --stat app/engine/config/place_codes.yaml` empty; 121 codes | 0 | second `load_places` exit 0, `written` 0; `git diff --stat` empty; 121 codes |
| B1 | Port reproduces the research figures | equivalence run → paste the per-horizon table; holiday WAPE within ±0.5 %p of baseline 21.6 / model 17.4 at horizon 3 and baseline 21.6 / model 18.2 at horizon 7 | | |
| B2 | Served model evaluated and registered | served run table pasted; `select name, version, horizons, active from model_registry` → one active `ratio_v1` row whose `horizons` are exactly the horizons that pass the gate in the pasted table | | |
| B3 | Forecast rows | `python -m engine forecast` → exit 0; `select source, ready, count(*) from forecast_hourly group by 1,2 order by 1,2` pasted; every place not `off` has 8 × 24 rows; no row with `ready` and null `level` | | |
| B4 | Places refreshed from live data | `select tier, serve_state, count(*) from places group by 1,2 order by 1,2` and `detail.transitions` pasted. Do not steer these counts; report them | | |
| B5 | Log is append-only | run `forecast` twice the same day → `forecast_log` row count unchanged after the second run; rows exist only for `horizon_d in (1,3,7)` and hours 9–23 | | |
| B6 | Overlay via collect | after `python -m engine collect`: the current hour's `forecast_hourly` rows have `source='live'` for places with a fresh observation; the next hours covered by `city_fcst` have `source='seoul'` | | |
| B7 | Forecast scheduled | `Get-ScheduledTask 'UrbanPulse forecast'` → daily 05:00, battery settings as A1 | | |
| B8 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0 (stack up); stack stopped → database tests fail in under 30 s total naming `supabase start`; `ruff check app/engine` → exit 0 | | |
| B9 | No key, model tracked | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match; `git ls-files models/ratio_v1` lists `model.joblib` and `meta.json`; `model.joblib` under 50 MB | | |

## Report
(AGENTS.md format, appended when done)
