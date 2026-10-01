# SOW-M6 — Level thresholds that match Seoul's levels (local)

Backtest E17 (`analysis/scripts/exp_e17_levels_norm.py`, 2026-10-01) found the cause of "no pick" weekdays and of false "사람이 너무 많아요" hours: the threshold rule "lowest population ever labelled ≥ k" is dragged down by single outlier rows. Given the actual population it reproduces Seoul's level 48.6 % of the time on September data and returns a higher level 51.3 % of the time; 81 % of the hours it marked too busy were not. This SOW replaces the rule, turns off one combination that the new rule moves under its bar, and softens one sentence. Run it after SOW-MB.

## Decisions already made (user, 2026-10-01)

- Adopt the error-minimising boundary. The pre-registered decision rule said "keep the old rule if any served combination gets worse"; one did (`a1_foreign / shop / busy_ok`, lively 85.2 % → 84.8 %). The user chose to adopt the new rule and turn that combination off.
- Combinations that E17 judged **better** (A1 `calm`, `a1 / shop / moderate`) are **not** upgraded now. They wait for the weekly re-judgement on October data.
- The activity normaliser is unchanged (the per-day-class variant was worse).

## Files you may touch

Create: `app/engine/train/evaluate_levels.py`, `docs/tracking/criteria-m6.md`.
Edit: `app/engine/levels.py`, `app/engine/config/feature_flags.yaml` (one line), `app/engine/tests/test_levels.py` and other engine tests that pin threshold values, `app/web/messages/{ko,en}.json` (one key each), `docs/LLM_PROJECT_MAP.md`.
Read-only: everything else, including `analysis/`.

## Steps

### 1 Threshold rule — `levels.thresholds_for`
For each boundary `k` in 1, 2, 3, over the place's rows of the 90-day window (`value`, `level`):
- `hi` = values of rows with `level >= k`, `lo` = values of rows with `level < k`.
- `hi` empty → `Infinity`. `lo` empty → `min(hi)`.
- Otherwise the candidates are the distinct values of `hi ∪ lo`; for a candidate `c`, `errors(c)` = (count of `hi` below `c`) + (count of `lo` at or above `c`); `t_k` = the **lowest** candidate with the fewest errors.
- Then make them monotone: `t2 = max(t2, t1)`, `t3 = max(t3, t2)`.
`level_of`, `based_on_days`, and the threshold-ready rule (three of four levels present) do not change. Keep the old rule available as `thresholds_for(frame, rule="min")` for the evaluation in step 2; the default and the only rule `forecast` uses is `"split"`.

### 2 Measure it — `python -m engine.train.evaluate_levels`
For every place with `serve_state = 'on'`: thresholds from `live_obs` rows with `ts` in 2026-06-03 … 2026-08-31 (KST dates), applied to the rows of 2026-09-01 … 2026-09-29, hours 9–23, using each row's own `(pop_min + pop_max) / 2`. Print for `min` and `split`, as the mean over places: exact agreement with the row's `level`, share higher, share lower, share predicted 3, share actually 3. The designer measured `min` 48.6 / 51.3 / 0.2 / 21.5 / 3.2 and `split` 79.6 / 9.0 / 11.4 / 2.6 / 3.2. Tolerance ±1.0 %p on each of the ten figures. Outside → record FAIL with your table and continue.

### 3 Flag file
`{group: a1_foreign, purpose: shop, tolerance: busy_ok}` → `state: off`. `judged_at: "2026-10-01"`. No other line changes.

### 4 Copy
`reason.closed`: ko `이 시간에는 가게들이 한산해요.`, en `Shops are quiet at this hour.` (The cell means "below half of the place's weekend peak", which on weekdays at weekend-heavy places is open but quiet, not shut.)

### 5 Rebuild
`python -m engine forecast` (recomputes `level_thresholds`, `forecast_hourly`, `recommendations`). `recommendation_log` and `forecast_log` keep their existing rows; rows logged from now on use the new thresholds. Put `"levels_rule": "split"` in the forecast `job_runs.detail` so the evaluator's reader can tell the two periods apart.

### 6 Tests
- `test_levels.py`: a hand-built place where one outlier row (level 3 at a low value) moves the `min` threshold but not the `split` one; ties pick the lowest candidate; `hi` empty → infinity; `lo` empty → `min(hi)`; monotone after the fix-up (invariant 3, random inputs); `rule="min"` still returns the old values.
- `test_flags.py`: the changed line.
- Any test that hard-codes thresholds from the old rule is updated to the new rule's value worked out by hand in the test; no assertion is removed.

## Acceptance (`docs/tracking/criteria-m6.md`, rows created before step 1)

| # | Criterion | Command |
|---|---|---|
| A1 | New rule reproduces the measured agreement | `python -m engine.train.evaluate_levels` → table pasted; each of the ten figures within ±1.0 %p |
| A2 | Rebuilt | `python -m engine forecast` → exit 0; `detail.levels_rule = "split"`; `select count(*) from level_thresholds where not (t1 <= t2 and t2 <= t3)` → 0 |
| A3 | Fewer false "too busy" hours | before and after the rebuild, paste `select c->>'reason', count(*) from recommendations r cross join lateral jsonb_array_elements(r.hours) c where r.state <> 'off' and r.tolerance = 'moderate' and r.date > (now() at time zone 'Asia/Seoul')::date group by 1`. Report both; do not steer |
| A4 | No-pick days | before and after: `select count(*) filter (where no_window), count(*) from recommendations r join places p on p.id = r.place_id where r.state <> 'off' and p.tier = 'A1' and r.purpose = 'sight' and r.tolerance = 'moderate' and r.date > (now() at time zone 'Asia/Seoul')::date`; and the same for `POI083`, `POI060` alone |
| A5 | Flag applied | `select distinct r.state, r.off_reason from recommendations r join places p on p.id = r.place_id where p.foreign_heavy and r.purpose = 'shop' and r.tolerance = 'busy_ok' and p.serve_state = 'on'` → `off / failed` only |
| A6 | Invariants still hold | the five queries of SOW-M3 row A4 → 0 each |
| A7 | Tests, lint, web | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0; `cd app/web; npm run build; npx playwright test` → exit 0 |
| A8 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match |

## Open facts to report

- The evaluate_levels table.
- Before / after counts of A3 and A4, and the first-pick hour distribution after the rebuild.
- How many places changed `threshold-ready` (expected none).
