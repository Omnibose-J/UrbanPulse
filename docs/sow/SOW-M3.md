# SOW-M3 — Recommendations, feature flags, similar places (local)

Work unit W8 of the build contract (`docs/specs/UrbanPulse_구현설계서.md` §4.4, §4.5, §4.8). The engine turns `forecast_hourly` into `recommendations` rows for A1 and A2 places, driven by a flag file. Tier B and `ratio_v1b` are SOW-MB. No web work, no cloud.

## Depends on

SOW-M2 done: `forecast` writes `forecast_hourly`, `level_thresholds`, `lively_profile`; places carry live-derived `tier` and `serve_state`.

## Files you may touch

Create: `app/supabase/migrations/20261002000000_recommendation_log.sql` (also holds `lively_norm` and the `a_actual` column), `app/engine/config/feature_flags.yaml`, `app/engine/{flags,reco,similar,geo}.py`, `app/engine/tests/**`, `docs/tracking/criteria-m3.md`.
Edit: `app/engine/jobs/{forecast,collect}.py`, `app/engine/lively.py` (expose `p90` per place and purpose; no behaviour change), `app/supabase/tests/schema_test.sql` (add the new table), `docs/LLM_PROJECT_MAP.md`.
Read-only: `analysis/` (reference: `windows()` in `analysis/scripts/exp_e3_e4_reco.py`), specs, `docs/sow/`, `AGENTS.md`, `app/web/`.

## Definitions

- **Group** of a place: `a1` (tier A1, not `foreign_heavy`), `a1_foreign` (tier A1, `foreign_heavy`), `a2`.
- **Purposes**: A1 → `sight`, `food`, `shop`; A2 → `none`. **Tolerances**: `calm`, `moderate`, `busy_ok`.
- **Activity** `a` of an hour: A1 `sight` → `a_all`, `food` → `a_food`, `shop` → `a_shop` from `forecast_hourly`; A2 → 1.
- **Lively minimum** `lively_min`: `sight` 0.5, `food` 0.5, `shop` 0.6 (in the flag file, not in code).
- **Allowed level**: `calm` 1, `moderate` 2, `busy_ok` 3. An hour is **too busy** when its level is above the allowed level.
- **Strip hours**: 9…23 (15 cells). **Open hours**: A1 9…23; A2 9…20, and for a place with `open_hours` only hours `H` where `[H:00, H+1:00)` lies inside that weekday's range (`"09:30-18:00"` → 10…17; `null` → none).
- **Score** of an hour with level `L`: `calm` `a − 0.6·L`; `moderate` `a − 0.5·|L − 1|`; `busy_ok` `a − 0.2·max(L − 2, 0)`.
- **Day type**: as in SOW-M2.

## Steps

### 1 Migration — `recommendation_log`
Append-only copy of what was issued three days ahead, for the M5 evaluator (the live table is overwritten every 30 minutes).

```sql
create table recommendation_log (
  place_id     text not null references places (id),
  issued_date  date not null,
  date         date not null,
  tolerance    text not null check (tolerance in ('calm', 'moderate', 'busy_ok')),
  purpose      text not null check (purpose in ('sight', 'food', 'shop', 'none')),
  state        text not null check (state in ('on', 'reference')),
  windows      jsonb not null,
  hours        jsonb not null,
  p90          real,
  lively_min   real,
  primary key (place_id, issued_date, date, tolerance, purpose)
);
create index recommendation_log_date_idx on recommendation_log (date);
alter table recommendation_log enable row level security;

create table lively_norm (
  place_id     text primary key references places (id),
  p90_all      real,
  p90_food     real,
  p90_shop     real,
  computed_at  timestamptz not null default now()
);
alter table lively_norm enable row level security;

alter table forecast_hourly add column a_actual boolean not null default false;
```
`lively_norm` holds the normalisers that `lively.py` already computes, so `collect` can turn a fresh payment count into an activity value without recomputing them. `a_actual` marks a `forecast_hourly` row whose `a_*` are measured, not expected.
`p90` and `lively_min` are the purpose's normaliser and threshold at issue time (null for A2). Follow the RLS pattern of `20261001000100_rls.sql`. `cd app; supabase migration up` (never `db reset`: it would drop the collected data). Add the table to the pgTAP test.

