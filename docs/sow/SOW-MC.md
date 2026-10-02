# SOW-MC — Move to the cloud: hosted database, Cloud Run Jobs, GCS, Vercel

Everything runs on one laptop today, and it stops whenever the laptop sleeps (14 collect slots lost on 2026-10-02). This SOW moves the three parts to managed services without changing any computed value:

| Part | Local now | After this SOW |
|---|---|---|
| Database | local Supabase (Docker), 170 MB | hosted Supabase project, region Seoul |
| Engine jobs | Windows Task Scheduler | Cloud Run Jobs + Cloud Scheduler, `asia-northeast3` |
| Raw snapshots | `data/raw/` (70 MB) | GCS bucket, objects never overwritten |
| Web | `next dev` | Vercel, functions in `icn1` |

Not in this SOW: custom domain, CI, Google Maps (the map stays MapLibre + OpenFreeMap; the billing finding in `findings.md` is closed as "not needed"), `archive` to GCS (waits for the retention decision), running `tier_b` / `load_places` / `backfill` / training in the cloud (they need `geopandas` and `analysis/data`; they run on the laptop against the hosted database when needed).

## Inputs from the user (the implementer cannot do these; stop and list what is missing)

| # | Input | How the implementer checks it |
|---|---|---|
| U1 | Google Cloud project with billing enabled; `gcloud` installed and `gcloud auth login` done; `gcloud config set project <id>` | `gcloud config get-value project` prints an id; `gcloud billing projects describe <id> --format="value(billingEnabled)"` → `True` |
| U2 | Hosted Supabase project in **Northeast Asia (Seoul)**; `supabase login` done | `supabase projects list` shows it |
| U3 | `.env.cloud` at the repo root (gitignored by `.env.*`) with: `DATABASE_URL` (the **session pooler** connection string, port 5432: Cloud Run has no IPv6 route to the direct host), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_PROJECT_REF`, `GCP_PROJECT`, and the same `SEOUL_API_KEY`, `KASI_API_KEY`, `ADMIN_TOKEN` as `.env` | a script prints which names are present, never a value |
| U4 | `vercel login` done | `vercel whoami` |

If U1–U4 are not all present: do steps 1–2 (code and tests, no account needed), mark the rest `BLOCKED` with the missing input, and stop.

## Hard rules for this SOW

- A secret value never appears in a command line, a script, a log, the criteria file or the report. Values move from `.env.cloud` to Secret Manager and Vercel through stdin or a file read by the tool. Print names only.
- Every `gcloud` / `supabase` / `vercel` action is in a script under `scripts/cloud/` (PowerShell 5.1, ASCII, idempotent: a second run changes nothing and exits 0). No resource is created by hand.
- Nothing is deleted in the cloud by this SOW except what a script itself created in the same run and is replacing.
- The local stack keeps running until step 8 says to stop it. Never `supabase db reset`, locally or remotely.
- Bucket objects are write-once. The engine's service account cannot delete or overwrite them.

## Files you may touch

Create: `scripts/cloud/{00_check,10_gcp_setup,20_secrets,30_db_push,31_db_copy,40_raw_upload,50_engine_deploy,60_schedule,70_web_deploy,80_cutover,90_verify}.ps1`, `app/engine/raw_gcs.py`, `app/engine/tests/test_raw_gcs.py`, `app/web/vercel.json`, `docs/RUNBOOK.md`, `docs/tracking/criteria-mc.md`.
Edit: `app/engine/{raw_store,settings,__init__}.py`, `app/engine/jobs/{collect,ingest_raw}.py`, `app/engine/requirements.txt` (`google-cloud-storage` pinned), `app/engine/Dockerfile` (only if needed), `app/web/next.config.ts`, `.env.example`, `docs/LLM_PROJECT_MAP.md`, `docs/tracking/findings.md`.

## Steps

### 1 Raw snapshots can live in a bucket (code, no account needed)
- `RAW_DIR` may be a local path (as now) or `gs://<bucket>/<prefix>`. `raw_store.write` dispatches on the scheme; the GCS writer (`raw_gcs.py`) uploads with `if_generation_match=0`, so an existing object makes the write fail instead of replacing it. Same layout: `YYYY/MM/DD/HHMM/<code>.json.gz`.
- `ingest_raw` lists and reads from either kind.
- `collect` behaviour is otherwise unchanged: raw first, database second; database down → exit 1, raw kept.
- Tests with a fake storage client: object name layout; second write of the same name raises; `ingest_raw` reads what the writer wrote; a local `RAW_DIR` still works. No network in tests.

### 2 The engine can point at another env file (code)
`ENGINE_ENV_FILE=<path>` makes `settings.load_env` read that file instead of `.env` (default unchanged; `ENGINE_SKIP_DOTENV=1` still wins). This is how the laptop runs `tier_b`, `rejudge` or `ingest_raw` against the hosted database: `$env:ENGINE_ENV_FILE=".env.cloud"`. Test it.
`next.config.ts`: load `../../.env` only when the file exists (on Vercel it does not; the platform injects the variables).

