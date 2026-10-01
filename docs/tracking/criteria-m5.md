# criteria-m5 — Evaluate, rejudge, archive, admin

Written 2026-10-01 before implementation. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Evaluate runs | `python -m engine evaluate` → exit 0 or warn; paste `job_runs.detail`. Row counts may be 0 when no log row targets yesterday yet; report the counts, do not backfill them | 0 | detail `date=2026-09-30`, `eval_daily` 0, `reco_eval_daily` 0, `strip_eval_daily` 0, `unscored` 0, `warn_skipped` `fewer than 14 days` |
| A2 | Evaluate is idempotent | run again → the three tables' counts for that date are unchanged | 0 | second run exit 0; all three counts stayed 0 |
| A3 | Re-judge prints without changing flags | `python -m engine rejudge` → exit 0; table pasted (every combination `insufficient` is the expected outcome this early); `git diff --stat app/engine/config/feature_flags.yaml` → empty | 0 | all 18 `a1` and `a1_foreign` lines printed `insufficient`; flag diff empty |
| A4 | Archive dry run | `python -m engine archive --dry-run` → exit 0; candidate counts pasted; `select count(*) from live_obs` and `commerce_obs` unchanged; no file under `data/archive/` | 0 | `live_obs` 128863, `commerce_obs` 82369, `forecast_log` 0; table counts stayed 358102 and 227508; `data/archive` absent |
| A5 | No archive task | `Get-ScheduledTask 'UrbanPulse archive' -ErrorAction SilentlyContinue` → nothing | 0 | no task |
| A6 | Evaluate scheduled | `Get-ScheduledTask 'UrbanPulse evaluate'` → daily 06:00, battery settings as collect | 0 | start 2026-10-01T06:00:00+09:00; DisallowStartIfOnBatteries False; StopIfGoingOnBatteries False; StartWhenAvailable True |
| A7 | Admin page guarded | `curl -s -o NUL -w "%{http_code}" http://localhost:3000/admin/eval` → 404; with the token (read from `.env` by the script, never echoed) → 200 | 0 | no token 404; token present 200. Token value not printed |
| A8 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0; `cd app/web; npm run lint; npm run build; npx playwright test` → exit 0 | 0 | engine 73 passed; ruff clean; web lint clean; build exit 0; playwright 11 passed |
| A9 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match; the admin token value does not occur in `app/web/.next/static` (script prints `no match`) | 1 | `git grep` no match; static scan `no match` |

## Report

1. **Intent** — SOW-M5 scores yesterday's logs, prints a re-judge without changing flags, and dry-runs the archive. The admin page is English and hidden unless `ADMIN_TOKEN` is set.

2. **Files** — created: `app/engine/jobs/{evaluate,rejudge,archive}.py`, `app/engine/judge.py`, `scripts/register_evaluate_task.ps1`, `app/engine/tests/test_{evaluate,judge,archive}.py`, `app/web/src/app/admin/eval/page.tsx`, `app/web/e2e/admin.spec.ts`, `docs/tracking/criteria-m5.md`. Modified: `app/engine/__main__.py`, `docs/tracking/findings.md`, `docs/LLM_PROJECT_MAP.md`, `docs/tracking/criteria-m4.md` (later smoke).

3. **Commands and exit codes** — table above.

4. **Tests** — engine pytest 73 passed, exit 0. ruff exit 0. Playwright 11 passed, exit 0.

5. **Open facts** —
   - `forecast_log` and `recommendation_log` were first written on 2026-10-01 for later dates, so yesterday 2026-09-30 has no rows to score. The first date that can fill `eval_daily` is the first logged target date, 2026-10-02.
   - Archive candidates older than the cuts: `live_obs` 128863, `commerce_obs` 82369, `forecast_log` 0. Nothing was deleted. `docs/tracking/findings.md` records that deleting old commerce would starve the holiday activity profile.
   - `ADMIN_TOKEN` is empty. `/admin/eval` returns 404 with no token and would return 404 for any token until one is set. The value was not printed.
   - pandas warned that `read_sql_query` on a psycopg connection is not the supported path. The rejudge table still printed and the flag file did not change.

6. **Not done** — the admin 200 response. It needs a non-empty `ADMIN_TOKEN`.
