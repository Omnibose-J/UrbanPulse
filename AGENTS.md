# AGENTS.md — UrbanPulse

Read this and `docs/LLM_PROJECT_MAP.md` before touching anything. Human-facing specs are Korean; this file and `docs/sow/` are written for the implementing agent (Cursor). The designer (Claude) writes SOWs and reviews results; the implementer builds exactly what a SOW says and reports evidence.

UrbanPulse tells visitors (first target: Seoul residents and domestic travellers; English UI for tourists) when to go to a Seoul hotspot they already chose, from later today up to 7 days ahead, avoiding closed hours and the busiest hour. Tier B (station areas outside the 121 places) is an experimental feature reachable by search only. Screens read precomputed rows; a Python engine running as scheduled jobs does all computation.

## What is in this repo

| Path | What | Your access |
|---|---|---|
| `UrbanPulse_구현설계서.md` | **Build contract** (Korean): architecture, schema, jobs, invariants, work units W0–W13 | Read |
| `UrbanPulse_서비스정의서.md` | Product spec (Korean). Wins over the build contract on product questions; report any conflict | Read |
| `UrbanPulse_디자인명세서.md` | UI spec (Korean): tokens, components, screens, copy, states | Read |
| `*.docx` | Exports of the three specs for humans | Never edit |
| `analysis/scripts/` | Research code that produced every number in the specs. Source of parsers and model code the engine ports | **Read-only.** Port by copying into `app/engine/` when a SOW says so; never import from `analysis/` |
| `analysis/data/` | 6 GB of research data. Gitignored | Read-only. Never rewrite |
| `app/engine/` | Python engine (package `engine`), Docker image for Cloud Run Jobs | You build this |
| `app/supabase/` | Supabase config, migrations, pgTAP tests | You build this |
| `app/web/` | Next.js (App Router, TypeScript, Tailwind v4) on Vercel | You build this |
| `models/` | Trained model artifacts (W5+), tracked | Created by SOW steps only |
| `docs/LLM_PROJECT_MAP.md` | Where everything lives, entry-point commands, data flow, invariants, milestone order | Read first; update when you add a file class or a command |
| `docs/sow/` | Statements of work | Read; do not edit |
| `docs/tracking/` | `criteria-<milestone>.md` per milestone; `findings.md` for out-of-scope problems | You fill result cells **after** running |

## Hard rules

1. **No computation on the request path.** Web route handlers only read tables. Every forecast, level, recommendation and flag is computed by the engine and stored.
2. **The on/off table is data, not code.** Whether a recommendation combination is on, reference-only or off comes from `recommendations.state` (written by the engine from `app/engine/config/feature_flags.yaml`). The web app never hard-codes which combinations are off. A combination that is not in the flag file is off.
3. **Fail loud, no silent fallback.** Missing data → `ready=false` and the "준비 중" state. An API failure → the error state, never stale data shown as fresh. A missing env var → exit non-zero naming the variable. Do not add a fallback a SOW did not ask for.
4. **Secrets via environment only.** `.env` stays gitignored; commit `.env.example` with names only. Never print a secret or a URL that contains one (the Seoul API puts the key in the URL path — log the place code, never the URL). Never paste a secret into a report. The service-role key and database URL never reach browser code.
5. **Korean and English UI strings live only in `app/web/messages/{ko,en}.json`**, copied byte-for-byte from `UrbanPulse_디자인명세서.md` §5 and §9. Components contain no literal user-facing text. Do not "improve" copy.
6. **Colors, type and spacing only through the tokens** in 디자인명세서 §3 (`app/web/src/styles/tokens.css`). No hex values in components.
7. **Evidence = literal command + exit code + the decisive output line**, recorded in `docs/tracking/criteria-<milestone>.md` **after** the run. Create that file with empty result cells before you start; never pre-fill a cell. Never weaken, skip or delete a test, special-case a fixture, or hard-code an expected value. Pre-registered bars (build contract §7, reproduction tolerances in §8) are not tuned to pass: if one is missed, stop that step, record the measured value, and follow `docs/sow/README.md` "Unattended run".
8. **Language.** Code, comments, commit messages, docs you write → English. User-facing strings → from the specs.
9. **Windows dev box.** Python 3.10 at `python`; PowerShell 5.1 (no `&&`/`||`); paths may contain Korean, always quote them; write files as UTF-8; set `PYTHONUTF8=1` when a script prints Korean. Installed: git, gh, node 24, npm, Docker Desktop, `supabase`, `vercel`, `pandoc`. `gcloud` arrives at SOW-MC. Local Supabase for this project runs on ports 553xx (`app/supabase/config.toml`) because another project occupies 543xx. `pip install -e .` once, then `python -m engine <job>` works from any directory.
10. **Do not run research scripts** in `analysis/scripts/` unless a SOW step names the exact command. Some of them download for hours or rewrite `analysis/data/`.
11. **When blocked** (API behaves differently, platform limit, spec conflict, bar missed): stop that step, write it under **Open facts** in your report, and if it is outside the SOW's scope append it to `docs/tracking/findings.md` with why it cannot be fixed now and what it touches. Do not invent a workaround or silently narrow scope.
12. **Surgical.** Touch only what the SOW names. Do not reformat, rename or reorganise files you did not create.
13. **Time.** Store `timestamptz`; the engine computes in `Asia/Seoul`; display KST.

## Report format (end of every SOW, in the chat and in `docs/tracking/criteria-<milestone>.md`)

1. **Intent** — one paragraph: what the SOW asked, what you built.
2. **Files** — created / modified / deleted, one line each.
3. **Commands and exit codes** — every acceptance command, verbatim, with exit code and the decisive output line.
4. **Tests** — name, pass/fail, count.
5. **Open facts** — anything measured that the SOW did not predict, and anything you could not verify.
6. **Not done** — every SOW item not finished, and why. Empty = everything in scope is done and verified.