### 3 GCP foundation — `10_gcp_setup.ps1`, `20_secrets.ps1`
- Enable APIs: Run, Cloud Scheduler, Artifact Registry, Secret Manager, Cloud Storage.
- Artifact Registry repo `urbanpulse` (Docker, `asia-northeast3`) with a cleanup policy keeping the 3 newest images.
- Bucket `gs://<project>-urbanpulse-raw` (`asia-northeast3`, uniform access, public access prevention on, **object versioning on**).
- Service accounts: `urbanpulse-engine` (runs the jobs) with `roles/secretmanager.secretAccessor` on the three secrets and, on the bucket, `roles/storage.objectCreator` + `roles/storage.objectViewer` (no delete, no overwrite); `urbanpulse-scheduler` with `roles/run.invoker` on the jobs.
- Secrets `urbanpulse-database-url`, `urbanpulse-seoul-api-key`, `urbanpulse-kasi-api-key`: created if absent; a new version is added only when the value differs from the latest (compare by hash inside the script; print `unchanged` / `updated`).

### 4 Database — `30_db_push.ps1`, `31_db_copy.ps1`
1. `supabase link --project-ref <ref>`; `supabase db push` (the three migrations). Run the pgTAP file against the hosted database only if it needs no fixture writes that would stay; otherwise check with: 19 tables exist, RLS enabled on all, `anon` has no grant.
2. Copy data once, **before** any cloud job is scheduled: `pg_dump --data-only --no-owner --schema=public` from the local database (run it inside the local Postgres container so the client version matches), restore into the hosted one in a single transaction. Order by foreign keys (`places` first). If the hosted `public` tables are not all empty, stop: never merge by hand.
3. Compare: for every table, row count local at dump time = hosted after restore; `max(ts)` of `live_obs` equal. Paste the table of counts.
4. Report the hosted database size (`pg_database_size`). The free plan holds 500 MB; today's data is about 170 MB. Do not change the plan; report the number.

### 5 Raw upload — `40_raw_upload.ps1`
`gcloud storage rsync data/raw gs://<bucket>/raw --recursive` (no `--delete-unmatched-destination-objects`). Compare object count and total bytes with the local folder.

### 6 Engine image and jobs — `50_engine_deploy.ps1`
- Build with the existing Dockerfile, tag `asia-northeast3-docker.pkg.dev/<project>/urbanpulse/engine:<git short sha>`, push. The working tree must be clean; the script refuses otherwise.
- Cloud Run Jobs, all with service account `urbanpulse-engine`, secrets mounted as env (`DATABASE_URL`, `SEOUL_API_KEY`, `KASI_API_KEY`), `RAW_DIR=gs://<bucket>/raw`, `TZ=Asia/Seoul`, `max-retries=0` (a retry would write a second run folder; the next slot is the retry):

| Job | Args | CPU / memory | Timeout |
|---|---|---|---|
| `urbanpulse-healthcheck` | `healthcheck` | 1 / 512Mi | 5m |
| `urbanpulse-collect` | `collect` | 1 / 1Gi | 10m |
| `urbanpulse-forecast` | `forecast` | 2 / 4Gi | 30m |
| `urbanpulse-evaluate` | `evaluate` | 1 / 1Gi | 20m |
| `urbanpulse-sync-holidays` | `sync_holidays` | 1 / 512Mi | 10m |
| `urbanpulse-ingest-raw` | `ingest_raw` (date passed with `--args` at execution) | 1 / 1Gi | 20m |

- Execute once, by hand through the script, in this order and stop at the first failure: `healthcheck` → `collect` → `forecast` → `evaluate`. `healthcheck` proves the Seoul API (plain HTTP on port 8088), KASI and the database are reachable from the region. If memory or time is short for `forecast`, raise the job's limits and report the peak; do not change code.

### 7 Schedules — `60_schedule.ps1`
Cloud Scheduler, time zone `Asia/Seoul`, OAuth with `urbanpulse-scheduler`: collect `*/30 * * * *`; forecast `0 5 * * *`; evaluate `0 6 * * *`; sync-holidays `0 4 * * 1`. No schedule for `ingest-raw`, `healthcheck`, `archive`, `tier_b`, `rejudge`.

### 8 Cutover — `80_cutover.ps1`
The laptop keeps collecting into `data/raw/` and the local database through steps 3–7, so the hosted database is missing everything after the dump. Close the gap, then stop the laptop:
1. Confirm two consecutive scheduled cloud `collect` executions ended `ok` (`job_runs` in the hosted database).
2. Disable (do not delete) the three local tasks `UrbanPulse collect|forecast|evaluate`.
3. Run step 5's rsync again (uploads the folders written since).
4. Execute `urbanpulse-ingest-raw` for each KST date from the dump date to today. It is idempotent; folders the cloud wrote itself are simply re-read.
5. Execute `urbanpulse-forecast` once so today's rows are built from the complete data.
6. Check: hosted `live_obs` has every observation time the local database has for the gap period (paste both distinct-`ts` counts).
Leave the local Supabase stack installed and stopped (`supabase stop`); its data is the rollback copy.

