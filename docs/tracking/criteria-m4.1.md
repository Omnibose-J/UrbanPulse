# criteria-m4.1 — Screens match the design; today's picks stay ahead

Written 2026-10-01 before implementation. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | Today's picks are ahead | `python -m engine collect` → exit 0 or warn; `select count(*) from recommendations r cross join lateral jsonb_array_elements(r.windows) w where r.date = (now() at time zone 'Asia/Seoul')::date and r.state <> 'off' and (w->'hours'->>0)::int < extract(hour from now() at time zone 'Asia/Seoul')` → 0 | | |
| A2 | Home has a "now" at any minute | within the first 10 minutes of an hour: `/api/home` → `busy_top` has 5 rows (paste the time and the five levels) | | |
| A3 | Engine tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 | | |
| A4 | Web checks | `cd app/web; npm run lint; npm run build; npx playwright test` → exit 0 (paste the passed count) | | |
| A5 | Visual assertions | `npx playwright test e2e/visual.spec.ts` → exit 0; list the screenshot files written | | |
| A6 | Map renders | paste the console message that was the cause and the fix; pin bounding box size from the test | | |
| A7 | Admin guarded and reachable | M5 row A7 filled: no token 404, token 200 | | |
| A8 | No literal copy, no hex, no key | the three `git grep` commands of SOW-M4 rows A5, A6 and SOW-M3 row A10 → no match | | |

## Report
(AGENTS.md format, appended when done)
