# SOW-M1.1 — Collect hardening (found in the M1 review, 2026-10-01)

M1 was accepted: every acceptance row reproduced under independent verification. The review found gaps that lose live data, which is the one thing this project cannot re-create later. Fix them before M2.

## What the review observed

- The scheduled task ran at 09:30, 10:00, 10:30, then missed five slots (11:00–13:00). `Get-ScheduledTask` showed `DisallowStartIfOnBatteries = True`, `StopIfGoingOnBatteries = True` (PowerShell defaults). The laptop was on battery. The designer already flipped both settings on the live task by hand; the script must do it.
- Docker Desktop was not running at 13:25, so Postgres was down. `collect` reads `places` from the database before fetching, so with the database down nothing is fetched and no raw snapshot is written.
- Commerce category keys differ: the research extracts use eight fixed keys (`음식·음료, 유통, 패션·뷰티, 여가·오락, 생활서비스, 의료·건강, 교육, 숙박`, zero-filled), the live API sends `의료` (not `의료·건강`), and `collect` stores only the categories present in a response.
- `test_backfill` needs the local database; with the stack down the suite hung for 148 s before failing.

## Files you may touch

Edit: `scripts/register_collect_task.ps1`, `app/engine/jobs/collect.py`, `app/engine/jobs/load_places.py`, `app/engine/parsers.py`, `app/engine/__main__.py`, `app/engine/tests/**`, `docs/LLM_PROJECT_MAP.md`.
Create: `app/engine/config/place_codes.yaml`, `app/engine/jobs/ingest_raw.py`, `docs/tracking/criteria-m1.1.md`.
Read-only: everything else, as in SOW-M1.

## Steps

### M1.1-1 Task runs on battery
`register_collect_task.ps1`: settings `-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable`, execution limit 10 minutes as before. Re-running the script must update an existing task's settings, not skip it.

### M1.1-2 Raw first, database second
- `load_places` also writes `app/engine/config/place_codes.yaml`: the 121 POI codes in order, tracked in git. Re-running without a change leaves the file byte-identical.
- `collect` takes the place codes from that file, fetches, and writes raw **before** any database call. Then it opens the ledger, reads `serve_state`, and upserts.
- If the database is unreachable at that point: log `{"event": "fail", "reason": "database unavailable", "raw_dir": ...}`, exit 1. The raw folder stays. No retry loop, no queue.
- A code present in the file but missing from `places` (or the reverse) → exit 1 naming the code; do not guess.

### M1.1-3 `ingest_raw` job
`python -m engine ingest_raw [--date YYYY-MM-DD]` (default: today, KST): for every run folder under `RAW_DIR/YYYY/MM/DD/`, parse each `.json.gz` with the same `parse_citydata` and upsert `live_obs`, `commerce_obs`, `city_fcst` with the same statements `collect` uses (share them; do not copy). Idempotent. One `job_runs` row with `{"folders": n, "files": n, "live": n, "commerce": n}`. This is how snapshots taken while the database was down get in.

### M1.1-4 Commerce categories
- `parsers.py`: `COMMERCE_CATEGORIES` = the eight names above. `cat_counts` always has exactly these eight keys, zero-filled. Alias `의료` → `의료·건강`.
- A category name outside the eight and the alias: keep collecting, add the count under key `기타`, and report the raw names in the run's `detail.unknown_categories`. (Deliberate, requested behaviour: an unexpected label must not stop collection; it must be visible.)
- Normalize rows already written by `collect` on 2026-10-01 by running `ingest_raw --date 2026-10-01`.

### M1.1-5 Database-dependent tests fail fast
Tests that need Postgres connect with `connect_timeout=5` and fail with the message `local database not reachable (cd app; supabase start)`. They still fail (never skip) when the database is down.

## Acceptance (`docs/tracking/criteria-m1.1.md`, rows created before M1.1-1)

| # | Criterion | Command |
|---|---|---|
| A1 | Task survives battery | run the script; `(Get-ScheduledTask 'UrbanPulse collect').Settings | Select DisallowStartIfOnBatteries, StopIfGoingOnBatteries, StartWhenAvailable` → `False, False, True`; `schtasks` still lists one task |
| A2 | Raw written with the database down | `cd app; supabase stop`; `python -m engine collect` → exit 1, log line `database unavailable`; the run folder has ≥ 100 `.json.gz` |
| A3 | Raw ingested afterwards | `cd app; supabase start`; `python -m engine ingest_raw` → exit 0; `select count(*) from live_obs where ts >= <that run's minute>` ≥ 100; second `ingest_raw` changes 0 rows |
| A4 | Categories normalized | `select count(*) from commerce_obs where (select count(*) from jsonb_object_keys(cat_counts)) <> 8` → 0 (after `ingest_raw --date 2026-10-01`); `select count(*) from commerce_obs where cat_counts ? '의료'` → 0 |
| A5 | Place codes file | `git diff --stat app/engine/config/place_codes.yaml` after a second `load_places` → empty; the file lists 121 codes |
| A6 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0 with the stack up; with the stack stopped the database tests fail in under 30 s total naming `supabase start`; `ruff check app/engine` → exit 0 |

## Open facts to report
- Which category names, if any, landed in `기타`.
- Runs between 11:00 and 13:00 on 2026-10-01 are lost (no raw). State how many slots are missing in `job_runs` for that day.
- Whether `POI122`–`POI131` (stored `serve_state = off`) keep returning live rows; do **not** change their state (M2 decides).