### 2 Flag file — `app/engine/config/feature_flags.yaml`, loader `app/engine/flags.py`

```yaml
version: 1
judged_at: "2026-09-29"
lively_min: {sight: 0.5, food: 0.5, shop: 0.6}
combos:
  - {group: a1, purpose: sight, tolerance: calm, state: off, strip: windows_only}
  - {group: a1, purpose: sight, tolerance: moderate, state: on, strip: windows_only}
  # … one line per row below
```

| group | purpose | calm | moderate | busy_ok |
|---|---|---|---|---|
| a1 | sight | off | on | on |
| a1 | food | off | on | on |
| a1 | shop | off | reference | on |
| a1_foreign | sight | off | reference | reference |
| a1_foreign | food | off | reference | reference |
| a1_foreign | shop | off | off | reference |
| a2 | none | on | on | on |

`a1 / sight / calm` is `off`, not the build contract's `reference`: backtest E15 (`analysis/scripts/exp_e15_window_rule.py`, 2026-10-01) judged the window rule of step 3 and this one combination fell below the lively bar (84.4 %). Every other state was confirmed. Every `strip` is `windows_only`. `flags.lookup(group, purpose, tolerance)` → `(state, strip)`; a combination not in the file → `('off', 'windows_only')`. The loader rejects unknown groups, purposes, tolerances, states and duplicate lines (exit 1 naming the line). No table of states anywhere in Python code.

### 3 One row — `app/engine/reco.py`
`build_row(place, date, tolerance, purpose, hourly, flags, day_type)` where `hourly` is the 15 `forecast_hourly` rows of that date (hours 9…23).

**State**, first match wins:
1. place `serve_state = 'preparing'` → `off`, `off_reason = 'preparing'`.
2. any of the 15 hours missing or `ready = false`; or A1 and the purpose's activity is null on any of them → `off`, `'preparing'`.
3. A1 and `day_type = 'myeongjeol'` → `off`, `'myeongjeol'`.
4. flag state `off` → `off`; `off_reason = 'failed'` when the file lists the combination, `'unverified'` when it does not.
5. otherwise the flag state (`on` / `reference`).

Off rows carry `windows, no_window, hours, strip_mode, alt_dates, alt_places` all null (table checks).

