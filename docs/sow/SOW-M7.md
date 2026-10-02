# SOW-M7 — Collection is broken since tier B loaded; stabilise the jobs (local)

Review of SOW-MB and SOW-M6 on 2026-10-02 09:55 KST. Both criteria files reproduce (pytest 92 passed, ruff clean, level agreement, flag, invariants). Running the system overnight exposed the problems below. **Step 1 is urgent: every collect run has failed since 2026-10-01 23:30.**

## What the review saw

1. `job_runs`: `collect` is `fail` at 23:30, 00:00, 00:30, 01:00, 01:30, 02:00, 02:30 with `detail.only_in_db = ["STN001", …, "STN590"]`. The place-code check of SOW-M2 step A-2 compares the code file with **all** `places` rows; the 590 station rows have no code. Raw snapshots were written (raw-first held), nothing was stored. `max(live_obs.ts)` is 2026-10-01 22:30.
2. No collect ran after 02:30 and the 05:00 forecast and 06:00 evaluate tasks never ran: the laptop slept. The tasks do not wake it.
3. `forecast` took 1,821 s and 755 s. The task's limit is 20 minutes, so the scheduler would kill it.
4. 17 files are modified but not committed (`git status`): the midnight fix in `forecast.py`, stable station ids, the `--check` exit code, web changes.
5. 343 of the 590 station places have no profile (no 집계구 overlap: stations outside Seoul). They are in `places`, so search finds them and the screen can only say "준비 중".
6. `pytest` reports `1 skipped` (`test_cli.py:6: got empty parameter set`): the not-yet-implemented job list is empty now. AGENTS.md rule 7: no skipped test.
7. `findings.md` (2026-10-02): `apply_overlay` bounds its reads with SQL `now()` instead of the job's own time.

## Files you may touch

`app/engine/**`, `scripts/register_*_task.ps1`, `docs/tracking/criteria-m7.md`, `docs/tracking/findings.md` (mark the overlay finding resolved), `docs/LLM_PROJECT_MAP.md`. Web files only to commit what is already modified.

## Steps

### 1 Collect ignores places that have no code (urgent)
The check compares the code file with `places` rows whose `poi_code` is not null. Regression test: with a tier B row present, a mocked collect run ends `ok`. Then store what was missed: `python -m engine ingest_raw --date 2026-10-01` and `--date 2026-10-02`. Then `python -m engine collect`.

### 2 Commit the pending work
Review your own uncommitted diff, run the tests, and commit it in coherent commits named for what each does (`M7-2a: …`). Nothing stays uncommitted at the end of this SOW.

### 3 Tasks wake the machine and have room to finish
All three register scripts: add `-WakeToRun` to the task settings. `forecast` limit 60 minutes. Re-register the three tasks. (Waking works from sleep, not from shutdown or a closed lid on some hardware; report what `powercfg /waketimers` shows after registering.)

### 4 Make `forecast` faster
Measure where the time goes (per phase seconds into `job_runs.detail.timing`: refresh, thresholds, profile, forecast_hourly, recommendations, tier B, log). Fix the dominant cost without changing any stored value: the usual causes are per-row model calls instead of one batched predict per place, per-row inserts instead of batched upserts, and re-querying per place. Target: under 5 minutes for a full run. Prove equality: before the change dump `forecast_hourly` and `recommendations` (excluding `issued_ts`, `generated_at`) for a fixed `today` into `data/tmp/before.parquet`; after, the same dump is identical (row-for-row, floats within 1e-6). Not reached → report the timing table and what remains.

### 5 Station places only where a profile exists
`tier_b` removes tier B places that have no `tier_b_profile` rows after the profile step and does not insert them again on the next run (a station becomes a place when it gets a profile). `drop_unprofiled_tier_b` in `forecast.py` then has nothing to do; remove it. Ids stay stable (computed over all kept station names as now).

### 6 Small fixes
- `test_cli.py`: replace the parametrised not-yet-implemented test with one that asserts every job name in the map's entry-point table parses; no skipped test remains.
- `apply_overlay` takes the run's timestamp from its caller instead of SQL `now()`; `forecast` passes its issue time, `collect` its run time. Test: a run whose clock crosses midnight overlays only the issued day.

## Acceptance (`docs/tracking/criteria-m7.md`, rows created before step 1)

| # | Criterion | Command |
|---|---|---|
| A1 | Collect works with stations present | `python -m engine collect` → exit 0 or warn, `ok ≥ 100`; `select max(ts) from live_obs` within the last 40 minutes |
| A2 | Missed snapshots stored | after the two `ingest_raw` runs: `select count(distinct ts) from live_obs where ts >= '2026-10-01 23:00+09' and ts < '2026-10-02 03:00+09'` pasted with the list of raw folders of that span |
| A3 | Nothing uncommitted | `git status --short` → empty |
| A4 | Tasks | for the three tasks paste `Settings.WakeToRun`, `ExecutionTimeLimit`; forecast `PT1H`; `powercfg /waketimers` output |
| A5 | Forecast time and equality | `detail.timing` before and after; total seconds; the equality check result |
| A6 | Station places | `select count(*) from places where tier = 'B'` = `select count(distinct place_id) from tier_b_profile`; a second `tier_b` run changes 0 rows |
| A7 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0 with **0 skipped**; `ruff check app/engine` → exit 0; `cd app/web; npm run build; npx playwright test` → exit 0 |
| A8 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match |

## Open facts to report

- Which half-hour slots between 2026-10-01 23:00 and now have no raw folder (lost for good).
- The timing table before and after.
- Whether the machine can wake for the tasks.
