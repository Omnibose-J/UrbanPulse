# criteria-m1 — Places, holidays, backfill, collect (local)

Written 2026-10-01 before implementation. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Places loaded with the expected split | `python -m engine load_places` → exit 0; `select tier, serve_state, count(*) from places group by 1,2 order by 1,2` → `A1 preparing 81`, `A2 preparing 30`, `A2 off 10`; `select count(*) from places where foreign_heavy` → 11; every row has `lat`, `lon`, `geom`; palaces have `open_hours` | 0 | `A1 preparing 81`, `A2 off 10`, `A2 preparing 30` (order by 1,2); foreign_heavy 11; null lat/lon/geom 0; open_hours on POI008, POI011, POI012. Second run written 0, max(updated_at) unchanged |
| A2 | Holidays 2023–2027 | `python -m engine sync_holidays` → exit 0; `select count(*) from holidays where date between '2023-01-01' and '2027-12-31'` (paste); `select date, kind from holidays where date between '2026-09-24' and '2026-09-26'` → three `chuseok` rows; `select count(*) from holidays where name_en is null` → 0 | 0 | count 102; 2026-09-24, 2026-09-25, 2026-09-26 all `chuseok`; `name_en` null 0; second run `written` 0 |
| A3 | Backfill idempotent | `python -m engine backfill` twice → both exit 0; counts of `live_obs` and `commerce_obs` identical after the second run (paste both); `min(ts)` ≤ 2026-05-12, `max(ts)` ≥ 2026-09-29 | | |
| A4 | Collect writes a snapshot | `python -m engine collect` → exit 0 or `warn`; latest `job_runs` row has `called: 121`, `ok ≥ 100`; `select count(*) from live_obs where ts >= now() - interval '2 hours'` ≥ 100; the run's `RAW_DIR/.../HHMM/` folder has one `.json.gz` per successful place | | |
| A5 | Scheduler registered once | `powershell -File scripts/register_collect_task.ps1` twice → `schtasks /Query /TN "UrbanPulse collect"` lists exactly one task with a 30-minute trigger; after ≥ 1 hour, `select job, status, started_at from job_runs where job='collect' order by id desc limit 3` shows runs 30 minutes apart | | |
| A6 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 | | |
| A7 | No key anywhere | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match; the Seoul key value does not appear in `data/logs/collect.log` or in any `job_runs.detail` (script prints `matched`/`no match`) | | |
| A8 | Raw never rewritten | run `collect` twice within the same minute is impossible by design (folder per run start); instead: `python -m engine collect` then `Get-ChildItem -Recurse data/raw | Measure-Object` count equals the `ok` count of that run; a second run adds a new folder and leaves the first untouched (`LastWriteTime` unchanged) | | |

## Report
(AGENTS.md format, appended when done)
