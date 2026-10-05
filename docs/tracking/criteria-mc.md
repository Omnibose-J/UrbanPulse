# criteria-mc — Move the running system to managed services

Written 2026-10-02 before step 1; result cells filled 2026-10-05 after running each command. No value of any
secret appears here. Accounts: GCP `urbanpulse-sbj` (sobeomjin@gmail.com, billing linked), Supabase `urbanpulse`
(Seoul, free plan, imsw000111), Vercel `urbanpulse` (team `imsw`).

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Code changes are safe locally | pytest, ruff, local collect `ok >= 100` | 0 | 2026-10-02: pytest 102 passed, 0 skipped; ruff clean; collect ok 121. Unchanged code since (image tag 0510acf) |
| A2 | Inputs present | `scripts/cloud/00_check.ps1` | 0 | `U1 present`, `U2 present`, `U3 present` (all eight names), `U4 present` |
| A3 | Scripts idempotent | second run of 10, 20, 30, 50, 60 | 0 | 10: every resource `exists`; 20: three secrets `unchanged`; 30: `Remote database is up to date`, `schema OK`; 50: `exists image engine:0510acf`, jobs redeployed with the same spec; 60: four triggers `update`, state unchanged |
| A4 | Schema on the hosted database | 19 tables, RLS on all, anon/authenticated grants 0 | 0 | `tables 19 (source 19)`, `missing [] extra []`, `without_rls []`, `anon_authenticated_grants 0` |
| A5 | Data copied | per-table counts equal; hosted size pasted | 0 | all 19 rows equal (live_obs 373348, commerce_obs 236499, forecast_hourly 70656, recommendations 12768, tier_b_profile 17784, city_fcst 12221, forecast_log 14982, lively_profile 7848, recommendation_log 1534, similar_places 780, places 368, level_thresholds 121, job_runs 118, holidays 102, lively_norm 82, model_registry 1, three eval tables 0); live_obs max(ts) equal (2026-10-05 12:00 UTC); size 160 MB after the copy, 184 MB after the first cloud day |
| A6 | Raw in the bucket, write-once | object count and bytes match; second upload fails | 0 | after the cutover rsync: bucket 18261 objects / 210,344,834 bytes vs local 18140 / 208,964,159 (the surplus is what the cloud `collect` wrote itself). Engine account holds only `roles/storage.objectCreator` + `objectViewer` on the bucket (IAM policy read back); the write-once path (`if_generation_match=0`) raised on an existing name in the rehearsal (`OK an existing object is not replaced`) |
| A7 | Jobs run in the cloud | four manual executions; forecast peak memory | 0 | healthcheck-fjpgg 15 s, collect-gd5nv 29 s, forecast-cf7d4 89 s, evaluate-5j9ns 33 s, all `succeededCount 1`. Memory utilization upper bounds from Cloud Monitoring: forecast ≤ 8 % of 4Gi (about 330 MB; rehearsal measured 344 MB), collect ≤ 17 % of 1Gi, healthcheck ≤ 17 % of 512Mi, ingest-raw ≤ 16 % of 1Gi; the evaluate series had not landed when read |
| A8 | Schedules | four ENABLED schedules, Asia/Seoul | 0 | `gcloud scheduler jobs list --location asia-northeast3`: collect `*/30 * * * *`, forecast `10 5 * * *`, evaluate `0 6 * * *`, sync-holidays `0 4 * * 1`, all `Asia/Seoul`, `ENABLED` |
| A9 | Cutover complete | two cloud collects ok; local tasks Disabled; gap counts equal | 0 | scheduled cloud collects 22:00 and 22:30 KST `ok`; `UrbanPulse collect|forecast|evaluate` → `Disabled`; `distinct ts since 2026-10-05: source 45 target 46 missing_in_target 0` |
| A10 | Web live | `90_verify.ps1 <url>` every line OK | 0 | https://urbanpulse-swart.vercel.app — 25 lines OK, `0 failed` (8 API routes with their keys, four pages 200 + noindex, worker JS 200, admin 404/303/200, collect 10 min, forecast 2 min, evaluate 43 min, newest observation 40 min, 5566 raw objects today, three secret searches `no match`) |
| A11 | Screens on the deployed site | Playwright live smoke and visual spec against the URL | 1 | `PLAYWRIGHT_BASE_URL=<url> npx playwright test e2e/screens.spec.ts e2e/visual.spec.ts -g ...`: live smoke passed, visual 5 of 6 passed. The one failure (`week cards show one range and even rows`, English, POI008) is a 4 px text overflow of "10 AM to 12 PM" in the 104 px cell with Pretendard loaded — a content/layout defect independent of the move, recorded in `findings.md` 2026-10-05 |
| A12 | No secret anywhere | three searches `no match`; git status empty | 0 | `served pages and API bodies - no match`, `app/web/.next/static - no match`, `git grep - no match`; `git status --short` empty after the docs commit |
| A13 | Values unchanged by the move | cloud and local recommendations for dates >= tomorrow match | 0 | rehearsal: `recommendations from today+1: left 11172 target 11172 differing 0` (same data, all columns); cutover: `recommendations from today+2: left 9576 target 9576 differing 0` (`alt_dates` excluded across two collectors) |

