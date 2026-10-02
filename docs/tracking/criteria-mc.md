# criteria-mc — Move the running system to managed services

Written 2026-10-02 before step 1. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Code changes are safe locally | pytest, ruff, local collect `ok >= 100` | 0 | pytest 102 passed, 0 skipped; ruff clean; collect ok 121 |
| A2 | Inputs present | `scripts/cloud/00_check.ps1` → exit 0, U1–U4 present (names only) | 1 | U1 missing. U2 present. U3 missing (all eight names). U4 present |
| A3 | Scripts idempotent | second run of 10, 20, 30, 50, 60 → exit 0, no change | | BLOCKED: U1 and U3 missing |
| A4 | Schema on the hosted database | 19 tables, RLS on all, anon/authenticated grants 0 | | BLOCKED: U1 and U3 missing |
| A5 | Data copied | per-table counts equal; hosted size pasted | | BLOCKED: U1 and U3 missing |
| A6 | Raw in the bucket, write-once | object count and bytes match; second upload fails | | BLOCKED: U1 and U3 missing |
| A7 | Jobs run in the cloud | four manual executions; forecast peak memory | | BLOCKED: U1 and U3 missing |
| A8 | Schedules | four ENABLED schedules, Asia/Seoul | | BLOCKED: U1 and U3 missing |
| A9 | Cutover complete | two cloud collects ok; local tasks Disabled; gap counts equal | | BLOCKED: U1 and U3 missing |
| A10 | Web live | `90_verify.ps1` every line OK | | BLOCKED: U1 and U3 missing |
| A11 | Screens on the deployed site | Playwright against the URL → exit 0 | | BLOCKED: U1 and U3 missing |
| A12 | No secret anywhere | three searches `no match`; git status empty | | BLOCKED: U1 and U3 missing |
| A13 | Values unchanged by the move | cloud and local recommendations for dates >= tomorrow match | | BLOCKED: U1 and U3 missing |

## Report

1. **Intent** — Steps 1 and 2 only. Raw snapshots can be written once to a `gs://` prefix, and the engine can read `ENGINE_ENV_FILE`. Cloud setup stopped because U1 and U3 are missing.

2. **Files** — `raw_gcs.py`, `raw_store.py`, `ingest_raw.py`, `settings.py`, `next.config.ts`, `scripts/cloud/00_check.ps1`, tests.

3. **Commands and exit codes** — A1 exit 0. `00_check.ps1` exit 1.

4. **Tests** — pytest 102 passed, 0 skipped, exit 0. ruff exit 0. Local collect ok 121, raw folder `data/raw/2026/10/02/1313`.

5. **Open facts** —
   - Present: U2, U4. Missing: U1 (no billed gcloud project), U3 (`.env.cloud` has none of `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_PROJECT_REF`, `GCP_PROJECT`, `SEOUL_API_KEY`, `KASI_API_KEY`, `ADMIN_TOKEN`).
   - No deployed URL, hosted database size, cloud job duration, or copy counts. Those steps were not run.

6. **Not done** — steps 3–10. BLOCKED on U1 and U3. Local tasks were not disabled.
