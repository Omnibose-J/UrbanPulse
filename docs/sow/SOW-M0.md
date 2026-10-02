# SOW-M0 — Local foundation: repo, schema, engine skeleton, empty web (no cloud)

Work units W0 + W1 of the build contract (`docs/specs/UrbanPulse_구현설계서.md` §1, §3, §8). No product logic and **no cloud** in M0: everything runs on the dev laptop (local Supabase in Docker, `python -m engine`, `next dev`). The goal is that every piece exists and talks to the next one, so M1+ only add behaviour. Cloud wiring (GCP, Vercel, hosted Supabase, GCS) is SOW-MC, after the screens work locally (decided 2026-10-01: local first).

## Goal

1. A git repo at `UrbanPulse/` with the layout in `README.md` → Conventions (GitHub push only if the user confirms).
2. The full schema (§3 of the build contract, as refined in the tables below) migrated to the local Supabase stack, with anon/authenticated access denied, proven by pgTAP tests.
3. An engine package whose `healthcheck` job, run with `python -m engine healthcheck` on the laptop, reads `.env`, calls the Seoul and KASI APIs once, and writes a `job_runs` row to the local database. The Docker image builds locally too (it is what SOW-MC will push).
4. An empty Next.js app running with `next dev` whose `/api/health` reads the local database server-side.

## Inputs from the user (collect before step M0-1; record which were provided, never the values)

| Input | Notes |
|---|---|
| Docker Desktop running | `supabase start` needs it |
| `.env` at the repo root | Already present (2026-09-29) with `SEOUL_API_KEY` and `KASI_API_KEY`, both verified against the live APIs; `GOOGLE_MAPS_KEY` is present but its project has no billing (irrelevant until SOW-MC). Fill `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` from the `supabase start` output in M0-2 (local values only) |
| GitHub (optional): confirm repo name `urbanpulse`, private | `gh auth status` is logged in. Skip the push if the user does not confirm; everything else works without it |

## Files you may touch

Create: `.gitignore`, `.env.example`, `pyproject.toml`, `app/engine/**`, `app/supabase/**` (via `supabase init` plus the files named below), `app/web/**` (via `create-next-app` plus the files named below), `docs/tracking/criteria-m0.md`, `docs/tracking/findings.md`.
Everything else is read-only: the three specs and their `.docx`, `AGENTS.md`, `docs/sow/`, all of `analysis/`.

## Steps

### M0-1 Repo
- `git init` at `UrbanPulse/`. `.gitignore`: `analysis/data/`, `data/`, `.env`, `.env.*` with `!.env.example`, `__pycache__/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `node_modules/`, `.next/`, `.vercel/`, `app/supabase/.temp/`, `app/supabase/.branches/`, `*.log`.
- `.env.example` (names only): `SEOUL_API_KEY=`, `KASI_API_KEY=`, `DATABASE_URL=`, `SUPABASE_URL=`, `SUPABASE_SERVICE_ROLE_KEY=`, `RAW_DIR=`, `GOOGLE_MAPS_KEY=`, `ADMIN_TOKEN=`. `RAW_DIR` is the local folder for raw snapshots until SOW-MC moves them to GCS (default `data/raw/`, gitignored). The existing `.env` is never read into the repo, printed, or committed.
- Before the first commit, `git add -A; git diff --cached --name-only | Select-String "analysis/data"` must print nothing. After it, `git count-objects -vH` must show `size-pack` under 20 MB. Then, only if the user confirms, `gh repo create urbanpulse --private --source . --push`.

### M0-2 Supabase schema (W1)
- `supabase init` in `app/` (creates `app/supabase/`). Set `project_id = "urbanpulse"` and move every port from 543xx to 553xx in `config.toml` (another local project holds 543xx). Local stack via `supabase start` (Docker). Copy the printed `DB URL`, `API URL` and `service_role key` into `.env` as `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (local-only values; the file stays gitignored).
- `app/supabase/migrations/<timestamp>_schema.sql`: the tables below, exactly. `<timestamp>_rls.sql`: enable RLS on every table in `public`; `revoke all on all tables in schema public from anon, authenticated`; `alter default privileges in schema public revoke all on tables from anon, authenticated`; same for sequences. No policies. (`service_role` bypasses RLS; the engine connects as `postgres` via `DATABASE_URL`.)
- Enum-like columns use `text` + `check`, not Postgres enums (new values must not need a type migration).

