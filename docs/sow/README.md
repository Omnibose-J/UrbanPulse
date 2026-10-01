# Statements of Work — UrbanPulse v1

Build of UrbanPulse v1 (mobile web + PC map dashboard, ko/en, visitors only). Architecture and product decisions are fixed in `../../UrbanPulse_구현설계서.md` (build contract, Korean); UI in `../../UrbanPulse_디자인명세서.md`. This folder turns the work units W0–W13 (build contract §8) into milestones an implementing agent can execute and prove.

## Roles

| Who | Does | Does not |
|---|---|---|
| **Claude** (designer) | Writes and revises SOWs, pre-registers acceptance bars, reviews each milestone's evidence, updates the Korean specs when a finding changes the design | Write application code |
| **Cursor** (implementer) | Implements a SOW end to end, creates and fills `docs/tracking/criteria-<milestone>.md`, reports per `AGENTS.md` | Change scope, relax a bar or a test, edit `analysis/`, decide product questions |
| **User / team** | Keys (Seoul Open API and data.go.kr are already in `.env`), product answers, user interviews; cloud accounts and billing only at SOW-MC | — |

## Milestones

| SOW | Work units | Delivers | Depends on |
|---|---|---|---|
| [SOW-M0](SOW-M0.md) | W0, W1 | git repo · local Supabase schema + RLS with pgTAP tests · engine skeleton with `healthcheck` running locally · empty Next.js (`next dev`) reading the local DB. **No cloud** | Docker Desktop, `.env` (present) |
| [SOW-M1](SOW-M1.md) | W2, W4, W3a, W3 | `places` loaded (tiers, English names, palace hours, foreign-heavy flag, serve state) · holidays 2023–2027 · backfill 5/11→ into the local DB · `collect` every 30 min via Windows Task Scheduler on the dev box, raw snapshots to `data/raw/` | M0 |
| [SOW-M2](SOW-M2.md) | W3 hardening, W5, W6, W7 | Part A: task runs on battery · raw before database · `ingest_raw` · eight commerce categories · holidays filtered by `isHoliday`. Part B: `ratio_v1` ported and proven against the research figures · registration gate · `level_thresholds`, `lively_profile` · daily `forecast` job · places refreshed from live data | M1 |
| SOW-M3 (outline) | W8, W9 | recommendations + flags + alternatives + similar places · `tier_b` job | M2 |
| SOW-M4 (outline) | W10, W13 | mobile screens `/`, `/search`, `/p/[id]`, `/p/[id]/[date]`, `/map`, `/about` per the design spec · ko/en · all on `next dev` against the local DB | M0 (can start on mock rows), real data from M3 |
| SOW-MC (outline) | W0 cloud half | GCP project, Artifact Registry image push, Cloud Run Jobs + Scheduler for the six jobs, GCS buckets (raw archive moves from `data/raw/`), hosted Supabase (`db push`), Vercel deploy, Google Maps billing or MapLibre decision | M4 working locally; accounts and billing (user) |
| SOW-M5 (outline) | W11, W12 | `evaluate` (incl. weekly re-judgement) and `archive` jobs · `/admin/eval` · E6 strip verification | MC |

M3–MC–M5 are outlines (M0 and M1 are done; M2 is expanded). Claude expands each one when the previous milestone's evidence is in. Do not start a milestone from an outline; ask for the expanded SOW. Order is local first: nothing touches a cloud account before SOW-MC.

## Definition of done (every milestone)

- Every acceptance row in `docs/tracking/criteria-<milestone>.md` has a command, an exit code and the decisive output line, filled after the run.
- The report (AGENTS.md format) is in the chat and at the bottom of the criteria file.
- No test was weakened; no fixture replaced to pass; no result cell pre-filled; no bar tuned.
- `git status` shows only paths the SOW lists.
- No secret in any tracked file, log line or report (`git grep` checks in each SOW).

## Criteria file template

```
# criteria-<milestone> — <title>

Written <date> before implementation. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | … | `…` | | |

## Report
(AGENTS.md format, appended when done)
```

## Conventions

- **Repo root** is `UrbanPulse/`. Layout after M0:
  ```
  AGENTS.md  .gitignore  .env.example  pyproject.toml
  UrbanPulse_*.md / .docx        specs (read-only)
  analysis/scripts/              research (read-only)   analysis/data/  gitignored
  app/engine/                    package `engine` + Dockerfile + requirements.txt + tests/
  app/supabase/                  config.toml, migrations/, tests/
  app/web/                       Next.js
  docs/sow/  docs/tracking/
  ```
- **Python**: 3.10, `ruff` (line length 110), `pytest`. Type hints on public functions. Run from the repo root after `pip install -e .` (editable install of `engine`); `pyproject.toml` also sets `pythonpath = ["app"]` for pytest. In the image the package sits at `/srv/engine` and runs as `python -m engine <job>`.
- **Database access**: engine → Postgres directly with `psycopg` 3 (`DATABASE_URL`, Supabase session pooler); web → `@supabase/supabase-js` from server code only with the service-role key.
- **TypeScript**: strict. Supabase client only in server components and route handlers.
- **Commits**: one per SOW step, message `M0-3: …`, English. Never commit `.env`, `analysis/data/`, `node_modules`, `.next`, `.vercel`.
- **Cloud**: region `asia-northeast3` (Seoul) for Cloud Run, Artifact Registry, GCS; Supabase region Northeast Asia (Seoul).
