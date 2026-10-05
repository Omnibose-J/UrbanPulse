# AGENTS.md — UrbanPulse

Rules for any coding agent (or person) changing this repo. Read this file, then `docs/LLM_PROJECT_MAP.md` (where things live, every command). Setup for a fresh clone is in `README.md` (Korean).

UrbanPulse tells a visitor when to go to a Seoul hotspot they already chose, from later today up to 7 days ahead, avoiding closed hours and the busiest hour. A Python engine runs as scheduled batch jobs and writes precomputed rows to Postgres; a Next.js app only reads them. Since 2026-10-05 it runs in the cloud: hosted Supabase (Seoul), Cloud Run Jobs + Cloud Scheduler in `asia-northeast3`, raw snapshots in GCS, the web on Vercel (`docs/RUNBOOK.md`). The laptop's three scheduled tasks are disabled and its local stack is the stopped rollback copy.

## Sources of truth

| Question | Where | Note |
|---|---|---|
| What the product promises and why | `docs/specs/UrbanPulse_서비스정의서.md` | Wins over the other specs |
| Architecture, schema, jobs, invariants | `docs/specs/UrbanPulse_구현설계서.md` | The build contract |
| Screens, tokens, copy, states | `docs/specs/UrbanPulse_디자인명세서.md` | Copy tables in §5 and §9 |
| One-page summary | `docs/specs/UrbanPulse_PRD.md` | Not a contract |
| Cloud move and operations | `docs/RUNBOOK.md`, `docs/sow/SOW-MC.md` | SOW-MC is the acceptance list for the move |
| Known problems not yet fixed | `docs/tracking/findings.md` | Append-only table |

The specs are Korean and are the contract. When a change alters behaviour, a screen, a token, a message or the schema, update the matching spec section in the same commit and add one line to the version notes at the top of that spec.

## Where to change what

| Task | Files | Then |
|---|---|---|
| UI text | `app/web/messages/ko.json` and `en.json` (both, same keys) | the copy table in the design spec; `node app/web/scripts/check-messages.mjs` |
| Colour, radius, shadow, spacing | `app/web/src/styles/tokens.css` | design spec §3; no hex in components |
| A screen | `app/web/src/screens/*.tsx`, shared parts in `src/components/ui.tsx` | e2e spec for that screen |
| What an API returns | `app/web/src/lib/queries.ts`, routes under `src/app/api/` | `e2e/api.spec.ts` |
| Turn a recommendation combination on, reference or off | `app/engine/config/feature_flags.yaml` | `python -m engine forecast`; never hard-code it in the web app |
| Recommendation rules | `app/engine/reco.py`, `judge.py` | `app/engine/tests/`; build contract §4.4 |
| Level thresholds, forecast | `app/engine/levels.py`, `ratio_model.py`, `jobs/forecast.py` | build contract §4.2, §5 |
| A job | `app/engine/jobs/<job>.py`, wired in `app/engine/__main__.py` | a test that runs the job on `tempdb.schema()` |
| Schema | a new file in `app/supabase/migrations/` (never edit an applied one) | build contract §3; `scripts/cloud/rehearse.ps1` |
| Cloud scripts | `scripts/cloud/` | `-Plan` run; `rehearse.ps1`; `docs/RUNBOOK.md` |

## Hard rules

1. **No computation on the request path.** Route handlers only read tables. Forecasts, levels, recommendations and flags are computed by the engine and stored.
2. **The on/off table is data.** A combination's state comes from `recommendations.state`, written by the engine from `feature_flags.yaml`. A combination missing from the file is off.
3. **Fail loud, no silent fallback.** Missing data shows the "준비 중" state; an API failure shows the error state; stale data is labelled stale; a missing env var exits non-zero naming it. Never show a default in place of a value that is not there.
4. **Secrets via environment only.** `.env` and `.env.cloud` are gitignored; `.env.example` has names only. Never print a secret or a URL containing one (the Seoul API key is in the URL path: log the place code, not the URL). The service-role key and the database URL never reach browser code. The admin token is never put in an address.
5. **UI strings live only in `app/web/messages/{ko,en}.json`** and match the design spec's copy tables. Components contain no literal user-facing text. Korean copy is 해요체, plain, with the visitor as the subject.
6. **Colours, type and spacing only through tokens.** No gradients, no hex in components.
7. **Evidence is a command and its exit code.** Before saying something works, run the gates below and report what ran. Untested code is "built, untested". Never weaken, skip or delete a test to get green, special-case a fixture, or hard-code an expected value. Pre-registered bars (build contract §7) are not tuned to pass: report the measured value instead.
8. **Language.** Code, comments, this file and `docs/` (except `docs/specs/`) are English. Specs, `README.md`, UI copy and **commit messages are Korean**.
9. **Research code is frozen.** `analysis/scripts/` produced every number in the specs: read it, never edit or import it, and do not run it (some scripts download for hours). `analysis/data/` is gitignored and read-only.
10. **Surgical changes.** Touch what the task needs. No reformatting or renaming of unrelated files. A problem outside the task goes to `docs/tracking/findings.md` (date, where found, why not now, what it touches), not into the diff.
11. **Never destroy data.** No `supabase db reset`, locally or remotely. Raw snapshots and `forecast_log` are never modified. Engine tests use a throwaway schema (`engine.tests.tempdb`), never the live tables.
12. **No cloud action without the user.** Nothing touches a cloud account until `scripts/cloud/00_check.ps1` exits 0 and the user says go.
13. **Time.** Store `timestamptz`; compute in `Asia/Seoul`; display KST.

## Gates (run what your change touches; all of them before a push)

```
python -m pytest app/engine/tests -q
ruff check app/engine scripts/cloud
cd app/web; npm run lint; npm test; npx playwright test
python -m engine integrity --full
powershell -File scripts/cloud/rehearse.ps1      # engine, migrations or scripts/cloud changed
```

Playwright needs the local database with data and starts `next dev` itself. Stop `next dev` before `npm run build`.

## Environment

Windows, PowerShell 5.1 (no `&&`), Python 3.10 at `python`, Node 24, Docker Desktop, `supabase`, `vercel`, `pandoc`, `gcloud` (user-local install; the session's bash finds it only by its short path `%LOCALAPPDATA%\Google\CLOUDS~1\google-cloud-sdk\bin`). Paths may contain Korean: quote them, write files as UTF-8, set `PYTHONUTF8=1` when printing Korean. `.ps1` files stay ASCII. Local Supabase runs on ports 553xx (`app/supabase/config.toml`). Write any file that contains backslashes or quotes with an editor tool, not a shell heredoc.

## Reporting a change

State what changed, the commands you ran with exit codes, anything measured that was not expected, and anything not done. Do not claim more than the commands proved.