**Column types** (all `not null` unless marked `null`; `ts`-like columns are `timestamptz`; `level` is `smallint`):

| Table | Columns | Keys and checks |
|---|---|---|
| `places` | `id text`, `tier text`, `name text`, `name_en text null`, `category text null`, `gu text null`, `lat double precision null`, `lon double precision null`, `geom jsonb null`, `poi_code text null`, `station_codes text[] default '{}'`, `open_hours jsonb null`, `foreign_heavy boolean default false`, `serve_state text default 'preparing'`, `updated_at timestamptz default now()` | PK `id`. `tier in ('A1','A2','B')`. `serve_state in ('on','preparing','off','experimental')` (`experimental` = tier B, reachable by search only). Unique `poi_code`. Id convention: A1/A2 = Seoul POI code (`POI001`), B = `B-<station code>` |
| `live_obs` | `place_id text`, `ts`, `pop_min int`, `pop_max int`, `level`, `age_rates jsonb null`, `male_rate real null` | PK (`place_id`,`ts`). FK → `places`. `level between 0 and 3`. `pop_min <= pop_max`. Index `ts` |
| `commerce_obs` | `place_id text`, `ts`, `level null`, `pay_cnt int`, `cat_counts jsonb` | PK (`place_id`,`ts`). FK. `level between 0 and 3`. Index `ts` |
| `city_fcst` | `place_id text`, `target_ts`, `issued_ts`, `pop_min int`, `pop_max int`, `level` | PK (`place_id`,`target_ts`). FK. `level between 0 and 3` |
| `holidays` | `date date`, `name text`, `name_en text null`, `kind text` | PK `date`. `kind in ('holiday','substitute','seol','chuseok')` |
| `level_thresholds` | `place_id text`, `t1 real`, `t2 real`, `t3 real`, `based_on_days int`, `computed_at timestamptz default now()` | PK `place_id`. FK. `t1 <= t2 and t2 <= t3` (invariant 3 at the data level) |
| `tier_b_profile` | `place_id text`, `day_type text`, `hour smallint`, `rel real` | PK (`place_id`,`day_type`,`hour`). FK. `day_type in ('weekday','sat','sun')`. `hour between 0 and 23`. `rel >= 0` |
| `lively_profile` | `place_id text`, `day_type text`, `hour smallint`, `a_all real null`, `a_food real null`, `a_shop real null`, `n_days int` | PK (`place_id`,`day_type`,`hour`). FK. `day_type in ('weekday','weekend','holiday','myeongjeol')`. `hour between 0 and 23` |
| `forecast_hourly` | `place_id text`, `target_ts`, `issued_ts`, `source text`, `pop real null`, `rel real null`, `level null`, `a_all real null`, `a_food real null`, `a_shop real null`, `stale boolean default false`, `ready boolean` | PK (`place_id`,`target_ts`). FK. `source in ('live','seoul','model','profile')`. `level between 0 and 3`. `ready = false or level is not null` |
| `recommendations` | `place_id text`, `date date`, `tolerance text`, `purpose text`, `state text`, `off_reason text null`, `windows jsonb null`, `no_window boolean null`, `hours jsonb null`, `strip_mode text null`, `alt_dates jsonb null`, `alt_places jsonb null`, `generated_at timestamptz default now()` | PK (`place_id`,`date`,`tolerance`,`purpose`). FK. `tolerance in ('calm','moderate','busy_ok')`. `purpose in ('sight','food','shop','none')` (`none` for A2/B). `state in ('on','reference','off')`. `off_reason in ('failed','unverified','myeongjeol','preparing')`. Check: `state = 'off'` ⇔ `off_reason is not null` ⇔ `windows is null` ⇔ `hours is null` ⇔ `strip_mode is null`. `strip_mode in ('two_step','windows_only')`. `hours is null or (jsonb_typeof(hours) = 'array' and jsonb_array_length(hours) = 15)`. Index (`date`,`tolerance`,`purpose`) for the map query. Per-cell rules of `hours` (build contract §4.8 invariants 9–10) are engine tests, not SQL |
| `similar_places` | `place_id text`, `other_id text`, `score real`, `rank smallint` | PK (`place_id`,`other_id`). Both FK. `place_id <> other_id`. `rank between 1 and 10` |
| `forecast_log` | `place_id text`, `issued_date date`, `target_ts`, `horizon_d smallint`, `pred real`, `baseline real`, `model_version text` | PK (`place_id`,`issued_date`,`target_ts`). FK. `horizon_d between 0 and 7`. Index `target_ts` |
| `eval_daily` | `date date`, `horizon_d smallint`, `segment text`, `wape_model real`, `wape_baseline real`, `n int` | PK (`date`,`horizon_d`,`segment`). `segment in ('normal','holiday')` |
| `reco_eval_daily` | `date date`, `place_id text`, `purpose text`, `tolerance text`, `n_hours int`, `n_lively int`, `n_crowd_ok int null`, `chance_hours int`, `chance_lively int` | PK (`date`,`place_id`,`purpose`,`tolerance`). FK. Same `purpose`/`tolerance` checks as `recommendations`. `n_crowd_ok is null` iff `tolerance = 'busy_ok'` (the busy_ok crowd promise is true by definition and is not scored). Per-place counts so the weekly re-judgement can bootstrap by place |
| `strip_eval_daily` | `date date`, `place_id text`, `purpose text`, `tolerance text`, `n_ok int`, `n_ok_lively int null`, `n_ok_crowd_ok int null`, `n_avoid int`, `n_avoid_unfit int` | PK (`date`,`place_id`,`purpose`,`tolerance`). FK. Same `purpose`/`tolerance` checks as `recommendations`. `n_ok_crowd_ok is null` iff `tolerance = 'busy_ok'`. `n_ok_lively` null for A2 (no commerce data). All counts `>= 0`, `n_ok_lively <= n_ok`, `n_avoid_unfit <= n_avoid` |
| `model_registry` | `name text`, `version text`, `trained_range text`, `horizons smallint[]`, `metrics jsonb`, `artifact_uri text`, `active boolean default false`, `created_at timestamptz default now()` | PK (`name`,`version`). Partial unique index on (`name`) where `active` |
| `job_runs` | `id bigint generated always as identity`, `job text`, `started_at timestamptz default now()`, `finished_at timestamptz null`, `status text`, `detail jsonb null` | PK `id`. `status in ('running','ok','warn','fail')`. Index (`job`,`started_at` desc) |

