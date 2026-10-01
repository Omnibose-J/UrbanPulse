# SOW-M6 — Level thresholds that match Seoul's levels (local)

Backtest E17 (`analysis/scripts/exp_e17_levels_norm.py`, 2026-10-01) found the cause of "no pick" weekdays and of false "사람이 너무 많아요" hours: the threshold rule "lowest population ever labelled ≥ k" is dragged down by single outlier rows. Given the actual population it reproduces Seoul's level 48.6 % of the time on September data and returns a higher level 51.3 % of the time; 81 % of the hours it marked too busy were not. This SOW replaces the rule, turns off one combination that the new rule moves under its bar, and softens one sentence. Run it after SOW-MB.

## Decisions already made (user, 2026-10-01)

- Adopt the error-minimising boundary. The pre-registered decision rule said "keep the old rule if any served combination gets worse"; one did (`a1_foreign / shop / busy_ok`, lively 85.2 % → 84.8 %). The user chose to adopt the new rule and turn that combination off.
- Combinations that E17 judged **better** (A1 `calm`, `a1 / shop / moderate`) are **not** upgraded now. They wait for the weekly re-judgement on October data.
- The activity normaliser is unchanged (the per-day-class variant was worse).

## Files you may touch

Create: `app/engine/train/evaluate_levels.py`, `docs/tracking/criteria-m6.md`.
Edit: `app/engine/levels.py`, `app/engine/config/feature_flags.yaml` (one line), `app/engine/tests/test_levels.py` and other engine tests that pin threshold values, `app/web/messages/{ko,en}.json` (one key each), `docs/LLM_PROJECT_MAP.md`; for Part B: `app/web/src/**`, `app/web/e2e/**`.
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

---

# Part B — Remove fallbacks that hide a failure (web)

The designer read every `??`, `||` default and `catch` in `app/web/src` (2026-10-01). AGENTS.md rule 3: fail loud, no fallback a SOW did not ask for. Fix these; add rows B1–B9 to `docs/tracking/criteria-m6.md`.

| # | Where | What it hides | Fix | Check |
|---|---|---|---|---|
| B1 | `screens/map.tsx` fetch | No `response.ok` check; a 400/500 body has no `places`, `?? []` and `.catch(() => setPlaces([]))` turn it into an empty map with no message | Use the same loader as the other screens (`use-load`); on failure show the error box with retry, never an empty map | Playwright: `/api/map` mocked to 500 → error box visible, zero pins |
| B2 | `screens/map.tsx` `styleFailed` branch and the `lon ?? 0` / `lat ?? 0` bounds | A silent plain-background mode when the map style fails (SOW-M4.1 allowed it; the designer withdraws that) | Remove the branch and the percent-positioned pins. Style or worker failure → the error box. Remove the dead `?? 0` after the null filter | Playwright: style URL blocked → error box |
| B3 | `screens/day.tsx` `none = no_window \|\| state === 'off'` | A combination that is switched off (`failed`, `unverified`) reads as "이날은 추천할 시간이 없어요" with alternatives. Off means "준비 중", not "no time" | `off_reason` `failed` or `unverified` → the preparing box with a line naming the condition (new key `state.comboOff`: "이 조건은 아직 준비하고 있어요. 조건을 바꿔 보세요." / "This setting is not ready yet. Try another one.") and the condition field; no alternatives | Playwright: recommend mocked `state: off, off_reason: failed` → that text, no AltButton |
| B4 | `lib/queries.ts` `ts: live?.ts ?? row.target_ts` | With no `live_obs` row the "기준" time is invented from the forecast hour | No live row → `now = null` (the screen then shows no now line) | unit test on the shaping function |
| B5 | `screens/day.tsx` `alt.name ?? alt.place_id` | A raw id such as `POI045` shown to the visitor | The API drops an alt place whose name cannot be joined; the screen has no id fallback | unit test: unjoined alt is absent |
| B6 | every route handler `catch { return jsonFail(500, …) }` | Any bug in a query or shaping function becomes "unavailable" with no trace | `console.error("[api] <route>", error.message)` before the 500 (message only; never the URL, key or row data) | test: a thrown error is logged once and the response is 500 `{"error":"unavailable"}` |
| B7 | `lib/storage.ts` `parsed.purpose ?? DEFAULTS.purpose` | A stored value outside the allowed set passes through, every API call returns 400, and the screen shows the error box until storage is cleared | Validate both values against the allowed sets; an invalid stored value is replaced by the default and rewritten | unit test |
| B8 | defaults on values that cannot be missing: `foreign_heavy ?? false` (NOT NULL), `kst.ts` `?? ""` and `?? "0"` (Intl always returns the part; `"0"` would silently mean midnight), `event.error.message ?? ""`, `api/health` `count ?? 0` (reports `db: ok, places: 0` when the count failed) | Each one turns an impossible or failed state into a plausible value | Remove them; where the type allows undefined, throw with a message naming the field. `health`: null count → 500 | `tsc` green; health test |
| B9 | `MiniStrip` / `DayStrip` `(hours ?? [])` | An off row draws an empty strip area | Callers pass `hours` only for on / reference rows; for off rows the list row shows its state text ("준비 중", "명절") with no strip, and the components take a non-null array | Playwright state screenshots unchanged in count; week list with an off day shows the text |

Keep as they are (requested behaviour, not hidden failures): `localStorage` read/write `catch` (spec §2.4, §2.5), `combos … ?? "off"` and `strip_mode ?? "windows_only"` (invariants 7 and 11: unlisted means off), `searchParams … ?? ""` defaults, `holiday.name_en || holiday.name` (wrap the Korean fallback in `lang="ko"`), default date and hour on the map.

Acceptance for Part B: each check above, plus `npm run lint; npm run build; npx playwright test` → exit 0.
