# criteria-ux — UX pass after the cloud move (three tiers, in order)

Written 2026-10-06 before the first edit, from the UX review of the deployed screens. Each row is flipped to `[x]`
with the literal command and exit code when it passes. Contract changes below are authorised by the user
("싹 다 순차적으로 진행해", 2026-10-06); the design spec moves to v3.0 with them.

Goal (user's view): the strips show how busy each hour is forecast to be, not only which hours are picked; the
home leads with places worth going to; every "nothing here" state says why; sharing, comparing and a weekend
reminder exist.

## Tier 1 — legibility (UI only, existing API data)

- [ ] T1.1 In `windows_only` mode every non-window cell of the day strip, the week rows and the home mini strips is
      shaded by its forecast crowd level (0–3, four neutral shades); window cells stay `--go`; `outside_hours` cells
      are drawn hollow. `two_step` mode is unchanged. Map pins unchanged.
      → verify: `npm test` (strip.test: `cellShade`), Playwright screens D11 (`data-crowd` differs across cells)
- [ ] T1.2 The week list has one hour axis (9 12 15 18 21) above the rows, aligned to the strip column; today's
      past hours are dimmed and the current hour carries a ring, on the day strip and today's week row.
      → verify: Playwright visual "week cards" (axis present, `[data-week-axis] span` = 5), screens D17 (ring on
      current hour, past cells `data-past`)
- [ ] T1.3 Tapping a non-window hour in `windows_only` says the forecast crowd (or "outside opening hours") and the
      next pick of the day: "14시는 추천 시간이 아니에요. 조금 붐벼요. 18시부터 추천 시간이에요". Never the two-step
      verdict. Same sentence on the map card.
      → verify: `npm test` (strip.test notPick whys/next), Playwright verdict.spec updated text
- [ ] T1.4 The week-list legend names the busiest dot ("● 가장 붐빌 때") and the crowd shades ("예상 혼잡 한산→붐빔").
      → verify: Playwright screens D15 (legend items), D9 no stray Hangul in en
- [ ] T1.5 A holiday row keeps its date: "금 / 10/9 / 한글날"; the best row keeps its date too ("목 / 10/8 / 추천").
      → verify: Playwright screens D18 (mocked holiday row shows both), visual "week cards" row heights still even
- [ ] T1.6 Wording: home section "지금 열려 있고 여유로운 곳" / "Open and uncrowded right now"; en `tol.moderate`
      "Moderate"; a quiet card whose pick includes the current hour says "지금 가기 좋아요" / "Good right now".
      → verify: `node scripts/check-messages.mjs` exit 0; Playwright screens D12/D14 updated; D9

## Tier 2 — recommendation quality

- [ ] T2.1 Home order: favorites (when any) → open-and-uncrowded → tomorrow morning (night) → busiest. Spec §6.1.
      → verify: Playwright screens D19 (section order by `data-*` y positions)
- [ ] T2.2 Place kind: `/api/home`, `/api/places` rows carry `category`; cards and search rows show a kind chip
      (관광특구 / 발달상권 / 고궁·문화유산 / 공원 / 인구 밀집 지역); quiet and tomorrow picks rank 인구밀집지역 after
      the other kinds (same rule otherwise). Spec §5.7, §5.7-2, §5.8.
      → verify: `npm test` (home-rules, morning tests), api.spec key sets, Playwright D12 chips visible
- [ ] T2.3 (dropped) A three-tier strip "추천/괜찮음/붐빔" is the E5-rejected rating; the crowd shading of T1.1 is
      the honest replacement. Recorded in the spec §7.3 and the decision memory.
- [ ] T2.4 A week row that is off for `preparing` says why: "기록이 모자라 아직 예상할 수 없어요" / en. No date promise
      (the engine cannot know one).
      → verify: Playwright visual "off day says its state once" updated

## Tier 3 — service features

- [ ] T3.1 Nearby now: a home section with a "내 위치로 찾기" button; with permission it lists up to 5 A1/A2 places
      within today's `/api/map` payload that have a pick still ahead, by distance, with "1.2 km"; denied → "위치
      권한이 없어 찾을 수 없어요"; no geolocation API → section absent.
      → verify: Playwright screens D20 (context.setGeolocation + mocked map), D21 denied text
- [ ] T3.2 Share: the day screen's bar has a share button; `navigator.share` when present, else clipboard copy with
      "링크를 복사했어요".
      → verify: Playwright screens D22 (stubbed share receives url + text)
- [ ] T3.3 Compare: `/[locale]/compare?a=&b=` shows two places' best time and 8 week rows side by side; entry from
      the week screen ("다른 장소와 비교" → search in compare mode).
      → verify: Playwright screens D23 (mocked two weeks), D5 flow
- [ ] T3.4 Weekend reminder: browser push. `push_subscriptions` table (RLS, no anon grants), `POST/DELETE
      /api/push/subscribe`, `public/sw.js`, Vercel cron Friday 18:00 KST → `/api/push/weekend` (CRON_SECRET) sends
      each subscriber the best Sat/Sun pick of their saved places. VAPID keys in Vercel env (names only in logs).
      → verify: `npm test` (push message builder), `supabase db push` exit 0 + `dbtool check-schema`, cron route 401
      without secret and 200 with it (`90_verify`), one real subscription round-trip in the browser

## Docs, tests, deploy

- [ ] D1 Design spec v3.0 (§0, §2.1, §5.4, §5.5, §5.7, §5.8, §5.12–5.15, §6.1, §7.3, §9.2, §9.3, §10),
      build contract (push table, cron, API list), RUNBOOK (env names, cron), project map, findings rows.
- [ ] D2 Gates: `npm run lint`, `npx tsc --noEmit`, `npm test`, full Playwright on the deployment, `90_verify`.
- [ ] D3 Korean commits per tier, pushed; Vercel deploys from `main`.

## Out of scope

- Map pin colours and clustering, CSP header, English place names (needs the data.go.kr key), dark mode,
  engine changes (no new `off_reason`), the E6 experiment itself, PC layout of the compare screen.

## Boundaries

- ✅ always: run `npm test`, `lint`, `tsc` before each commit; strings only in `messages/{ko,en}.json`; no
  secrets in commands or logs (names only).
- ⚠️ confirm first: none requested — the user asked for a straight-through run; the push table migration and
  Vercel env writes are reported, not asked.
- 🛑 never: weaken or delete a test to pass; state the two-step verdict in `windows_only`; print a key value;
  `supabase db reset`.
- Files: `app/web/src/{components,screens,lib,app}`, `app/web/messages`, `app/web/e2e`, `app/web/public/sw.js`,
  `app/web/vercel.json`, `app/supabase/migrations/*push*`, `docs/**`, `scripts/cloud/90_verify.ps1`.
