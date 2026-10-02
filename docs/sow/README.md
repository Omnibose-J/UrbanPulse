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
| [SOW-M3](SOW-M3.md) | W8 | `recommendation_log` migration · flag file · recommendations with `hours`, alternatives · similar places · today's rows refreshed by `collect` | M2 |
| [SOW-M4](SOW-M4.md) | W10, W11, W13 | read-only API · screens `/`, `/search`, `/p/[id]`, `/p/[id]/[date]`, `/map` (MapLibre), `/about` per the design spec · ko/en · Playwright checks D1-D12 · all on `next dev` against the local DB | M3 |
| [SOW-M4.1](SOW-M4.1.md) | W10, W11 fixes | screens rebuilt against mockup v6 with DOM-measured visual checks · map renders · today's windows only from hours still ahead · home "now" from the latest measured hour | M4 review |
| [SOW-M5](SOW-M5.md) | W12 | `evaluate` (daily) · `rejudge` (prints, applies only with `--apply`) · `archive` (dry run only for now) · `/admin/eval` | M3, M4 |
| [SOW-MB](SOW-MB.md) | W9 (cut down) | tier B station places, usual-flow profile, B recommendations; experimental, search and map toggle only. Holiday adjustment and `ratio_v1b` deferred | M3, M4 |
| [SOW-M6](SOW-M6.md) | W6 fix | level thresholds by the error-minimising boundary (E17) · one combination off · `reason.closed` copy | MB |
| [SOW-M7](SOW-M7.md) | W3, W7 fixes | collect works with station places present · missed snapshots ingested · tasks wake the machine · forecast under 5 minutes · station places only with a profile | MB, M6 |
| SOW-MC (outline) | W0 cloud half | GCP project, Artifact Registry image push, Cloud Run Jobs + Scheduler, GCS buckets (raw and archive move from `data/`), hosted Supabase (`db push`), Vercel deploy, map provider decision | everything above working locally; accounts and billing (user) |

Run order: **M2 → M3 → M4 → M5 → M4.1 → MB → M6 → M7**. SOW-MC is an outline and needs the user's cloud accounts; do not start it.

## Unattended run

The implementer may run M2 → M3 → M4 → M5 → MB back to back without waiting for a review. The designer reviews all of it afterwards from the criteria files and the diff.

- Finish a SOW (criteria file filled, report appended, commits made) before starting the next one.
- A pre-registered check that misses (a reproduction tolerance, the registration gate, any bar) is **recorded, not fixed**: fill the row with the measured value and `FAIL`, write it under Open facts, change no number, seed, sample, threshold or test. Then continue with the consequence the SOW registers for that case (for example: no horizon passes the gate → every forecast uses the baseline). Where a SOW says "stop and report" for such a miss, read it as "stop that step, record, continue with the steps that do not depend on it".
- A step that is blocked for another reason (missing input, tool failure you cannot resolve in three attempts, spec conflict): mark its rows `BLOCKED` with the reason, append to `docs/tracking/findings.md` when it is out of scope, skip only what depends on it, continue.
- A later SOW that cannot work at all without a blocked earlier result (for example M4's live smoke test with no `recommendations` rows) still builds and tests everything it can on mocked data and marks the live rows `BLOCKED`.
- Never, in any case: touch a cloud account, push, print a key, edit `analysis/`, run `supabase db reset`, weaken or delete a test, or fill a criteria cell without running its command.

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