- `app/supabase/tests/schema_test.sql` (pgTAP, run by `supabase test db`):
  - every table above exists with exactly its primary-key columns (`has_table`, `col_is_pk`);
  - each check constraint rejects one bad row (`throws_ok` with SQLSTATE `23514`): `places.tier = 'C'`, `live_obs.level = 4`, `recommendations` with `state='off'` and non-null `windows`, `recommendations` with `state='on'` and non-null `off_reason`, `recommendations` with `state='on'` and a 14-element `hours` array, `recommendations` with `state='off'` and non-null `strip_mode`, `strip_eval_daily` with `tolerance='busy_ok'` and non-null `n_ok_crowd_ok`, `strip_eval_daily` with `n_avoid_unfit > n_avoid`, `reco_eval_daily` with `tolerance='busy_ok'` and non-null `n_crowd_ok`, `level_thresholds` with `t1 > t2`, `forecast_hourly` with `ready=true` and null `level`;
  - a second `model_registry` row with `active=true` for the same name fails (`23505`);
  - as role `anon` and as role `authenticated`, `select` from every table fails with `42501`.

### M0-3 Engine skeleton
- The package is the directory `app/engine/` itself (`app/engine/__init__.py`). `pyproject.toml` at the repo root makes it an installable project (`package-dir = {"" = "app"}`): `pip install -e .` once, then `python -m engine` works from any directory; pytest also gets `pythonpath = ["app"]`. `Dockerfile`, `requirements.txt` and `tests/` also live in `app/engine/`.
- Modules now: `__init__.py`, `__main__.py`, `settings.py`, `db.py`, `log.py`, `jobs/__init__.py`, `jobs/healthcheck.py`.
- `__main__.py`: `argparse` subcommands `backfill`, `collect`, `forecast`, `tier_b`, `evaluate`, `archive`, `healthcheck`. The first six print `not implemented until <W#>` (W3a, W3, W7, W9, W12, W12) to stderr and exit **2**. Unknown subcommand → argparse's exit 2.
- `settings.py`: reads env; a job declares the variables it needs; a missing one → message `missing env var: NAME` to stderr, exit 1. Values are never printed, not even partially.
- `log.py`: one JSON line per event to stdout (`{"job","event","ms",...}`), UTF-8 regardless of the console codepage (`sys.stdout.reconfigure(encoding="utf-8")` once). Never logs a URL.
- `db.py`: `connect()` → `psycopg.connect(DATABASE_URL, autocommit=False)`; `job_run(job)` context manager inserts a `running` row, and on exit updates `finished_at` and `status` (`ok`, or `fail` with `{"error": type name + message}` when an exception escapes, then re-raises).
- `jobs/healthcheck.py` needs `DATABASE_URL`, `SEOUL_API_KEY`, `KASI_API_KEY`. Inside `job_run("healthcheck")`:
  1. `GET http://openapi.seoul.go.kr:8088/{key}/json/citydata/1/5/POI001` (timeout 20 s). Record `seoul_status` (HTTP code) and `seoul_ok` = response JSON has `CITYDATA.AREA_NM`.
  2. `GET http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo?solYear=2026&solMonth=10&_type=json&ServiceKey={key}`. Record `kasi_status` and `kasi_items` = number of holiday items returned (the build contract expects 10/3, 10/5 (substitute) and 10/9; record what actually came back).
  3. Write both into `detail`; status `ok` only if both calls returned 200 and parsed; otherwise raise (→ `fail`, exit 1).
  The key must not appear in logs, exception messages or `detail`: wrap httpx errors and re-raise with the place code / endpoint name only.
