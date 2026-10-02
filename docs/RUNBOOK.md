# UrbanPulse runbook

How to move the system to the cloud and how to operate it there. Every command runs from the repo root in
PowerShell 5.1. Cloud scripts live in `scripts/cloud/`, read `.env.cloud` (gitignored) and never print a value.
Add `-Plan` to any script to see its steps without running them.

Status on 2026-10-02: steps 0–2 below are rehearsed end to end against local stand-ins
(`scripts/cloud/rehearse.ps1`). The `gcloud` and `vercel` calls in 10, 20, 40, 50, 60, 70 and 80 have only been
parsed and plan-run: no cloud account existed. Expect to fix a flag or two on the first real run, and record it here.

## 0 Before the first cloud run (the user)

1. Supabase: create project `urbanpulse`, region Northeast Asia (Seoul). Never use another project of the account.
2. Google Cloud: create a project with billing; install `gcloud`; `gcloud auth login`; `gcloud config set project <id>`.
3. Fill `.env.cloud`: `DATABASE_URL` (the **session pooler** string, port 5432, password percent-encoded),
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_PROJECT_REF`, `GCP_PROJECT`. The other three are filled.
4. `powershell -File scripts/cloud/00_check.ps1` must exit 0 (U1–U4 `present`).
5. Turn off laptop sleep until the cutover is done; a sleeping laptop collects nothing.

## 1 Rehearse (no account needed, about 4 minutes)

```
powershell -File scripts/cloud/rehearse.ps1
```

It builds the engine image, starts a throwaway Postgres (same image as the local stack) and a fake bucket, pushes
the migrations, copies the data, runs `healthcheck`, `collect`, `forecast`, `evaluate`, `ingest_raw` in the image
under the Cloud Run limits, checks that an existing raw object is not replaced, and compares the recommendations
with a Windows run on the same data. It ends with `0 failed` and removes everything it started. Run it after any
change to the engine, the migrations or the scripts, before touching the cloud.

## 2 Move (in this order; each script can be rerun)

| Step | Command | Ends with |
|---|---|---|
| Foundation | `scripts/cloud/10_gcp_setup.ps1` | APIs on, image repository, bucket (versioned, no public access), two service accounts |
| Secrets | `scripts/cloud/20_secrets.ps1` | three secrets; `unchanged` or `updated` per name |
| Schema | `scripts/cloud/30_db_push.ps1` | `schema OK` (same tables as local, RLS on all, no anon grant) |
| Data | `scripts/cloud/31_db_copy.ps1` | a count table with every row equal, `copy OK`, the database size |
| Raw | `scripts/cloud/40_raw_upload.ps1` | bucket object count and bytes at least the local ones |
| Engine | `scripts/cloud/50_engine_deploy.ps1 -Execute` | six jobs deployed; `healthcheck`, `collect`, `forecast`, `evaluate` executed once |
| Schedules | `scripts/cloud/60_schedule.ps1` | four triggers, Asia/Seoul, ENABLED |
| Cutover | `scripts/cloud/80_cutover.ps1 -Since <date of the data copy>` | local tasks disabled, gap closed, recommendations equal |
| Web | `scripts/cloud/70_web_deploy.ps1` | the deployment URL |
| Verify | `scripts/cloud/90_verify.ps1 -Url <url>` | every line `OK`, `0 failed` |

Rules that are easy to break:
- Copy the data **before** any schedule exists. `31_db_copy` refuses a target that already holds rows; it never merges.
- The tree must be clean for `50_engine_deploy`: the image tag is the commit.
- Do not schedule anything twice: the laptop tasks stay on until `80_cutover` disables them, and the cloud
  `collect` writing the same observation is harmless (same key), but two `forecast` runs are wasted work.
- Never `supabase db reset`, locally or remotely.

Expected on the first real run (from a documentation review, 2026-10-02; none of it was executed):
- Cloud Scheduler needs its own service agent role in the project; triggers fail without it. If a trigger
  fails with a permission error, grant the role the error names, then rerun `60_schedule.ps1`.
- `vercel link --yes` stops asking which team to use from CLI 55 on; with more than one team add
  `--scope <team>` in `70_web_deploy.ps1`.
- Artifact Registry applies a cleanup policy about a day after it is set, and may count one pushed image as
  several versions; check that three images really remain after the fourth deploy.
- `80_cutover` passes `--args "ingest_raw,--date,<day>"`; no documented example has a later element
  starting with `--`. If it is rejected, use `--args=ingest_raw --args=--date --args=<day>`.

## 3 Operate

| Need | Do |
|---|---|
| New engine code | commit, `rehearse.ps1`, then `50_engine_deploy.ps1` (jobs take the new tag) |
| New web code | `70_web_deploy.ps1`, then `90_verify.ps1 -Url <url>` |
| Run a job by hand | `gcloud run jobs execute urbanpulse-<job> --region asia-northeast3 --wait` |
| Read a job's log | `gcloud run jobs executions list --job urbanpulse-<job> --region asia-northeast3`, then `gcloud beta run jobs executions logs read <execution> --region asia-northeast3` |
| Is it healthy | `/admin` on the site (token form) → jobs table; or `python scripts/cloud/dbtool.py last-runs --target-env .env.cloud --job collect --count 2` |
| Re-ingest a date | `gcloud run jobs execute urbanpulse-ingest-raw --region asia-northeast3 --args "ingest_raw,--date,YYYY-MM-DD" --wait` (idempotent) |
| Laptop-only job against the hosted database (`tier_b`, `rejudge`, `load_places`, `backfill`, training) | `$env:ENGINE_ENV_FILE=".env.cloud"; python -m engine <job>; Remove-Item Env:ENGINE_ENV_FILE` |
| Rotate a secret | change the value in `.env.cloud`, `20_secrets.ps1` (prints `updated`), then `50_engine_deploy.ps1`; for `ADMIN_TOKEN` or the service-role key, `70_web_deploy.ps1` |
| Pause everything | `60_schedule.ps1 -Pause`; resume with `-Resume` |
| Roll back to the laptop | `60_schedule.ps1 -Pause`; `cd app; supabase start`; `Enable-ScheduledTask` for `UrbanPulse collect`, `UrbanPulse forecast`, `UrbanPulse evaluate`; `python -m engine ingest_raw --date <each missed day>` after downloading the bucket's folders for those days into `data/raw` |
| Launch publicly | remove the `X-Robots-Tag` header in `app/web/next.config.ts` and redeploy |

## 4 What the rehearsal measured (2026-10-02, laptop, 2 CPU limit)

| Job | Time | Peak memory | Cloud Run limit |
|---|---|---|---|
| healthcheck | 3 s | 101 MB | 512Mi |
| collect | 8 s | 167 MB | 1Gi |
| forecast | 49 s | 323 MB | 4Gi |
| evaluate | 8 s | 154 MB | 1Gi |
| ingest_raw (one folder) | 3 s | 116 MB | 1Gi |

Database after the copy: 150 MB (free plan holds 500 MB). Engine image: about 930 MB.
The forecast limit is far above the peak; lower it only after a cloud run confirms the number.

## 5 Recurring cost (what to look at, not a quote)

Cloud Run Jobs bill CPU and memory for the seconds a job runs: 48 collects, one forecast and one evaluate a day
is a few minutes of one or two CPUs. Cloud Scheduler bills per trigger (four). Artifact Registry bills the stored
image (three tags kept, about 0.9 GB each). GCS bills the raw objects (about 70 MB on 2026-10-02, growing with
every collect) and their versions. Supabase and Vercel are on their free plans until a limit is hit: the database
size against 500 MB is the one to watch. No figure here was read from a bill; check the billing page after the
first week.

## 6 Known gaps

- No alert when a cloud job fails; the jobs table on `/admin` is the only place it shows.
- Place names have no English version (`name_en` is null).
- Hours that were never collected are not marked on any screen.
