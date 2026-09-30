# criteria-m0 — Local foundation (SOW-M0)

Written 2026-10-01 before implementation. Result cells filled after running each command (2026-10-01).

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Schema + RLS tests pass locally | `supabase test db` (from `app/`) | 0 | `Files=1, Tests=99 ... Result: PASS` |
| A2 | Local stack up | `supabase status -o env` (from `app/`) | 0 | printed `API_URL`, `DB_URL`, `SERVICE_ROLE_KEY`; copied into `.env` without echoing |
| A3 | Engine tests and lint | `python -m pytest app/engine/tests -q`; `ruff check app/engine` | 0 / 0 | `12 passed in 11.45s`; `All checks passed!` |
| A4 | Image builds and skeleton behaves | `docker build -f app/engine/Dockerfile -t urbanpulse-engine .`; `docker run --rm urbanpulse-engine collect` | 0 / 2 | `transferring context: 10.23kB`; `naming to docker.io/library/urbanpulse-engine:latest`; run printed `collect: not implemented until W3`; image 866MB |
| A5 | Local healthcheck writes to local DB | `python -m engine healthcheck` (repo root, after `pip install -e .`); `select job, status, detail from job_runs order by id desc limit 1` | 0 | log `{"event": "ok", "seoul_status": 200, "seoul_ok": true, "kasi_status": 200, "kasi_items": 3}`; row `healthcheck ok {"seoul_ok": true, "kasi_items": 3, "kasi_dates": ["20261003","20261005","20261009"], ...}` |
| A6 | Web reads DB server-side | `npm run dev`; `curl -s -o NUL -w "%{http_code}" http://localhost:3000/api/health` | 0 | `200`, body `{"db":"ok","places":0}` |
| A7 | Service-role key not in client bundle | `npm run build` then search `app/web/.next/static` for the key value | 0 | build `Compiled successfully in 14.2s`; search → `not found` |
| A8 | No secrets tracked | `git ls-files .env analysis/data data` → empty; `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match | 0 / 1 | `0` tracked; the only `git grep` hits without `:!docs` are the two doc lines quoting the pattern itself |
| A9 | Secrets never echoed | healthcheck stdout+stderr searched for the `SEOUL_API_KEY` and `KASI_API_KEY` values | 0 | `no match` |

## Report

1. **Intent** — SOW-M0 asked for a local-first foundation: repo, full schema with RLS proven by pgTAP, an engine skeleton whose `healthcheck` hits the real Seoul and KASI APIs and writes `job_runs`, an empty Next.js app whose `/api/health` reads the database, and a Docker image that builds. Built exactly that on the laptop against a local Supabase stack; no cloud account was touched. Also wrote `docs/LLM_PROJECT_MAP.md` so the next agent (Cursor, from M1) can navigate.
2. **Files** — created: `.gitignore`, `.env.example`, `pyproject.toml`, `app/engine/{__init__,__main__,settings,db,log}.py`, `app/engine/jobs/{__init__,healthcheck}.py`, `app/engine/{requirements.txt,Dockerfile,Dockerfile.dockerignore}`, `app/engine/tests/{conftest,test_cli,test_healthcheck}.py`, `app/supabase/config.toml` (project `urbanpulse`, ports 553xx), `app/supabase/migrations/20261001000000_schema.sql`, `20261001000100_rls.sql`, `app/supabase/tests/schema_test.sql`, `app/web/**` (create-next-app 16.3.8 + `src/lib/supabase-server.ts`, `src/app/api/health/route.ts`, `src/app/page.tsx`, `next.config.ts`), `docs/LLM_PROJECT_MAP.md`, `docs/tracking/{criteria-m0,findings}.md`. Modified: `AGENTS.md` (map link, rule 9), `docs/sow/SOW-M0.md` and `docs/sow/README.md` (editable install, ports), `.env` (three local Supabase values appended to empty lines; not tracked).
3. **Commands and exit codes** — table above.
4. **Tests** — pytest 12 passed (CLI exit codes, missing-env exit 1, healthcheck ok/fail paths with mocked HTTP and a fake ledger, key never leaks); pgTAP 99 passed (17 tables, 17 primary keys, 13 check/unique rejections, 2 valid rows, anon/authenticated denial and RLS on 17 tables).
5. **Open facts** — Seoul citydata POI001 returned 200 with `CITYDATA.AREA_NM` (shape assumed by `analysis/scripts/collect_rtd.py` holds). KASI 2026-10 returned 10/3 개천절, 10/5 대체공휴일(개천절), 10/9 한글날 (matches the build contract). Engine image 866 MB (numpy/pandas/scikit-learn). Local DB 12 MB right after migrations. Another local project (`localsync`) holds Supabase ports 543xx (its containers auto-restart with Docker Desktop), so this project uses 553xx. Next.js warns that a stray `C:\Users\sobeo\package-lock.json` outside the repo is ignored; harmless. A mid-run test failure exposed a real gap (partial API results were lost when a call failed); fixed by filling `detail` in place so a `fail` row keeps `seoul_status`/`kasi_status`.
6. **Not done** — GitHub push (needs the user's confirmation; repo is local only). Everything else in scope is done and verified.