- `requirements.txt`, pinned: `psycopg[binary]` (latest 3.2.x), `httpx==0.27.2`, `PyYAML==6.0.3`, `numpy==2.2.6`, `pandas==2.3.3`, `pyarrow==24.0.0`, `scikit-learn==1.7.2`. No Google Cloud packages until SOW-MC. The numeric pins match the environment that produced the spec's numbers; do not change them. Dev extras in `pyproject.toml`: `pytest`, `ruff`.
- `Dockerfile`: `python:3.10-slim`, `WORKDIR /srv`, install requirements, `COPY app/engine /srv/engine`, `ENV PYTHONUTF8=1 TZ=Asia/Seoul`, `ENTRYPOINT ["python","-m","engine"]`. Build context is the repo root because later milestones copy `models/`. The root holds 6 GB of `analysis/data/`, so add `app/engine/Dockerfile.dockerignore` (BuildKit reads `<Dockerfile>.dockerignore`) that excludes everything except `app/engine/` and `models/`, and inside those excludes `tests/`, `__pycache__/`, `.pytest_cache/`. Check: the build log's context transfer is under 5 MB.
- Tests `app/engine/tests/`:
  - `test_cli.py`: each of the six jobs exits 2 with its W# in stderr; `healthcheck` without env exits 1 naming the first missing variable.
  - `test_settings.py`: with `SEOUL_API_KEY` set to a sentinel string, running `healthcheck` against mocked HTTP (`httpx.MockTransport`) that returns 500 → exit 1, and the sentinel appears nowhere in captured stdout/stderr or in the `detail` passed to the DB layer (DB layer faked).
  - `test_healthcheck.py`: mocked 200 responses with a minimal `CITYDATA.AREA_NM` body and a KASI body with 3 items → `detail` has `seoul_ok=true`, `kasi_items=3`, status `ok`.

