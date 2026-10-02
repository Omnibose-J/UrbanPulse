# criteria-l1 — Finish locally, so that the cloud move is "run the scripts"

Written 2026-10-02 before any work. Result cells were filled only after running the command.
Implemented by the designer (Claude) directly.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Every cloud script parses and is ASCII | PowerShell parser over `scripts/cloud/*.ps1` → 0 errors; non-ASCII byte count 0 | 0 | 13 files, `parse_errors=0 non_ascii=0` each |
| A2 | Plan mode runs every script without any cloud tool and prints no secret | each script with `-Plan -EnvFile <fake env>` → exit 0; none of the env values occurs in the output | 0 | 10 scripts exit 0 with `gcloud` not installed; 6 marker values searched in the output, 0 hits |
| A3 | `00_check` ties U2 to the project ref and fails when something is missing | run against `.env.cloud` as it is → exit 1, U2 missing | 1 (expected) | `U1 missing`, `U2 missing`, `U3 missing` (5 names), `U4 present` |
| A4 | Schema lands on an empty Postgres as on a hosted project | `30_db_push.ps1 -EnvFile .env.rehearsal` (inside `rehearse.ps1`) | 0 | 3 migrations applied; `tables 19 (source 19)`, `without_rls []`, `anon_authenticated_grants 0`, `schema OK`; second run applies nothing |
| A5 | Data copy is complete and refuses a non-empty target | `31_db_copy.ps1`, then `dbtool.py copy` again | 0, then 1 (expected) | 19 tables, every count equal (`live_obs` 362,579; `commerce_obs` 230,265); `max(ts)` equal; target 150 MB; second copy: `target is not empty … Nothing was copied` |
| A6 | The engine image runs the jobs against the stand-ins inside the Cloud Run limits | container `healthcheck`, `collect`, `forecast`, `evaluate`, `ingest_raw` | 0 each | healthcheck 3 s / 101 MB; collect 8 s / 167 MB, ok 121; forecast 49 s / 323 MB of 4Gi, 2 CPU; evaluate 8 s / 154 MB; ingest_raw 3 s / 116 MB |
| A7 | Raw objects are write-once through the real client | `rehearse_write_once.py` in the image; bucket listing | 0 | `second PreconditionFailed`, `kept [('ONCE', {'written': 1})]`; 121 collect objects in the bucket; `ingest_raw` read them |
| A8 | Values unchanged by the move | `dbtool.py recos-diff --against <saved>` (same data, image vs Windows, from tomorrow); `recos-diff` stand-in vs live (from today+2) | 0, 0 | same data: 11,172 rows, 0 differing, every column; vs live: 9,576 rows, 0 differing, every column except `alt_dates` (see open facts) |
| A9 | The rehearsal leaves nothing behind and does not touch live data | end of `rehearse.ps1` | 0 | `runs of [healthcheck, forecast, evaluate, ingest_raw] since <start> UTC: 0` on the live ledger; no `urbanpulse-rehearsal*` container; `.env.rehearsal` gone; the containers have no mount, so `data/raw` cannot be written |
| A10 | The verify script passes on the production build and fails on a broken target | `verify.py http://localhost:3100 --env-file .env`; same against a closed port | 0, then 1 (expected) | 25 lines OK, `0 failed`; closed port: `16 failed` |
| A11 | noindex and region are set | `curl -I` on `/ko`, `/api/health`, the worker file; `vercel.json` | 0 | `X-Robots-Tag: noindex` on all three; worker `200 application/javascript`; `"regions": ["icn1"]` |
| B1 | The admin token is never in a URL | `e2e/admin.spec.ts`; `admin-session.test.ts` | 0 | no cookie → 404; `?token=<right>` → 404; wrong token stays on `/admin` with no cookie; right token → `/admin/eval`, no query; cookie httpOnly, SameSite=Strict, path `/admin`, does not contain the token |
| B2 | `proxy.ts` replaces `middleware.ts` | `npm run build`; `states.spec` "the bare address goes to the visitor's language" | 0 | build prints `ƒ Proxy (Middleware)`, 0 lines matching `deprecat`; `en` → `/en`, `ko` → `/ko`, `fr` → `/ko`, each 307 |
| B3 | Navigation does not reload the page | `journey.spec` | 0 | a value set on `window` at home is still there on the day screen after search → week → day |
| B4 | Map legend, card and credit do not cover each other on a phone | `map.spec` "the legend, the card and the map credit…" | 0 | passes with the credit at bottom right; fails (`legend over credit`) when it is put back at top right |
| B5 | Suite passes on the production build | `PLAYWRIGHT_BASE_URL=http://localhost:3100 npx playwright test`, three runs; default (dev server) once | 0 | 49 passed ×3 on the production build (32–43 s); 49 passed on a fresh dev server |
| G1 | Engine gates | `python -m pytest app/engine/tests -q`; `ruff check app/engine scripts/cloud` | 0 | 137 passed; `All checks passed!`. No pytest file was written under `scripts/cloud`: `dbtool.py` and `verify.py` are proven by the rehearsal and by A10, not by unit tests |
| G2 | Web gates | `npm run lint`; `npm test`; `npm run build` | 0 | lint clean; 27 pass; build compiled |
| G3 | Live system still healthy | `python -m engine collect`; `forecast`; `integrity --full` | 0 | collect ok 121; forecast done, 121 places; integrity `found: 0` |
| G4 | No secret, clean tree | search for the five env values in tracked and new files; `git status --short` | 0 | `no match`; tree clean after the commit |

