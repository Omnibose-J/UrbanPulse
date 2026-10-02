# SOW-L1 — Finish locally, so that the cloud move is "run the scripts"

The user postponed the cloud accounts (2026-10-02). Everything SOW-MC needs that does not need an account is built and
rehearsed now, against local stand-ins, and the deferred product items that block a public URL are closed.
Implemented by the designer (Claude) directly. No cloud account is touched by this SOW.

## Stand-ins used for the rehearsal

| Cloud part | Stand-in | Lifetime |
|---|---|---|
| Hosted Supabase database | a throwaway container of the same Postgres image as the local stack (`urbanpulse-rehearsal-db`) | created and removed by the rehearsal script |
| GCS bucket | `fsouza/fake-gcs-server` container (`urbanpulse-rehearsal-gcs`), reached through `STORAGE_EMULATOR_HOST` | same |
| Cloud Run Job | the engine image run with `docker run --memory 4g --cpus 2` | per run |
| Vercel | `next build` + `next start` (production mode) | per run |

The rehearsal never writes the live local tables, `data/raw/`, or the `localsync` stack.

## Part A — cloud scripts and their rehearsal

- A1 `scripts/cloud/_lib.ps1`: read an env file into a hashtable without printing; run-or-plan helper. Every script
  takes `-EnvFile` (default `.env.cloud`) and `-Plan` (print each action as a name, run nothing, exit 0).
- A2 `00_check.ps1`: U2 is present only when `SUPABASE_PROJECT_REF` occurs in `supabase projects list`.
- A3 Scripts `10_gcp_setup`, `20_secrets`, `30_db_push`, `31_db_copy`, `40_raw_upload`, `50_engine_deploy`,
  `60_schedule`, `70_web_deploy`, `80_cutover`, `90_verify` as SOW-MC steps 3–10 describe. ASCII, PowerShell 5.1.
- A4 Database work is Python, not `pg_dump` on a command line: `scripts/cloud/dbtool.py`
  (`check-schema`, `copy`, `compare`, `recos-diff`). `copy` refuses a target whose public tables are not all empty,
  copies in foreign-key order in one transaction with `COPY`, and resets sequences. URLs are read from env files.
- A5 `scripts/cloud/verify.py <url>`: the checks of SOW-MC step 10, one line each, exit 1 on any failure; no secret
  in its output.
- A6 `scripts/cloud/rehearse.ps1`: start the stand-ins, push the migrations, copy the data, run
  `healthcheck → collect → forecast → evaluate → ingest_raw` in the engine container against them, compare
  recommendations with the live local database, remove the stand-ins.
- A7 `app/web/vercel.json` (`icn1`); `X-Robots-Tag: noindex` on every route.
- A8 `docs/RUNBOOK.md`.

## Part B — product items that should not go public as they are

- B1 The admin token leaves the query string: `/admin` takes the token in a form, `POST /admin/session` sets an
  httpOnly, SameSite=Strict cookie (Secure in production); `/admin/eval` answers 404 without a valid cookie.
- B2 `middleware.ts` → `proxy.ts` (Next 16 name).
- B3 In-app navigation uses client-side links instead of full page loads.
- B4 Map: the legend, the card and the attribution do not cover each other on a phone. (The first place in the list stays selected on load: the spec's layout always has a card. Whether nothing should be selected is a design question, not changed here.)
- B5 Playwright can run against the production build (`PLAYWRIGHT_BASE_URL`), and does so in the gate.

## Not in this SOW

Any `gcloud` / hosted Supabase / Vercel action; English place names (no local source; needs the place-list file or
the `DATA_GO_KR_KEY` API); the collection-gap marker and archive retention (design decisions); alerts on job failure;
E6 and the weekly rejudge (wait for October data).

## Acceptance

`docs/tracking/criteria-l1.md`.
