# criteria-mb — Tier B station areas (local, experimental)

Written before step 1. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Port reproduces E1 | `python -m engine tier_b --check` → the three figures pasted next to 0.84 / 6.67 % / 62.28 % with PASS or FAIL per tolerance | 0 | median r 0.84 PASS; r<0.3 6.67% PASS; agreement 62.26% vs 62.28 PASS (tol 2 pp). 291s |
| A2 | Stations loaded | `python -m engine tier_b` → exit 0; `select count(*) from places where tier = 'B'` pasted with the dropped-by-overlap count; `select tier, serve_state, count(*) from places where tier <> 'B' group by 1,2` identical before and after | 0 | B 590, dropped 63. A1 on 78, preparing 4; A2 on 22, preparing 17. Second upsert changed 0 |
| A3 | Profiles | `select count(distinct place_id), count(*) from tier_b_profile` → rows = places × 3 × 24; `detail` pasted | 0 | 247 places, 17784 rows = 247×72. detail places 590, profiles 247, used_ridership 87, no_profile 343 |
| A4 | B rows | `python -m engine forecast` → exit 0; `select state, off_reason, count(*) from recommendations r join places p on p.id = r.place_id where p.tier = 'B' group by 1,2`; no B cell with non-null `act`; no B cell with `crowd = 3` | 0 | forecast exit 0. on 3705; off preparing 741; off unverified 1482. act strings 0; crowd 3 is 0 |
| A5 | Reachable by search and toggle only | with `npm run dev`: `/api/places?q=` (empty) has no tier B row; `/api/places?q=<a station name>` has one; `/api/map?...&stations=0` has none; `&stations=1` has some; `/api/home` has none | 0 | empty search 100 A1/A2; one name query 1 B; map stations=0 has 0 B; stations=1 has 247 B; home has 0 STN |
| A6 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 | 0 | 84 passed, 1 skipped; ruff All checks passed |
| A7 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match | 1 | no match |

## Report

1. **Intent** — SOW-MB adds experimental station-area places outside the 121 live places, with a usual-flow profile and recommendations. They show up in search and on the map only when the station toggle is on.

2. **Files** — created `app/engine/tierb/{flows,stations,profile}.py`, `app/engine/jobs/tier_b.py`, `app/engine/tests/test_tierb_*.py`, `test_reco_b.py`. Edited `app/engine/__main__.py`, `forecast.py`, `reco.py`, `flags.py`, `feature_flags.yaml`, `pyproject.toml`.

3. **Commands and exit codes** — table above.

4. **Tests** — `python -m pytest app/engine/tests -q` → 84 passed, 1 skipped, exit 0. `ruff check app/engine` → exit 0.

5. **Open facts** —
   - Stations kept 590, dropped by the 50% overlap rule 63. Profiles 247. No tract overlap (or an incomplete week) 343. Ridership flow chosen for 87. `name_en` is null on every station, so English screens show the Korean name with `lang="ko"`.
   - `--check`: median r 0.84 PASS, r<0.3 share 6.67% PASS, three-level agreement 62.26% vs 62.28 PASS.
   - `tier_b` profile build about 4 minutes after the station load. `forecast` with recommendations about 30 minutes (exit 0, 121 live places refreshed, 0 tier transitions).
   - Today's tier B rows are `off / preparing` because the job crossed midnight and the existing delete of past forecast hours removed 2026-10-01. 2026-10-02 through 2026-10-08 are `on`, except holiday dates `off / unverified`.

6. **Not done** — empty. Holiday adjustment and `ratio_v1b` stay deferred, as the SOW says.