### 9 Web — `70_web_deploy.ps1`, `app/web/vercel.json`
- `vercel link` with root directory `app/web`; `vercel.json`: `"regions": ["icn1"]`.
- Production env (added through stdin, names only printed): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ADMIN_TOKEN`. Nothing with `NEXT_PUBLIC_`.
- Response header `X-Robots-Tag: noindex` on every route (in `next.config.ts`). The service is not announced yet; the designer removes it at launch.
- `vercel deploy --prod`. The MapLibre worker route (`/vendor/maplibre/[file]`) and the Pretendard font must work in the build output; check them on the deployed URL, not only locally.
- Git integration (auto-deploy on push) is not set up here.

### 10 Verify and document — `90_verify.ps1`, `docs/RUNBOOK.md`
- `90_verify.ps1 <url>` prints one line per check: every API route of SOW-M4 step 2 → 200 with its top-level keys; `/ko`, `/en`, `/ko/map` → 200; `/admin/eval` 404 without the token and 200 with it; the worker file → 200 with a JavaScript content type; latest `job_runs` row per job with status and age; newest `live_obs.ts` age under 60 minutes; object count under today's raw prefix.
- Run the Playwright live smoke and `visual.spec.ts` against the deployed URL (`PLAYWRIGHT_BASE_URL`), mobile viewport.
- Secrets: the service-role key, the database URL, the admin token and the two API keys do not occur in `app/web/.next/static`, in the deployed page sources fetched by the verify script, or in `git grep`. Print `no match` only.
- `docs/RUNBOOK.md` (English, for an agent or the user): how to deploy a new engine image, redeploy the web, run a job by hand, read a job's logs, re-ingest a date, run a laptop-only job against the hosted database with `ENGINE_ENV_FILE`, rotate a secret, pause all schedules, roll back to the laptop (re-enable the three tasks, `supabase start`), and what each recurring cost is (Cloud Run, Scheduler jobs, Artifact Registry storage for an ~870 MB image, GCS, Supabase plan).
- `findings.md`: close the Google Maps billing row; add "no alert when a cloud job fails; `/admin/eval` is the only place it shows" with why-not-now (needs a notification channel the user owns).

## Acceptance (`docs/tracking/criteria-mc.md`, rows created before step 1)

| # | Criterion | Command |
|---|---|---|
| A1 | Code changes are safe locally | `python -m pytest app/engine/tests -q` → exit 0, 0 skipped; `ruff check app/engine` → exit 0; local `python -m engine collect` with the local `RAW_DIR` → `ok ≥ 100` |
| A2 | Inputs present | `scripts/cloud/00_check.ps1` → exit 0, lists U1–U4 as present (names only) |
| A3 | Scripts idempotent | each of `10`, `20`, `30`, `50`, `60` run a second time → exit 0 and reports no change |
| A4 | Schema on the hosted database | 19 public tables; RLS enabled on all; `select count(*) from information_schema.role_table_grants where grantee in ('anon','authenticated') and table_schema = 'public'` → 0 |
| A5 | Data copied | the per-table count comparison of step 4.3, all equal; hosted database size pasted |
| A6 | Raw in the bucket, write-once | object count and bytes equal the local folder at upload time; as `urbanpulse-engine`, a second upload of an existing object name fails (paste the error class, not a URL) |
| A7 | Jobs run in the cloud | the four manual executions succeeded; paste status and duration of each and the peak memory of `forecast` |
| A8 | Schedules | `gcloud scheduler jobs list --location asia-northeast3` shows the four schedules, time zone Asia/Seoul, state ENABLED |
| A9 | Cutover complete | two scheduled cloud collects `ok`; the three local tasks `Disabled`; the gap comparison of step 8.6 equal |
| A10 | Web live | `scripts/cloud/90_verify.ps1 <url>` → every line OK (paste the output; it contains no secret) |
| A11 | Screens on the deployed site | Playwright live smoke and visual spec against the URL → exit 0 |
| A12 | No secret anywhere | the three searches of step 10 → `no match`; `git status --short` → empty |
| A13 | Values unchanged by the move | for the same `today`, `recommendations` (excluding `generated_at`) built by the cloud forecast equals the local rebuild from the same data: run local `forecast` with `ENGINE_ENV_FILE` unset right before cutover step 2 and compare a dump of both for dates ≥ tomorrow. Differences → list the first ten, do not adjust |

## Open facts to report

- Hosted database size and how far it is from 500 MB; the growth per day measured from `live_obs` + `commerce_obs` + raw-independent tables.
- Durations and peak memory of each cloud job; the image size pushed.
- The deployed URL.
- Anything the Seoul API or KASI did differently from a cloud address.
- What a day of this costs by the pricing pages you can read (state the assumptions); if you cannot establish a number, say so rather than estimate.