**Cells** (on / reference rows), one per hour 9…23:
- `reason`, first match: `outside_hours` (hour not in the place's open hours) → `closed` (A1 and `a < lively_min`) → `too_busy` (level above allowed) → `fit`.
- `rating` = 1 when `reason = 'fit'`, else 0.
- `crowd` = the hour's level. `act` = A1: `"lively"` when `a >= lively_min` else `"quiet"`; A2: null.
- `in_window` set after windows are chosen.
- Cell shape: `{"h": 14, "rating": 1, "in_window": false, "reason": "fit", "crowd": 1, "act": "lively"}`.

**Windows**: port `windows()` from `exp_e3_e4_reco.py` (1-hour and 2-consecutive-hour candidates, 2-hour score = mean, sort by score descending, greedy non-overlapping, at most 3). Allowed hours = the cells with `rating = 1`. Ties keep the candidate order of the research function (earlier hour first, 1-hour before 2-hour).
  - This narrows the research rule (which allowed every lively hour and let the score penalise crowding) to the design spec's rule (§7.1: windows come from "가도 괜찮아요" hours). E15 re-judged every combination under this rule; the flag table in step 2 is its result.
- `windows` = `[{"hours": [12, 13], "score": 0.71, "crowd": 1, "act": "food", "act_level": "lively"}, …]` in pick order. `crowd` = highest level in the window. `act` = the purpose for A1 (`sight`/`food`/`shop`), null for A2; `act_level` = `"lively"` for A1 (every window hour is lively by construction), null for A2. `score` rounded to 3 decimals.
- `no_window` = `windows` is empty (then `windows = []`).
- `strip_mode` = the flag's `strip`.

### 4 All rows, alternatives, log — called from `forecast`
After `forecast_hourly` is written (SOW-M2 step B-6.5), in the same job run:
1. For every A1/A2 place not `off`, every date today…today+7, every tolerance, every purpose of its tier: `build_row`. Upsert all rows (`generated_at` = job start).
2. **`alt_dates`** (on / reference rows): among the same place, tolerance, purpose and the other 7 dates, rows that are on / reference with a window. When this row has a window, keep only dates whose best window score is higher than this row's best. Order by best score descending, at most 2: `[{"date": "2026-10-04", "hours": [13, 14], "score": 0.8}]`. Always an array (possibly empty).
3. **`alt_places`** (A1 on / reference rows; A2 → `[]`): from `similar_places` of this place in rank order, places within 5 km (haversine on `lat`/`lon`, `app/engine/geo.py`) whose row for the same date, tolerance, purpose is on / reference with a window, and, when this row has a window, whose best window `crowd` is at least 1 lower than this row's best window `crowd`. At most 3: `[{"place_id": "POI045", "hours": [18, 19], "crowd": 1}]`.
4. **Log**: for `date = today + 3`, insert every on / reference row into `recommendation_log` with `issued_date = today`, `p90`, `lively_min`. `on conflict do nothing`; never update or delete.
5. Delete `recommendations` rows with `date` before today.
6. `job_runs.detail.reco` = `{"rows", "on", "reference", "off_by_reason": {...}, "no_window", "logged"}`.

### 5 Today's rows after each collect
`forecast` step 2 also replaces `lively_norm`. The overlay (SOW-M2 step B-6.5) gains one rule: for an A1 place and an hour of today that has `commerce_obs` rows, set `a_all`, `a_food`, `a_shop` = hourly commerce value ÷ the place's `p90_*` (null where the `p90` is null or zero) and `a_actual = true`. Rows written by `forecast` start with `a_actual = false`. Backtest E16 is the reason: choosing "open now" from the expected profile was right 84.2 % of the time, under the 85 % bar, so the home list must use the measured value.

`collect`, after the overlay, rebuilds today's rows (steps 4.1–4.3 restricted to today and to the places it just stored; alternatives read the other dates' stored rows). No log write.

### 6 Similar places — `app/engine/similar.py`, run by `forecast` before step 4
A1 places with `serve_state = 'on'`. Feature vector = concatenation of blocks, each L2-normalised on its own:
- commerce mix: share of each of the eight categories in the sum of `cat_counts` over the last 28 days;
- place category: one-hot of `places.category`;
- visitors: mean `age_rates` values and `male_rate` over the last 28 days. Use this block only when every one of these places has non-null `age_rates` on at least 28 distinct dates; otherwise leave it out for all of them (report which happened).
Cosine similarity; for each place the top 10 others with `rank` 1…10. Replace the table in one transaction.

