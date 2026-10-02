# SOW-M8 — Review round after M7: unverified verdicts, stale station rows, small screen defects (local)

Review of SOW-M7 on 2026-10-02 11:35 KST. Every M7 figure reproduced (pytest 97 passed / 0 skipped, collect `ok` 121 since 10:00, forecast 91 s, 247 station places = 247 profiles, clean tree). The designer then opened the live screens at 390 × 844. These remain.

## What the review saw

1. **A hour that fits is told "avoid".** On ⑤ with `strip_mode = 'windows_only'`, tapping a grey cell says "12시는 피하는 게 좋아요. 가도 괜찮아요" (a station place): the verdict is "avoid" for every cell outside a window, even `rating = 1`, and the reason sentence contradicts it. The two-step rating is not verified until E6 (design spec §7.3), so in `windows_only` the screen must not state it at all. The map card has the same fault ("11시는 피하는 게 좋아요."), and the map legend shows all three kinds.
2. **Station rows for today go stale.** At 11:35, 445 windows on today's tier B rows start before the current hour (`generated_at` 10:55, the forecast run). `collect` refreshes today's rows for A1/A2 only.
3. **② Search**: the field has no inner padding and no icon; the language switch sits next to the back button instead of the right edge; rows show no status on the right for A1/A2 (§5.8).
4. **① Home place card**: the status ("● 적당해요") collides with a long place name.
5. **③ Week list**: an off day prints its state twice ("준비 중" in the strip area and again on the right).
6. **⑦ Map**: at the initial zoom the 28 px pins pile on top of each other across central Seoul.

## Files you may touch

`app/web/**` (not its `AGENTS.md`, `CLAUDE.md`, `README.md`), `app/engine/jobs/collect.py`, `app/engine/jobs/forecast.py`, `app/engine/tests/**`, `docs/tracking/criteria-m8.md`.

## Steps

### 1 `windows_only` states only what is verified (web)
With `strip_mode = 'windows_only'`:
- Tapping a window cell: "{h}시는 추천 시간이에요." followed by the reason sentence of that window (unchanged).
- Tapping any other cell: one sentence, no reason. New key `reason.notPick`: ko `{hour}시는 추천 시간이 아니에요.`, en `{hour} is not one of the best times.` (en uses the 12-hour form, e.g. `12 PM`).
- Map card: the same two sentences. Map legend: "추천" only.
With `strip_mode = 'two_step'` nothing changes (verdict + reason as built). One function decides the sentence for the strip and the map card; do not duplicate the rule.

### 2 Today's station rows follow the clock (engine)
The collect-time refresh of today's rows also rebuilds today's rows of tier B places (profile-based, no new data needed), so their windows come only from hours still ahead. Test: at `now_hour = 15` a station row has no window starting before 15.

### 3 Screen defects 3–6
- ② `SearchField` in the bar: 44 high, `--bg-soft`, 12 px inner padding, search icon; language switch at the right edge; A1/A2 rows show the now status ("● 한산해요") from `/api/places` (add `level` of the latest measured hour to that route for `on` places; null when there is none, and then the row shows nothing).
- ① `PlaceCard`: the name truncates with an ellipsis; the status never wraps and never overlaps.
- ③ An off day shows its state text once, in the strip area; the right column is empty.
- ⑦ Pins are 18 px below zoom 12 and 28 px from zoom 12 up (selected pin 38 at any zoom).

## Acceptance (`docs/tracking/criteria-m8.md`, rows created before step 1)

| # | Criterion | Command |
|---|---|---|
| A1 | No unverified verdict | Playwright, mocked `windows_only` row with a `rating = 1` cell outside the windows: tapping it shows `reason.notPick` and nothing else; the strings of `reason.avoid` and `reason.ok` do not occur on ⑤ or the map card; map legend has one entry. Mocked `two_step` row: verdict and reason as before |
| A2 | Station rows fresh | `python -m engine collect` → exit 0 or warn; `select count(*) from recommendations r cross join lateral jsonb_array_elements(r.windows) w where r.date = (now() at time zone 'Asia/Seoul')::date and r.state <> 'off' and (w->'hours'->>0)::int < extract(hour from now() at time zone 'Asia/Seoul')` → 0 (all tiers) |
| A3 | Screens | `npx playwright test e2e/visual.spec.ts` → exit 0 with DOM checks added for: search field text x ≥ 28 and an icon; language switch right edge within 16 px of the viewport edge on ②; place-card status and name boxes do not intersect; an off row contains its state text exactly once; pin size 18 at the initial zoom |
| A4 | Collect and forecast still run | `python -m engine collect` → `ok ≥ 100`; `python -m engine forecast` → exit 0 under 300 s |
| A5 | Tests and lint | `python -m pytest app/engine/tests -q` → exit 0, 0 skipped; `ruff check app/engine` → exit 0; `cd app/web; npm run lint; npm run build; npx playwright test` → exit 0 |
| A6 | Clean tree, no key | `git status --short` → empty; `git grep -I -n -e "eyJhbGci" -e "sb_secret_" -- . ':!docs'` → no match |

## Open facts to report

- New message keys with both texts.
- The saved screenshots of ②, ⑤ (a tapped non-window cell), and ⑦.