### M0-4 Run the healthcheck locally
- `python -m engine healthcheck` from the repo root with `.env` loaded (`settings.py` reads a `.env` file at the repo root when present, via `python-dotenv`; add it to `requirements.txt`, pinned). It must write a `job_runs` row to the local database with `status='ok'`.
- Run it twice; both rows must exist (no upsert on `job_runs`).

### M0-5 Web skeleton
- `npx create-next-app@latest app/web --ts --app --src-dir --tailwind --eslint --import-alias "@/*" --use-npm`.
- `src/app/page.tsx`: the word `UrbanPulse` only. No design work in M0 (design spec is M4).
- `src/lib/supabase-server.ts`: creates the client from `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`; the file starts with `import "server-only"` so importing it from client code fails the build.
- `src/app/api/health/route.ts`: `GET` → `{ "db": "ok", "places": <count of places> }` with status 200; on a DB error → status 503 `{ "db": "error" }` (no error text, no key). `Cache-Control: no-store`.
- `app/web/.env.local` is not used; the web app reads the repo-root `.env` through `next.config.ts` (`dotenv` path `../../.env`) so there is one secrets file. `npm run dev` on port 3000. No Vercel in M0.

## Acceptance (`docs/tracking/criteria-m0.md`, rows created before M0-1)

| # | Criterion | Command |
|---|---|---|
| A1 | Schema + RLS tests pass locally | `supabase test db` (from `app/`) → exit 0, paste the `ok`/`not ok` summary line |
| A2 | Local stack up | `supabase status` (from `app/`) → exit 0, prints the API and DB URLs |
| A3 | Engine tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 |
| A4 | Image builds and skeleton behaves | `docker build -f app/engine/Dockerfile -t urbanpulse-engine .` → exit 0; `docker run --rm urbanpulse-engine collect` → exit 2 and prints `W3` |
| A5 | Local healthcheck writes to local DB | `python -m engine healthcheck` → exit 0; then `psql "$env:DATABASE_URL" -c "select job, status, detail from job_runs order by id desc limit 1"` shows `healthcheck`, `ok`, `seoul_ok: true`, `kasi_items ≥ 1` (paste the row; it contains no key) |
| A6 | Web reads DB server-side | with `npm run dev` running: `curl -s -o NUL -w "%{http_code}" http://localhost:3000/api/health` → `200`; body `{"db":"ok","places":0}` |
| A7 | Service-role key not in client bundle | a small node or PowerShell script that reads `SUPABASE_SERVICE_ROLE_KEY` from `.env` and searches `app/web/.next/static` for it, printing only `found`/`not found` → `not found` |
| A8 | No secrets tracked | `git ls-files .env analysis/data` → empty; `git grep -I -n -e "eyJhbGci" -e "sb_secret_"` → no match (exit 1). These are the prefixes of Supabase JWT keys and secret keys |
| A9 | Secrets never echoed | `python -m engine healthcheck 2>&1 | Select-String -SimpleMatch (Get-Content .env | Select-String SEOUL_API_KEY).Line.Split('=')[1]` → no match (the script prints only `matched`/`no match`) |

## Open facts to report

- Seoul API: HTTP code and response time for POI001; anything in the body that differs from `CITYDATA.AREA_NM` (the collector parsers in `analysis/scripts/collect_rtd.py` assume this shape).
- KASI: the October 2026 dates and names returned (the build contract expects 10/3, 10/5, 10/9; report what came back).
- Image size (`docker images urbanpulse-engine`).
- Local DB size right after the migrations (`select pg_size_pretty(pg_database_size(current_database()))`), baseline for build contract §1.3.
- Any `create-next-app` default you had to change and why.
