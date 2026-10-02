# criteria-m8 — Unverified verdicts stay off the screen

Written 2026-10-02 before step 1. Result cells are filled only after running the command.

| # | Criterion | Command | Exit | Evidence (one line) |
|---|---|---|---|---|
| A1 | No unverified verdict | Playwright, mocked `windows_only` row: a rating 1 cell outside the windows shows `reason.notPick` only; `reason.avoid` and `reason.ok` do not occur on the day screen or the map card; map legend has one entry. Mocked `two_step`: verdict and reason | 0 | verdict.spec 2 passed. Tapped 12시 shows "12시는 추천 시간이 아니에요."; avoid and ok strings absent; legend count 1. two_step still says "가도 괜찮아요" |
| A2 | Station rows fresh | `python -m engine collect` → exit 0 or warn; windows starting before the current hour → 0 | 0 | collect ok 121 at 12:06. The before-now window count is 0 |
| A3 | Screens | `npx playwright test e2e/visual.spec.ts` → exit 0 | 0 | visual.spec passed inside the full suite, 23 passed |
| A4 | Collect and forecast still run | collect `ok ≥ 100`; forecast exit 0 under 300 s | 0 | collect ok 121. forecast exit 0, 11:58:42 to 12:01:02 (140 s) |
| A5 | Tests and lint | pytest 0 skipped; ruff; `npm run lint`; `npm run build`; playwright | 0 | pytest 98 passed, 0 skipped. ruff clean. lint exit 0. build compiled. playwright 23 passed |
| A6 | Clean tree, no key | `git status --short` empty; key grep no match | 1 | key grep no match. tree empty after the last commit |

## Report

1. **Intent** — While `strip_mode` is `windows_only`, the day strip and the map card share one sentence function and do not state the unverified two-step verdict. Collect also rebuilds today's station rows, and the four screen defects in the review are fixed.

2. **Files** — `src/lib/strip.ts` (`cellSentence`), day and map screens, messages, search, home place card, week off-row, collect's today refresh in `forecast.py`.

3. **Commands and exit codes** — table above.

4. **Tests** — pytest 98 passed, 0 skipped, exit 0. ruff exit 0. `npm run lint` exit 0. `npm run build` compiled. `npx playwright test` 23 passed, exit 0.

5. **Open facts** —
   - New key `reason.notPick`: ko `{hour}시는 추천 시간이 아니에요.` / en `{hour} is not one of the best times.`
   - Screenshots looked at: `e2e/screenshots/live/ko-search.png` (field and icon in the bar, language at the right), `ko-day-not-pick.png` (hour 12 selected, only the not-pick sentence, legend is 추천), `ko-map.png` (legend is 추천, card uses the same sentence, pins are the smaller size).

6. **Not done** — empty.