### 7 Tests
- `test_flags.py`: every table cell above; unlisted → off + `unverified` reason downstream; duplicate line and unknown value rejected.
- `test_reco_cells.py`: reason priority (an hour that is both closed and too busy → `closed`; an A2 hour 21 → `outside_hours`); `rating = 0 ⇔ reason ≠ fit` (invariant 10); A2 `act` null (invariant 6); 15 cells in order (invariant 8); palace closed weekday → 15 × `outside_hours`, `no_window`.
- `test_reco_windows.py`: equals a hand-worked case of the research `windows()`; windows contain only lively hours (invariant 2) and only `rating = 1` hours; `in_window` cells equal the union of `windows[*].hours` (invariant 9); at most 3, non-overlapping; `busy_ok` never produces `too_busy`.
- `test_reco_state.py`: the five state rules in order; off rows have every computed column null; `strip_mode` mirrors the file (invariant 11); A1 myeongjeol → off for all nine combinations (invariant 7).
- `test_reco_alts.py`: `alt_dates` only better dates, at most 2; with `no_window`, any date with a window; `alt_places` respects 5 km, crowd-lower rule, at most 3; A2 `alt_places = []`.
- `test_reco_log.py`: second `forecast` the same day leaves `recommendation_log` unchanged; only `date = issued_date + 3`.
- `test_overlay_activity.py`: an hour with commerce rows gets measured `a_*` and `a_actual`; an hour without keeps the profile values; zero `p90` → null; A2 rows never get `a_actual`.
- `test_similar.py`: identical vectors → score 1, rank order, no self row, visitors block dropped when one place lacks 28 days.
- Property test (random `hourly` inputs, 200 cases): invariants 8, 9, 10 hold for every on / reference row.

## Acceptance (`docs/tracking/criteria-m3.md`, rows created before step 1)

| # | Criterion | Command |
|---|---|---|
| A1 | Migration applied, schema tests pass | `cd app; supabase migration up` → exit 0; `supabase test db` → exit 0; `select count(*) from live_obs` unchanged from before the migration (paste both) |
| A2 | Rows for every served place | `python -m engine forecast` → exit 0; `select count(*) from recommendations` = 8 × 3 × (3 × A1 places not off + A2 places not off) (paste the two place counts and the product) |
| A3 | States follow the file | `select p.tier, p.foreign_heavy, r.purpose, r.tolerance, r.state, r.off_reason, count(*) from recommendations r join places p on p.id = r.place_id where p.serve_state = 'on' and r.date = current_date group by 1,2,3,4,5,6 order by 1,2,3,4` pasted; for a non-myeongjeol today every (group, purpose, tolerance) shows the table's state, or `off / preparing` |
| A4 | Stored invariants | each returns 0: rows with `state <> 'off'` and `jsonb_array_length(hours) <> 15`; cells with `in_window` and `rating = 0`; cells with `(rating = 0) = (reason = 'fit')`; A2 cells with non-null `act`; rows where the set of `in_window` hours differs from the union of `windows[*].hours` (write the five queries into the criteria file) |
| A5 | Log is append-only | `forecast` twice → `select count(*), min(date - issued_date), max(date - issued_date) from recommendation_log` identical after the second run, both differences 3 |
| A6 | Collect refreshes today | `python -m engine collect` → exit 0 or warn; `select max(generated_at) from recommendations where date = current_date` is later than the forecast run; rows of later dates keep the forecast's `generated_at` |
| A6b | Measured activity on live hours | after that collect: `select count(*) from forecast_hourly where a_actual` > 0, all of them on today's date and A1 places; `select count(*) from lively_norm` = A1 places with a profile |
| A7 | Similar places | `select count(*), count(distinct place_id), max(rank) from similar_places` pasted; no place has more than 10 rows |
| A8 | Ten places by eye | for 10 `on` places (5 A1, 2 `a1_foreign`, 3 A2 including POI008), paste today+2's `windows` and the 15 `rating` digits for `moderate` and the default purpose. Do not judge them; the designer reads them |
| A9 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0; `ruff check app/engine` → exit 0 |
| A10 | No key | `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match |

## Open facts to report

- Counts: on / reference / off by reason; share of on / reference rows with `no_window`, by group, purpose and tolerance.
- How many rows are `off / preparing` because an hour was not ready or an activity value was null, and for which day types.
- Whether the visitors block was used in `similar_places`.
- Hour distribution of first-pick windows over all on rows (the research saw 12–14h 36 % and 18–20h 42 %).
- Duration of `forecast` with recommendations, and of the collect-time refresh.
