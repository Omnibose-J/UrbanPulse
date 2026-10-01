# criteria-mb — Tier B station areas (local, experimental)

Written before step 1. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Port reproduces E1 | `python -m engine tier_b --check` → the three figures pasted next to 0.84 / 6.67 % / 62.28 % with PASS or FAIL per tolerance | | |
| A2 | Stations loaded | `python -m engine tier_b` → exit 0; `select count(*) from places where tier = 'B'` pasted with the dropped-by-overlap count; `select tier, serve_state, count(*) from places where tier <> 'B' group by 1,2` identical before and after | | |
| A3 | Profiles | `select count(distinct place_id), count(*) from tier_b_profile` → rows = places × 3 × 24; `detail` pasted | | |
| A4 | B rows | `python -m engine forecast` → exit 0; `select state, off_reason, count(*) from recommendations r join places p on p.id = r.place_id where p.tier = 'B' group by 1,2`; no B cell with non-null `act`; no B cell with `crowd = 3` | | |
| A5 | Reachable by search and toggle only | with `npm run dev`: `/api/places?q=` (empty) has no tier B row; `/api/places?q=<a station name>` has one; `/api/map?...&stations=0` has none; `&stations=1` has some; `/api/home` has none | | |
| A6 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 | | |
| A7 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match | | |

## Report
(AGENTS.md format, appended when done)