## Report

1. **Intent** — The user postponed the cloud accounts and asked for everything to be finished locally so that the
   later move is only a matter of running it. Every SOW-MC script now exists; the database, engine and raw-object
   parts were rehearsed against local stand-ins; the web runs and is tested in production mode; the admin token no
   longer travels in an address.

2. **Files** — New: `scripts/cloud/{_lib,10_gcp_setup,20_secrets,30_db_push,31_db_copy,40_raw_upload,50_engine_deploy,60_schedule,70_web_deploy,80_cutover,90_verify,rehearse}.ps1`,
   `scripts/cloud/{dbtool,verify,rehearse_write_once}.py`, `scripts/cloud/ar_cleanup_policy.json`, `docs/RUNBOOK.md`,
   `docs/sow/SOW-L1.md`, `app/web/vercel.json`, `app/web/scripts/copy-maplibre.mjs`, `app/web/src/app/admin/page.tsx`,
   `app/web/src/app/admin/session/route.ts`, `app/web/src/lib/admin-session{,.test}.ts`.
   Changed: `scripts/cloud/00_check.ps1`, `app/engine/reco.py`, `app/engine/tests/test_reco_alts.py`,
   `app/web/{next.config.ts,package.json,playwright.config.ts,eslint.config.mjs}`, `app/web/src/proxy.ts` (was
   `middleware.ts`), `app/web/src/app/admin/eval/page.tsx`, the two place pages, `components/ui.tsx`,
   `screens/{home,map,search}.tsx`, `e2e/{admin,journey,map,states}.spec.ts`, `.gitignore`, the specs and maps.
   Deleted: `app/web/src/app/vendor/maplibre/[file]/route.ts`.

3. **Commands and exit codes** — table above.

4. **Tests** — engine 136 → 137; web unit 25 → 27; Playwright 47 → 49, on the production build and on the dev server.

5. **Open facts** —
   - **Not proven:** the `gcloud` and `vercel` invocations. No account exists and `gcloud` is not installed; the
     scripts were parsed, run in plan mode, and read against the vendor documentation by an independent reviewer
     (33 call sites: 30 match the documentation, 3 were uncertain; two of those were changed to the documented
     form, the Vercel team scope is left for the first run and noted in the runbook).
     Outbound calls from the Seoul region to the Seoul API (plain HTTP, port 8088) are also untested.
   - **A defect the rehearsal found:** alternative dates with equal scores were ordered by an unordered SQL read,
     so `forecast` and the `collect` refresh could store them in different orders. Ties now go to the nearer date
     (test added, red before the fix). This changes stored `alt_dates` only where scores tie.
   - `alt_dates` of a later date can point at today, and two databases fed by different collectors hold different
     rows for today, so the cross-database comparison leaves that column out. On identical data every column matches.
   - The Supabase CLI only speaks TLS to `--db-url` and does not read the URL from the environment, so the URL is a
     child-process argument of `supabase db push` (never echoed), and the stand-in database gets a self-signed
     certificate.
   - The map worker was a route handler reading `node_modules` at request time; a serverless bundle would likely
     not contain those files. It is now a static file copied at build.
   - `forecast` peaked at 323 MB under a 4Gi limit. The limit is unchanged until a cloud run confirms the figure.
   - A `next build` under a running `next dev` left the dev server's API routes answering 404; the dev server was
     restarted. Recorded in `findings.md`.
   - `90_verify` does not send the token in an address, even to prove it is refused; the local e2e proves that.
   - B4 was narrowed: the first place of the list stays selected on the map (the spec's layout always has a card).
     Whether nothing should be selected is recorded as a design question.

6. **Not done** — nothing inside this SOW. Outside it and still open: English place names, the collection-gap
   marker, archive retention, an alert on job failure, E6 and the weekly rejudge (need October data), and every
   step of SOW-MC that needs an account.
