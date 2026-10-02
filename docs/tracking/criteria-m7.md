# criteria-m7 — Collection works with station places present

Written 2026-10-02 before step 1. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Collect works with stations present | `python -m engine collect` → exit 0 or warn, `ok ≥ 100`; `select max(ts) from live_obs` within the last 40 minutes | 0 | ok 121; job_runs status ok at 2026-10-02 10:03; max(ts) 2026-10-02 09:30 |
| A2 | Missed snapshots stored | after the two `ingest_raw` runs: `select count(distinct ts) from live_obs where ts >= '2026-10-01 23:00+09' and ts < '2026-10-02 03:00+09'` pasted with the list of raw folders of that span | 0 | distinct ts 7 (23:00, 23:30, 00:00, 00:30, 01:00, 01:30, 02:00). folders 2300, 2330, 0000, 0030, 0100, 0130, 0200, 0230. 0230 carries PPLTN_TIME 02:00 |
| A3 | Nothing uncommitted | `git status --short` → empty | | |
| A4 | Tasks | for the three tasks paste `Settings.WakeToRun`, `ExecutionTimeLimit`; forecast `PT1H`; `powercfg /waketimers` output | | |
| A5 | Forecast time and equality | `detail.timing` before and after; total seconds; the equality check result | | |
| A6 | Station places | `select count(*) from places where tier = 'B'` = `select count(distinct place_id) from tier_b_profile`; a second `tier_b` run changes 0 rows | | |
| A7 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0 with **0 skipped**; `ruff check app/engine` → exit 0; `cd app/web; npm run build; npx playwright test` → exit 0 | | |
| A8 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match | | |

## Report
(appended when the SOW is done)