## Report

1. **Intent** — Steps 3–10 of SOW-MC executed for real on 2026-10-05 (steps 1–2 were done on 2026-10-02). The
   system now runs on hosted Supabase, Cloud Run Jobs + Cloud Scheduler, GCS and Vercel; the laptop's three tasks
   are disabled and its Supabase stack is stopped as the rollback copy.

2. **Files** — `docs/RUNBOOK.md` (status, log command, observed first-run facts), `docs/tracking/findings.md`
   (one row), `app/web/.gitignore` (`.vercel`, added by `vercel link`), this file. No source change; the
   deployed image is commit 0510acf.

3. **Commands and exit codes** — `00_check` 0; `rehearse` 0 (`0 failed`); `10` 0 (second run 0); `20` 0 (0);
   `30` 0 (0); `31` 0; `40` 0; `50 -Execute` 0 (second run 0); `60` 0 (0); `70` 0; `80 -Since 2026-10-05` 0;
   `90` 0; Playwright 1 (A11).

4. **Open facts** —
   - Hosted database 184 MB of the 500 MB free plan; `live_obs` 0.31 MB/day and `commerce_obs` 0.58 MB/day over
     145 collected days, so about 0.9 MB/day for the observation tables before index growth (roughly a year of
     headroom at this rate; the forecast tables are rebuilt daily and do not grow).
   - Cloud job durations: healthcheck 15 s, collect 29 s, forecast 89 s (manual) / 93 s (cutover), evaluate 33 s,
     ingest_raw for one day (45 folders) 5 min — slower than the laptop's 3 s per folder; fine for a by-hand job.
     Image: one tag in the repository, digest sha256:fbec520b…; the registry does not print a size per tag.
   - Deployed URL: https://urbanpulse-swart.vercel.app (functions in `icn1`, `X-Robots-Tag: noindex`).
   - The Seoul API and KASI answered from the region exactly as from the laptop: `collect` 121/121 ok, no
     different behaviour observed.
   - Cost: no figure was read from a bill. Free plans for Supabase and Vercel; Cloud Run, Scheduler, Artifact
     Registry and GCS are billed to the linked account — check the billing page after the first week.
   - Deviations from the SOW text: `urbanpulse-sw` (imsw000111, no billing) and `urbanpulse-skku` (school
     account, billing blocked) exist as empty projects; the Supabase project was created through the Management
     API because the CLI takes the password only as a flag.

5. **Not done** — A11's one visual failure (a product decision, in `findings.md`); the Artifact Registry
   cleanup-policy check waits for the fourth deploy; the `evaluate` memory figure was not yet in Monitoring.
